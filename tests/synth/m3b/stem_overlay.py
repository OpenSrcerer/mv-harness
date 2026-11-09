"""Real-song fixture overlay for the M3b stages (owner builder-m3b).

The real-song adapters (tests/contract/real-<slug>/) have no ``stem_activity`` outputs, but notes, vocals and
instruments depend on that stage. This tool builds ``out/_wip/builder-m3b/fx/<slug>/``: every file of the real
fixture hard-linked (copied when linking fails), plus a REFERENCE stem_activity (PLAN §5 rule: RMS > -45 dBFS and
within 18 dB of the mix, 300 ms attack / 500 ms release hysteresis) so the M3b stages can run through the runner
with ``MVH_FIXTURE_DIR`` pointing at the overlay. It is a test aid, not the production stem_activity stage (M3a).

    uv run --frozen --no-sync python -m tests.synth.m3b.stem_overlay jeremy [megafauna ...]
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np

from mvh.contract import curvefile
from mvh.contract.ids import DRUM_SUBSTEMS, STEM_NAMES
from mvh.io import audio as aio

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "out" / "_wip" / "builder-m3b" / "fx"
SPECTRAL_PLACEHOLDER_CURVES = ("hits.mid_raw", "hits.high_raw", "timbre.slope_db_oct", "stereo.balance")
SPECTRAL_PLACEHOLDER_EVENTS = ("hits.kick", "hits.mid", "hits.high", "onsets.bass", "onsets.mid", "onsets.high")
ACTIVE_DB, WITHIN_DB, ATTACK_S, RELEASE_S = -45.0, 18.0, 0.3, 0.5


def _link_tree(src: Path, dst: Path) -> None:
    for p in sorted(src.rglob("*")):
        if p.is_dir():
            continue
        rel = p.relative_to(src)
        if rel.parts[0] == "curves":
            continue  # re-assembled below
        q = dst / rel
        q.parent.mkdir(parents=True, exist_ok=True)
        if q.exists():
            continue
        try:
            os.link(p, q)
        except OSError:
            shutil.copy2(p, q)


def rms_db_100hz(x: np.ndarray, sr: int, n_frames: int, win_s: float = 0.046) -> np.ndarray:
    """Centred-window RMS (dBFS, floored at -120) of a mono signal at 100 Hz."""
    p = np.asarray(x, dtype=np.float64) ** 2
    c = np.concatenate([[0.0], np.cumsum(p)])
    half = int(round(win_s * sr / 2))
    centres = np.round(np.arange(n_frames) * sr / 100.0).astype(np.int64)
    a = np.clip(centres - half, 0, p.size)
    b = np.clip(centres + half, 0, p.size)
    e = (c[b] - c[a]) / np.maximum(b - a, 1)
    return np.maximum(10 * np.log10(np.maximum(e, 1e-12)), -120.0)


def hysteresis(cond: np.ndarray, attack: int, release: int) -> np.ndarray:
    out = np.zeros(cond.size, dtype=np.float32)
    on, run_on, run_off = False, 0, 0
    for i, c in enumerate(cond):
        if c:
            run_on += 1
            run_off = 0
        else:
            run_off += 1
            run_on = 0
        if not on and run_on >= attack:
            on = True
            out[max(0, i - attack + 1): i + 1] = 1.0
            continue
        if on and run_off >= release:
            on = False
            out[max(0, i - release + 1): i + 1] = 0.0
            continue
        out[i] = 1.0 if on else 0.0
    return out


def build(slug: str, log=print) -> Path:
    src = REPO / "tests" / "contract" / f"real-{slug}"
    if not src.is_dir():
        raise SystemExit(f"no fixture {src}")
    dst = OUT / slug
    dst.mkdir(parents=True, exist_ok=True)
    _link_tree(src, dst)
    index = curvefile.read_index(src)
    entries = []
    for e in index["channels"]:
        fid = e["file"]
        if index["files"][fid]["dtype"] != "f32le":
            arr, finfo = curvefile.read_matrix(src, index, fid)
            meta = {k: finfo[k] for k in ("band_edges_hz",) if k in finfo}
            entries.append(curvefile.ChannelData(e["id"], arr, meta))
            continue
        v, meta = curvefile.read_channel(src, index, e["id"])
        keep = {}
        if meta.get("norm") and isinstance(meta["norm"], dict):
            keep.update({k: meta["norm"][k] for k in ("lo", "hi") if k in meta["norm"]})
        entries.append(curvefile.ChannelData(e["id"], v, keep))
    mix = aio.decode(src / "_intermediate" / "ingest" / "canonical.wav", mono=True)
    n_frames = -(-mix.n * 100 // mix.sr)
    mix_db = rms_db_100hz(mix.samples[0], mix.sr, n_frames)
    names = list(STEM_NAMES) + [f"drums_{s}" for s in DRUM_SUBSTEMS]
    rms: dict[str, np.ndarray] = {}
    for name in names:
        rel = f"stems/{name}.flac" if name in STEM_NAMES else f"stems/drums/{name[6:]}.flac"
        if not (src / rel).is_file():
            continue
        d = aio.decode(src / rel, mono=True)
        rms[name] = rms_db_100hz(d.samples[0], d.sr, n_frames)
        log(f"{slug}: {name} median {np.median(rms[name]):.1f} dBFS")
    allv = np.concatenate([v[v > -119] for v in rms.values()]) if rms else np.array([-60.0, 0.0])
    lo, hi = float(np.percentile(allv, 2)), float(np.percentile(allv, 99.5))
    stems_meta, events = {}, []
    for name, r in rms.items():
        rel_db = np.maximum(r - mix_db, -120.0)
        act = hysteresis((r > ACTIVE_DB) & (rel_db > -WITHIN_DB), int(ATTACK_S * 100), int(RELEASE_S * 100))
        level = np.clip((r - lo) / max(hi - lo, 1e-6), 0, 1)
        for suffix, v, meta in (("level", level, {"lo": lo, "hi": hi}), ("rms_db", r, {}), ("rel_db", rel_db, {}),
                                ("active", act, {})):
            entries.append(curvefile.ChannelData(f"stem.{name}.{suffix}", v.astype(np.float32), meta))
        a = act > 0.5
        edges = np.flatnonzero(np.diff(np.concatenate([[0], a.astype(np.int8), [0]])))
        for s, e in zip(edges[::2], edges[1::2]):
            events.append({"t": round(s / 100.0, 6), "d": round((e - s) / 100.0, 6), "stem": name,
                           "mean_db": round(float(np.mean(r[s:e])), 2)})
        lin = 10 ** (r / 10)
        mlin = 10 ** (mix_db / 10)
        stems_meta[name] = {"present": bool(a.mean() >= 0.01), "active_ratio": round(float(a.mean()), 4),
                            "median_rms_db": round(float(np.median(r)), 2), "peak_db": round(float(r.max()), 2),
                            "share_of_mix_db": round(float(10 * np.log10(max(lin.mean(), 1e-12) / max(mlin.mean(), 1e-12))), 2)}
    have = {e.id for e in entries}
    for cid in SPECTRAL_PLACEHOLDER_CURVES:
        if cid not in have:  # partial spectral adapter: zero placeholders so the spectral stub can run upstream
            entries.append(curvefile.ChannelData(cid, np.zeros(n_frames, np.float32), {}))
    curvefile.assemble(dst, entries)
    prov = {"stage": "stem_activity", "stage_version": "0.0.0-m3b-overlay", "contract_version": "1.0.0-rc.1",
            "key": "0" * 64, "params": {"truth": "reference", "slug": slug}, "models": [], "tools": [],
            "device": "cpu", "upstream": {}, "overrides_applied": [], "fallbacks": [],
            "notes": ["builder-m3b overlay: reference stem activity for testing the M3b stages, not the M3a stage"]}
    from mvh.contract.events import dumps_events, dumps_json, make_envelope

    (dst / "events").mkdir(exist_ok=True)
    events.sort(key=lambda it: (it["t"], it["stem"]))
    for name in SPECTRAL_PLACEHOLDER_EVENTS:
        q = dst / "events" / f"{name}.json"
        if not q.exists():
            sp = dict(prov, stage="spectral", notes=["builder-m3b overlay: EMPTY placeholder (real adapter is partial)"])
            q.write_text(dumps_events(make_envelope(name, [], sp)), encoding="utf-8", newline="\n")
    for p in (dst / "events/stem_activity.json", dst / "meta/stems.json"):
        if p.exists():
            p.unlink()
    (dst / "events/stem_activity.json").write_text(dumps_events(make_envelope("stem_activity", events, prov)),
                                                   encoding="utf-8", newline="\n")
    (dst / "meta/stems.json").write_text(dumps_json({"stems": stems_meta, "thresholds": {
        "active_db": ACTIVE_DB, "within_db": WITHIN_DB, "attack_ms": ATTACK_S * 1000, "release_ms": RELEASE_S * 1000}}),
        encoding="utf-8", newline="\n")
    with open(dst / "m3b_overlay.json", "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"source": str(src), "stems": sorted(rms), "n_frames": n_frames}, fh, indent=1)
    log(f"{slug}: overlay at {dst}")
    return dst


if __name__ == "__main__":
    for s in sys.argv[1:] or ["megafauna", "versatile", "jeremy", "newton-vs-nye"]:
        build(s)
