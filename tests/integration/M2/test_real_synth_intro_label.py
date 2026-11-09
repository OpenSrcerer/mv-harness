"""Seam S09 (M2, minor): on the synthetic song (full real pipeline) the 4-bar intro is split into two 2-bar sections
labelled verse (truth: one intro), and the bridge is labelled verse. The boundaries themselves are fine (F 0.92)."""

from __future__ import annotations

import json

from tests.integration.conftest import REPO


def test_real_synth_intro_is_one_intro_section(real_song):
    s = real_song("synth")
    truth = json.loads((REPO / "tests/contract/synth/_truth/truth.json").read_text(encoding="utf-8"))
    secs = s.events("sections")
    t_intro_end = truth["sections"][1]["t"]
    intro = [x for x in secs if x["t"] < t_intro_end - 0.5]
    assert len(intro) == 1 and intro[0]["label"] == "intro", [(x["label"], round(x["t"], 2)) for x in intro]
