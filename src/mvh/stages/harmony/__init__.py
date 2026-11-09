"""harmony stage (contract v1, owner M4).

HPSS + CQT chroma (100 Hz curve), lv-chordia chords snapped to beats (template + Viterbi fallback, which is also an
independent check on every chord), and a key ensemble: S-KEY ONNX, three chroma profiles, a chord-histogram fit and a
bass-line fit, combined by z-score voting; the confidence comes from window/method agreement (the S-KEY softmax is flat).
Key changes are found by a sticky Viterbi over 30 s windows.

Human-correction hook: ``--param harmony.key_override="A minor"`` forces the key (confidence 1, flagged).
Deps, env and the catalogue outputs are FROZEN by docs/CONTRACT.md (PLAN §3.2).
"""
from __future__ import annotations

from mvh.runner.spec import StageResult, StageSpec, catalog_outputs

STAGE = StageSpec(
    "harmony",
    ('ingest', 'rhythm'),
    "main",
    "1.2.0",
    override_keys=(),
    outputs=catalog_outputs("harmony"),
    params={
        'key_window_s': 30.0, 'key_hop_s': 5.0, 'key_min_region_s': 20.0, 'key_override': '',
        'chord_dict': 'submission', 'snap_max_beat_frac': 0.5, 'hpss_margin': 2.0,
        # W4V-GAIN (W4-AN-9): chroma and the chord model read the mix scaled to this integrated loudness (null = master)
        'analysis_lufs': -10.0,
    },
    models=("skey_onnx", "lv_chordia_ismir2019_chordnet"),
    module="M4",
    description='HPSS + CQT chroma; key ensemble (S-KEY + profiles + chord histogram); lv-chordia chords snapped to beats.',
)


def _versions() -> list[dict[str, str]]:
    import importlib.metadata as md

    out = []
    for pkg in ("lv-chordia", "librosa", "onnxruntime", "numpy"):
        try:
            out.append({"name": pkg, "version": md.version(pkg)})
        except md.PackageNotFoundError:
            pass
    return out


def run(ctx) -> StageResult:
    import math

    import numpy as np
    from scipy.io import wavfile

    from . import chords as C
    from . import keys as K
    from .chroma import compute_chroma
    from .core import SR, analyse

    src = ctx.upstream("ingest").json("meta/source.json")
    n_samples, native_sr = int(src["n_samples"]), int(src["sample_rate"])
    duration = n_samples / native_sr
    n_curve = int(math.ceil(n_samples * 100 / native_sr))

    y = ctx.audio("mix", sr=SR, mono=True).samples
    y = np.asarray(y, np.float32).reshape(-1)
    from mvh.stages.loudness.level import mix_gain

    a_gain, _, _ = mix_gain(ctx, ctx.params.get("analysis_lufs", -10.0))
    if a_gain != 1.0:
        y = (y * np.float32(a_gain)).astype(np.float32)
    beats = list(ctx.events("beats").items)
    bars = list(ctx.events("bars").items)

    wav = ctx.scratch / "harmony_mix22k.wav"
    ctx.scratch.mkdir(parents=True, exist_ok=True)
    wavfile.write(str(wav), SR, y.astype(np.float32))

    def lv():
        import os

        cwd = os.getcwd()
        os.chdir(ctx.scratch)
        try:
            return C.run_lv_chordia(wav, str(ctx.params.get("chord_dict", "submission")))
        finally:
            os.chdir(cwd)

    skey = None
    try:
        h = ctx.model("skey_onnx")
        skey = K.SKey(h.files["skey/skey.onnx"], h.files["skey/config.json"], threads=ctx.threads)
    except Exception as e:  # noqa: BLE001
        ctx.log.warning("S-KEY unavailable (%s): key from profiles + chords only", type(e).__name__)
    try:
        ctx.model("lv_chordia_ismir2019_chordnet")
    except Exception:  # noqa: BLE001
        pass

    cf = compute_chroma(y, SR, margin=float(ctx.params.get("hpss_margin", 2.0)))
    res = analyse(y, duration, n_curve, beats, bars, lv, skey, ctx.params, cf=cf)

    ctx.writer.curves("chroma12", {f"chroma.{pc}": res.chroma_curve[pc] for pc in range(12)}, rate_hz=100.0)
    ctx.writer.events("chords", res.chords, kind="segment")
    ctx.writer.events("key", res.key_regions, kind="segment")
    ctx.writer.json("meta/key.json", res.key_meta)

    degraded = bool(res.fallbacks)
    notes = [f"chords from {res.chord_source}; no-chord share {res.summary['no_chord_share']:.1%}",
             f"chroma: HPSS (margin {ctx.params.get('hpss_margin', 2.0)}) + CQT 3 bins/semitone, tuning {cf.tuning:+.2f} semitones, hop {cf.hop}/{SR}"]
    if skey is None:
        notes.append("S-KEY unavailable: key from KS/Temperley/Albrecht profiles, chord fit and bass")
    return StageResult(
        status="degraded" if degraded else "ok",
        summary=res.summary,
        warnings=res.warnings,
        fallbacks=res.fallbacks,
        provenance={"tools": _versions(), "notes": notes},
        confidence=float(res.key_meta["global"]["conf"]),
    )
