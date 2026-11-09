"""The fixture's audio agrees with its truth: stems sum to the mix, onsets sit where the truth says, f0 matches the notes."""

import numpy as np
import pytest
from tests.synth.audio_io import decode, read_wav
from tests.synth.stubrun import load_json

pytestmark = pytest.mark.timeout(600)

STEMS = (
    "vocals",
    "lead_vocals",
    "backing_vocals",
    "drums",
    "bass",
    "guitar",
    "piano",
    "other",
    "instrumental",
)
SUBS = ("kick", "snare", "toms", "hihat", "ride", "crash")


@pytest.fixture(scope="module")
def audio(synth):
    a = {"mix": decode(synth / "audio/mix.flac")[0]}
    for s in STEMS:
        a[s] = decode(synth / f"stems/{s}.flac")[0]
    for s in SUBS:
        a[f"drums_{s}"] = decode(synth / f"stems/drums/{s}.flac")[0]
    return a


def test_lengths_and_rate(synth, audio):
    src = load_json(synth / "meta/source.json")
    for k, x in audio.items():
        assert x.shape == (2, src["n_samples"]), k
    canon, sr = read_wav(synth / "_intermediate/ingest/canonical.wav")
    assert sr == 44100 and np.array_equal(canon.astype(np.float32), audio["mix"].astype(np.float32))


def test_stems_sum_exactly(audio):
    m = audio["mix"]
    tol = 1e-9  # 24-bit grid: integer sums, exact in float
    assert np.max(np.abs(audio["vocals"] - audio["lead_vocals"] - audio["backing_vocals"])) < tol
    assert np.max(np.abs(audio["drums"] - sum(audio[f"drums_{s}"] for s in SUBS))) < tol
    six = audio["vocals"] + audio["drums"] + audio["bass"] + audio["guitar"] + audio["piano"] + audio["other"]
    assert np.max(np.abs(m - six)) < tol
    assert np.max(np.abs(audio["instrumental"] - (m - audio["vocals"]))) < tol
    assert np.max(np.abs(audio["guitar"])) == 0.0
    assert np.max(np.abs(m)) < 1.0


def test_input_file_tags_cover_and_decode(synth, audio):
    import subprocess

    from tests.synth.audio_io import ffprobe_exe

    inp = synth / "_truth/synth-song.flac"
    x, sr = decode(inp)
    assert sr == 44100 and np.array_equal(x, audio["mix"])
    r = subprocess.run(
        [
            ffprobe_exe(),
            "-v",
            "error",
            "-show_entries",
            "format_tags=title,artist,album:stream=codec_type",
            "-of",
            "json",
            str(inp),
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    import json

    info = json.loads(r.stdout)
    assert {s["codec_type"] for s in info["streams"]} == {"audio", "video"}  # attached cover art stream
    tags = {k.lower(): v for k, v in info["format"]["tags"].items()}
    src = load_json(synth / "meta/source.json")
    assert tags["title"] == src["tags"]["title"] and tags["artist"] == src["tags"]["artist"]


def test_silent_bar_is_digital_silence(audio, truth):
    sil = truth["silences"][0]
    a, b = int(round(sil["t"] * 44100)), int(round((sil["t"] + sil["d"]) * 44100))
    assert np.max(np.abs(audio["mix"][:, a:b])) == 0.0
    assert np.max(np.abs(audio["mix"][:, : int(0.5 * 44100)])) == 0.0  # pre-roll before the pickup


def _diff_energy(x, i0, i1):
    d = np.diff(x[:, max(i0, 1) - 1 : i1], axis=1)
    return float(np.sum(d * d))


@pytest.mark.parametrize(
    "drum,sub", [("kick", "kick"), ("snare", "snare"), ("hat", "hihat"), ("tom", "toms"), ("cymbal", "crash")]
)
def test_drum_onsets_match_truth(audio, ev, drum, sub):
    """At every truth hit the sub-stem's high-pass (first difference) energy jumps (2 ms after vs 4 ms before)."""
    x = audio[f"drums_{sub}"]
    hits = [h for h in ev["drum_hits"] if h["drum"] == drum and h.get("sub_stem", sub) == sub]
    assert hits
    bad = []
    prev = -1.0
    for h in hits:
        i = int(round(h["t"] * 44100))
        after = _diff_energy(x, i, i + 88) / 88
        before = _diff_energy(x, i - 176, i) / 176
        ratio = (
            10.0 if h["t"] - prev >= 0.15 else 1.5
        )  # dense rolls: the previous hit's tail is still ringing
        if not after > ratio * before + 1e-12:
            bad.append(h["t"])
        prev = h["t"]
    assert not bad, f"{drum}: onsets without a transient at {bad[:5]}"


def _f0_acf(x, sr, fmin=70.0, fmax=1000.0):
    x = x - x.mean()
    ac = np.correlate(x, x, "full")[x.size - 1 :]
    lo, hi = int(sr / fmax), int(sr / fmin)
    k = lo + int(np.argmax(ac[lo:hi]))
    if 0 < k < ac.size - 1:  # parabolic refinement
        a, b, c = ac[k - 1], ac[k], ac[k + 1]
        k = k + 0.5 * (a - c) / (a - 2 * b + c)
    return sr / k


def test_lead_vocal_pitch_matches_notes(audio, truth):
    lead = audio["lead_vocals"].mean(axis=0)
    checked = 0
    for w in truth["words"]:
        if w["d"] < 0.45:
            continue
        a, b = w["nucleus"]
        c = 0.5 * (a + b)
        i = int(round(c * 44100))
        seg = lead[i - 1024 : i + 1024]
        f0 = _f0_acf(seg, 44100)
        midi = 69 + 12 * np.log2(f0 / 440.0)
        assert abs(midi - w["midi"]) < 0.6, (w["id"], w["midi"], round(float(midi), 2))
        checked += 1
    assert checked >= 10


def test_vocal_curve_matches_word_notes(synth, truth):
    from mvh.contract import curvefile

    idx = curvefile.read_index(synth)
    midi, _ = curvefile.read_channel(synth, idx, "vocal.midi")
    for w in truth["words"]:
        a, b = (
            int(np.ceil((w["t"] + 0.05) * 100)),
            int(np.floor((w["t"] + w["d"]) * 100)),
        )  # skip the 40 ms glide-in
        seg = midi[a : b + 1]
        seg = seg[np.isfinite(seg)]
        if seg.size >= 5:
            assert abs(float(np.median(seg)) - w["midi"]) < 0.35, w["id"]  # vibrato +-0.3 st, 40 ms glide in
            assert np.mean(np.abs(seg - w["midi"]) <= 0.31) >= 0.8, w["id"]


def test_word_onsets_audible(audio, truth):
    """Each lead word starts with sound where the truth says (after a >= 25 ms gap of the same track)."""
    lead = audio["lead_vocals"].mean(axis=0)
    ws = sorted(truth["words"], key=lambda w: w["t"])
    prev_end = -1.0
    for w in ws:
        if w["t"] - prev_end >= 0.025:
            i = int(round(w["t"] * 44100))
            after = float(np.sqrt(np.mean(lead[i : i + 2205] ** 2)))
            before = float(np.sqrt(np.mean(lead[i - 441 : i] ** 2))) if i > 441 else 0.0
            assert after > 4 * before + 1e-6, (w["id"], after, before)
        prev_end = w["t"] + w["d"]
