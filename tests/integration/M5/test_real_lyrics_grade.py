"""Seam S03 (M5): Jeremy's lyrics come from a synced LRCLIB entry with the exact duration; the lines that exist align
well (G2-G5 pass), but the text has no lines for the sung outro (about 70 s of vocal phrases after 217 s). The ASR
hears the outro, so the ASR-vs-text agreement G1 lands at 0.697 against 0.70 and the whole file is graded D ("wrong
text"), which tells every agent not to trust correct timings. The outro is wordless singing (W0), so it is flagged for
review instead of filled with lines (M5-D52)."""

from __future__ import annotations


def test_real_jeremy_correct_synced_text_is_not_graded_wrong_text(real_song):
    s = real_song("jeremy")
    lyr = s.json("lyrics/lyrics.json")
    checks = lyr["gate"]["checks"]
    assert lyr["source"]["kind"] == "lrclib" and abs(lyr["source"].get("duration_diff_s") or 0) < 1
    assert all(checks[k]["pass"] is not False for k in ("G2", "G3", "G4", "G5"))
    # G1 should be judged on the span the text covers: ASR words in an uncovered outro are no evidence of a wrong text
    assert lyr["grade"] != "D", f"grade {lyr['grade']} (G1 {checks['G1']['value']})"


def test_real_jeremy_sung_outro_is_flagged_for_review(real_song):
    """W3 (integrator-r2): W0 measured Jeremy's 217-300 s outro as WORDLESS singing (bench-words §2: no VAD words, 22
    low-confidence no-VAD words), so filling it with lines would invent lyrics. The stage instead reports the vocal time
    after the last line (M5-D52: lyrics.json alignment.vocals_after_last_line_s) and warns for review; both fixer M5 r3/r4
    and the M5 verifier (r4-m3) agreed the old assertion (< 20 s of phrases after the last line) was wrong."""
    s = real_song("jeremy")
    lyr = s.json("lyrics/lyrics.json")
    lines = lyr["lines"]
    vp = s.events("vocal_phrases")
    last_line = max(ln["t"] + ln["d"] for ln in lines)
    sung_after = sum(p["d"] for p in vp if p["t"] > last_line + 2)
    tail = (lyr.get("alignment") or {}).get("vocals_after_last_line_s")
    assert tail is not None, "lyrics.json does not report the vocals after the last line (M5-D52)"
    if sung_after >= 20:
        # a long sung tail without lines must be visible to agents and reviewers
        assert tail >= 20, (f"{sung_after:.0f} s of vocal phrases after the last line, but lyrics reports only "
                            f"{tail:.0f} s of lead vocals there")
        run = s.json("run.json")
        warns = [w for w in (run["stages"].get("lyrics") or {}).get("warnings") or [] if "after the last lyric line" in str(w)]
        assert warns, "no review warning for the sung outro without lines"
