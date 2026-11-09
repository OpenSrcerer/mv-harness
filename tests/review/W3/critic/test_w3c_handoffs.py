"""W3C-5 (M5 lyrics -> voices/lipsync/meaning, R16 and R11): in dense rap the last word of every line is held up
to 1.5 s into the next line, so at each rapper hand-off two characters "sing" at once.

lyrics core `_finalise_line` extends a line's last word on the vocal envelope by up to 1.5 s with no limit at the
next line's first word (the limit only applies inside a line). In Newton vs Nye the vocal stem never drops while
the next rapper starts, so 47 of 53 consecutive line pairs overlap (median 1.4 s, max 1.5 s): the outgoing word
keeps running under the incoming line. Downstream:
- events/singing.json rows of different voices on different lines overlap for 7.0 s in total, all at the hand-offs;
- the per-voice `vocal.mouth_open.<V>` curves (gated by those word spans) have two voices open for 6.7 s;
- `singer_at(t)` returns two different characters at the hand-offs and duplicate entries for the same character on
  47 % of the sung instants (one per overlapping row).
A character agent animates both rappers' mouths exactly when the battle switches between them.
"""

from __future__ import annotations

import numpy as np


def test_w3c_rap_words_do_not_run_into_the_next_line(real_folder):
    f = real_folder("newton-vs-nye")
    ly = f.json("lyrics/lyrics.json")
    first = {}
    last_end = {}
    for w in ly["words"]:
        first.setdefault(w["line_id"], w["t"])
        last_end[w["line_id"]] = max(last_end.get(w["line_id"], 0.0), w["t"] + w["d"])
    lines = ly["lines"]
    over = [last_end[a["id"]] - first[b["id"]] for a, b in zip(lines, lines[1:])
            if a["id"] in last_end and b["id"] in first]
    bad = [o for o in over if o > 0.05]
    assert len(bad) <= 0.1 * len(over), (f"newton-vs-nye: in {len(bad)} of {len(over)} consecutive line pairs the last "
                                         f"word ends after the next line's first word (median overlap {np.median(bad):.2f} s)")


def test_w3c_one_character_at_a_rapper_handoff(real_folder):
    f = real_folder("newton-vs-nye")
    sg = f.events("singing")
    overlap = 0.0
    for i, a in enumerate(sg):
        for b in sg[i + 1:]:
            if b["t"] >= a["t"] + a["d"]:
                break
            if b["voice_id"] != a["voice_id"] and b["line_id"] != a["line_id"]:
                overlap += min(a["t"] + a["d"], b["t"] + b["d"]) - b["t"]
    assert overlap <= 1.0, (f"newton-vs-nye: singing rows of different voices on different lines overlap for "
                            f"{overlap:.1f} s (rapper hand-offs show two singers)")


def test_w3c_per_voice_mouths_do_not_overlap_at_handoffs(real_folder):
    f = real_folder("newton-vs-nye")
    song = f.song()
    mo = [c for c in song.channel_ids if c.startswith("vocal.mouth_open.")]
    assert len(mo) >= 3
    dur = song.manifest["source"]["duration_s"]
    ts = np.arange(0.0, dur, 0.02)
    m = np.array([[song.curve(c).at(t) for t in ts] for c in mo])
    both = float(((m > 0.1).sum(axis=0) >= 2).sum() * 0.02)
    assert both <= 1.5, f"newton-vs-nye: two or more per-voice mouth curves are open (> 0.1) for {both:.1f} s"


def test_w3c_singer_at_lists_each_character_once(real_folder):
    f = real_folder("newton-vs-nye")
    song = f.song()
    dup = n = 0
    for t in np.arange(0.0, song.manifest["source"]["duration_s"], 0.1):
        s = song.singer_at(float(t))
        if not s:
            continue
        n += 1
        keys = [(x["character_id"], x["voice_id"]) for x in s]
        dup += len(keys) != len(set(keys))
    assert dup <= 0.02 * n, f"newton-vs-nye: singer_at returns the same character twice on {dup} of {n} sung instants"
