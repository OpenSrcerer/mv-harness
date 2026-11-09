# ruff: noqa: E501  (long docstrings)
"""R-ML review M3a, finding F2 (rounds 1-2), updated in round 3 to the behaviour the fix round chose.

The classifier path (no DrumSep sub-stems: the htdemucs fallback) cannot deliver hat and cymbal at the PLAN §7 gates
from one mixed drum stem (clean generator drum stem, round 3: kick 0.977, snare 0.967, hat 0.793, tom 1.000, cymbal
0.444). Round 2 asked for one of: leave hat / cymbal out, scale their vel and envelopes by the confidence cap, or a
manifest-level flag. fixer-m3a-r2 scales hat / cymbal ``vel`` by 0.45 (raw value in ``vel_raw``; the choreo / cues
packs read ``t, drum, vel`` and the ``drums.*`` envelopes follow vel) and adds the fallback
``drums:low_confidence(hat,cymbal)``. Round 3 verified this on the stage (synthetic separated drum stem, path=classifier:
hat / cymbal vel <= 0.45, conf <= 0.45, kick vel up to 1.0). These tests hold that behaviour and the PLAN gates on the
classes the path does claim (kick, snare, tom). Synthetic input only (fast).
"""
from __future__ import annotations

import json
import shutil
import sys

from m3a_rml_util import REPO, SYNTH, scores, truth


def test_classifier_path_meets_plan_f1_on_its_reliable_classes():
    from mvh.io import audio as aio
    from mvh.stages.drums import core

    d = aio.decode(SYNTH / "stems" / "drums.flac")
    hits, _ = core.classify(d.samples, d.sr)
    f1 = scores([{"t": h.t, "drum": h.drum} for h in hits], truth()["drum_hits"])
    assert set(core.CLASSIFIER_RELIABLE) == {"kick", "snare", "tom"}
    failing = {k: f1[k] for k in core.CLASSIFIER_RELIABLE if f1[k] < (0.9 if k in ("kick", "snare") else 0.7)}
    assert not failing, f"classifier path below the PLAN §7 gates on kick / snare / tom: {failing} (all: {f1})"


def test_classifier_path_weighs_hat_and_cymbal_down_where_the_consumers_read(tmp_path):
    sys.path.insert(0, str(REPO))
    from tests.synth.m3a import fixture_upstreams, run_stage

    ups, ing = fixture_upstreams(SYNTH)
    hq = tmp_path / "hq"
    (hq / "stems").mkdir(parents=True)
    shutil.copy(SYNTH / "stems" / "drums.flac", hq / "stems" / "drums.flac")
    shutil.copytree(SYNTH / "meta", hq / "meta")
    ups["separate_hq"] = str(hq)
    sa, _ = run_stage("stem_activity", tmp_path, ups, ing)
    ups["stem_activity"] = str(sa)
    out, done = run_stage("drums", tmp_path, ups, ing)
    with open(out / "events" / "drum_hits.json", encoding="utf-8") as fh:
        items = json.load(fh)["items"]
    low = [it for it in items if it["drum"] in ("hat", "cymbal")]
    assert low and max(it["vel"] for it in low) <= 0.45 + 1e-6 and max(it["conf"] for it in low) <= 0.45 + 1e-6
    assert max(it["vel"] for it in items if it["drum"] == "kick") > 0.9   # the reliable classes keep their full weight
    fb = done["result"]["fallbacks"]
    assert "drums:classifier" in fb and "drums:low_confidence(hat,cymbal)" in fb
