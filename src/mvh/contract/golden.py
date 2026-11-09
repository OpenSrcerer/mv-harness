"""Golden-vector cases for the loaders (PLAN §7 helper parity / golden vectors).

    python -m mvh.contract.golden            # write docs/contract/golden-vectors.json
    python -m mvh.contract.golden --check    # exit 1 if the file is out of date

Every expected value is computed with ``mvh.contract.conventions`` (the reference). ``lib/mvh.js`` and
``lib/mvh_load.py`` must reproduce every case within 1e-6 (ints, bools, ids and nulls exactly).
The lib builder copies this file to ``src/mvh/assets/golden/`` and runs both loaders against it.
Inputs are inline and synthetic: no song data, no lyric text.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from . import conventions as cv
from .catalog import CONTRACT_VERSION

OUT = Path(__file__).resolve().parents[3] / "docs" / "contract" / "golden-vectors.json"

FPS = [23.976, [24000, 1001], 24, 25, 29.97, [30000, 1001], 30, 60]
FRAME0 = [0, 1]
EARLY = [False, True]
NAN = float("nan")


def _r(x):
    if isinstance(x, float):
        if math.isnan(x):
            return None
        return round(x, 9)
    if isinstance(x, dict):
        return {k: _r(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_r(v) for v in x]
    return x


def _fr(fps, frame0, early):
    return {"fps": fps, "frame0": frame0, "early": early}


# --------------------------------------------------------------------------------------------- inputs
def test_curve() -> list[float]:
    """60 samples (0.6 s at 100 Hz): a ramp-and-wiggle with one spike at i = 23 (a 'flash')."""
    v = [round(0.5 + 0.4 * math.sin(i * 0.7) * ((i % 7) / 7.0), 6) for i in range(60)]
    v[23] = 1.0
    v[24] = 1.0      # flash rule: peak held at floor and ceil of the event time 0.2337 s
    return v


FLASH_EVENT_T = 0.2337


def pitch_curve() -> list[float]:
    """MIDI curve with an unvoiced gap (NaN) at samples 5..9 and a trailing unvoiced tail from 16 on."""
    v = [60.0, 60.5, 61.0, 61.5, 62.0, NAN, NAN, NAN, NAN, NAN, 64.0, 64.5, 65.0, 65.0, 64.0, 63.0, NAN, NAN, NAN, NAN]
    return v


def beats_pickup() -> list[dict]:
    """4/4 at 120 BPM with a one-beat pickup: beat 0 is bar 0 beat 4; bar 1 starts at t = 0.75.
    Beats 0..20 every 0.5 s from t = 0.25; beats 13..14 are virtual (in_pulse false)."""
    out = []
    for i in range(21):
        k = i - 1                     # beats after the pickup
        bar = 0 if i == 0 else k // 4 + 1
        bib = 4 if i == 0 else k % 4 + 1
        out.append({"beat_index": i, "t": round(0.25 + 0.5 * i, 6), "bar": bar, "beat_in_bar": bib, "beats_in_bar": 4,
                    "in_pulse": i not in (13, 14), "strength": 0.8, "conf": 0.9})
    return out


def counts_odd_section(beats) -> list[dict]:
    """Section A = bars 1-5 (5 bars, odd length: 8 + 8 + 4-count partial), section B from bar 6.
    E000 lead-in = 4 beats before E001 (starts at beat -3, i.e. one virtual beat before the song's first beat)."""
    def t_of(b):
        return round(0.25 + 0.5 * b, 6)
    items = [
        {"id": "E000", "start_beat": -3, "len": 4, "first_count": 5, "partial": True, "lead_in": True, "phrase_id": None,
         "section_id": None, "in_pulse": False, "accents": [0.2, 0.2, 0.3, 0.6]},
        {"id": "E001", "start_beat": 1, "len": 8, "first_count": 1, "partial": False, "lead_in": False, "phrase_id": "P01",
         "section_id": "S01", "in_pulse": True, "accents": [1.0, 0.2, 0.5, 0.2, 0.8, 0.2, 0.5, 0.2]},
        {"id": "E002", "start_beat": 9, "len": 8, "first_count": 1, "partial": False, "lead_in": False, "phrase_id": "P01",
         "section_id": "S01", "in_pulse": False, "accents": [1.0, 0.2, 0.5, 0.2, 0.8, 0.2, 0.5, 0.2]},
        {"id": "E003", "start_beat": 17, "len": 4, "first_count": 1, "partial": True, "lead_in": False, "phrase_id": "P02",
         "section_id": "S01", "in_pulse": True, "accents": [0.9, 0.1, 0.4, 0.1]},
        {"id": "E004", "start_beat": 21, "len": 8, "first_count": 1, "partial": False, "lead_in": False, "phrase_id": "P03",
         "section_id": "S02", "in_pulse": False, "accents": [1.0, 0.2, 0.5, 0.2, 0.8, 0.2, 0.5, 0.2]},
    ]
    for it in items:
        it["t"] = t_of(it["start_beat"])
        it["d"] = round(0.5 * it["len"], 6)
    return items


def segments() -> list[dict]:
    return [{"id": "S01", "t": 0.0, "d": 2.0}, {"id": "S02", "t": 2.0, "d": 1.5},
            {"id": "S03", "t": 3.0, "d": 1.0},            # overlaps S02 (latest start wins)
            {"id": "S04", "t": 5.0, "d": 1.0}]            # gap 4.0..5.0


def cues() -> list[dict]:
    return [{"id": "Q0001", "t": 0.0, "tier": 1}, {"id": "Q0002", "t": 0.5, "tier": 4}, {"id": "Q0003", "t": 1.0, "tier": 2},
            {"id": "Q0004", "t": 1.0, "tier": 3}, {"id": "Q0005", "t": 1.5, "tier": 4}, {"id": "Q0006", "t": 2.0, "tier": 1},
            {"id": "Q0007", "t": 2.0416, "tier": 3}]


def singing() -> list[dict]:
    """Three voices: V1 lead, V2 lead entering in a duet overlap, V3 backing under V2 (call and response)."""
    return [
        {"t": 0.5, "d": 1.5, "character_id": "C1", "voice_id": "V1", "line_id": "L001", "lead_backing": "lead"},
        {"t": 1.75, "d": 1.25, "character_id": "C2", "voice_id": "V2", "line_id": "L002", "lead_backing": "lead"},
        {"t": 2.25, "d": 0.5, "character_id": "C3", "voice_id": "V3", "line_id": "L003", "lead_backing": "backing"},
        {"t": 3.5, "d": 0.5, "character_id": "C1", "voice_id": "V1", "line_id": "L004", "lead_backing": "lead"},
    ]


def mouth_curves() -> dict[str, list[float]]:
    n = 450
    return {
        "vocal.mouth_open.V1": [round(0.5 + 0.5 * math.sin(i * 0.31), 6) if (50 <= i < 200 or 350 <= i < 400) else 0.0 for i in range(n)],
        "vocal.mouth_open.V2": [round(0.5 + 0.5 * math.sin(i * 0.23 + 1), 6) if 175 <= i < 300 else 0.0 for i in range(n)],
        "vocal.mouth_open.V3": [round(0.4 + 0.4 * math.cos(i * 0.17), 6) if 225 <= i < 275 else 0.0 for i in range(n)],
    }


def _mouth(curves):
    def f(voice, t):
        key = f"vocal.mouth_open.{voice}" if voice and f"vocal.mouth_open.{voice}" in curves else "vocal.mouth_open"
        return cv.curve_at(curves[key], t, 100, "max")
    return f


# --------------------------------------------------------------------------------------------- cases
def build() -> dict:
    g: dict = {"contract_version": CONTRACT_VERSION, "tolerance": 1e-6, "notes": [
        "fps is a number or [num, den]; numbers are literal (23.976 != 24000/1001)",
        "null in an expected value means null/None (NaN never appears in helper outputs)",
        "every curve is at 100 Hz unless 'rate' is given; sample i is centred at i / rate"]}

    # 1. frame conversions -------------------------------------------------------------------------
    ts = [0.0, 0.004, 0.0208, 0.020833333, 0.02086, 0.5, 1.0, 1.0010, 1.0427, 9.999, 10.0, 316.587]
    frames = []
    for fps in FPS:
        for f0 in FRAME0:
            for early in EARLY:
                fr = _fr(fps, f0, early)
                ns = [f0, f0 + 1, f0 + 23, f0 + 24, f0 + 239, f0 + 7589]
                frames.append({
                    "fr": fr,
                    "time_of": [[n, cv.time_of(n, fr)] for n in ns],
                    "frame_centre": [[n, cv.frame_centre(n, fr)] for n in ns],
                    "frame_window": [[n, list(cv.frame_window(n, fr))] for n in ns[:3]],
                    "frame_of": [[t, cv.frame_of(t, fr)] for t in ts],
                    "roundtrip": [[n, cv.frame_of(cv.time_of(n, fr), fr)] for n in ns],
                    "frame_count": [[d, cv.frame_count(d, fr)] for d in (10.0, 170.43, 316.587)],
                })
    g["frames"] = frames

    # 2. curve sampling under the four policies ------------------------------------------------------
    v = test_curve()
    pol = []
    for fps in FPS:
        for f0 in FRAME0:
            for early in EARLY:
                fr = _fr(fps, f0, early)
                cnt = cv.frame_count(len(v) / 100, fr)
                ns = list(range(f0, f0 + cnt))
                pol.append({"fr": fr, "frames": {p: [[n, cv.curve_frame(v, n, fr, 100, p)] for n in ns] for p in cv.POLICIES},
                            "samples_in_frame": [[n, [r.start, r.stop]] for n in ns
                                                 for r in [cv.samples_in_frame(n, fr, 100, len(v))]]})
    ats = [-0.1, 0.0, 0.004, 0.005, 0.0051, 0.123, 0.2299, 0.2337, 0.595, 0.599, 0.7]
    g["curve"] = {"values": v, "rate": 100,
                  "at": {p: [[t, cv.curve_at(v, t, 100, p)] for t in ats] for p in cv.POLICIES},
                  "frame": pol}

    # 3. flash rule: the event and its max-pooled flash land on the same frame ------------------------
    flash = []
    for fps in FPS:
        for f0 in FRAME0:
            for early in EARLY:
                fr = _fr(fps, f0, early)
                n = cv.frame_of(FLASH_EVENT_T, fr)
                flash.append({"fr": fr, "event_frame": n, "max_at_event_frame": cv.curve_frame(v, n, fr, 100, "max")})
    g["flash"] = {"event_t": FLASH_EVENT_T, "flash_samples": list(cv.flash_samples(FLASH_EVENT_T)), "cases": flash}

    # 4. voiced/unvoiced boundary ----------------------------------------------------------------------
    m = pitch_curve()
    voiced = [0.0 if math.isnan(x) else 1.0 for x in m]
    hz = [NAN if math.isnan(x) else 440.0 * 2 ** ((x - 69) / 12) for x in m]
    pitch01 = [0.2, 0.25, 0.3, 0.35, 0.4, 0.42, 0.44, 0.46, 0.48, 0.5, 0.8, 0.85, 0.9, 0.9, 0.8, 0.7, 0.7, 0.7, 0.7, 0.7]
    conf = [0.9] * 5 + [0.1] * 5 + [0.95] * 6 + [0.05] * 4
    ch = {"vocal.midi": m, "vocal.f0_hz": hz, "vocal.voiced": voiced, "vocal.pitch01": pitch01, "vocal.conf": conf}
    phrases = [{"id": "VP001", "t": 0.0, "d": 0.05}, {"id": "VP002", "t": 0.1, "d": 0.06}]
    vnotes = [{"t": 0.0, "d": 0.05, "midi": 61, "name": "C#4", "vel": 0.7, "conf": 0.8},
              {"t": 0.1, "d": 0.06, "midi": 64, "name": "E4", "vel": 0.8, "conf": 0.9}]
    vts = [0.0, 0.015, 0.04, 0.044, 0.045, 0.046, 0.07, 0.094, 0.095, 0.0951, 0.105, 0.155, 0.16, 0.19, 0.25]
    vfr = []
    for fps in (24, 60):
        fr = _fr(fps, 0, False)
        cnt = cv.frame_count(len(m) / 100, fr)
        vfr.append({"fr": fr, "frames": {p: [[n, cv.curve_frame(m, n, fr, 100, p, nan_aware=True)] for n in range(cnt)]
                                         for p in cv.POLICIES}})
    g["voicing"] = {"channels": {k: [None if (isinstance(x, float) and math.isnan(x)) else x for x in vals] for k, vals in ch.items()},
                    "phrases": phrases, "notes": vnotes,
                    "midi_at": [[t, cv.curve_at(m, t, 100, "linear", nan_aware=True)] for t in vts],
                    "vocal_at": [[t, cv.vocal_at(t, ch, 100, phrases, vnotes)] for t in vts],
                    "frames": vfr}

    # 5. beats with a pickup bar, odd-length section, counts ----------------------------------------
    beats = beats_pickup()
    counts = counts_odd_section(beats)
    bts = [-0.5, 0.0, 0.1, 0.25, 0.5, 0.75, 0.8125, 1.0, 2.6, 4.75, 6.6, 7.0, 8.75, 9.0, 10.25, 10.26, 10.75, 11.0]
    g["beats"] = {"beats": beats, "counts": counts,
                  "beat_pos": [[t, cv.beat_pos(t, beats)] for t in bts],
                  "beat_phase": [[t, cv.beat_phase(t, beats)] for t in bts],
                  "bar_phase": [[t, cv.bar_phase(t, beats)] for t in bts],
                  "count": [[t, cv.count_at(t, beats, counts)] for t in bts],
                  "no_beats": [[t, cv.beat_pos(t, [])] for t in (0.0, 0.75)],
                  "osc": [[t, {s: cv.osc(t, beats, s, pb, ph) for s in ("sine", "saw", "square", "triangle")}, pb, ph]
                          for t in (0.25, 0.5, 0.875, 2.6) for pb, ph in ((1.0, 0.0), (4.0, 0.25))]}

    # 6. events ---------------------------------------------------------------------------------------
    seg = segments()
    q = cues()
    ets = [-1.0, 0.0, 1.0, 1.99, 2.0, 2.9, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0]
    g["events"] = {
        "segments": seg, "cues": q,
        "at": [[t, (lambda r: None if r is None else {"id": r["item"]["id"], "progress": r["progress"], "t_in": r["t_in"],
                                                     "t_left": r["t_left"]})(cv.event_at(seg, t))] for t in ets],
        "next": [[t, mt, (lambda r: r and r["id"])(cv.event_next(q, t, mt))] for t in (-1.0, 0.0, 0.5, 1.0, 1.9, 2.0)
                 for mt in (None, 2, 3)],
        "prev": [[t, mt, (lambda r: r and r["id"])(cv.event_prev(q, t, mt))] for t in (-1.0, 0.0, 0.49, 1.0, 1.9, 2.5)
                 for mt in (None, 2)],
        "all_at": [[t, [it["id"] for it in cv.event_all_at(seg, t)]] for t in ets],
        "between": [[a, b, [it["id"] for it in cv.event_between(q, a, b)]] for a, b in ((0.0, 1.0), (1.0, 2.0), (0.5, 0.5), (1.0, 2.05))],
        "in_frame": [[fr, n, [it["id"] for it in cv.event_in_frame(q, n, fr)]]
                     for fr in (_fr(24, 0, False), _fr(24, 0, True), _fr(60, 1, False)) for n in range(0, 4)]
                    + [[_fr(24, 0, False), 49, [it["id"] for it in cv.event_in_frame(q, 49, _fr(24, 0, False))]],
                       [_fr(24, 0, True), 48, [it["id"] for it in cv.event_in_frame(q, 48, _fr(24, 0, True))]],
                       [_fr(24, 0, True), 49, [it["id"] for it in cv.event_in_frame(q, 49, _fr(24, 0, True))]]],
    }
    hits = [{"t": 0.5, "strength": 0.8}, {"t": 1.0}, {"t": 1.1, "strength": 0.5}]
    g["pulse"] = {"items": hits, "beats": "beats.beats", "cases": [
        [t, kw, cv.pulse(t, hits, beats, **kw)]
        for t in (0.4, 0.5, 0.55, 0.75, 0.99, 1.0, 1.05, 1.2, 2.0)
        for kw in ({}, {"attack": 0.1, "decay": 0.2, "shape": "linear"}, {"decay": 0.5, "unit": "beats", "shape": "smooth"})]}

    # 7. singerAt with three voices --------------------------------------------------------------------
    sg = singing()
    mc = mouth_curves()
    g["singer_at"] = {"singing": sg, "mouth_open": mc, "rate": 100,
                      "cases": [[t, cv.singer_at(t, sg, _mouth(mc))] for t in (0.4, 0.5, 1.0, 1.75, 2.0, 2.3, 2.75, 3.0, 3.6, 4.0)]}

    # 8. wrapped textures --------------------------------------------------------------------------------
    a = [round(math.sin(i * 0.013) * 0.5 + 0.5, 6) for i in range(2500)]
    b = [round((i % 100) / 100.0, 6) for i in range(1100)]
    data, height, lay = cv.texture_data([a, b], width=1024)
    tts = [0.0, 5.0, 10.229, 10.235, 10.2399, 20.475, 24.99, 30.0]
    g["texture"] = {"width": 1024, "height": height, "layout": lay,
                    "channels": {"a": {"n": len(a), "formula": "round(sin(i*0.013)*0.5+0.5, 6)"},
                                 "b": {"n": len(b), "formula": "round((i % 100)/100, 6)"}},
                    "texels": [[c, i, data[(lay[c]["row0"] + i // 1024) * 1024 + i % 1024]]
                               for c, i in ((0, 1023), (0, 1024), (0, 2499), (0, 2500), (0, 3071), (1, 0), (1, 1099), (1, 2047))],
                    "sample": [[c, t, cv.texture_sample(data, lay[c], t), cv.curve_at([a, b][c], t)] for c in (0, 1) for t in tts]}
    g["spectrum_rows"] = {"n_frames": 500, "cases": [[t, s, cv.spectrum_rows(t, s, 500)]
                                                     for t, s in ((0.0, 0.0), (0.0, 0.03), (1.234, 0.05), (4.995, 0.02), (5.2, 0.02))]}
    return _r(g)


MD = OUT.with_name("golden-spec.md")


def _j(x) -> str:
    return "`" + json.dumps(x, ensure_ascii=False, separators=(", ", ": ")) + "`"


def _fmt_fr(fr) -> str:
    return f"{json.dumps(fr['fps'])} fps, frame0={fr['frame0']}, {'early' if fr['early'] else 'centred'}"


def render_md(g: dict) -> str:
    L: list[str] = []
    a = L.append
    a("# Golden-vector spec (contract v" + g["contract_version"] + ")\n")
    a("Generated by `python -m mvh.contract.golden` from `src/mvh/contract/conventions.py` (the reference). **Do not edit by hand.**")
    a("The complete machine-readable set is [`golden-vectors.json`](golden-vectors.json); this page lists every case group with its")
    a("inputs and a representative slice of expected outputs. `lib/mvh.js` and `lib/mvh_load.py` must match **every** value in the JSON")
    a(f"within {g['tolerance']} (integers, booleans, ids and nulls exactly). Inputs are synthetic; there is no song data and no lyric text.\n")
    a("Coverage required by PLAN §7: fps 23.976, 24, 25, 29.97, 30, 60 (plus the exact NTSC rationals [24000,1001] and [30000,1001]);")
    a("frame0 0 and 1; centred and early rules; all four policies; a voiced/unvoiced boundary; a pickup bar; an odd-length section;")
    a("wrapped-texture sampling; events.at/next/prev (+ allAt, between, inFrame); count(t); singerAt with 3 voices. Extra: pulse, osc, spectrum rows.\n")

    a("## 1. Frame conversions (`frames`)\n")
    a("Inputs: for every `fr` = {fps, frame0, early}: frame numbers n and times t. Expected: `time_of`, `frame_centre`, `frame_window`,")
    a("`frame_of`, the round trip `frame_of(time_of(n)) == n`, and `frame_count(duration)`.\n")
    a("| fr | frame_of(t) for t = 0.0208, 0.02086, 1.0, 1.0427, 316.587 | time_of(frame0+24) | frame_count(316.587) |")
    a("|---|---|---|---|")
    for c in g["frames"]:
        fo = dict((t, n) for t, n in c["frame_of"])
        to = dict((n, t) for n, t in c["time_of"])
        fc = dict((d, n) for d, n in c["frame_count"])
        a(f"| {_fmt_fr(c['fr'])} | {fo[0.0208]}, {fo[0.02086]}, {fo[1.0]}, {fo[1.0427]}, {fo[316.587]} | "
          f"{to[c['fr']['frame0'] + 24]} | {fc[316.587]} |")
    a("")

    a("## 2. Curve sampling, all four policies (`curve`)\n")
    a("Input: a 60-sample curve at 100 Hz (`curve.values`, spike 1.0 at samples 23 and 24). `curve.at` gives point values per policy;")
    a("`curve.frame` gives `curve_frame(v, n, fr, policy)` for every frame of the curve under every fr, plus `samples_in_frame` (start, stop).\n")
    a("Point values `at(t)`:\n")
    a("| t | " + " | ".join(g["curve"]["at"].keys()) + " |")
    a("|---|" + "---|" * len(g["curve"]["at"]) )
    ats = [t for t, _ in g["curve"]["at"]["linear"]]
    for i, t in enumerate(ats):
        a(f"| {t} | " + " | ".join(str(g["curve"]["at"][p][i][1]) for p in g["curve"]["at"]) + " |")
    a("")
    for c in g["curve"]["frame"]:
        if c["fr"]["fps"] in (24, 60) and c["fr"]["frame0"] == 0:
            a(f"Frames 0..5 at {_fmt_fr(c['fr'])}:\n")
            a("| n | samples | " + " | ".join(c["frames"].keys()) + " |")
            a("|---|---|" + "---|" * len(c["frames"]))
            for k in range(6):
                s = c["samples_in_frame"][k][1]
                a(f"| {k} | [{s[0]}, {s[1]}) | " + " | ".join(str(c["frames"][p][k][1]) for p in c["frames"]) + " |")
            a("")

    a("## 3. Flash rule (`flash`)\n")
    f = g["flash"]
    a(f"An event at t = {f['event_t']} s; its envelope holds the peak (1.0) at samples {f['flash_samples']} (floor and ceil of t*100).")
    a("For every fr, the `max` value of the event's frame (`frame_of(t)`) is the peak: the flash and the event share a frame.\n")
    a("| fr | event frame | max at that frame |")
    a("|---|---|---|")
    for c in f["cases"]:
        a(f"| {_fmt_fr(c['fr'])} | {c['event_frame']} | {c['max_at_event_frame']} |")
    a("")

    a("## 4. Voiced / unvoiced boundary (`voicing`)\n")
    a("Input channels (20 samples at 100 Hz): " + _j(g["voicing"]["channels"]["vocal.midi"]) + " (`null` = NaN = unvoiced),")
    a("with `vocal.f0_hz`, `vocal.voiced`, `vocal.pitch01`, `vocal.conf`, vocal phrases and vocal notes (see JSON).")
    a("Rules: both neighbours voiced -> lerp; else nearest sample if voiced; else hold the last voiced value (else the first voiced after).\n")
    a("| t | midi at(t) | vocalAt(t) |")
    a("|---|---|---|")
    va = dict((t, r) for t, r in g["voicing"]["vocal_at"])
    for t, mval in g["voicing"]["midi_at"]:
        r = va[t]
        a(f"| {t} | {mval} | voiced={r['voiced']}, midi={r['midi']}, hz={r['hz']}, pitch01={r['pitch01']}, phrase={r['phrase_id']}, "
          f"note={r['note']['midi'] if r['note'] else None} |")
    a("\nFrame values with `nan_aware` resampling (mean/max use voiced samples only) are in `voicing.frames` (24 and 60 fps).\n")

    a("## 5. Beats, pickup bar, odd-length section, count(t) (`beats`)\n")
    a("Input: 21 beats every 0.5 s from t = 0.25 (4/4); beat 0 is a one-beat pickup (bar 0, beat_in_bar 4); bar 1 starts at 0.75;")
    a("beats 13 and 14 are virtual (`in_pulse` false). Counts: E000 lead-in (start_beat -3, counts 5-8), E001 and E002 (8 each),")
    a("E003 a 4-beat partial count (section S01 = 5 bars, an odd length), E004 starts section S02 at beat 21 (beyond the last beat).\n")
    a("| t | beat_pos | bar_phase | count(t) |")
    a("|---|---|---|---|")
    bp = dict((t, r) for t, r in g["beats"]["bar_phase"])
    ct = dict((t, r) for t, r in g["beats"]["count"])
    for t, r in g["beats"]["beat_pos"]:
        c = ct[t]
        a(f"| {t} | {r['value']} ({'in' if r['in_pulse'] else 'off'} pulse) | {bp[t]['value']} | "
          f"{c['eight_id']} count {c['count']} sub {c['sub']} phase {c['phase']} accent {c['accent']}"
          f"{' partial' if c['partial'] else ''}{' lead-in' if c['lead_in'] else ''} |")
    a("\n`beats.no_beats`: with no beats the grid is 120 BPM from t = 0. `beats.osc`: osc(t) for four shapes, two (periodBeats, phase) pairs.\n")

    a("## 6. Events (`events`, `pulse`)\n")
    a("Segments " + _j(g["events"]["segments"]) + " (S03 overlaps S02: the latest start wins; 4.0-5.0 is a gap).\n")
    a("| t | at(t) |")
    a("|---|---|")
    for t, r in g["events"]["at"]:
        a(f"| {t} | {'null' if r is None else r['id'] + ' progress ' + str(r['progress']) + ' t_in ' + str(r['t_in']) + ' t_left ' + str(r['t_left'])} |")
    a("\nCues (with tiers) " + _j(g["events"]["cues"]) + ":\n")
    a("| t | minTier | next | prev |")
    a("|---|---|---|---|")
    pv = {(t, mt): r for t, mt, r in g["events"]["prev"]}
    for t, mt, r in g["events"]["next"]:
        a(f"| {t} | {mt} | {r} | {pv.get((t, mt), '(see JSON)')} |")
    a("\n`between(t0, t1)` is half-open [t0, t1): " + "; ".join(f"[{x}, {y}) -> {ids}" for x, y, ids in g["events"]["between"]) + ".\n")
    a("`allAt(t)` returns every segment containing t, in file order (the segments overlap at 3.0..3.5): " + "; ".join(f"{t} -> {ids}" for t, ids in g["events"]["all_at"]) + ".\n")
    a("`inFrame(n, fr)` uses `frame_of(item.t) == n`: " + "; ".join(
        f"{_fmt_fr(fr)} n={n} -> {ids}" for fr, n, ids in g["events"]["in_frame"] if ids) + ".\n")
    a("`pulse`: items " + _j(g["pulse"]["items"]) + "; cases are [t, options, value] (defaults attack 0, decay 0.25 s, exp shape).\n")

    a("## 7. singerAt with three voices (`singer_at`)\n")
    a("Input: " + _j(g["singer_at"]["singing"]) + " and per-voice `vocal.mouth_open.V1..V3` curves (450 samples, in the JSON).\n")
    a("| t | singerAt(t) -> [voice (lead/backing) line mouth_open] |")
    a("|---|---|")
    for t, r in g["singer_at"]["cases"]:
        a(f"| {t} | " + ("[]" if not r else "; ".join(f"{x['voice_id']}/{x['character_id']} ({x['lead_backing']}) {x['line_id']} {x['mouth_open']}" for x in r)) + " |")
    a("")

    a("## 8. Wrapped textures (`texture`)\n")
    tx = g["texture"]
    a(f"Two channels (a: n = {tx['channels']['a']['n']}, b: n = {tx['channels']['b']['n']}) wrapped at width {tx['width']} -> height {tx['height']};")
    a("layout " + _j(tx["layout"]) + ". Padding repeats the last value. `texels` lists [channel, i, texel value];")
    a("`sample` lists [channel, t, mvhCurve value, curve.at value] - the two must be equal (t = 10.235 interpolates across the row wrap).\n")
    a("| channel | t | texture sample | curve.at |")
    a("|---|---|---|---|")
    for c, t, s1, s2 in tx["sample"]:
        a(f"| {c} | {t} | {s1} | {s2} |")
    a("")
    a("## 9. Spectrum rows (`spectrum_rows`)\n")
    a("[t, s, row indices] for spectrumWindow(t, s) on a 500-row spectrum (null = outside, returned as zero bytes): " +
      "; ".join(f"({t}, {s}) -> {r}" for t, s, r in g["spectrum_rows"]["cases"]) + ".\n")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    g = build()
    txt = json.dumps(g, ensure_ascii=False, indent=None, separators=(",", ":"), allow_nan=False) + "\n"
    md = render_md(g)
    if a.check:
        ok = OUT.exists() and OUT.read_text(encoding="utf-8") == txt and MD.exists() and MD.read_text(encoding="utf-8") == md
        print("golden vectors " + ("up to date" if ok else "OUT OF DATE"))
        return 0 if ok else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    for p, s in ((OUT, txt), (MD, md)):
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(s)
    print(f"wrote {OUT} ({len(txt)} bytes) and {MD.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
