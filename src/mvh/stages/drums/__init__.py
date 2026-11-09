"""drums stage (PLAN §5 drums, R8; owner M3a).

Hits come from the MDX23C DrumSep sub-stems of ``separate_hq`` (kick, snare, toms, hihat, ride, crash) when they
exist ("drumsep" path), otherwise from a band-energy classifier on the drum stem ("classifier" path; the
``separate_hq`` htdemucs fallback has no sub-stems). In the DrumSep path the classifier also runs on the full drum
stem and raises the confidence of hits it confirms. See ``core`` for the detector.

Outputs:
* ``events/drum_hits.json``: ``t`` (the one-shot's first sample), ``drum``, ``vel`` (loudness relative to the
  loudest hits of the same drum, p98 -> 1), ``level_db`` (loudest 10 ms RMS in the 60 ms after the onset),
  ``conf``, ``source``; additive ``sub_stem``, ``rise_db``, ``in_active`` and ``evidence``;
* classifier path: the vel of hat and cymbal hits (classes below the PLAN gates there) is scaled by 0.45 and the unscaled value
  kept as ``vel_raw``; the envelopes follow the scaled vel;
* curves ``drums.{kick,snare,hat,tom,cymbal,perc}`` (100 Hz, ``max`` policy, flash rule, velocity-scaled
  exponential release). ``perc`` stays zero: DrumSep has no perc stem and the classifier never guesses one.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from mvh.contract.ids import DRUM_SUBSTEMS
from mvh.runner.spec import StageResult, StageSpec, catalog_outputs

from . import core

STAGE = StageSpec(
    "drums",
    ('separate_hq', 'stem_activity'),
    "main",
    "1.1.0",
    override_keys=(),
    outputs=catalog_outputs("drums"),
    params={'path': 'auto', 'rise_db': 2.0, 'rel_gate_db': 30.0, 'abs_floor_db': -70.0, 'min_gap_ms': 30.0,
            'bleed_db': 18.0, 'bleed_rel_db': 12.0, 'inactive_conf_factor': 0.6, 'confirm_ms': 15.0,
            'min_substem_peak_db': -80.0},
    module="M3a",
    description='Drum hits from DrumSep sub-stems, else a classifier on the drum stem; velocities and 100 Hz envelopes.',
)

LOW_CONF_VEL = 0.45   # vel factor of the classes the classifier path does not deliver at the PLAN gates (= their conf cap)

FIELDS = {
    "vel_raw": {"unit": None, "type": "number"},
    "sub_stem": {"unit": None, "type": "string"},
    "rise_db": {"unit": "dB", "type": "number"},
    "in_active": {"unit": None, "type": "boolean"},
    "evidence": {"unit": None, "type": "string[]"},
}


def _load_mono(up, rel: str) -> tuple[np.ndarray, int]:
    from mvh.io import audio as aio
    from mvh.io.wav import read_wav

    p = up.path(rel)
    if p.suffix.lower() == ".wav":
        try:
            x, sr = read_wav(p)
            return x.mean(axis=0, dtype=np.float64), sr
        except ValueError:
            pass
    d = aio.decode(p)
    return d.samples.mean(axis=0, dtype=np.float64), d.sr


def _rel(up, base: str) -> str | None:
    for ext in (".wav", ".flac"):
        if up.exists(base + ext):
            return base + ext
    return None


def run(ctx) -> StageResult:
    p = dict(ctx.params)
    prm = core.DetectParams(rise_db=float(p["rise_db"]), abs_floor_db=float(p["abs_floor_db"]),
                            rel_gate_db=float(p["rel_gate_db"]), min_gap_ms=float(p["min_gap_ms"]))
    hq = ctx.upstream("separate_hq")
    mix = ctx.audio("mix")
    n_samples, sr_mix = int(mix.samples.shape[1]), int(mix.sr)
    nf = -(-n_samples * 100 // sr_mix)
    sa = ctx.upstream("stem_activity")
    stems_meta = sa.json("meta/stems.json").get("stems", {}) if sa.exists("meta/stems.json") else {}

    warnings: list[str] = []
    fallbacks: list[str] = []
    notes: list[str] = []
    subs: dict[str, np.ndarray] = {}
    sr = sr_mix
    if p["path"] in ("auto", "drumsep"):
        for sub in DRUM_SUBSTEMS:
            rel = _rel(hq, f"stems/drums/{sub}")
            if rel is None:
                continue
            pk = stems_meta.get(f"drums_{sub}", {}).get("peak_db")
            if pk is not None and pk < float(p["min_substem_peak_db"]):
                notes.append(f"sub-stem {sub} is silent (peak {pk} dBFS): skipped")
                continue
            subs[sub], sr = _load_mono(hq, rel)
    drum_rel = _rel(hq, "stems/drums")
    drums_x = None
    if drum_rel is not None:
        drums_x, sr_d = _load_mono(hq, drum_rel)
        sr = sr_d

    stats: dict[str, Any] = {}
    if subs:
        path = "drumsep"
        ch: list[core.Hit] = []
        if drums_x is not None and np.any(drums_x):
            # the classifier on the full drum stem is an independent second opinion: it confirms cymbals the DrumSep
            # ride / crash stems carry below the leak gate, raises the confidence of the hits it agrees with, and
            # recovers toms a DrumSep pass dropped (the toms stem differs from run to run)
            ch, cst = core.classify(drums_x, sr, prm)
            stats["classifier"] = cst["hits"]
        hits, st = core.drumsep_hits(subs, sr, prm, bleed_db=float(p["bleed_db"]), bleed_rel_db=float(p["bleed_rel_db"]),
                                     cymbal_confirm=[h.t for h in ch if h.drum == "cymbal"], confirm_ms=float(p["confirm_ms"]), drums_mix=drums_x)
        stats["drumsep"] = st
        if ch:
            by: dict[str, np.ndarray] = {d: np.array(sorted(h.t for h in ch if h.drum == d)) for d in core.DRUMS}
            tol = float(p["confirm_ms"]) / 1000.0
            confirmed = 0
            for h in hits:
                arr = by.get(h.drum)
                if arr is not None and arr.size:
                    j = np.searchsorted(arr, h.t)
                    near = [arr[k] for k in (j - 1, j) if 0 <= k < arr.size]
                    if any(abs(t - h.t) <= tol for t in near):
                        h.conf = min(1.0, h.conf + 0.15)
                        h.evidence.append("classifier_agrees")
                        confirmed += 1
            stats["classifier_confirmed"] = confirmed
            have = np.array(sorted(h.t for h in hits if h.drum == "tom"))
            kick_snare = np.array(sorted(h.t for h in hits if h.drum in ("kick", "snare")))   # a tom is not played with them
            added = 0
            for c in ch:
                if c.drum != "tom":
                    continue
                if kick_snare.size and float(np.min(np.abs(kick_snare - c.t))) <= 0.025:
                    continue   # a kick / snare transient the classifier read as a tom (real stems: 90 % of its toms)
                if have.size and float(np.min(np.abs(have - c.t))) <= 2 * tol:
                    continue
                c.source = "drumsep"   # event path stays drumsep; evidence classifier_only marks the recovered stroke
                c.conf = min(c.conf, 0.5)
                c.evidence = list(c.evidence) + ["classifier_only"]
                hits.append(c)
                added += 1
            stats["classifier_only_toms"] = added
    elif drums_x is not None and np.any(drums_x):
        path = "classifier"
        hits, st = core.classify(drums_x, sr, prm)
        stats["classifier"] = st
        fallbacks.append("drums:classifier")
        fallbacks.append("drums:low_confidence(hat,cymbal)")
        warnings.append("no DrumSep sub-stems: drum hits come from the band classifier on the drum stem; kick, snare and "
                        "tom are reliable, hat and cymbal hits are low confidence (hats under snare tails and rides under "
                        "strokes are missed or mislabelled)")
        for h in hits:
            if h.drum not in core.CLASSIFIER_RELIABLE:
                h.conf = min(h.conf, 0.45)
                h.evidence.append("low_confidence_class")
    else:
        path = "none"
        hits = []
        warnings.append("no drum stem: no drum hits")

    # activity of the drum stem: hits outside it are kept with lower confidence
    try:
        act = ctx.curve("stem.drums.active").values
    except Exception:  # noqa: BLE001  (stem_activity without the drums stem)
        act = None
    n_out_active = 0
    for h in hits:
        i = int(round(h.t * 100))
        inside = bool(act[min(max(i, 0), act.size - 1)] > 0.5) if act is not None and act.size else True
        h.evidence = list(h.evidence)
        if not inside:
            h.conf *= float(p["inactive_conf_factor"])
            n_out_active += 1
        setattr(h, "in_active", inside)
    refs = core.velocities(hits)
    for h in hits:
        # a very faint hit (relative to the loudest of its drum) is bleed or an artefact more often than a stroke
        h.conf *= 0.5 + 0.5 * float(np.clip(h.vel / 0.15, 0.0, 1.0))
    vel_raw: dict[int, float] = {}
    if path == "classifier":
        # the consumers (choreo, cues) read only t, drum and vel: scale the vel of the classes this path does not deliver at
        # the PLAN gates (hat, cymbal) by the confidence cap, so they enter the choreography at a fraction of their weight
        for h in hits:
            if "low_confidence_class" in h.evidence:
                vel_raw[id(h)] = h.vel
                h.vel = h.vel * LOW_CONF_VEL
    items = []
    for h in sorted(hits, key=lambda h: (h.t, core.DRUMS.index(h.drum))):
        it: dict[str, Any] = {
            "t": round(h.t, 6), "drum": h.drum, "vel": round(h.vel, 4), "level_db": round(max(h.level_db, core.FLOOR_DB), 2),
            "conf": round(float(np.clip(h.conf, 0.0, 1.0)), 3), "source": h.source,
            "rise_db": round(float(min(h.rise_db, 120.0)), 2), "in_active": bool(getattr(h, "in_active", True)),
        }
        if id(h) in vel_raw:
            it["vel_raw"] = round(vel_raw[id(h)], 4)
        if h.sub_stem:
            it["sub_stem"] = h.sub_stem
        if h.evidence:
            it["evidence"] = sorted(set(h.evidence))
        items.append(it)
    ctx.writer.events("drum_hits", items, kind="event", fields=FIELDS)
    env = core.envelopes(hits, nf)
    ctx.writer.curves("core", {f"drums.{d}": env[d] for d in core.DRUMS})

    counts = {d: sum(1 for h in hits if h.drum == d) for d in core.DRUMS}
    if n_out_active:
        notes.append(f"{n_out_active} hits fall outside stem.drums.active (confidence x{p['inactive_conf_factor']})")
    summary = {"path": path, "counts": counts, "n_hits": len(hits)}
    if path == "classifier":
        summary["low_confidence_classes"] = [d for d in core.DRUMS if d not in core.CLASSIFIER_RELIABLE and counts[d]]
    conf = float(np.mean([h.conf for h in hits])) if hits else None
    return StageResult(
        status="degraded" if path == "classifier" else "ok",
        summary=summary, warnings=warnings, fallbacks=fallbacks,
        provenance={"notes": notes + [f"vel = peak / p98 peak of the same drum: refs {{{', '.join(f'{k}: {v:.4f}' for k, v in sorted(refs.items()))}}}"],
                    "drum_stats": stats,
                    "models": [{"id": "sep.mdx23c-drumsep", "licence": "unclear (aufr33 + jarredou); personal non-commercial use",
                                "role": "sub-stems (run by separate_hq)"}] if path == "drumsep" else []},
        confidence=conf,
    )


__all__ = ["STAGE", "run"]
