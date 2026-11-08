"""Golden vectors (docs/contract/golden-vectors.json) against lib/mvh_load.py."""

from __future__ import annotations

import ast
import math
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
ASSETS = REPO / "src" / "mvh" / "assets"
GOLDEN = REPO / "docs" / "contract" / "golden-vectors.json"
TOL = 1e-6


def close(actual, expected, where="$"):
    if expected is None:
        assert actual is None, f"{where}: expected None, got {actual!r}"
        return
    if isinstance(expected, bool):
        assert actual is expected or actual == expected, f"{where}: {actual!r} != {expected!r}"
        assert isinstance(actual, (bool, np.bool_)), f"{where}: expected a bool, got {actual!r}"
        return
    if isinstance(expected, (int, float)):
        assert isinstance(actual, (int, float, np.integer, np.floating)) and not isinstance(actual, bool), (
            f"{where}: expected a number, got {actual!r}"
        )
        assert not math.isnan(actual), f"{where}: NaN"
        assert abs(actual - expected) <= TOL * (1 + 1e-9) + 1e-12, f"{where}: {actual} != {expected}"
        return
    if isinstance(expected, str):
        assert actual == expected, f"{where}: {actual!r} != {expected!r}"
        return
    if isinstance(expected, list):
        assert len(actual) == len(expected), f"{where}: length {len(actual)} != {len(expected)}"
        for i, e in enumerate(expected):
            close(actual[i], e, f"{where}[{i}]")
        return
    assert isinstance(actual, dict), f"{where}: expected a dict, got {actual!r}"
    assert sorted(actual) == sorted(expected), f"{where}: keys {sorted(actual)} != {sorted(expected)}"
    for k, e in expected.items():
        close(actual[k], e, f"{where}.{k}")


def nanify(a):
    return [math.nan if x is None else x for x in a]


def test_golden_copy_is_current():
    assert (ASSETS / "golden" / "golden-vectors.json").read_bytes() == GOLDEN.read_bytes()


def test_module_imports_only_stdlib_and_numpy():
    tree = ast.parse((ASSETS / "mvh_load.py").read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            mods.add((node.module or "").split(".")[0])
    assert mods <= {"__future__", "bisect", "json", "math", "pathlib", "typing", "numpy"}, mods


def test_frames(ml, golden):
    for c in golden["frames"]:
        fr = c["fr"]
        for n, t in c["time_of"]:
            close(ml.time_of(n, fr), t, f"time_of {fr} {n}")
        for n, t in c["frame_centre"]:
            close(ml.frame_centre(n, fr), t)
        for n, w in c["frame_window"]:
            close(list(ml.frame_window(n, fr)), w)
        for t, n in c["frame_of"]:
            assert ml.frame_of(t, fr) == n, (fr, t)
        for n, m in c["roundtrip"]:
            assert ml.frame_of(ml.time_of(n, fr), fr) == m
        for d, k in c["frame_count"]:
            assert ml.frame_count(d, fr) == k


def test_curve_policies(ml, golden):
    v = golden["curve"]["values"]
    for p in ml.POLICIES:
        for t, y in golden["curve"]["at"][p]:
            close(ml.curve_at(v, t, 100, p), y, f"at {p} {t}")
    for c in golden["curve"]["frame"]:
        for p in ml.POLICIES:
            for n, y in c["frames"][p]:
                close(ml.curve_frame(v, n, c["fr"], 100, p), y, f"frame {p} {c['fr']} {n}")
        for n, se in c["samples_in_frame"]:
            r = ml.samples_in_frame(n, c["fr"], 100, len(v))
            assert [r.start, r.stop] == se or (r.start == r.stop and se[0] == se[1])


def test_flash(ml, golden):
    v = golden["curve"]["values"]
    f = golden["flash"]
    assert list(ml.flash_samples(f["event_t"])) == f["flash_samples"]
    for c in f["cases"]:
        assert ml.frame_of(f["event_t"], c["fr"]) == c["event_frame"]
        close(ml.curve_frame(v, c["event_frame"], c["fr"], 100, "max"), c["max_at_event_frame"])


def test_voicing(ml, golden):
    V = golden["voicing"]
    ch = {k: nanify(a) for k, a in V["channels"].items()}
    for t, y in V["midi_at"]:
        close(ml.curve_at(ch["vocal.midi"], t, 100, "linear", nan_aware=True), y, f"midi_at {t}")
    for t, r in V["vocal_at"]:
        close(ml.vocal_at(t, ch, 100, V["phrases"], V["notes"]), r, f"vocal_at {t}")
    ch32 = {k: np.asarray(a, dtype=np.float32) for k, a in ch.items()}
    for t, r in V["vocal_at"]:
        a = ml.vocal_at(t, ch32, 100, V["phrases"], V["notes"])
        assert a["voiced"] == r["voiced"] and abs(a["midi"] - r["midi"]) < 1e-4
    for c in V["frames"]:
        for p in ml.POLICIES:
            for n, y in c["frames"][p]:
                close(
                    ml.curve_frame(ch["vocal.midi"], n, c["fr"], 100, p, nan_aware=True), y, f"vframe {p} {n}"
                )


def test_beats_counts_osc(ml, golden):
    B = golden["beats"]
    for t, r in B["beat_pos"]:
        close(ml.beat_pos(t, B["beats"]), r, f"beat_pos {t}")
    for t, r in B["beat_phase"]:
        close(ml.beat_phase(t, B["beats"]), r)
    for t, r in B["bar_phase"]:
        close(ml.bar_phase(t, B["beats"]), r, f"bar_phase {t}")
    for t, r in B["count"]:
        close(ml.count_at(t, B["beats"], B["counts"]), r, f"count {t}")
    for t, r in B["no_beats"]:
        close(ml.beat_pos(t, []), r)
    for t, shapes, pb, ph in B["osc"]:
        for s, y in shapes.items():
            close(ml.osc(t, B["beats"], s, pb, ph), y, f"osc {s} {t}")


def test_events(ml, golden):
    E = golden["events"]
    for t, r in E["at"]:
        a = ml.event_at(E["segments"], t)
        close(
            None
            if a is None
            else {"id": a["item"]["id"], "progress": a["progress"], "t_in": a["t_in"], "t_left": a["t_left"]},
            r,
            f"at {t}",
        )
    for t, mt, rid in E["next"]:
        it = ml.event_next(E["cues"], t, mt)
        assert (it and it["id"]) == rid or (it is None and rid is None)
    for t, mt, rid in E["prev"]:
        it = ml.event_prev(E["cues"], t, mt)
        assert (it["id"] if it else None) == rid
    for t, ids in E["all_at"]:
        assert [x["id"] for x in ml.event_all_at(E["segments"], t)] == ids
    for a, b, ids in E["between"]:
        assert [x["id"] for x in ml.event_between(E["cues"], a, b)] == ids
    for fr, n, ids in E["in_frame"]:
        assert [x["id"] for x in ml.event_in_frame(E["cues"], n, fr)] == ids


def test_pulse(ml, golden):
    P = golden["pulse"]
    for t, kw, y in P["cases"]:
        close(ml.pulse(t, P["items"], golden["beats"]["beats"], **kw), y, f"pulse {t} {kw}")


def test_singer_at(ml, golden):
    S = golden["singer_at"]

    def mo(voice, t):
        key = (
            f"vocal.mouth_open.{voice}"
            if voice and f"vocal.mouth_open.{voice}" in S["mouth_open"]
            else "vocal.mouth_open"
        )
        return ml.curve_at(S["mouth_open"][key], t, S["rate"], "max")

    for t, r in S["cases"]:
        close(ml.singer_at(t, S["singing"], mo), r, f"singer_at {t}")


def _texture_channels(golden):
    a = [round(math.sin(i * 0.013) * 0.5 + 0.5, 6) for i in range(golden["texture"]["channels"]["a"]["n"])]
    b = [round((i % 100) / 100.0, 6) for i in range(golden["texture"]["channels"]["b"]["n"])]
    return [a, b]


def test_texture(ml, golden):
    T = golden["texture"]
    chans = _texture_channels(golden)
    data, height, lay = ml.pack_texture(chans, T["width"])
    assert height == T["height"] and lay == T["layout"]
    w = T["width"]
    for c, i, y in T["texels"]:
        close(float(data[(lay[c]["row0"] + i // w) * w + i % w]), y)
    for c, t, ts, ca in T["sample"]:
        close(ml.texture_sample(data, lay[c], t), ts, f"sample {c} {t}")
        close(ml.curve_at(chans[c], t), ca)


def test_spectrum_rows(ml, golden):
    for t, s, rows in golden["spectrum_rows"]["cases"]:
        assert ml.spectrum_rows(t, s, golden["spectrum_rows"]["n_frames"]) == rows
