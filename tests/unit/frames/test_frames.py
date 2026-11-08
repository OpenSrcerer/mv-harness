# ruff: noqa: E501
"""frames export: parity with the reference frame rules (conventions.curve_frame) at every fps / frame0 / early /
policy, never NaN, the file naming of CONTRACT §7, event columns, and the stage run on the synthetic song."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np
import pytest

from mvh.contract import conventions as cv
from mvh.stages.frames.export import (
    event_columns,
    file_tag,
    frame_times,
    parse_rules,
    sample_frames,
    select_channels,
)

ROOT = Path(__file__).resolve().parents[3]
SYNTH = ROOT / "tests" / "contract" / "synth"
RATES = (23.976, 24, 25, 29.97, 30, 60, [24000, 1001], 120)
TOL = 1e-6  # PLAN §7 helper parity


def _curve(n: int, seed: int, nan: bool) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = np.cumsum(rng.normal(size=n)).astype(np.float32)
    if nan:
        mask = rng.random(n) < 0.35
        mask[:7] = True  # unvoiced start
        mask[n // 2: n // 2 + 40] = True  # a long gap
        v[mask] = np.nan
    return v


@pytest.mark.parametrize("fps", RATES, ids=str)
@pytest.mark.parametrize("frame0", (0, 1))
@pytest.mark.parametrize("early", (False, True))
def test_parity_with_reference(fps, frame0, early):
    r = cv.FrameRule(fps, frame0, early)
    for rate, n in ((100.0, 1003), (1.0, 11)):
        dur = n / rate
        nf = cv.frame_count(dur, r) + 2  # also frames past the end (clamping)
        for pol in cv.POLICIES:
            for nan in (False, True):
                v = _curve(n, 7 + n, nan)
                got = sample_frames(v, rate, r, nf, pol, nan_aware=nan)
                ref = np.array([cv.curve_frame(v, k, r, rate, pol, nan) for k in range(frame0, frame0 + nf)])
                ref = np.nan_to_num(ref, nan=0.0)
                assert np.isfinite(got).all()
                assert np.max(np.abs(got - ref)) <= TOL, (fps, frame0, early, rate, pol, nan)


def test_all_unvoiced_is_zero_not_nan():
    v = np.full(200, np.nan, dtype=np.float32)
    r = cv.FrameRule(24)
    for pol in cv.POLICIES:
        assert (sample_frames(v, 100.0, r, 48, pol, nan_aware=True) == 0).all()


def test_file_tags_and_rules():
    assert file_tag(cv.FrameRule(24)) == "24"
    assert file_tag(cv.FrameRule(23.976)) == "23.976"
    assert file_tag(cv.FrameRule([24000, 1001], 1)) == "24000-1001_f1"
    assert file_tag(cv.FrameRule(30, 0, True)) == "30_early"
    rs = parse_rules([24000, 1001])
    assert len(rs) == 1 and (rs[0].num, rs[0].den) == (24000.0, 1001.0)
    rs = parse_rules([24, 30])
    assert [r.fps for r in rs] == [24.0, 30.0]
    rs = parse_rules(["24000/1001", {"fps": 60, "frame0": 1, "early": True}, 24, 24], frame0=0)
    assert [file_tag(r) for r in rs] == ["24000-1001", "60_f1_early", "24"]


def test_frame_count_matches_contract_examples():
    for fps, want in ((24, 7599), (23.976, 7591), (30, 9498)):
        n, t, c = frame_times(cv.FrameRule(fps), 316.587)
        assert n.size == want and t[0] == 0.0
    n, t, c = frame_times(cv.FrameRule([24000, 1001], 1), 2.0)
    assert n[0] == 1 and abs(t[24] - 1.001) < 1e-12  # Blender: time_of(25) = 1.001 s


def test_event_columns_follow_membership_rule():
    beats = [{"beat_index": i, "t": 0.5 + 0.5 * i, "bar": 1 + i // 4, "beat_in_bar": 1 + i % 4, "beats_in_bar": 4,
              "in_pulse": True} for i in range(40)]
    secs = [{"id": "S01", "t": 0.5, "d": 8.0}, {"id": "S02", "t": 8.5, "d": 12.0}]
    cues = [{"id": "Q0001", "t": 0.5, "tier": 4}, {"id": "Q0002", "t": 0.5104, "tier": 1}, {"id": "Q0003", "t": 8.5, "tier": 1}]
    for fr in (cv.FrameRule(24), cv.FrameRule(30, 1, True), cv.FrameRule([24000, 1001])):
        n, _t, c = frame_times(fr, 25.0)
        cols = event_columns(["section_id", "beat", "downbeat", "bar", "cue_tier", "cue_id"], fr, n, c,
                             {"beats": beats, "sections": secs, "cues": cues})
        for i, k in enumerate(n):
            assert cols["beat"][i] == len(cv.event_in_frame(beats, int(k), fr))
            e = cv.event_at(secs, float(c[i]))
            assert cols["section_id"][i] == (e["item"]["id"] if e else None)
            inf = cv.event_in_frame(cues, int(k), fr)
            assert cols["cue_tier"][i] == (min(x["tier"] for x in inf) if inf else None)
        assert sum(cols["beat"]) == 40 and sum(cols["downbeat"]) == 10


def test_select_channels():
    avail = ["bands.bass", "bands.mid", "drums.kick", "vocal.mouth_open.V2", "vocal.mouth_open", "mood.valence",
             "stem.bass.level"]
    assert select_channels(avail, ["*"])[0] == "bands.bass" and len(select_channels(avail, ["*"])) == len(avail)
    assert select_channels(avail, ["drums.*", "stem.*"]) == ["drums.kick", "stem.bass.level"]
    dflt = select_channels(avail, [])
    assert "vocal.mouth_open.V2" in dflt and "stem.bass.level" not in dflt


# ----------------------------------------------------------------------------------------------- stage run
@pytest.fixture(scope="module")
def synth_frames(tmp_path_factory):
    if not (SYNTH / ".done.json").is_file():
        pytest.skip("tests/contract/synth is not built")
    from mvh.stages.meaning.devrun import DevRun

    dr = DevRun(SYNTH, tmp_path_factory.mktemp("frames"))
    dr.run("meaning")
    done = dr.run("frames", {"fps": [24, {"fps": [24000, 1001], "frame0": 1}], "format": "deforum"})
    return dr, done


def _rows(dr, rel):
    with open(Path(dr.upstream["frames"]["dir"]) / rel, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_stage_writes_valid_csv(synth_frames):
    dr, done = synth_frames
    assert set(done["result"]["summary"]["files"]) >= {"frames/24fps.csv", "frames/24000-1001_f1fps.csv"}
    rows = _rows(dr, "frames/24fps.csv")
    assert len(rows) == cv.frame_count(56.5, cv.FrameRule(24)) == 1356
    assert list(rows[0])[:2] == ["frame", "t"]
    curve_cols = [c for c in rows[0] if "." in c]
    assert len(curve_cols) >= 15
    for r in rows:
        for c in curve_cols:
            assert r[c] != "" and math.isfinite(float(r[c]))
    b = _rows(dr, "frames/24000-1001_f1fps.csv")
    assert b[0]["frame"] == "1" and float(b[24]["t"]) == pytest.approx(1.001)
    from mvh.runner.validate import validate_files

    assert validate_files(Path(dr.upstream["frames"]["dir"]), ["frames/24fps.csv"]) == []
    with open(Path(dr.upstream["frames"]["dir"]) / "frames/24fps.deforum.json", encoding="utf-8") as fh:
        df = json.load(fh)
    assert df["max_frames"] == 1356 and df["keyframes"]["bands.bass"].startswith("0:(")


def test_flash_and_event_share_a_frame(synth_frames, truth_kicks):
    """PLAN §4.2: a curve flash and its event land on the same frame (kick hits from the synthetic truth)."""
    dr, _ = synth_frames
    rows = _rows(dr, "frames/24fps.csv")
    kick = np.array([float(r["drums.kick"]) for r in rows])
    fr = cv.FrameRule(24)
    ok = 0
    for t in truth_kicks:
        f = cv.frame_of(t, fr)
        if f >= len(kick):
            continue
        lo, hi = max(0, f - 1), min(len(kick), f + 2)
        ok += int(kick[f] >= kick[lo:hi].max() - 1e-9 and kick[f] > 0)
    assert ok / len(truth_kicks) >= 0.95  # PLAN §7 kick-event threshold


def test_beat_column_matches_truth(synth_frames):
    dr, _ = synth_frames
    rows = _rows(dr, "frames/24fps.csv")
    with open(SYNTH / "_truth" / "truth.json", encoding="utf-8") as fh:
        beats = json.load(fh)["beats"]
    want = {}
    for b in beats:
        k = cv.frame_of(b["t"], cv.FrameRule(24))
        want[k] = want.get(k, 0) + 1
    got = {int(r["frame"]): int(r["beat"]) for r in rows if int(r["beat"])}
    assert got == {k: v for k, v in want.items() if k < len(rows)}
    secs = {r["section_id"] for r in rows if r["section_id"]}
    assert secs == {"S01", "S02", "S03", "S04", "S05", "S06"}
    assert any(r["singer"] == "C1+C2" for r in rows) and any(r["count"] == "8" for r in rows)


@pytest.fixture(scope="module")
def truth_kicks() -> list[float]:
    with open(SYNTH / "_truth" / "truth.json", encoding="utf-8") as fh:
        hits = json.load(fh)["drum_hits"]
    ts = sorted(h["t"] for h in hits if h["drum"] == "kick")
    out = []
    for t in ts:  # distinct hits (>= 3 frames apart at 24 fps) so neighbouring flashes do not mask each other
        if not out or t - out[-1] >= 0.125:
            out.append(t)
    return out


@pytest.mark.real
@pytest.mark.parametrize("slug", ("megafauna", "versatile", "jeremy", "newton-vs-nye"))
def test_real_frames(tmp_path, slug):
    import time

    from mvh.stages.meaning.devrun import DevRun

    fx = ROOT / "tests" / "contract" / f"real-{slug}"
    if not fx.is_dir():
        pytest.skip(f"{fx} missing")
    dr = DevRun(fx, tmp_path)
    dr.run("meaning")
    t0 = time.time()
    done = dr.run("frames", {"fps": [24, "30000/1001", 60], "curves": ["*"]})
    secs = time.time() - t0
    src = json.loads((fx / "meta/source.json").read_text(encoding="utf-8"))
    dur = src["n_samples"] / src["sample_rate"]
    for rel, fr in (("frames/24fps.csv", cv.FrameRule(24)), ("frames/30000-1001fps.csv", cv.FrameRule([30000, 1001])),
                    ("frames/60fps.csv", cv.FrameRule(60))):
        rows = _rows(dr, rel)
        assert len(rows) == cv.frame_count(dur, fr)
        cols = [c for c in rows[0] if "." in c]
        assert len(cols) >= 20
        for r in rows[:: max(1, len(rows) // 500)]:
            assert all(math.isfinite(float(r[c])) for c in cols)
    print(f"{slug}: frames {secs:.1f} s, {done['result']['summary']['n_channels']} channels")
