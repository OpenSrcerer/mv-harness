# ruff: noqa: E501  (long catalogue tables / docstrings)
"""Generate src/mvh/assets/golden/addendum-vectors.json: golden cases for the lib-only helpers.

    python tests/unit/lib/make_addendum.py           # write
    python tests/unit/lib/make_addendum.py --check   # exit 1 if out of date

The core golden vectors (docs/contract/golden-vectors.json) come from mvh.contract.conventions.
vizState, the lyricAt singer join, the meaningAt merge, the NaN fill of textureData and the
spectrumWindow bytes have no reference function there, so this generator computes their expected
values from first principles (conventions.py primitives plus the rules written in
docs/contract/golden-addendum.md), independently of lib/mvh.js and lib/mvh_load.py. Both loaders
must reproduce every case within 1e-6 (ints, bools, ids and nulls exactly). Inputs are inline and
synthetic (no song data, no lyric text).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

from mvh.contract import conventions as cv
from mvh.contract.catalog import CONTRACT_VERSION

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "src" / "mvh" / "assets" / "golden" / "addendum-vectors.json"
NAN = float("nan")
N = 120  # 1.2 s at 100 Hz
DURATION = 1.2

# viz/js/audio.js constants (see docs/contract/golden-addendum.md)
BEAT_DECAY_S, PULSE_DECAY_S, PEAK_FALL_PER_S = 0.3, 0.11, 0.45
BEAT_MIN, PULSE_MIN, PEAK_WINDOW_S, BEAT_WINDOW_S = 0.55, 0.6, 2.25, 10.0

POLICY = {
    "bands.bass_viz": "mean",
    "bands.mid_viz": "mean",
    "bands.high_viz": "mean",
    "bands.level": "mean",
    "hits.kick": "max",
    "hits.kick_raw": "max",
    "hits.mid": "max",
    "hits.high": "max",
    "tempo.bpm": "linear",
    "vocal.f0_hz": "linear",
    "vocal.midi": "linear",
    "vocal.pitch01": "linear",
    "vocal.voiced": "max",
    "vocal.conf": "mean",
    "vocal.mouth_open": "max",
}
FILE = {k: ("vocal" if k.startswith("vocal.") else "core") for k in POLICY}


def f32(x: float) -> float:
    return float(np.float32(x))


def inputs() -> dict:
    i = np.arange(N)
    t = i / 100.0
    ch = {
        "bands.bass_viz": 0.4 + 0.3 * np.sin(t * 9.1),
        "bands.mid_viz": 0.35 + 0.2 * np.cos(t * 7.3),
        "bands.high_viz": 0.3 + 0.25 * np.sin(t * 13.7 + 1),
        "bands.level": 0.5 + 0.2 * np.sin(t * 3.1),
        "hits.kick": np.where(i % 40 < 3, 1.3, np.exp(-(i % 40) / 12.0) * 0.9),  # > 1: vizState clamps to 1
        "hits.kick_raw": np.where(i % 40 < 3, 0.95, 0.0),
        "hits.mid": np.abs(np.sin(t * 11)) ** 3,
        "hits.high": np.abs(np.cos(t * 17)) ** 5,
        "tempo.bpm": 120 + 3 * np.sin(t * 2),
    }
    midi = 60 + 4 * np.sin(t * 5)
    gap = (t >= 0.3) & (t < 0.55) | (t >= 1.05)
    midi = np.where(gap, NAN, midi)
    ch.update(
        {
            "vocal.midi": midi,
            "vocal.f0_hz": np.where(gap, NAN, 440 * 2 ** ((midi - 69) / 12)),
            "vocal.voiced": (~gap).astype(float),
            "vocal.pitch01": np.clip((np.where(gap, 60, midi) - 56) / 8, 0, 1),
            "vocal.conf": np.where(gap, 0.1, 0.9),
            "vocal.mouth_open": np.where((t >= 0.1) & (t < 0.9), 0.5 + 0.5 * np.sin(t * 40), 0),
        }
    )
    channels = {k: [None if math.isnan(x) else f32(x) for x in v] for k, v in ch.items()}
    k = np.arange(128)[None, :]
    spec = np.clip(
        np.round(128 + 110 * np.sin(t[:, None] * 6.0 + k * 0.13) * np.cos(k * 0.04 + t[:, None])), 0, 255
    ).astype(int)
    events = {
        "onsets.bass": [
            {"t": 0.05, "strength": 0.9},
            {"t": 0.3, "strength": 0.2},
            {"t": 0.31},
            {"t": 0.62, "strength": 0.5},
            {"t": 0.95, "strength": 1.0},
        ],
        "onsets.mid": [{"t": 0.12, "strength": 0.4}, {"t": 0.5, "strength": 0.0}, {"t": 0.83}],
        "onsets.high": [{"t": 0.2, "strength": 0.7}],
        "sections": [
            {"id": "S01", "t": 0.0, "d": 0.6},
            {"id": "S02", "t": 0.6, "d": 0.4},
            {"id": "S03", "t": 0.9, "d": 0.2},
        ],
        "singing": [
            {
                "t": 0.1,
                "d": 0.4,
                "character_id": "C2",
                "voice_id": "V2",
                "line_id": "L001",
                "lead_backing": "backing",
            },
            {
                "t": 0.1,
                "d": 0.4,
                "character_id": "C1",
                "voice_id": "V1",
                "line_id": "L001",
                "lead_backing": "lead",
            },
            {
                "t": 0.6,
                "d": 0.3,
                "character_id": "C1",
                "voice_id": "V1",
                "line_id": "L002",
                "lead_backing": "lead",
            },
        ],
    }
    lyrics = {
        "lines": [
            {"id": "L001", "t": 0.1, "d": 0.4, "text": "la la", "section_id": "S01"},
            {"id": "L002", "t": 0.6, "d": 0.3, "text": "na", "section_id": "S02"},
            {"id": "L003", "t": 1.0, "d": 0.1, "text": "oh", "section_id": "S03"},
        ],
        "words": [
            {"id": "L001.01", "line_id": "L001", "t": 0.1, "d": 0.15, "text": "la", "conf": 0.9},
            {"id": "L001.02", "line_id": "L001", "t": 0.3, "d": 0.2, "text": "la", "conf": 0.8},
            {"id": "L002.01", "line_id": "L002", "t": 0.6, "d": 0.3, "text": "na", "conf": 0.7},
        ],
    }
    meaning = {
        "status": "draft",
        "do_not": ["no logos", "no text"],
        "sections": [
            {
                "section_id": "S01",
                "t0": 0.0,
                "t1": 0.6,
                "feel": "calm",
                "meaning": "dawn",
                "emotion": {"lyric": "hope", "audio": "calm", "agree": True},
                "palette_hint": ["#102030"],
                "movement_hint": "slow",
                "camera_hint": "wide",
                "characters_present": ["C1", "C2"],
                "do_not": ["no text", "no faces"],
                "provenance": {"source": "user", "status": "user", "cites": []},
            },
            {
                "section_id": "S09",
                "t0": 0.9,
                "t1": 1.1,
                "feel": "loud",
                "meaning": None,
                "emotion": None,
                "palette_hint": [],
                "movement_hint": None,
                "camera_hint": None,
                "characters_present": [],
                "do_not": [],
                "provenance": None,
            },
        ],
    }
    return {
        "duration_s": DURATION,
        "rate_hz": 100,
        "policy": POLICY,
        "file": FILE,
        "channels": channels,
        "spectrum": spec.tolist(),
        "events": events,
        "lyrics": lyrics,
        "meaning": meaning,
    }


def _vals(inp, cid):
    return [NAN if x is None else x for x in inp["channels"][cid]]


def viz_expected(inp, t, fr) -> dict:
    r = cv.frame_rule(fr)
    n = cv.frame_of(t, r)
    tc = cv.frame_centre(n, r)

    def fv(cid):
        return cv.curve_frame(_vals(inp, cid), n, r, 100, POLICY[cid])

    out = {
        "frame": n,
        "t": tc,
        "bass": fv("bands.bass_viz"),
        "mid": fv("bands.mid_viz"),
        "high": fv("bands.high_viz"),
        "level": fv("bands.level"),
        "kick": min(1.0, max(0.0, fv("hits.kick"))),
        "kickRaw": min(1.0, max(0.0, fv("hits.kick_raw"))),
        "midHit": min(1.0, max(0.0, fv("hits.mid"))),
        "highHit": min(1.0, max(0.0, fv("hits.high"))),
        "bpm": fv("tempo.bpm"),
    }
    fired = lambda items: [it for it in items if cv.frame_of(it["t"], r) <= n]  # noqa: E731
    s01 = lambda it: min(1.0, max(0.0, 1.0 if it.get("strength") is None else it["strength"]))  # noqa: E731
    bass = fired(inp["events"]["onsets.bass"])
    out["beatCount"] = len(bass)
    out["onset"] = bool(bass) and cv.frame_of(bass[-1]["t"], r) == n
    out["beatPulse"] = math.exp(-max(0.0, tc - bass[-1]["t"]) / PULSE_DECAY_S) if bass else 0.0
    out["beat"] = max(
        [
            (BEAT_MIN + (1 - BEAT_MIN) * s01(it)) * math.exp(-max(0.0, tc - it["t"]) / BEAT_DECAY_S)
            for it in bass
            if tc - it["t"] <= BEAT_WINDOW_S
        ]
        or [0.0]
    )
    rb, ra = [-100.0] * 8, [0.0] * 8
    for j, it in enumerate(reversed(bass[-8:])):
        amp = BEAT_MIN + (1 - BEAT_MIN) * s01(it)
        a = max(
            cv.curve_at(_vals(inp, "hits.kick_raw"), it["t"]),
            cv.curve_at(_vals(inp, "hits.kick"), it["t"]),
            0.6 * amp,
        )
        rb[7 - j], ra[7 - j] = f32(it["t"]), f32(min(1.0, max(0.0, a)))
    out["recentBeats"], out["recentBeatAmp"] = rb, ra
    for band, pk, ok in (("mid", "midPulse", "midOnset"), ("high", "highPulse", "highOnset")):
        f = fired(inp["events"][f"onsets.{band}"])
        out[ok] = bool(f) and cv.frame_of(f[-1]["t"], r) == n
        out[pk] = (
            (PULSE_MIN + (1 - PULSE_MIN) * s01(f[-1])) * math.exp(-max(0.0, tc - f[-1]["t"]) / PULSE_DECAY_S)
            if f
            else 0.0
        )
    spec = inp["spectrum"]
    row = spec[min(N - 1, max(0, math.floor(tc * 100 + 0.5 + cv.EPS)))]
    bands = [f32(b / 255) for b in row]
    peaks = []
    rows = [j for j in cv.spectrum_rows(tc, PEAK_WINDOW_S, N) if j is not None]
    for k in range(128):
        p = bands[k]
        for j in rows:
            p = max(p, spec[j][k] / 255 - PEAK_FALL_PER_S * max(0.0, tc - j / 100))
        peaks.append(f32(min(1.0, max(0.0, p))))
    out["bands"], out["bandsRaw"], out["peaks"] = bands, bands, peaks
    out["bandBytes"] = [x for b in row for x in (b, b, b, 255)]
    out["waveBytes"] = [128] * 512
    return out


def lyric_expected(inp, t) -> dict:
    lines = inp["lyrics"]["lines"]
    r = cv.event_at(lines, t)
    if r is None:
        return {"line": None, "word": None, "progress": None, "word_progress": None}
    lid = r["item"]["id"]
    sung = [s for s in inp["events"]["singing"] if s["line_id"] == lid]
    sung = [s for s in sung if s["lead_backing"] == "lead"] + [s for s in sung if s["lead_backing"] != "lead"]
    line = dict(
        r["item"],
        singer=list(dict.fromkeys(s["character_id"] for s in sung)),
        voice_ids=list(dict.fromkeys(s["voice_id"] for s in sung)),
    )
    w = cv.event_at([x for x in inp["lyrics"]["words"] if x["line_id"] == lid], t)
    return {
        "line": line,
        "word": w["item"] if w else None,
        "progress": r["progress"],
        "word_progress": w["progress"] if w else None,
    }


def meaning_expected(inp, t) -> dict:
    M = inp["meaning"]
    sec = cv.event_at(inp["events"]["sections"], t)
    out = {
        "section_id": None,
        "meaning": None,
        "feel": None,
        "emotion": None,
        "palette_hint": [],
        "movement_hint": None,
        "camera_hint": None,
        "characters_present": [],
        "do_not": list(dict.fromkeys(M["do_not"])),
        "provenance": None,
        "status": M["status"],
    }
    if sec is None:
        return out
    sid = sec["item"]["id"]
    out["section_id"] = sid
    e = next((s for s in M["sections"] if s["section_id"] == sid), None) or next(
        (s for s in M["sections"] if s["t0"] <= t < s["t1"]), None
    )
    if e is None:
        return out
    out.update(
        {k: e[k] for k in ("meaning", "feel", "emotion", "movement_hint", "camera_hint", "provenance")}
    )
    out.update(
        {
            "palette_hint": e["palette_hint"],
            "characters_present": e["characters_present"],
            "do_not": list(dict.fromkeys(M["do_not"] + e["do_not"])),
        }
    )
    return out


def _r(x):
    if isinstance(x, float):
        return round(x, 9)
    if isinstance(x, dict):
        return {k: _r(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_r(v) for v in x]
    return x


def build() -> dict:
    inp = inputs()
    frs = [{"fps": 24}, {"fps": 60, "frame0": 1}, {"fps": [30000, 1001], "early": True}, {"fps": 23.976}]
    ts = [0.0, 0.04, 0.05, 0.3, 0.305, 0.31, 0.33, 0.5, 0.62, 0.7, 0.95, 1.0, 1.19]
    viz = [[t, fr, viz_expected(inp, t, fr)] for fr in frs for t in ts]
    viz += [[t, {"fps": 60}, viz_expected(inp, t, {"fps": 60})] for t in (0.05, 0.62, 0.9)]
    for k, (_, _, e) in enumerate(viz):  # keep the 128/512-long arrays in every 4th case only (file size)
        if k % 4:
            for key in ("bands", "bandsRaw", "peaks", "bandBytes", "waveBytes"):
                del e[key]
    lts = [0.0, 0.1, 0.2, 0.25, 0.3, 0.49, 0.5, 0.6, 0.95, 1.05, 1.1]
    nan_aware = [f32(cv.nan_aware_at(_vals(inp, "vocal.midi"), i)) for i in range(N)]
    width = 32
    tex = nan_aware + [nan_aware[-1]] * (math.ceil(N / width) * width - N)
    sw = [
        [
            t,
            s,
            [
                b
                for j in cv.spectrum_rows(t, s, N)
                for b in (inp["spectrum"][j] if j is not None else [0] * 128)
            ],
        ]
        for t, s in ((0.0, 0.0), (0.004, 0.02), (0.5, 0.05), (1.19, 0.03), (1.3, 0.2))
    ]
    g = {
        "contract_version": CONTRACT_VERSION,
        "tolerance": 1e-6,
        "notes": [
            "generated by tests/unit/lib/make_addendum.py; rules in docs/contract/golden-addendum.md",
            "viz_state cases are [t, fr, expected subset of fields]; the frame rule is mandatory (no default)",
            "channel values are float32; null = NaN (unvoiced)",
        ],
        "song": inp,
        "viz_state": viz,
        "lyric_at": [[t, lyric_expected(inp, t)] for t in lts],
        "meaning_at": [[t, meaning_expected(inp, t)] for t in (0.0, 0.59, 0.6, 0.95, 1.05, 1.15)],
        "texture_nan_fill": {
            "ids": ["vocal.midi"],
            "width": width,
            "height": math.ceil(N / width),
            "data": tex,
        },
        "spectrum_window": sw,
    }
    return _r(g)


def dumps(g: dict) -> str:
    return json.dumps(g, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    txt = dumps(build())
    if a.check:
        ok = OUT.exists() and OUT.read_text(encoding="utf-8") == txt
        print("addendum vectors " + ("up to date" if ok else "OUT OF DATE"))
        return 0 if ok else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(txt)
    print(f"wrote {OUT} ({len(txt)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
