"""lipsync: the sustain-extended gate on synthetic envelopes, and the stage on the synthetic song's TRUTH lyrics
and voice spans (copied from tests/contract/synth): per-voice channels, duet overlap, ungated fallback, Rhubarb
visemes (when Rhubarb is installed) and g2p phonemes. No ML models; Rhubarb runs on synthetic TTS only."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from mvh.stages.lipsync.core import find_rhubarb, gate_for_words

REPO = Path(__file__).resolve().parents[3]
SYNTH = REPO / "tests" / "contract" / "synth"


def test_gate_holds_to_next_word_and_sustains_last():
    n = 1000
    env = np.zeros(n)
    env[100:400] = 1.0          # a sustained note until 4.0 s
    words = [{"t": 1.0, "d": 0.2}, {"t": 1.8, "d": 0.2}, {"t": 2.5, "d": 0.3}]
    g = gate_for_words(words, env, floor=0.1, n=n, pad=0.08, max_hold=1.5)
    assert g[150] == 1 and g[170] == 1          # word 1 held to word 2's start (gap 1.2-1.8 s)
    assert g[350] == 1                            # last word held while the note sustains (2.8 -> 4.0 s)
    assert g[420] == 0                            # ... but not past the note
    env2 = np.ones(n)
    g2 = gate_for_words(words, env2, floor=0.1, n=n, pad=0.08, max_hold=1.5)
    assert g2[int((2.8 + 1.5 + 0.08) * 100) + 3] == 0        # the hold is capped at 1.5 s


@pytest.fixture(scope="module")
def synth_lipsync(tmp_path_factory):
    from tests.synth.m5.harness import Harness
    from tests.synth.m5.harness import slot as heavy

    h = Harness(SYNTH, tmp_path_factory.mktemp("lipsync"))
    with heavy("builder-m5:lipsync-test", threads=3):      # Rhubarb's recogniser is real inference
        rec = h.run("lipsync", stub_deps=("lyrics", "voices"))
    return h, rec


@pytest.mark.models
def test_channels_and_shapes(synth_lipsync):
    h, rec = synth_lipsync
    mo = h.curve("lipsync", "vocal.mouth_open")
    v1 = h.curve("lipsync", "vocal.mouth_open.V1")
    v2 = h.curve("lipsync", "vocal.mouth_open.V2")
    n = -(-2491650 * 100 // 44100)
    assert len(mo) == len(v1) == len(v2) == n
    assert np.all((mo >= 0) & (mo <= 1)) and np.allclose(mo, np.maximum(mo, np.maximum(v1, v2)))
    assert np.allclose(mo, np.maximum(v1, v2), atol=1e-6) or rec["result"]["summary"]["ungated_fallback_s"] > 0


@pytest.mark.models
def test_per_voice_gating_follows_truth(synth_lipsync):
    h, _ = synth_lipsync
    v1 = h.curve("lipsync", "vocal.mouth_open.V1")
    v2 = h.curve("lipsync", "vocal.mouth_open.V2")
    truth = json.loads((SYNTH / "_truth" / "truth.json").read_text(encoding="utf-8"))
    # call-and-response verse: L001 (V1) and L002 (V2); inside V1's words only V1 opens and vice versa
    for w in truth["words"]:
        if w["line_id"] not in ("L001", "L002", "L003", "L004"):
            continue
        a, b = int(w["nucleus"][0] * 100) + 2, int(w["nucleus"][1] * 100) - 2
        mine, other = (v1, v2) if w["voice"] == "V1" else (v2, v1)
        assert mine[a:b].max() > 0.05, w["id"]
        assert other[a:b].max() < 0.02, w["id"]
    # duet chorus: both voices sing L005 (V2 on backing) -> both channels open somewhere in it
    a, b = int(17.1 * 100), int(20.3 * 100)
    assert v1[a:b].max() > 0.05 and v2[a:b].max() > 0.05
    # the instrumental tail (after the last word + hold) is closed
    assert v1[4500:5000].max() < 0.02 and v2[4500:5000].max() < 0.02


@pytest.mark.models
def test_summary_and_phonemes(synth_lipsync):
    h, rec = synth_lipsync
    s = rec["result"]["summary"]
    assert s["voices"] == 2 and "vocal.mouth_open.V1" in s["channels"]
    assert s["energy_outside_gate"] < 0.15
    ph = h.json("lipsync", "lipsync/phonemes.json")
    assert ph["kind"] == "segment" and len(ph["items"]) > 100
    assert {it["voice_id"] for it in ph["items"]} == {"V1", "V2"}
    assert all(it["word_id"].startswith("L") for it in ph["items"])


@pytest.mark.models
@pytest.mark.skipif(find_rhubarb() is None, reason="Rhubarb not installed")
def test_visemes(synth_lipsync):
    h, rec = synth_lipsync
    vis = h.json("lipsync", "lipsync/visemes.json")
    items = vis["items"]
    assert items and set(it["viseme"] for it in items) <= set("ABCDEFGHX")
    assert {it["voice_id"] for it in items} == {"V1", "V2"}
    for v in ("V1", "V2"):
        vs = sorted((it for it in items if it["voice_id"] == v), key=lambda it: it["t"])
        assert vs[0]["t"] == 0.0 and abs(vs[-1]["t"] + vs[-1]["d"] - 56.5) < 0.02     # whole timeline per voice
        assert all(abs(a["t"] + a["d"] - b["t"]) < 0.002 for a, b in zip(vs, vs[1:]))  # no gaps, no overlaps
    open_in_words = [it for it in items if it["viseme"] != "X" and it["line_id"]]
    assert len(open_in_words) > 30
    assert not list((h.work / "_scratch").glob("**/*.txt"))                          # dialog files deleted
