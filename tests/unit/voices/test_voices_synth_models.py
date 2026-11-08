# ruff: noqa: E501
"""voices on the synthetic song (two SAPI voices, call-and-response verse, duet chorus with the second voice on
backing_vocals) through ECAPA, on the fixture's TRUTH lyrics: the estimate finds 2 voices, >= 90 % of the lead
lines get the right voice (PLAN §7 gate for line attribution), the duet lines carry a backing span of the other
voice; with intent.md the count and the character proposals come from the user; overrides force a voice."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.models

REPO = Path(__file__).resolve().parents[3]
SYNTH = REPO / "tests" / "contract" / "synth"
TRUTH_SPANS = json.loads((SYNTH / "events" / "voice_spans.json").read_text(encoding="utf-8"))["items"]


def _run(tmp, intent=False, overrides=None):
    from tests.synth.m5.harness import Harness
    from tests.synth.m5.harness import slot as heavy

    h = Harness(SYNTH, tmp, overrides=overrides)
    if intent:
        (h.song_dir / "meaning").mkdir(parents=True, exist_ok=True)
        shutil.copy(SYNTH / "meaning" / "intent.md", h.song_dir / "meaning" / "intent.md")
    with heavy("builder-m5:voices-test", threads=6):
        rec = h.run("voices", stub_deps=("lyrics",))
    return h, rec


@pytest.fixture(scope="module")
def est(tmp_path_factory):
    return _run(tmp_path_factory.mktemp("est"))


def _lead_truth():
    # the lead voice of a line is the truth span with the highest confidence (0.9; the duet harmony is 0.75)
    best = {}
    for s in TRUTH_SPANS:
        if s["line_id"] not in best or s["conf"] > best[s["line_id"]]["conf"]:
            best[s["line_id"]] = s
    return {k: v["voice_id"] for k, v in best.items()}


def test_estimate_two_voices_and_line_attribution(est):
    h, rec = est
    meta = h.json("voices", "meta/voices.json")
    assert meta["n_voices"] == 2 and meta["n_source"] == "estimate"
    spans = h.json("voices", "events/voice_spans.json")["items"]
    lead = {s["line_id"]: s["voice_id"] for s in spans if s["role"] == "lead"}
    truth = _lead_truth()
    ok = sum(1 for lid, v in truth.items() if lead.get(lid) == v)
    assert ok / len(truth) >= 0.9, (lead, truth)          # V ids by first appearance match the fixture's
    assert all(0 <= s["conf"] <= 1 for s in spans)
    act = h.json("voices", "events/voice_activity.json")["items"]
    assert {a["voice_id"] for a in act} == {"V1", "V2"}


def test_duet_backing_spans(est):
    h, _ = est
    spans = h.json("voices", "events/voice_spans.json")["items"]
    back = {s["line_id"]: s["voice_id"] for s in spans if s["role"] == "backing"}
    duet = {s["line_id"] for s in TRUTH_SPANS if s["conf"] < 0.9}           # L005, L006, L009, L010
    assert duet and set(back) >= duet - {"L010"} and all(back[k] == "V2" for k in back)


def test_intent_count_and_overrides(tmp_path):
    h, rec = _run(tmp_path, intent=True, overrides={"voices.lines": {"L003": "V2"}})
    meta = h.json("voices", "meta/voices.json")
    assert meta["n_source"] == "intent" and meta["n_voices"] == 2
    assert {v["id"]: v["proposed_character_id"] for v in meta["voices"]} == {"V1": "C1", "V2": "C2"}
    spans = h.json("voices", "events/voice_spans.json")["items"]
    s3 = [s for s in spans if s["line_id"] == "L003" and s["role"] == "lead"]
    assert s3 and s3[0]["voice_id"] == "V2" and s3[0]["conf"] == 1.0 and s3[0]["source"] == "override"
