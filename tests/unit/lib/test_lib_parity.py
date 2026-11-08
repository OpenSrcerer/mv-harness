"""JS (lib/mvh.js) vs Python (lib/mvh_load.py) parity on whole song folders, within 1e-6.

Covers 23.976, 24, 25, 29.97, 30 and 60 fps (plus [24000, 1001] and [30000, 1001]), frame0 0 and 1,
centred and early, all four policies, NaN-aware pitch, 1 Hz curves, every helper on a dense time grid,
textures and vizState. The song folder is built in a temp dir with the contract writers
(lib_synth_song.py); when the fixtures builder has finished tests/contract/synth/ (.done.json present),
the same checks also run on it.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path

import lib_synth_song
import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[3]
DUMP_JS = Path(__file__).with_name("parity_dump.mjs")
SYNTH = REPO / "tests" / "contract" / "synth"
TOL = 1e-6

FPS = [23.976, [24000, 1001], 24, 25, 29.97, [30000, 1001], 30, 60]
FRAME_RULES = [{"fps": f, "frame0": f0, "early": e} for f in FPS for f0 in (0, 1) for e in (False, True)]


def make_spec(song) -> dict:
    dur = song.duration
    step = max(0.0173, round((dur + 1.0) / 700, 4))  # about 700 grid times for any song length
    times = [round(-0.5 + step * k, 9) for k in range(int((dur + 1.0) / step) + 1)]
    special = [0.0, 1 / 48, 0.020833333, 0.0208, dur - 1e-6, dur, 1.0, 1.37, 3.0, 3.005, 5.5]
    for name in ("beats", "sections", "cues", "onsets.bass", "singing", "counts"):
        for it in song.events(name).items[:40]:
            special += [float(it["t"]), float(it["t"]) - 1e-7, float(it["t"]) + 1e-7]
            if it.get("d"):
                special.append(float(it["t"]) + float(it["d"]))
    times = sorted(set(times + [round(x, 9) for x in special]))
    ids = song.channel_ids
    pick = [
        c
        for c in (
            "hits.kick",
            "bands.bass",
            "bands.bass_viz",
            "tempo.bpm",
            "rhythm.in_pulse",
            "choreo.accent",
            "vocal.midi",
            "vocal.f0_hz",
            "vocal.voiced",
            "vocal.conf",
            "vocal.pitch01",
            "vocal.mouth_open",
            "mood.valence",
            "stem.vocals.active",
            "stem.drums.level",
        )
        if c in ids
    ]
    float_ids = [c for c in ids if c != "spectrum128"]
    events = sorted(
        set(song.event_names) | {"beats", "counts", "sections", "cues", "singing", "visemes", "not.a.file"}
    )
    tex_ids = [
        c for c in ("hits.kick", "vocal.midi", "rhythm.in_pulse", "mood.valence") if c in ids
    ] or float_ids[:2]
    return {
        "times": times,
        "frame_rules": FRAME_RULES,
        "curve_ids": float_ids,
        "frame_curve_ids": pick,
        "event_names": events,
        "tiers": [None, 1, 2, 3],
        "in_frame_events": ["cues", "onsets.bass"],
        "pulse": [
            ["onsets.bass", {}],
            ["hits.kick", {"attack": 0.05, "decay": 0.2, "shape": "linear"}],
            ["onsets.mid", {"decay": 0.5, "unit": "beats", "shape": "smooth"}],
            ["cues", {"decay": 1.0}],
            ["notes.bass", {"decay": 0.3, "shape": "exp"}],
        ],
        "osc": [
            {"shape": s, "period_beats": pb, "phase": ph}
            for s in ("sine", "saw", "square", "triangle")
            for pb, ph in ((1.0, 0.0), (4.0, 0.25), (0.5, 0.9))
        ],
        "window_s": [0.0, 0.05, 0.333],
        "texture": [
            {"ids": tex_ids, "width": 1024, "format": "r32f"},
            {"ids": tex_ids, "width": 100, "format": "r8"},
            {"ids": tex_ids[:1], "width": 7, "format": "r32f"},
        ],
        "viz_rules": [
            {"fps": 24},
            {"fps": 60, "frame0": 1},
            {"fps": [30000, 1001], "early": True},
            {"fps": 25},
        ],
        "viz_step": 3,
        "viz_max": 200,
        "frame_span_s": 12.0,
    }


def frame_list(r, cnt: int, span_s: float) -> list[int]:
    """Frames frame0-1 .. frame0+cnt; long songs: the first span_s and the last quarter-span."""
    k = math.ceil(span_s * r.num / r.den)
    if cnt + 2 <= k:
        return list(range(r.frame0 - 1, r.frame0 + cnt + 1))
    return list(range(r.frame0 - 1, r.frame0 + k)) + list(range(r.frame0 + cnt - k // 4, r.frame0 + cnt + 1))


def _ref(it):
    return None if it is None else [it["t"], it.get("id")]


def plain(x):
    if x is None:
        return None
    if isinstance(x, np.ndarray):
        return [plain(v) for v in x.tolist()]
    if isinstance(x, (np.bool_, bool)):
        return bool(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        f = float(x)
        return f if math.isfinite(f) else f"NON-FINITE:{f}"
    if isinstance(x, dict):
        return {k: plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, range)):
        return [plain(v) for v in x]
    return x


def _at(r):
    return (
        None
        if r is None
        else {"item": _ref(r["item"]), "progress": r["progress"], "t_in": r["t_in"], "t_left": r["t_left"]}
    )


def dump(ml, song, spec) -> dict:
    T = spec["times"]
    out = {
        "meta": {
            "duration": song.duration,
            "event_names": sorted(song.event_names),
            "channel_ids": sorted(song.channel_ids),
        }
    }
    out["frame_count"] = [song.frame_count(fr) for fr in spec["frame_rules"]]
    out["curve_at"] = {cid: [song.curve(cid).at(t) for t in T] for cid in spec["curve_ids"]}
    out["curve_frame"] = []
    for fr in spec["frame_rules"]:
        r = ml.frame_rule(fr)
        for cid in spec["frame_curve_ids"]:
            c = song.curve(cid)
            cnt = ml.frame_count(c.n / c.rate, r)
            out["curve_frame"].append([c.frame(n, r) for n in frame_list(r, cnt, spec["frame_span_s"])])
    out["events"] = {}
    for name in spec["event_names"]:
        e = song.events(name)
        out["events"][name] = {
            "exists": e.exists,
            "n": len(e.items),
            "at": [_at(e.at(t)) for t in T],
            "next": [[_ref(e.next(t, min_tier=mt)) for t in T] for mt in spec["tiers"]],
            "prev": [[_ref(e.prev(t, min_tier=mt)) for t in T] for mt in spec["tiers"]],
            "between": [[it["t"] for it in e.between(t, t + 0.37)] for t in T],
        }
    out["in_frame"] = []
    for fr in spec["frame_rules"]:
        r = ml.frame_rule(fr)
        for name in spec["in_frame_events"]:
            e = song.events(name)
            cnt = song.frame_count(r)
            rows = []
            for n in frame_list(r, cnt, spec["frame_span_s"]):
                a = [it["t"] for it in e.in_frame(n, r)]
                b = [it["t"] for it in e.in_frame(n, r, min_tier=2)] if name == "cues" else []
                rows.append([a, b])
            out["in_frame"].append(rows)
    out["rhythm"] = {
        "beat_pos": [song.beat_pos(t) for t in T],
        "beat_phase": [song.beat_phase(t) for t in T],
        "bar_phase": [song.bar_phase(t) for t in T],
        "count": [song.count(t) for t in T],
        "pulse": [[song.pulse(src, t, **kw) for t in T] for src, kw in spec["pulse"]],
        "osc": [[song.osc(t, **kw) for t in T] for kw in spec["osc"]],
    }
    out["lyric_at"] = [song.lyric_at(t) for t in T]
    out["vocal_at"] = [song.vocal_at(t) for t in T]
    out["singer_at"] = [song.singer_at(t) for t in T]
    out["meaning_at"] = [song.meaning_at(t) for t in T]
    out["spectrum_at"] = [song.spectrum_at(t) for t in T]
    out["spectrum_window"] = [[song.spectrum_window(t, s) for t in T] for s in spec["window_s"]]
    out["texture"] = [
        song.texture_data(x["ids"], width=x["width"], format=x["format"]) for x in spec["texture"]
    ]
    out["viz"] = []
    for fr in spec["viz_rules"]:
        r = ml.frame_rule(fr)
        cnt = song.frame_count(r)
        step = max(spec["viz_step"], cnt // spec["viz_max"])
        rows = [song.viz_state(ml.frame_centre(n, r), fr) for n in range(r.frame0, r.frame0 + cnt, step)]
        rows.append(song.viz_state(T[3], fr))
        out["viz"].append(rows)
    out["viz_default"] = [song.viz_state(t, {"fps": 60}) for k, t in enumerate(T) if k % 7 == 0]
    return plain(out)


def compare(js, py, where="$", errors=None, limit=25):
    errors = [] if errors is None else errors
    if len(errors) >= limit:
        return errors
    if isinstance(py, bool) or isinstance(js, bool):
        if js is not py:
            errors.append(f"{where}: js={js!r} py={py!r}")
    elif isinstance(py, (int, float)) and isinstance(js, (int, float)):
        if not abs(js - py) <= TOL * (1 + 1e-9) + 1e-12:
            errors.append(f"{where}: js={js!r} py={py!r}")
    elif isinstance(py, list) and isinstance(js, list):
        if len(js) != len(py):
            errors.append(f"{where}: length js={len(js)} py={len(py)}")
        else:
            for i, (a, b) in enumerate(zip(js, py)):
                compare(a, b, f"{where}[{i}]", errors, limit)
    elif isinstance(py, dict) and isinstance(js, dict):
        if sorted(js) != sorted(py):
            errors.append(
                f"{where}: keys js-only={sorted(set(js) - set(py))} py-only={sorted(set(py) - set(js))}"
            )
        for k in py:
            if k in js:
                compare(js[k], py[k], f"{where}.{k}", errors, limit)
    elif js != py:
        errors.append(f"{where}: js={js!r} py={py!r}")
    return errors


def _no_nonfinite(x, where="$"):
    if isinstance(x, str):
        assert not x.startswith("NON-FINITE"), where
    elif isinstance(x, dict):
        for k, v in x.items():
            _no_nonfinite(v, f"{where}.{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            _no_nonfinite(v, f"{where}[{i}]")


def _run_parity(ml, song_dir: Path, tmp: Path) -> tuple[dict, dict]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not on PATH")
    song = ml.load(song_dir)
    spec = make_spec(song)
    spec_path, out_path = tmp / "spec.json", tmp / "js.json"
    with open(spec_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(spec, fh, ensure_ascii=False)
    py = dump(ml, song, spec)
    proc = subprocess.run(
        [node, str(DUMP_JS), str(song_dir), str(spec_path), str(out_path)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    assert proc.returncode == 0, proc.stderr[-4000:]
    with open(out_path, encoding="utf-8") as fh:
        js = json.load(fh)
    return js, py


@pytest.fixture(scope="module")
def synth_song(tmp_path_factory):
    return lib_synth_song.build(tmp_path_factory.mktemp("lib-synth") / "song")


@pytest.fixture(scope="module")
def parity_synth(ml, synth_song, tmp_path_factory):
    return _run_parity(ml, synth_song, tmp_path_factory.mktemp("parity"))


def test_parity_all_helpers(parity_synth):
    js, py = parity_synth
    errs = compare(js, py)
    assert not errs, "\n".join(errs)


def test_parity_never_nan(parity_synth):
    js, py = parity_synth
    _no_nonfinite(js)
    _no_nonfinite(py)


def test_parity_dump_is_meaningful(parity_synth):
    """Guard against a vacuous comparison: the dump exercises the interesting cases."""
    _, py = parity_synth
    assert len(py["curve_frame"]) == len(FRAME_RULES) * 13  # 13 channels: every policy, NaN-aware, 1 Hz
    assert len(py["frame_count"]) == 32 and len(py["in_frame"]) == 64
    counts = [c["eight_id"] for c in py["rhythm"]["count"]]
    assert {"E000", "E001", "E002", "E003", None} <= set(counts)
    assert any(c["partial"] for c in py["rhythm"]["count"]) and any(
        c["lead_in"] for c in py["rhythm"]["count"]
    )
    assert any(len(s) == 2 for s in py["singer_at"]) and any(len(s) == 3 for s in py["singer_at"])
    assert any(v["voiced"] for v in py["vocal_at"]) and any(
        not v["voiced"] and v["midi"] > 0 for v in py["vocal_at"]
    )
    assert any(m["section_id"] == "S03" for m in py["meaning_at"]) and any(
        m["section_id"] is None for m in py["meaning_at"]
    )
    assert any(lv["word"] for lv in py["lyric_at"]) and any(
        lv["line"] and not lv["word"] for lv in py["lyric_at"]
    )
    assert any(r["onset"] for rows in py["viz"] for r in rows) and any(
        r["beat"] > 0.5 for rows in py["viz"] for r in rows
    )
    assert py["events"]["not.a.file"]["exists"] is False and py["events"]["visemes"]["n"] == 0
    assert compare([1.0, {"a": True}], [1.0 + 2e-6, {"a": False}])  # the comparer does flag differences


@pytest.mark.skipif(not (SYNTH / ".done.json").exists(), reason="tests/contract/synth/ is not finished yet")
def test_parity_contract_synth_fixture(ml, tmp_path):
    js, py = _run_parity(ml, SYNTH, tmp_path)
    errs = compare(js, py)
    assert not errs, "\n".join(errs)
    _no_nonfinite(py)
    # the fixture exercises the joins and the rhythm helpers (not just empty files)
    assert any(c["eight_id"] for c in py["rhythm"]["count"])
    assert any(lv["word"] for lv in py["lyric_at"]) and any(s for s in py["singer_at"])
    assert any(v["voiced"] for v in py["vocal_at"]) and any(m["section_id"] for m in py["meaning_at"])
    assert any(r["onset"] for rows in py["viz"] for r in rows)
