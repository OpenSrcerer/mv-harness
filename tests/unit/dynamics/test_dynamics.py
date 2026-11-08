# ruff: noqa: E501  (long formulas, tables and docstrings)
"""dynamics stage: synthetic ground truth (silence, stop, impacts, decay tail, loud/quiet parts and their role hints),
robustness on a heavily limited master (SPIKE: the fixed-threshold prototype found 3 parts on Jeremy), the contract
fixture's truth, contract outputs and edge cases."""

from __future__ import annotations

import json

import numpy as np
import pytest
from tests.synth.m1.fakectx import FakeCtx
from tests.synth.m1.harness import run_m1
from tests.synth.m1.markers import REAL_SONGS, REPO, real_available, real_dir
from tests.synth.m1.signals import dynamics_song

from mvh.contract.conventions import n_curve_frames
from mvh.contract.ids import ID_KINDS
from mvh.stages import dynamics as dyn_pkg
from mvh.stages.dynamics import stage as dyn_stage

LEVEL_ORDER = {"silence": 0, "quiet": 1, "soft": 2, "medium": 3, "loud": 4, "peak": 5}


def _events(ctx, name):
    return ctx.written_events(name)["items"]


def _part_at(parts, t):
    for p in parts:
        if p["t"] <= t < p["t"] + p["d"]:
            return p
    return parts[-1]


@pytest.fixture(scope="module")
def dsong(tmp_path_factory):
    x, sr, truth = dynamics_song()
    r = run_m1(x, sr, tmp_path_factory.mktemp("dsong"), bars=truth["bars"])
    return r, x, sr, truth


@pytest.fixture(scope="module")
def dsong_limited(tmp_path_factory):
    x, sr, truth = dynamics_song()
    y = np.tanh(8.0 * x) * 0.98  # a heavily limited master of the same arrangement
    r = run_m1(y, sr, tmp_path_factory.mktemp("dsong_lim"), bars=truth["bars"])
    return r, y, sr, truth


# ------------------------------------------------------------------------------------------------ events
@pytest.mark.parametrize("which", ["dsong", "dsong_limited"])
def test_silence_and_stop(which, request):
    r, _, _, truth = request.getfixturevalue(which)
    ctx = r["ctx"]["dynamics"]
    sil = [s for s in _events(ctx, "silences") if not s["edge"]]
    assert len(sil) == 1
    t0, t1 = truth["silences"][0]
    assert abs(sil[0]["t"] - t0) <= 0.02 and abs(sil[0]["t"] + sil[0]["d"] - t1) <= 0.02
    assert sil[0]["depth_db"] >= 40.0 and sil[0]["digital"]
    stops = _events(ctx, "stops")
    assert len(stops) == 1 and abs(stops[0]["t"] - truth["stops"][0]) <= 0.02
    assert stops[0]["strength"] >= 0.9 and abs(stops[0]["gap_s"] - 2.0) <= 0.05


@pytest.mark.parametrize("which", ["dsong", "dsong_limited"])
def test_impacts(which, request):
    r, _, _, truth = request.getfixturevalue(which)
    imps = _events(r["ctx"]["dynamics"], "impacts")
    for t in truth["impacts"]:
        near = [i for i in imps if abs(i["t"] - t) <= 0.2]
        assert near, (t, [i["t"] for i in imps])
        assert near[0]["major"], t
    drop = [i for i in imps if abs(i["t"] - 48.0) <= 0.2][0]
    assert drop["after_silence"] and drop["strength"] >= 0.9 and drop["delta_bass_db"] > 20
    assert len(imps) <= 8
    assert [i["id"] for i in imps] == [f"I{k:03d}" for k in range(1, len(imps) + 1)]


def test_decay_tail(dsong):
    r, _, _, truth = dsong
    tails = _events(r["ctx"]["dynamics"], "decay_tails")
    t0, t1 = truth["decay_tails"][0]
    hit = [y for y in tails if abs(y["t"] - t0) <= 0.1]
    assert hit and hit[0]["d"] >= 2.0 and hit[0]["t"] + hit[0]["d"] <= t1 + 0.05 and hit[0]["strength"] >= 0.8


# ------------------------------------------------------------------------------------------------ parts
@pytest.mark.parametrize("which", ["dsong", "dsong_limited"])
def test_parts_boundaries_levels_and_roles(which, request):
    r, _, _, truth = request.getfixturevalue(which)
    ctx = r["ctx"]["dynamics"]
    parts = _events(ctx, "dynamics")
    starts = [p["t"] for p in parts]
    for t in (8.0, 24.0, 46.0, 48.0, 60.0):
        assert min(abs(s - t) for s in starts) <= 0.05, (t, starts)  # bars are 2 s; boundaries sit on downbeats
    assert parts[0]["t"] == 0.0 and abs(parts[-1]["t"] + parts[-1]["d"] - 64.0) < 1e-3
    assert all(abs(a["t"] + a["d"] - b["t"]) < 1e-6 for a, b in zip(parts, parts[1:]))  # contiguous
    lv = {name: _part_at(parts, 0.5 * (a + b)) for name, a, b in truth["sections"]}
    assert lv["silence"]["level"] == "silence"
    for louder, quieter in truth["louder_than"]:
        if which == "dsong_limited" and quieter == "main":
            continue  # tanh limiting flattens the drop and the main groove to the same loudness
        assert lv[louder]["rel_lu"] > lv[quieter]["rel_lu"], (louder, quieter)
    assert LEVEL_ORDER[lv["drop"]["level"]] >= LEVEL_ORDER["loud"]
    assert LEVEL_ORDER[lv["breakdown"]["level"]] <= LEVEL_ORDER["soft"]
    # role hints: evidence for structure (drop at 48, a build ending at the stop, a breakdown at 24)
    assert lv["drop"]["role_hint"] == "drop" and abs(lv["drop"]["t"] - 48.0) <= 0.05
    builds = [p for p in parts if p["role_hint"] == "build"]
    assert any(abs(p["t"] + p["d"] - 46.0) <= 0.05 and p["t"] >= 30.0 for p in builds), builds
    assert lv["breakdown"]["role_hint"] == "breakdown"
    assert all(0.0 <= p["conf"] <= 1.0 for p in parts)


def test_limited_master_is_still_segmented(dsong, dsong_limited):
    """Heavy limiting removes most of the loudness range (and fixed-threshold novelty with it); the adaptive
    thresholds, bass/kick features and level scaling keep the parts."""
    a = _events(dsong[0]["ctx"]["dynamics"], "dynamics")
    b = _events(dsong_limited[0]["ctx"]["dynamics"], "dynamics")
    assert len(b) >= 5 and abs(len(a) - len(b)) <= 3


def test_curves_and_summary(dsong):
    r, x, sr, truth = dsong
    ctx = r["ctx"]["dynamics"]
    ch = ctx.written_curves()
    n = n_curve_frames(x.shape[1], sr)
    assert sorted(ch) == ["dyn.intensity", "dyn.novelty"]
    for v in ch.values():
        assert v.size == n and v.min() >= 0.0 and v.max() <= 1.0 and np.all(np.isfinite(v))
    it = ch["dyn.intensity"]

    def mean(a, b):
        return float(it[int(a * 100) : int(b * 100)].mean())

    assert mean(49, 59) > mean(9, 23) > mean(25, 31)  # drop > main > breakdown
    assert mean(46.3, 47.7) < 0.05  # digital silence
    nov = ch["dyn.novelty"]
    assert nov[int(48 * 100) - 100 : int(48 * 100) + 100].max() > 0.5
    doc = ctx.written_json("meta/dynamics.json")
    assert doc["parts"] == len(_events(ctx, "dynamics")) and doc["loudest_parts"] and doc["quietest_parts"]
    assert sum(doc["level_seconds"].values()) == pytest.approx(64.0, abs=1e-3)


def test_ids_match_the_contract(dsong):
    ctx = dsong[0]["ctx"]["dynamics"]
    import re

    for name, kind in (("impacts", "impact"), ("stops", "stop"), ("silences", "silence"), ("decay_tails", "decay_tail")):
        for it in _events(ctx, name):
            assert re.match(ID_KINDS[kind].regex, it["id"]), it["id"]


# ------------------------------------------------------------------------------------------------ fixture truth
SYNTH = REPO / "tests" / "contract" / "synth"


@pytest.mark.skipif(not (SYNTH / "_truth" / "truth.json").is_file(), reason="synth fixture missing")
def test_contract_fixture_truth(tmp_path):
    from mvh.io import audio as aio

    with open(SYNTH / "_truth" / "truth.json", encoding="utf-8") as fh:
        truth = json.load(fh)
    with open(SYNTH / "events" / "bars.json", encoding="utf-8") as fh:
        bars = json.load(fh)["items"]
    d = aio.decode(SYNTH / "_intermediate" / "ingest" / "canonical.wav")
    r = run_m1(d.samples, d.sr, tmp_path, bars=bars)
    ctx = r["ctx"]["dynamics"]
    z = truth["silences"][0]
    sil = [s for s in _events(ctx, "silences") if not s["edge"]]
    assert len(sil) == 1 and abs(sil[0]["t"] - z["t"]) <= 0.02 and abs(sil[0]["d"] - z["d"]) <= 0.03
    assert abs(sil[0]["depth_db"] - z["depth_db"]) <= 0.5
    x = truth["stops"][0]
    stops = _events(ctx, "stops")
    assert any(abs(s["t"] - x["t"]) <= 0.02 and abs(s["gap_s"] - x["gap_s"]) <= 0.05 for s in stops)
    imps = _events(ctx, "impacts")
    drop = [i for i in imps if abs(i["t"] - 34.5) <= 0.05]
    assert drop and drop[0]["major"] and drop[0]["after_silence"]
    found = sum(1 for i in truth["impacts"] if any(abs(j["t"] - i["t"]) <= 0.15 for j in imps))
    assert found >= 2, [j["t"] for j in imps]  # 34.5 (drop) and 52.5 (final hit); 17.0 is a crash with +0.5 LU
    y = truth["decay_tails"][0]
    tails = _events(ctx, "decay_tails")
    assert any(abs(t["t"] - y["t"]) <= 0.35 and t["d"] >= 3.0 for t in tails), tails
    parts = _events(ctx, "dynamics")
    assert any(p["level"] == "silence" and abs(p["t"] - 32.5) <= 0.02 for p in parts)
    assert any(p["role_hint"] == "drop" and abs(p["t"] - 34.5) <= 0.05 for p in parts)


# ------------------------------------------------------------------------------------------------ edge cases
def _bare_ctx(tmp_path, n, sr=44100, **kw):
    x = kw.pop("x", np.zeros((2, n)))
    n100 = n_curve_frames(x.shape[1], sr)
    curves = {"loud.short_term_lufs": np.full(n100, -70.0), "loud.momentary_lufs": np.full(n100, -70.0),
              "bands.bass_db": np.full(n100, -120.0), "bands.kick_db": np.full(n100, -120.0),
              "timbre.centroid_hz": np.zeros(n100), "timbre.slope_db_oct": np.zeros(n100),
              "stereo.width": np.zeros(n100)}
    curves.update(kw.pop("curves", {}))
    ev = {"hits.kick": [], "onsets.mid": [], "onsets.high": [], "bars": []}
    return FakeCtx(dyn_pkg.STAGE, tmp_path, samples=x, sr=sr, curves=curves, events=ev,
                   docs={"loudness": {"meta/loudness.json": {"integrated_lufs": -70.0}}})


def test_all_silent_song(tmp_path):
    ctx = _bare_ctx(tmp_path, 44100 * 5)
    res = dyn_pkg.run(ctx)
    parts = _events(ctx, "dynamics")
    assert res.status == "ok" and len(parts) == 1 and parts[0]["level"] == "silence"
    assert _events(ctx, "impacts") == [] and _events(ctx, "stops") == []


def test_allin1_boundaries_are_guarded(tmp_path):
    ctx = _bare_ctx(tmp_path, 44100 * 2)
    assert dyn_stage.allin1_boundaries(ctx) is None  # not a declared dep in contract v1 (change request)


# ------------------------------------------------------------------------------------------------ real songs
@pytest.mark.real
@pytest.mark.slow
@pytest.mark.parametrize("slug", list(REAL_SONGS))
def test_real_song_dynamics(slug, tmp_path):
    if not real_available(slug):
        pytest.skip("real fixture missing")
    from mvh.io import audio as aio

    p = real_dir(slug) / "_intermediate" / "ingest" / "canonical.wav"
    with open(real_dir(slug) / "events" / "bars.json", encoding="utf-8") as fh:
        bars = json.load(fh)["items"]
    d = aio.decode(p)
    r = run_m1(d.samples, d.sr, tmp_path, bars=bars, audio_path=p)
    ctx = r["ctx"]["dynamics"]
    parts = _events(ctx, "dynamics")
    dur = d.samples.shape[1] / d.sr
    assert len(parts) >= dur / 45, len(parts)  # the fixed-threshold prototype found 3 parts on jeremy
    levels = {p["level"] for p in parts}
    assert len(levels - {"silence"}) >= 3, levels  # loud and quiet parts are told apart
    if slug == "megafauna":  # the drops (W0: after the long breakdown; the +48 dB bass entry)
        drops = [p["t"] for p in parts if p["role_hint"] == "drop"]
        assert any(94 <= t <= 98 for t in drops) and any(139 <= t <= 144 for t in drops), drops
