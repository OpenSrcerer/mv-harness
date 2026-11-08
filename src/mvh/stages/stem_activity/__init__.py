# ruff: noqa: E501  (long catalogue tables / docstrings)
"""stem_activity stage (PLAN §5 stem_activity; owner M3a).

Per stem (the nine stems of ``separate_hq`` plus the DrumSep sub-stems that exist):
* curves ``stem.{stem}.rms_db`` / ``.rel_db`` / ``.level`` / ``.active`` at 100 Hz (``curves/stems.f32``);
* ``events/stem_activity.json``: active segments with ``mean_db`` and (additive) ``conf`` / ``mean_rel_db``;
* ``meta/stems.json``: ``present``, ``active_ratio``, ``median_rms_db``, ``peak_db``, ``share_of_mix_db`` and
  (additive) ``conf``, ``evidence``, ``present_energy``, ``active_s``, ``n_segments``.

Activity follows PLAN (> -45 dBFS and within 18 dB of the mix, 300 ms attack / 500 ms release), evaluated on a
0.4 s RMS so sparse parts do not flicker (see ``core``). **Presence is not energy alone** (SPIKE: on MEGAFAUNA the
Mel-RoFormer vocals stem picks up synth leads at -12.8 dB): every stem that a second, independent separator also
produced (htdemucs from ``separate_fast``; BS-RoFormer-SW's own vocals, cached by ``separate_hq``) gets a per-frame
cross-model agreement; ``present`` requires energy **and** ``conf >= min_conf``. ``present_energy`` keeps the
energy-only verdict, and ``conf``/``evidence`` let instruments, vocals and lyrics combine it with the tagger and
the lyrics source.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from mvh.contract.ids import DRUM_SUBSTEMS, STEM_NAMES
from mvh.runner.spec import StageResult, StageSpec, catalog_outputs

from . import core

STAGE = StageSpec(
    "stem_activity",
    ('ingest', 'separate_fast', 'separate_hq'),
    "main",
    "1.0.0",
    override_keys=(),
    outputs=catalog_outputs("stem_activity"),
    params={'active_db': -45.0, 'within_db': 18.0, 'attack_ms': 300, 'release_ms': 500,
            'decision_window_s': core.DECISION_WINDOW_S, 'min_present_s': 2.0, 'min_present_drum_s': 0.5, 'min_conf': 0.4},
    module="M3a",
    description='Per-stem RMS dBFS at 100 Hz, level relative to the mix, activity with hysteresis, present flags '
                'with cross-model confidence.',
)

#: stems whose activity a second separator can confirm: stem -> [(source, rel path or fast stem), ...]
#: ('hq', rel) = a cache-only file of separate_hq; ('fast', [stems]) = the sum of separate_fast stems
ALTERNATIVES: dict[str, list[tuple[str, Any]]] = {
    "vocals": [("hq", "sep/vocals_sw.flac"), ("fast", ["vocals"])],
    "drums": [("fast", ["drums"])],
    "bass": [("fast", ["bass"])],
    "other": [("fast", ["other"])],
    "guitar": [("fast", ["guitar"]), ("fast", ["other"])],   # htdemucs 4-stem puts guitar in other
    "piano": [("fast", ["piano"]), ("fast", ["other"])],
    "instrumental": [("fast", ["drums", "bass", "other"])],
}
#: stems that inherit the per-frame agreement of their parent (karaoke split of the Mel vocals)
INHERIT = {"lead_vocals": "vocals", "backing_vocals": "vocals"}
#: stems that are splits of another stem: their activity is judged against the parent (the split's input)
PARENT = {"lead_vocals": "vocals", "backing_vocals": "vocals", **{f"drums_{s}": "drums" for s in DRUM_SUBSTEMS}}

FIELDS = {
    "conf": {"unit": "0..1", "type": "number"},
    "mean_rel_db": {"unit": "dB", "type": "number"},
}


def _load(up, rel: str) -> np.ndarray:
    """Decode an upstream audio file without caching it in the Upstream (stems are large)."""
    from mvh.io import audio as aio
    from mvh.io.wav import read_wav

    p = up.path(rel)
    if p.suffix.lower() == ".wav":
        try:
            return read_wav(p)[0]
        except ValueError:
            pass
    return aio.decode(p).samples


def _hq_rel(up, stem: str) -> str | None:
    base = f"stems/{stem}" if stem in STEM_NAMES else f"stems/drums/{stem[6:]}"
    for ext in (".wav", ".flac"):
        if up.exists(base + ext):
            return base + ext
    return None


def _fit(a: np.ndarray, n: int) -> np.ndarray:
    a = np.asarray(a, dtype=np.float32)
    if a.ndim == 1:
        a = a[None, :]
    if a.shape[1] >= n:
        return a[:, :n]
    return np.pad(a, ((0, 0), (0, n - a.shape[1])))


def run(ctx) -> StageResult:
    p = dict(ctx.params)
    mix = ctx.audio("mix")
    x_mix = np.asarray(mix.samples, dtype=np.float32)
    sr = int(mix.sr)
    n = int(x_mix.shape[1])
    dur = n / sr
    nf = core.n_frames(n, sr)
    win_dec = float(p.get("decision_window_s", core.DECISION_WINDOW_S))

    mix_db = core.power_db(core.frame_power(x_mix, sr, core.RMS_WINDOW_S, nf))
    mix_dec_db = core.power_db(core.frame_power(x_mix, sr, win_dec, nf))
    mix_energy = float(np.sum(np.square(x_mix, dtype=np.float64))) / x_mix.shape[0]

    hq = ctx.upstream("separate_hq")
    fast = ctx.upstream("separate_fast")
    sep_meta: dict[str, Any] = hq.json("meta/separation.json") if hq.exists("meta/separation.json") else {}
    lead_split = bool(sep_meta.get("lead_backing_split", True))

    stems = [s for s in STEM_NAMES if _hq_rel(hq, s)]
    stems += [f"drums_{s}" for s in DRUM_SUBSTEMS if _hq_rel(hq, f"drums_{s}")]

    # ---- alternative-model levels (decision window), loaded lazily and shared
    alt_cache: dict[tuple[str, str], np.ndarray | None] = {}

    def alt_dec(kind: str, what: Any) -> np.ndarray | None:
        key = (kind, what if isinstance(what, str) else "+".join(what))
        if key in alt_cache:
            return alt_cache[key]
        val = None
        if kind == "hq" and hq.exists(what):
            val = core.power_db(core.frame_power(_fit(_load(hq, what), n), sr, win_dec, nf))
        elif kind == "fast":
            rels = [f"fast/{s}.wav" for s in what]
            if all(fast.exists(r) for r in rels):
                acc = None
                for r in rels:
                    a = _fit(_load(fast, r), n)
                    acc = a if acc is None else acc + a
                val = core.power_db(core.frame_power(acc, sr, win_dec, nf))
        alt_cache[key] = val
        return val

    curves: dict[str, np.ndarray] = {}
    rms_all: dict[str, np.ndarray] = {}
    items: list[dict[str, Any]] = []
    stats: dict[str, Any] = {}
    agree_frames: dict[str, np.ndarray] = {}
    dec_frames: dict[str, np.ndarray] = {}
    masks: dict[str, np.ndarray] = {}
    warnings: list[str] = []
    flags: list[str] = []
    th = dict(active_db=float(p["active_db"]), within_db=float(p["within_db"]),
              attack_ms=float(p["attack_ms"]), release_ms=float(p["release_ms"]))

    for stem in stems:
        x = _fit(_load(hq, _hq_rel(hq, stem)), n)
        rms = core.power_db(core.frame_power(x, sr, core.RMS_WINDOW_S, nf))
        dec = core.power_db(core.frame_power(x, sr, win_dec, nf))
        evidence: list[str] = ["energy"]
        parent = PARENT.get(stem) if stem in PARENT else None
        if parent and parent in dec_frames:
            # a split of another stem (DrumSep on the drums, karaoke on the vocals): its "mix" is the parent stem,
            # and it can only be active where the parent is (docs/contract/decisions/M3a.md)
            dec_rel = core.rel_db(dec, dec_frames[parent])
            mask = core.activity_mask(dec, dec_rel, **th) & masks[parent]
            evidence.append(f"reference:{parent}")
        else:
            dec_rel = core.rel_db(dec, mix_dec_db)
            mask = core.activity_mask(dec, dec_rel, **th)
        # ---- confidence: cross-model agreement, inherited agreement, or the level margin
        agree = None
        if stem in ALTERNATIVES:
            alts = []
            for kind, what in ALTERNATIVES[stem]:
                v = alt_dec(kind, what)
                if v is not None:
                    alts.append(core.agreement(dec, v))
                    evidence.append(f"{'sw' if kind == 'hq' else 'htdemucs'}:{what if isinstance(what, str) else '+'.join(what)}")
                    if stem in ("guitar", "piano"):
                        break  # one alternative is enough (the dedicated stem when the draft model has it)
            if alts:
                agree = np.mean(np.stack(alts), axis=0)
        elif stem in INHERIT and INHERIT[stem] in agree_frames:
            agree = agree_frames[INHERIT[stem]]
            evidence.append(f"inherits:{INHERIT[stem]}")
        if agree is None:
            margin = np.clip((dec_rel + th["within_db"]) / 12.0, 0.0, 1.0) * np.clip((dec - th["active_db"]) / 12.0, 0.0, 1.0)
            agree = 0.5 + 0.5 * margin
            evidence.append("level_margin")
        agree_frames[stem] = agree
        dec_frames[stem] = dec
        masks[stem] = mask
        segs = core.segments_of(mask, dur)
        for t, d, i0, i1 in segs:
            seg_p = np.power(10.0, rms[i0:i1] / 10.0)
            mean_db = float(10.0 * np.log10(max(float(seg_p.mean()), 1e-12)))
            items.append({
                "t": round(t, 6), "d": round(d, 6), "stem": stem, "mean_db": round(max(mean_db, core.FLOOR_DB), 2),
                "conf": round(float(np.mean(agree[i0:i1])), 3),
                "mean_rel_db": round(float(np.mean(dec_rel[i0:i1])), 2),
            })
        conf = float(np.mean(agree[mask])) if mask.any() else 0.0
        if stem == "backing_vocals" and not lead_split:
            conf = 0.0
            evidence.append("no_lead_backing_split")
        st = core.stem_stats(x, rms, mask, mix_energy, duration_s=dur, n_segments=len(segs), conf=conf,
                             evidence=evidence, min_present_s=float(p["min_present_drum_s"] if stem.startswith("drums_") else p["min_present_s"]), min_conf=float(p["min_conf"]))
        stats[stem] = {
            "present": st.present, "active_ratio": round(st.active_ratio, 4), "median_rms_db": round(st.median_rms_db, 2),
            "peak_db": round(st.peak_db, 2), "share_of_mix_db": round(st.share_of_mix_db, 2),
            "conf": round(st.conf, 3), "evidence": st.evidence, "present_energy": st.present_energy,
            "active_s": round(st.active_s, 2), "n_segments": st.n_segments,
        }
        if st.present_energy and not st.present:
            flags.append(f"{stem}:unconfirmed")
            warnings.append(f"{stem}: energy says active for {st.active_s:.1f} s but a second separator does not confirm it "
                            f"(conf {st.conf:.2f}); present=false, present_energy=true")
        rel = core.rel_db(rms, mix_db)
        curves[f"stem.{stem}.rms_db"] = rms.astype(np.float32)
        curves[f"stem.{stem}.rel_db"] = rel.astype(np.float32)
        curves[f"stem.{stem}.active"] = mask.astype(np.float32)
        rms_all[stem] = rms
        del x

    lo, hi = core.shared_norm(rms_all)
    meta: dict[str, dict[str, Any]] = {}
    for stem, rms in rms_all.items():
        lvl = np.clip((rms - lo) / (hi - lo), 0.0, 1.0)
        lvl = np.where(rms <= core.FLOOR_DB, 0.0, lvl)
        curves[f"stem.{stem}.level"] = lvl.astype(np.float32)
        meta[f"stem.{stem}.level"] = {"norm": {"lo": lo, "hi": hi}}
    ctx.writer.curves("stems", curves, meta=meta)

    items.sort(key=lambda d: (d["t"], stems.index(d["stem"])))
    ctx.writer.events("stem_activity", items, kind="segment", fields=FIELDS)
    ctx.writer.json("meta/stems.json", {
        "stems": stats,
        "thresholds": {"active_db": th["active_db"], "within_db": th["within_db"], "attack_ms": th["attack_ms"],
                       "release_ms": th["release_ms"]},
        "decision_window_s": win_dec,
        "min_conf": float(p["min_conf"]),
        "level_norm": {"lo": round(lo, 3), "hi": round(hi, 3)},
        "flags": flags,
    })
    present = [s for s in stems if stats[s]["present"]]
    summary = {
        "present": present,
        "vocals_conf": stats.get("vocals", {}).get("conf"),
        "n_segments": len(items),
        "flags": flags,
    }
    return StageResult(
        status="ok", summary=summary, warnings=warnings,
        provenance={"notes": ["activity on a 0.4 s RMS; presence = energy AND cross-model agreement (conf >= min_conf)"]},
        confidence=float(np.mean([stats[s]["conf"] for s in present])) if present else None,
    )


__all__ = ["STAGE", "run", "ALTERNATIVES", "INHERIT"]
