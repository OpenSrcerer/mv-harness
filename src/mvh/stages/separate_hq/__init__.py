# ruff: noqa: E501  (long catalogue tables / docstrings)
"""separate_hq stage (PLAN §3.1/§5, SPIKE, docs/spike/sep.md; owner M3a).

Runs the audio-separator models in the sep worker (``ctx.worker``; variant rocm, then cpu; ``mvh.sep.hq_worker``):
BS-RoFormer-SW 6-stem on the mix, Mel-RoFormer vocals on the mix, the karaoke model on the Mel vocals
(lead / backing), MDX23C DrumSep on the SW drums. The parent then builds the stem set on the song's timebase
(resampled back when the song is not 44.1 kHz, same channels and length as the mix):

  vocals = Mel-RoFormer vocals          lead_vocals = karaoke "vocals"     backing_vocals = vocals - lead_vocals
  drums, bass, guitar, piano, other = BS-RoFormer-SW                        instrumental = mix - vocals
  drums/{kick,snare,toms,hihat,ride,crash} = DrumSep ("hh" -> hihat)

so ``instrumental + vocals == mix`` and ``lead + backing == vocals`` exactly (in float; the 24-bit FLACs add only
quantisation noise). ``backing_vocals`` is always written (D17). SW's own vocals stem is kept cache-only
(``sep/vocals_sw.flac``): stem_activity uses it as an independent vote on vocal presence.

Invariants (SPIKE re-baseline) in ``meta/separation.json``: six-stem SW sum residual <= -20 dB; per-stem LS gain
within 0.1 dB for stems within 6 dB of the mix and 0.5 dB within 20 dB. A failed gate is a QA flag and a warning,
not a failure (it is a model property: MEGAFAUNA measures -23.6 dB).

When both worker variants fail and ``variant_order`` contains ``htdemucs``, demucs-onnx htdemucs_6s runs in-process
(status ``degraded``, ``lead_vocals := vocals``, silent backing, no drum sub-stems).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from mvh.contract.ids import DRUM_SUBSTEMS, STEM_NAMES
from mvh.runner.spec import Output, StageError, StageResult, StageSpec, catalog_outputs

SEP_MODELS = ("sep.bs-roformer-sw-6stem", "sep.mel-roformer-vocals-kimberley",
              "sep.mel-roformer-karaoke-aufr33-viperx", "sep.mdx23c-drumsep")
FALLBACK_MODEL = "demucs_onnx_htdemucs_6s"

STAGE = StageSpec(
    "separate_hq",
    ('ingest',),
    "sep",
    "1.0.0",
    override_keys=(),
    outputs=catalog_outputs("separate_hq") + (
        Output("sep/vocals_sw.flac", "audio", None, required=False, public=False,
               description="BS-RoFormer-SW's own vocals stem (cache only): an independent vote on vocal presence"),
    ),
    params={'normalization_threshold': 100.0, 'amplification_threshold': 0.0, 'variant_order': ['rocm', 'cpu', 'htdemucs'],
            'overlap': 4, 'segment_size': 256, 'sum_gate_db': -20.0, 'lead_suspect_db': 3.0, 'narrow_side_db': -20.0},
    models=SEP_MODELS + (FALLBACK_MODEL,),
    gpu=True,
    module="M3a",
    description='audio-separator worker: 6 stems, vocals, lead/backing, DrumSep, instrumental (rocm -> cpu -> htdemucs degraded).',
)

ROLE = {
    "sep.bs-roformer-sw-6stem": "bass, drums, other, guitar, piano (+ vocals_sw)",
    "sep.mel-roformer-vocals-kimberley": "vocals",
    "sep.mel-roformer-karaoke-aufr33-viperx": "lead_vocals / backing_vocals (on the Mel vocals)",
    "sep.mdx23c-drumsep": "drum sub-stems (on the SW drums)",
}


def _stem_rel(name: str) -> str:
    return f"stems/{name}.flac" if name in STEM_NAMES else f"stems/drums/{name[6:]}.flac"


def _run_worker(ctx, x44: np.ndarray, skip_karaoke: bool = False) -> tuple[dict[str, np.ndarray], dict[str, Any], Any]:
    p = ctx.params
    heavy = bool(getattr(ctx, "job", {}).get("heavy_locks", True))
    wparams = {"overlap": int(p["overlap"]), "segment_size": int(p["segment_size"]), "heavy_locks": heavy,
               "normalization_threshold": float(p["normalization_threshold"]),
               "amplification_threshold": float(p["amplification_threshold"]),
               "variant_order": [v for v in p["variant_order"] if v in ("rocm", "cpu")]}
    models = list(SEP_MODELS)
    if skip_karaoke:
        wparams["skip_steps"] = ["karaoke"]
        models.remove("sep.mel-roformer-karaoke-aufr33-viperx")
    res = ctx.worker({"mix": (x44, 44100)}, params=wparams, models=models, hold_slot=False)
    outs = {}
    for rel in res.outputs:
        if rel.endswith(".wav"):
            a = res.read(rel)
            if a.sr != 44100:
                raise StageError(f"worker output {rel} is {a.sr} Hz")
            outs[rel[:-4]] = a.samples
    return outs, dict(res.result.get("summary", {})), res


def _run_fallback(ctx, x44: np.ndarray) -> dict[str, np.ndarray]:
    from mvh.sep import demucs

    h = ctx.model(FALLBACK_MODEL)
    onnx = next(iter(h.files.values()))
    heavy = bool(getattr(ctx, "job", {}).get("heavy_locks", True))
    if heavy:
        from mvh.runner import locks

        with locks.heavy(f"mvh:{ctx.slug}:separate_hq:htdemucs", threads=ctx.threads):
            st = demucs.separate(x44, "htdemucs_6s", onnx, ctx.threads)
    else:
        st = demucs.separate(x44, "htdemucs_6s", onnx, ctx.threads)
    return {f"sw_{k}": v for k, v in st.items()}


def _lead_share(lead: np.ndarray, backing: np.ndarray, sr: int, margin_db: float) -> dict[str, Any]:
    """Per-second lead share of the vocal energy (the split's own confidence): the fraction of vocal seconds in which the
    backing is NOT within ``margin_db`` of the lead (1.0 = a clean lead over the backing throughout), and the median lead
    minus backing level (dB) over those seconds."""
    a = np.asarray(lead, dtype=np.float64).mean(axis=0)
    b = np.asarray(backing, dtype=np.float64).mean(axis=0)
    w = max(1, int(sr))
    nb = a.shape[0] // w
    if nb == 0:
        return {"seconds": 0, "clean_fraction": None, "median_lead_minus_backing_db": None}
    ea = (a[: nb * w].reshape(nb, w) ** 2).mean(axis=1)
    eb = (b[: nb * w].reshape(nb, w) ** 2).mean(axis=1)
    voiced = (ea + eb) > 1e-9   # about -90 dBFS: seconds with a voice
    if not np.any(voiced):
        return {"seconds": 0, "clean_fraction": None, "median_lead_minus_backing_db": None}
    d = 10.0 * np.log10(np.maximum(ea[voiced], 1e-14) / np.maximum(eb[voiced], 1e-14))
    return {"seconds": int(voiced.sum()), "clean_fraction": round(float(np.mean(d > margin_db)), 3),
            "median_lead_minus_backing_db": round(float(np.median(d)), 2)}


def run(ctx) -> StageResult:
    from mvh.sep import fit, invariants

    p = ctx.params
    order = p["variant_order"]
    if not isinstance(order, (list, tuple)) or not order or any(v not in ("rocm", "cpu", "htdemucs") for v in order):
        raise StageError(f"separate_hq.variant_order must be a list drawn from rocm, cpu, htdemucs; got {order!r}")
    mix = ctx.audio("mix")
    xm = np.asarray(mix.samples, dtype=np.float32)
    n, sr, ch = int(xm.shape[1]), int(mix.sr), int(xm.shape[0])
    x44 = fit.stereo44(xm if sr == 44100 else ctx.audio("mix", sr=44100).samples)
    # The karaoke model was trained on stereo mixes and leans on the pan cue (lead centred, backing spread): on a
    # mono / dual-mono song its split inverts (the lead lands in backing). Skip it: lead := vocals, backing silent.
    mono_in = fit.is_mono(xm)
    width_db = fit.side_to_mid_db(xm)
    drop_split = False

    warnings: list[str] = []
    fallbacks: list[str] = []
    flags: list[str] = []
    summary_w: dict[str, Any] = {}
    degraded = False
    try:
        raw, summary_w, res = _run_worker(ctx, x44, skip_karaoke=mono_in)
        variant = res.variant
        fallbacks += list(res.fallbacks)
        for a in res.attempts:
            warnings.append(f"sep worker variant {a.get('variant')} failed: {a.get('error') or a.get('errors') or a.get('returncode')}")
    except StageError as e:
        if "htdemucs" not in list(p["variant_order"]):
            raise
        ctx.log.warning(f"separate_hq: worker failed ({e}); falling back to htdemucs_6s (degraded)")
        warnings.append(f"sep worker failed in every variant; htdemucs_6s fallback (degraded): {str(e)[:300]}")
        raw = _run_fallback(ctx, x44)
        variant = "htdemucs"
        degraded = True
        fallbacks += ["sep:htdemucs", "lead_vocals:=vocals"]

    def get(key: str) -> np.ndarray:
        return fit.to_mix(raw[key], 44100, sr, n, ch, ctx.scratch / "fit")

    stems: dict[str, np.ndarray] = {}
    sw = {s: get(f"sw_{s}") for s in ("bass", "drums", "other", "vocals", "guitar", "piano")}
    for s in ("drums", "bass", "guitar", "piano", "other"):
        stems[s] = sw[s]
    checks: dict[str, Any] = {"side_to_mid_db": round(width_db, 2) if np.isfinite(width_db) else None}
    models_used: list[str]
    if not degraded:
        vocals = get("mel_vocals")
        if mono_in:
            lead = vocals.copy()
            backing = np.zeros_like(vocals)
            flags.append("sep:lead_backing_mono")
            warnings.append("mono / dual-mono input: the karaoke lead/backing split needs a stereo pan cue and is not "
                            "trusted; lead_vocals := vocals, backing_vocals silent (lead_backing_split=false)")
            fallbacks.append("lead_vocals:=vocals(mono)")
        else:
            lead = get("kar_lead")
            backing = (vocals.astype(np.float64) - lead).astype(np.float32)
            checks["karaoke_backing_model_vs_vocals_minus_lead_db"] = round(invariants.diff_db(get("kar_backing"), backing), 2)
            # Sanity of the split: the lead is the louder voice in practice (real stereo songs measure the backing 9-22 dB
            # under the lead). Backing within ``lead_suspect_db`` of the lead or above it means the model's pan cue failed
            # (a near-mono master, a mono recording with stereo reverb): the lead / backing assignment is inverted or
            # smeared. On a narrow master the split is then dropped (lead := vocals); on a wide one it is only flagged
            # (a real duet can have two equal voices).
            lead_db, back_db = invariants.rms_dbfs(lead), invariants.rms_dbfs(backing)
            checks["lead_minus_backing_db"] = round(lead_db - back_db, 2)
            checks["lead_share_frames"] = _lead_share(lead, backing, sr, float(p["lead_suspect_db"]))
            suspect = invariants.rms_dbfs(vocals) > -80.0 and back_db >= lead_db - float(p["lead_suspect_db"])
            if suspect:
                flags.append("sep:lead_backing_suspect")
                warnings.append(f"karaoke split is suspect: backing {back_db - lead_db:+.1f} dB vs lead (lead is normally the louder voice)")
                if width_db <= float(p["narrow_side_db"]):
                    drop_split = True
                    lead = vocals.copy()
                    backing = np.zeros_like(vocals)
                    flags.append("sep:lead_backing_narrow")
                    warnings.append(f"narrow stereo master (side {width_db:.1f} dB under mid) and a suspect split: lead_vocals := "
                                    "vocals, backing_vocals silent (lead_backing_split=false)")
                    fallbacks.append("lead_vocals:=vocals(narrow)")
        for sub in DRUM_SUBSTEMS:
            stems[f"drums_{sub}"] = get(f"ds_{sub}")
        no_model = mono_in or drop_split
        lead_split = not no_model
        models_used = [m for m in SEP_MODELS if not (mono_in and m == SEP_MODELS[2])]
        stem_model = {"vocals": SEP_MODELS[1], "lead_vocals": SEP_MODELS[1 if no_model else 2], "backing_vocals": SEP_MODELS[1 if no_model else 2],
                      **{s: SEP_MODELS[0] for s in ("drums", "bass", "guitar", "piano", "other")},
                      **{f"drums_{s}": SEP_MODELS[3] for s in DRUM_SUBSTEMS}}
    else:
        vocals = sw["vocals"]
        lead = vocals.copy()
        backing = np.zeros_like(vocals)
        lead_split = False
        models_used = [FALLBACK_MODEL]
        stem_model = {s: FALLBACK_MODEL for s in ("vocals", "lead_vocals", "backing_vocals", "drums", "bass", "guitar", "piano", "other")}
    stems["vocals"] = vocals
    stems["lead_vocals"] = lead
    stems["backing_vocals"] = backing
    stems["instrumental"] = (xm.astype(np.float64) - vocals).astype(np.float32)
    stem_model["instrumental"] = stem_model["vocals"]

    # ---- invariants
    six = [sw[s] for s in ("bass", "drums", "other", "vocals", "guitar", "piano")]
    sum_db = invariants.residual_db(xm, six)
    gains = invariants.gain_gate(xm, {s: sw[s] for s in ("bass", "drums", "other", "vocals", "guitar", "piano")})
    gate = float(p["sum_gate_db"])
    if sum_db > gate:
        flags.append("sep:sum_residual")
        warnings.append(f"six-stem sum residual {sum_db:.1f} dB is above the {gate:.0f} dB gate (the model leaks; stems are unscaled)")
    bad = [k for k, g in gains.items() if g["pass"] is False]
    if bad:
        flags.append("sep:gain")
        warnings.append(f"LS gain gate failed for {bad}: a stem may have been re-levelled")
    checks.update({
        "instrumental_plus_vocals_vs_mix_db": round(invariants.diff_db(stems["instrumental"].astype(np.float64) + vocals, xm), 2),
        "lead_plus_backing_vs_vocals_db": round(invariants.diff_db(lead.astype(np.float64) + backing, vocals), 2),
        "stem_rel_db": {k: round(invariants.rms_dbfs(v) - invariants.rms_dbfs(xm), 2) for k, v in stems.items()},
        "peaks": {k: round(float(np.max(np.abs(v))), 4) for k, v in stems.items()},
        "sum_gate_db": gate, "sum_pass": bool(sum_db <= gate), "gain_pass": not bad, "gains": gains,
    })
    if not degraded:
        checks["mel_vs_sw_vocals_db"] = round(invariants.diff_db(sw["vocals"], vocals), 2)
        checks["sw_vocals_rel_db"] = round(invariants.rms_dbfs(sw["vocals"]) - invariants.rms_dbfs(xm), 2)
        dsum = sum(stems[f"drums_{s}"].astype(np.float64) for s in DRUM_SUBSTEMS)
        checks["drum_substems_vs_drums_db"] = round(invariants.diff_db(dsum, stems["drums"]), 2)

    # ---- write
    for name in list(STEM_NAMES) + [f"drums_{s}" for s in DRUM_SUBSTEMS]:
        if name in stems:
            ctx.writer.audio(_stem_rel(name), stems[name], sr)
    if not degraded:
        ctx.writer.audio("sep/vocals_sw.flac", sw["vocals"], sr)
    licences = {}
    for mid in models_used:
        try:
            licences[mid] = ctx.model(mid).licence
        except Exception:  # noqa: BLE001
            licences[mid] = "unknown"
    doc = {
        "variant": variant if variant in ("rocm", "cpu", "htdemucs") else "cpu",
        "degraded": degraded,
        "lead_backing_split": lead_split,
        "stems": {k: {"model": stem_model[k], "file": _stem_rel(k)} for k in stems},
        "models": [{"id": m, "licence": licences[m], "role": ROLE.get(m, "6 stems (fallback)")} for m in models_used],
        "invariants": {"sum_error_db": round(sum_db, 2), "gain_db": {k: g["gain_db"] for k, g in gains.items()}},
        "checks": checks,
        "flags": flags,
        "definitions": {"vocals": "Mel-RoFormer vocals", "backing_vocals": "vocals - lead_vocals (exact)",
                        "instrumental": "mix - vocals (exact, un-normalised)"},
    }
    if summary_w:
        doc["worker"] = {k: summary_w[k] for k in ("torch", "hip", "audio_separator", "settings", "devices") if k in summary_w}
    ctx.writer.json("meta/separation.json", doc)
    if summary_w.get("timings"):
        ctx.log.info(f"separate_hq timings: {summary_w['timings']}")
    tools = [{"name": "audio-separator", "version": str(summary_w.get("audio_separator", "unknown"))},
             {"name": "torch", "version": str(summary_w.get("torch", "unknown"))}] if summary_w else []
    return StageResult(
        status="degraded" if degraded else "ok",
        summary={"variant": doc["variant"], "degraded": degraded, "lead_backing_split": lead_split,
                 "sum_error_db": round(sum_db, 2), "flags": flags},
        warnings=warnings, fallbacks=fallbacks,
        provenance={"models": [{"id": m, "licence": licences[m]} for m in models_used], "tools": tools,
                    "notes": ["normalization_threshold=100.0 set as an attribute after Separator(); amplification_threshold=0.0; float WAV"]},
    )


__all__ = ["STAGE", "run", "SEP_MODELS"]
