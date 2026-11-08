# ruff: noqa: E501  (long docstrings and tables)
"""stem_activity: core definitions on synthetic signals, then the stage on the synthetic song (generator stems)."""

from __future__ import annotations

import json

import numpy as np
import pytest
from tests.synth.m3a import SYNTH, fixture_upstreams, real_fixture, run_stage, truth

from mvh.contract import schemas
from mvh.contract.curvefile import read_channel  # noqa: F401  (import check)
from mvh.stages.stem_activity import core

SR = 44100


# ------------------------------------------------------------------------------------------------ core
def test_n_frames_integer_rule():
    assert core.n_frames(44100, 44100) == 100
    assert core.n_frames(44101, 44100) == 101
    assert core.n_frames(48000 * 3, 48000) == 300


def test_frame_power_matches_sine_rms():
    t = np.arange(SR * 2) / SR
    x = 0.5 * np.sin(2 * np.pi * 440 * t)
    p = core.frame_power(np.stack([x, x]), SR, core.RMS_WINDOW_S, core.n_frames(x.size, SR))
    db = core.power_db(p)
    # sine RMS = A / sqrt(2) -> -9.03 dBFS (away from the edges)
    assert np.allclose(db[10:-10], 20 * np.log10(0.5 / np.sqrt(2)), atol=0.05)
    assert p.shape[0] == 200


def test_silence_floors_at_minus_120():
    db = core.power_db(core.frame_power(np.zeros((2, SR)), SR, 0.05, 100))
    assert np.all(db == core.FLOOR_DB)
    assert np.all(core.rel_db(db, db) == core.FLOOR_DB)


def test_activity_hysteresis_joins_short_gaps_and_drops_short_runs():
    n = 1000
    dec = np.full(n, -80.0)
    rel = np.full(n, -60.0)

    def on(a, b):
        dec[a:b] = -20.0
        rel[a:b] = -3.0

    on(100, 200)   # 1.0 s
    on(240, 300)   # gap 0.4 s < 0.5 s release -> joined
    on(400, 420)   # 0.2 s isolated < 0.3 s attack -> dropped
    on(600, 700)   # gap 3 s -> new segment
    m = core.activity_mask(dec, rel)
    segs = core.segments_of(m, 10.0)
    assert [(round(t, 2), round(d, 2)) for t, d, *_ in segs] == [(1.0, 2.0), (6.0, 1.0)]


def test_activity_requires_both_level_and_share():
    dec = np.full(100, -30.0)
    rel = np.full(100, -25.0)     # loud enough but more than 18 dB below the mix
    assert not core.activity_mask(dec, rel).any()
    dec[:] = -50.0
    rel[:] = 0.0                  # the whole mix but below -45 dBFS
    assert not core.activity_mask(dec, rel).any()


def test_agreement_scale():
    a = core.agreement(np.array([-20.0, -20.0, -20.0, -20.0]), np.array([-20.0, -26.0, -30.0, -40.0]))
    assert a.tolist() == [1.0, 1.0, pytest.approx(5 / 9), 0.0]


# ------------------------------------------------------------------------------------------------ stage on the synthetic song
@pytest.fixture(scope="module")
def synth_run(tmp_path_factory):
    ups, ing = fixture_upstreams(SYNTH)
    out, done = run_stage("stem_activity", tmp_path_factory.mktemp("sa"), ups, ing)
    return out, done


def test_stage_outputs_are_valid(synth_run):
    out, done = synth_run
    with open(out / "meta/stems.json", encoding="utf-8") as fh:
        meta = json.load(fh)
    assert schemas.validate(meta, "mvh/files/stems") == []
    with open(out / "events/stem_activity.json", encoding="utf-8") as fh:
        ev = json.load(fh)
    assert schemas.validate(ev, "mvh/events/stem_activity") == []
    assert ev["kind"] == "segment" and all(it["d"] > 0 for it in ev["items"])
    ts = [it["t"] for it in ev["items"]]
    assert ts == sorted(ts)
    # every stem (9 + 6 drum sub-stems) has its four channels with the right length
    tb = done["curves"]["stems"]
    n = -(-int(truth()["n_samples"]) * 100 // int(truth()["sr"]))
    stems = list(meta["stems"])
    assert len(stems) == 15
    for s in stems:
        for kind in ("level", "rms_db", "rel_db", "active"):
            assert tb[f"stem.{s}.{kind}"]["n"] == n


def test_presence_on_the_synthetic_song(synth_run):
    out, _ = synth_run
    with open(out / "meta/stems.json", encoding="utf-8") as fh:
        st = json.load(fh)["stems"]
    # guitar is digital silence in the generator; everything else plays
    assert st["guitar"]["present"] is False and st["guitar"]["active_ratio"] == 0.0
    for s in ("vocals", "lead_vocals", "drums", "bass", "piano", "other", "instrumental", "drums_kick", "drums_hihat"):
        assert st[s]["present"] is True, s
    # htdemucs (the fixture's fast stems are the exact generator sums) agrees with every confirmed stem
    assert st["vocals"]["conf"] >= 0.9 and st["drums"]["conf"] >= 0.9


def _truth_vocal_spans():
    t = truth()
    spans = [(w["t"], w["t"] + w["d"]) for w in t["words"]] + [(w["t"], w["t"] + w["d"]) for w in t["backing_words"]]
    return sorted(spans)


def test_vocal_activity_covers_sung_words(synth_run):
    """Every truth word lies inside an active vocals segment (recall), and active time far from any word is small."""
    out, _ = synth_run
    with open(out / "events/stem_activity.json", encoding="utf-8") as fh:
        items = [it for it in json.load(fh)["items"] if it["stem"] == "vocals"]
    segs = [(it["t"], it["t"] + it["d"]) for it in items]

    def covered(a, b):
        return sum(max(0.0, min(b, e) - max(a, s)) for s, e in segs) / (b - a)

    words = _truth_vocal_spans()
    cov = np.mean([covered(a, b) for a, b in words])
    assert cov >= 0.95, cov
    # false activity: active time more than 1 s from every word
    t = np.arange(0, truth()["duration_s"], 0.01)
    act = np.zeros_like(t, dtype=bool)
    for s, e in segs:
        act |= (t >= s) & (t < e)
    near = np.zeros_like(act)
    for a, b in words:
        near |= (t >= a - 1.0) & (t < b + 1.0)
    assert (act & ~near).sum() * 0.01 <= 1.0


def test_level_norm_is_shared(synth_run):
    _, done = synth_run
    metas = {k: v["meta"] for k, v in done["curves"]["stems"].items() if k.endswith(".level")}
    lo = {round(m["lo"], 6) for m in metas.values()}
    hi = {round(m["hi"], 6) for m in metas.values()}
    assert len(lo) == 1 and len(hi) == 1


def test_unconfirmed_vocals_are_not_present(tmp_path):
    """A 'vocals' stem that the independent model does not hear (MEGAFAUNA's synth leads) gets present=false."""
    import shutil

    from mvh.io.wav import read_wav, write_wav

    ups, ing = fixture_upstreams(SYNTH)
    fast = tmp_path / "fast_up"
    shutil.copytree(ups["separate_fast"], fast)
    x, sr = read_wav(fast / "fast" / "vocals.wav")
    write_wav(fast / "fast" / "vocals.wav", np.zeros_like(x), sr)   # htdemucs hears no vocals at all
    ups["separate_fast"] = str(fast)
    out, done = run_stage("stem_activity", tmp_path, ups, ing)
    with open(out / "meta/stems.json", encoding="utf-8") as fh:
        meta = json.load(fh)
    st = meta["stems"]
    assert st["vocals"]["present_energy"] is True
    assert st["vocals"]["present"] is False and st["vocals"]["conf"] < 0.4
    assert "vocals:unconfirmed" in meta["flags"]
    assert any("vocals" in w for w in done["result"]["warnings"])


# ------------------------------------------------------------------------------------------------ real songs (explicit)
REAL_EXPECT = {
    # slug: (vocals present, vocals conf range) -- snapshot with tolerances, from the W0 stems
    "megafauna": (False, (0.0, 0.45)),
    "versatile": (True, (0.5, 0.9)),
    "jeremy": (True, (0.9, 1.0)),
    "newton-vs-nye": (True, (0.9, 1.0)),
}


@pytest.mark.real
@pytest.mark.parametrize("slug", sorted(REAL_EXPECT))
def test_real_song_vocal_presence(slug, tmp_path):
    fx = real_fixture(slug)
    if not (fx / "stems").is_dir():
        pytest.skip(f"no fixture {fx}")
    ups, ing = fixture_upstreams(fx)
    # the W0 adapter has no cache-only SW vocals: provide them from the W0 cache when present
    sw = fx.parents[1] / ".cache" / "real" / slug / "sep" / "vocals_sw.wav"
    hq = tmp_path / "hq"
    if sw.is_file():
        import shutil

        shutil.copytree(fx / "stems", hq / "stems")
        shutil.copytree(fx / "meta", hq / "meta")
        from mvh.io import audio as aio

        (hq / "sep").mkdir(parents=True)
        d = aio.decode(sw)
        aio.encode_flac(d.samples, d.sr, hq / "sep" / "vocals_sw.flac")
        ups["separate_hq"] = str(hq)
    out, _ = run_stage("stem_activity", tmp_path, ups, ing)
    with open(out / "meta/stems.json", encoding="utf-8") as fh:
        st = json.load(fh)["stems"]
    present, (lo, hi) = REAL_EXPECT[slug]
    assert st["vocals"]["present"] is present
    assert lo <= st["vocals"]["conf"] <= hi
