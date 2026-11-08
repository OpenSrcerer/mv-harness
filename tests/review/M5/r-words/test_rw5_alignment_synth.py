# ruff: noqa: E501
"""R-WORDS M5 (major x2): word alignment on the synthetic song with a correct line-synced LRC.

Input: the fixture's own ``_truth/lyrics_input.lrc`` with the A2 word tags removed, i.e. an LRC whose line
timestamps are EXACT (the common LRCLIB case: line sync, no word sync). Clean TTS lead vocals.

Finding A (end to end): line L008 (truth 29.00-30.97 s, three words) comes out with its first word stretched over
26.82-35 s and its last two words at 35.06 / 35.36 s, inside line L009 (truth 34.5 s): onset errors -2.2 / +5.6 /
+5.6 s, L008 and L009 interleave, and the song still grades **A** (G5 = 0.9: only one of 10 lines off). The same
happens after any global shift (+-1.3, 2.5, 4 s: offset detected correctly, same 5.6 s error). Causes:
  * the line group [L001..L008] runs to L008's expected end (= L009's start) + 2 s context, so the group window
    contains the start of L009 (next group) and CTC parks "it comes" there; nothing keeps a group's words before
    the next group's first expected line start, and no cross-line monotonicity check exists;
  * the emissions just before the 30 s window seam are degraded (see the seam test below), so the true location
    scores low;
  * ASR repair (M5-D12) has the right ASR times (28.72 / 29.14 / 29.48 s, p 0.76-1.0) but rejects the re-alignment
    because the misplaced words' own score (mean 0.42, inflated by the wrong placement) sets the bar at 0.5 x 0.42.

Finding A2 (seam): ``MmsAligner.emissions`` uses 30 s windows with only 2 s of right context. Frames in the last
~1.3 s before a seam come out blank-dominated: on the synth, 28.7-30.0 s has 0 % non-blank frames with the
production settings but 8-14 % with a whole-file pass or 4 s of context, and L008 aligned alone in its true span
scores 0.17 / 0.14 / 0.24 in [28.1, 30.6] s (vs 0.57 / 0.50 / 0.42 with 4 s context; the seam test below, window
[28.4, 31.37] s, measures a mean of 0.243). Swept over 12 leading-silence pads (606 word
placements): words ending < 1 s before a seam score 0.51 (vs 0.70 with 6 s context) and 5-10 % of words ending
< 3 s before a seam fall below 0.10 (0 % with 6 s context); away from seams the two settings agree (0.725 / 0.71).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.models

REPO = Path(__file__).resolve().parents[4]
SYNTH = REPO / "tests" / "contract" / "synth"
TRUTH = json.loads((SYNTH / "_truth" / "truth.json").read_text(encoding="utf-8"))


def _line_only_lrc(dst: Path) -> Path:
    src = (SYNTH / "_truth" / "lyrics_input.lrc").read_text(encoding="utf-8")
    out = []
    for ln in src.splitlines():
        ln = re.sub(r"<\d+:\d+(?:\.\d+)?>\s?", "", ln).rstrip()
        out.append(ln)
    dst.write_text("\n".join(out) + "\n", encoding="utf-8")
    return dst


@pytest.fixture(scope="module")
def line_synced_run(tmp_path_factory):
    from tests.synth.m5.harness import Harness, slot

    tmp = tmp_path_factory.mktemp("rw5_lines")
    lrc = _line_only_lrc(tmp / "lines.lrc")
    h = Harness(SYNTH, tmp)
    with slot("r-words-m5:review-test", threads=6):
        h.run("lyrics", params_ext={"lyrics": str(lrc)})
    return h.json("lyrics", "lyrics/lyrics.json")


def test_line_synced_lrc_places_every_word_within_one_second(line_synced_run):
    d = line_synced_run
    tw = TRUTH["words"]
    assert len(d["words"]) == len(tw)
    err = np.array([w["t"] - t["t"] for w, t in zip(d["words"], tw)])
    bad = [(w["id"], round(float(e), 2)) for w, e in zip(d["words"], err) if abs(e) > 1.0]
    assert not bad, f"words placed > 1 s from the truth with an exact line-synced LRC: {bad} (grade {d['grade']})"


def test_lines_do_not_interleave(line_synced_run):
    """In a single-voice passage the words of line i must end before line i+1 starts (L008 vs L009)."""
    d = line_synced_run
    by = {}
    for w in d["words"]:
        by.setdefault(w["line_id"], []).append(w)
    lines = sorted(d["lines"], key=lambda ln: ln["t"])
    cross = []
    for a, b in zip(lines, lines[1:]):
        if a["backing"] or b["backing"]:
            continue
        last_start = max(w["t"] for w in by[a["id"]])
        if last_start > b["t"]:
            cross.append((a["id"], b["id"], round(last_start - b["t"], 2)))
    assert not cross, f"a line's words start after the next line has started: {cross}"


def test_emissions_before_a_window_seam_are_not_degraded():
    """L008 (truth 29.0-30.97 s) ends 0.03 s before the 30 s seam: aligned alone in its true span it must score
    like the rest of the song (G3 threshold 0.30), not like a miss."""
    from tests.synth.m5.harness import slot

    from mvh.io import audio as aio
    from mvh.runner import models
    from mvh.stages.lyrics import align as A
    from mvh.stages.lyrics import text as TX

    lead = aio.decode(SYNTH / "stems" / "lead_vocals.flac", sr=16000, mono=True).samples[0]
    words = [w for w in TRUTH["words"] if w["line_id"] == "L008"]
    h = models.handle("mms_fa")
    with slot("r-words-m5:review-test", threads=6):
        al = A.MmsAligner(next(iter(h.files.values())), 6)
        lp = al.emissions(lead, 30.0, 2.0)              # the stage defaults (window_s, context_s)
    tm = TX.TokenMaker(al.dictionary, "en")
    t0, t1 = words[0]["t"] - 0.6, words[-1]["t"] + words[-1]["d"] + 0.4
    r = A.align_window(lp, int(t0 / A.FR), int(np.ceil(t1 / A.FR)), [tm.tokens(w["text"]) for w in words])
    score = float(np.mean([x["score"] for x in r]))
    nonblank = float(np.mean(np.argmax(lp[int(28.7 / A.FR):int(30.0 / A.FR)], 1) != 0))
    assert score >= 0.30 and nonblank > 0.0, f"mean token score {score:.3f}, non-blank frames before the seam {nonblank:.2f}"
