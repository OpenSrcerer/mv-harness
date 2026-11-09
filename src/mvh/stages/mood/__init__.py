"""mood stage (contract v1, owner M4).

Essentia ONNX heads on a numpy mel front end: msd-musicnn embeddings -> emoMusic and DEAM (valence, arousal), and
discogs-effnet embeddings -> MTG-Jamendo mood/theme (56 tags). 1 Hz curves, per-section summaries and a global summary,
each with per-head values and a confidence. Arousal is fairly reliable; valence is low confidence (the heads disagree).
Mood is a hint for a director: the user's meaning wins.

Deps, env and the catalogue outputs are FROZEN by docs/CONTRACT.md (PLAN §3.2).
"""
from __future__ import annotations

from mvh.runner.spec import StageResult, StageSpec, catalog_outputs

STAGE = StageSpec(
    "mood",
    ('ingest', 'structure'),
    "main",
    "1.0.0",
    override_keys=(),
    outputs=catalog_outputs("mood"),
    params={'top_tags_per_section': 3, 'min_tag_p': 0.08, 'global_tags': 8},
    models=("essentia_msd_musicnn", "essentia_discogs_effnet"),
    module="M4",
    description='Essentia ONNX heads (emoMusic, DEAM, MTG-Jamendo mood/theme) with a numpy mel front end; per-section aggregation.',
)

_EXTRA_FIELDS = {
    "valence_emomusic": {"unit": "0..1", "type": "number"}, "valence_deam": {"unit": "0..1", "type": "number"},
    "arousal_emomusic": {"unit": "0..1", "type": "number"}, "arousal_deam": {"unit": "0..1", "type": "number"},
    "tag_p": {"unit": "0..1", "type": "array"},
}


def _versions() -> list[dict[str, str]]:
    import importlib.metadata as md

    out = []
    for pkg in ("onnxruntime", "numpy"):
        try:
            out.append({"name": pkg, "version": md.version(pkg)})
        except md.PackageNotFoundError:
            pass
    return out


def run(ctx) -> StageResult:
    import math

    import numpy as np

    from . import core as M

    src = ctx.upstream("ingest").json("meta/source.json")
    n_samples, native_sr = int(src["n_samples"]), int(src["sample_rate"])
    n = int(math.ceil(n_samples / native_sr))
    y16 = np.asarray(ctx.audio("mix", sr=16000, mono=True).samples, np.float32).reshape(-1)

    mus = ctx.model("essentia_msd_musicnn")
    eff = ctx.model("essentia_discogs_effnet")
    heads = M.Heads(mus.files, eff.files, threads=ctx.threads)
    raw = heads.run(y16)
    silent = M.silence_mask(y16, n)
    cur = M.to_curves(raw, n, silent)

    channels = {"mood.valence": cur.valence, "mood.arousal": cur.arousal}
    for j, tag in enumerate(cur.classes):
        channels[f"mood.tag.{tag}"] = cur.tags[j]
    ctx.writer.curves("mood_1hz", channels, rate_hz=1.0)

    sections = list(ctx.events("sections").items)
    items = []
    p = ctx.params
    for s in sorted(sections, key=lambda s: float(s["t"])):
        r = M.summarise(cur, float(s["t"]), float(s["d"]), int(p.get("top_tags_per_section", 3)), float(p.get("min_tag_p", 0.08)))
        items.append({
            "t": float(s["t"]), "d": float(s["d"]), "section_id": s["id"],
            "valence": round(r["valence"], 4), "arousal": round(r["arousal"], 4),
            "valence_conf": round(r["valence_conf"], 3), "arousal_conf": round(r["arousal_conf"], 3), "tags": r["tags"],
            "valence_emomusic": round(r["valence_emomusic"], 4), "valence_deam": round(r["valence_deam"], 4),
            "arousal_emomusic": round(r["arousal_emomusic"], 4), "arousal_deam": round(r["arousal_deam"], 4), "tag_p": r["tag_p"],
        })
    ctx.writer.events("mood", items, kind="segment", fields=_EXTRA_FIELDS)

    g = M.global_summary(cur, int(p.get("global_tags", 8)))
    flags: list[str] = []
    gap_v = abs(g["valence_emomusic"] - g["valence_deam"])
    gap_a = abs(g["arousal_emomusic"] - g["arousal_deam"])
    if gap_v > 0.12:
        flags.append("mood:valence_heads_disagree")
    if gap_a > 0.12:
        flags.append("mood:arousal_heads_disagree")
    flags.append("mood:valence_low_confidence")
    if bool(silent.all()):
        flags.append("mood:all_silent")
    doc = {
        "global": {"valence": round(g["valence"], 4), "arousal": round(g["arousal"], 4),
                   "valence_conf": round(g["valence_conf"], 3), "arousal_conf": round(g["arousal_conf"], 3),
                   "tags": [{"tag": t, "p": q} for t, q in zip(g["tags"], g["tag_p"])]},
        "models": ["essentia_msd_musicnn:msd-musicnn-1+emomusic-msd-musicnn-2+deam-msd-musicnn-2",
                   "essentia_discogs_effnet:discogs-effnet-bsdynamic-1+mtg_jamendo_moodtheme-discogs-effnet-1"],
        "heads": {"emomusic": {"valence": round(g["valence_emomusic"], 4), "arousal": round(g["arousal_emomusic"], 4)},
                  "deam": {"valence": round(g["valence_deam"], 4), "arousal": round(g["arousal_deam"], 4)},
                  "scale": "model output 1..9 mapped by (x - 1) / 8; valence/arousal = mean of the two heads"},
        "flags": flags,
        "arc": {"arousal_min": round(float(cur.arousal[~silent].min()), 4) if (~silent).any() else 0.5,
                "arousal_max": round(float(cur.arousal[~silent].max()), 4) if (~silent).any() else 0.5,
                "valence_min": round(float(cur.valence[~silent].min()), 4) if (~silent).any() else 0.5,
                "valence_max": round(float(cur.valence[~silent].max()), 4) if (~silent).any() else 0.5},
    }
    ctx.writer.json("meta/mood.json", doc)

    return StageResult(
        status="ok",
        summary={"valence": round(g["valence"], 3), "arousal": round(g["arousal"], 3), "valence_conf": round(g["valence_conf"], 2),
                 "arousal_conf": round(g["arousal_conf"], 2), "top_tags": g["tags"][:3], "n_sections": len(items),
                 "heads_valence_gap": round(gap_v, 3), "heads_arousal_gap": round(gap_a, 3)},
        warnings=[f for f in flags if f != "mood:valence_low_confidence"],
        provenance={"tools": _versions(), "notes": [
            "msd-musicnn patches 3.0 s / hop 1.5 s, discogs-effnet patches 2.06 s / hop 1.0 s, linear interpolation to 1 Hz",
            "digital-silence seconds (< -70 dBFS RMS) read neutral 0.5 with confidence 0",
            "valence confidence capped at 0.5 (emoMusic and DEAM disagree on real music); arousal is the reliable axis"]},
        confidence=float(g["arousal_conf"]),
    )
