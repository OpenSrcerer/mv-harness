# ruff: noqa: E501  (long data tables / docstrings in generated-fixture code)
"""Every ID in the synthetic fixture links: sections <-> phrases <-> bars <-> counts <-> lines <-> voices <-> characters <-> cues."""

import csv
import re

import pytest
from tests.synth.stubrun import load_json

from mvh.contract import ids as I

pytestmark = pytest.mark.timeout(300)


def _rows(p, sep=","):
    with open(p, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=sep))


def _numbered_in_time_order(items, kind):
    got = [it["id"] for it in items if it["id"] != "E000"]
    assert got == [I.make_id(kind, k) for k in range(1, len(got) + 1)], kind
    ts = [it["t"] for it in items]
    assert ts == sorted(ts)


def test_ids_numbered_in_time_order(ev):
    for name, kind in (
        ("sections", "section"),
        ("phrases", "phrase"),
        ("counts", "eight"),
        ("cues", "cue"),
        ("hit_points", "hit_point"),
        ("holds", "hold"),
        ("impacts", "impact"),
        ("stops", "stop"),
        ("silences", "silence"),
        ("decay_tails", "decay_tail"),
        ("vocal_phrases", "vocal_phrase"),
        ("edm_roles", "edm_role"),
    ):
        _numbered_in_time_order(ev[name], kind)
    assert (
        ev["counts"][0]["id"] == "E000" and ev["counts"][0]["lead_in"] and ev["counts"][0]["first_count"] == 5
    )


def test_beats_bars(ev):
    beats, bars = ev["beats"], ev["bars"]
    assert [b["beat_index"] for b in beats] == list(range(len(beats)))
    by_bar = {}
    for b in beats:
        by_bar.setdefault(b["bar"], []).append(b)
    for bar in bars:
        bs = by_bar[bar["bar"]]
        assert bs[0]["beat_index"] == bar["first_beat"] and len(bs) == bar["n_beats"]
        assert abs(bs[0]["t"] - bar["t"]) < 1e-6
        assert all(b["beats_in_bar"] == bar["beats_in_bar"] for b in bs)
    pick = bars[0]
    assert pick["bar"] == 0 and pick["pickup"] and by_bar[0][0]["beat_in_bar"] == 4  # D12
    assert [b["bar"] for b in bars if b["beats_in_bar"] == 3] == [16]


def test_sections_phrases_bars(ev, synth):
    secs = {s["id"]: s for s in ev["sections"]}
    bars = {b["bar"]: b for b in ev["bars"]}
    for p in ev["phrases"]:
        s = secs[p["section_id"]]
        assert (
            s["start_bar"] <= p["start_bar"] and p["start_bar"] + p["n_bars"] <= s["start_bar"] + s["n_bars"]
        )
        assert abs(p["t"] - bars[p["start_bar"]]["t"]) < 1e-6
    for s in ev["sections"]:
        assert abs(s["t"] - bars[s["start_bar"]]["t"]) < 1e-6
        assert s["occurrence_label"] == I.occurrence_label(s["label"], s["occurrence"])
    phr = {p["id"] for p in ev["phrases"]}
    groove_ids = {g["id"] for g in load_json(synth / "meta/grooves.json")["grooves"]}
    for r in _rows(synth / "tables/bars.csv"):
        b = int(r["bar"])
        assert (r["section_id"] == "") == (b == 0)
        if r["section_id"]:
            s = secs[r["section_id"]]
            assert s["start_bar"] <= b < s["start_bar"] + s["n_bars"]
            assert r["phrase_id"] in phr
        if r["groove_id"]:
            assert r["groove_id"] in groove_ids
    for e in ev["edm_roles"]:
        assert e["section_id"] in secs


def test_counts_link_phrases_and_beats(ev, synth):
    phr = {p["id"]: p for p in ev["phrases"]}
    beats = ev["beats"]
    for c in ev["counts"]:
        assert len(c["accents"]) == c["len"]
        if c["lead_in"]:
            continue
        p = phr[c["phrase_id"]]
        assert c["section_id"] == p["section_id"]
        b0 = beats[c["start_beat"]]
        assert p["start_bar"] <= b0["bar"] < p["start_bar"] + p["n_bars"]
        assert abs(c["t"] - b0["t"]) < 1e-6
    # every phrase starts a new count (restart rule)
    starts = {c["start_beat"] for c in ev["counts"]}
    bars = {b["bar"]: b for b in ev["bars"]}
    for p in ev["phrases"]:
        assert bars[p["start_bar"]]["first_beat"] in starts
    eights = {c["id"] for c in ev["counts"]}
    for r in _rows(synth / "tables/beats.csv"):
        assert r["eight_id"] == "" or r["eight_id"] in eights


def test_lyrics_voices_characters(ev, synth):
    lyr = load_json(synth / "lyrics/lyrics.json")
    secs = {s["id"]: s for s in ev["sections"]}
    lines = {ln["id"]: ln for ln in lyr["lines"]}
    words = {w["id"]: w for w in lyr["words"]}
    for ln in lyr["lines"]:
        s = secs[ln["section_id"]]
        assert s["t"] - 1e-6 <= ln["t"] and ln["t"] + ln["d"] <= s["t"] + s["d"] + 1e-6
        assert ln["first_word"] in words and words[ln["first_word"]]["line_id"] == ln["id"]
        assert sum(1 for w in lyr["words"] if w["line_id"] == ln["id"]) == ln["n_words"]
    for w in lyr["words"]:
        ln = lines[w["line_id"]]
        assert ln["t"] - 1e-6 <= w["t"] and w["t"] + w["d"] <= ln["t"] + ln["d"] + 1e-6
    tg = {}
    for ln in lyr["lines"]:
        tg.setdefault(ln["text_group"], set()).add(ln["text"])
    assert all(len(v) == 1 for v in tg.values())
    voices = {v["id"]: v for v in load_json(synth / "meta/voices.json")["voices"]}
    for s in ev["voice_spans"]:
        assert s["line_id"] in lines and s["voice_id"] in voices
        assert I.split_word_id(s["first_word"])[0] == s["line_id"] == I.split_word_id(s["last_word"])[0]
    meaning = load_json(synth / "meaning/meaning.json")
    chars = {c["id"]: c for c in meaning["characters"]}
    for c in chars.values():
        assert set(c["voice_ids"]) <= set(voices)
        assert set(c["line_ids"]) <= set(lines)
        assert set(c["section_ids"]) <= set(secs)
    for v in voices.values():
        assert v["proposed_character_id"] in chars
    for it in ev["singing"]:
        assert (
            it["character_id"] in chars
            and it["voice_id"] in chars[it["character_id"]]["voice_ids"]
            and it["line_id"] in lines
        )
    tsv = _rows(synth / "lyrics/lines.tsv", "\t")
    assert [r["id"] for r in tsv] == list(lines)
    for r in tsv:
            assert set(r["singer"].split("+")) <= set(chars) and r["section_id"] == lines[r["id"]]["section_id"]
    for s in meaning["sections"]:
        sec = secs[s["section_id"]]
        assert abs(s["t0"] - sec["t"]) < 1e-6 and abs(s["t1"] - (sec["t"] + sec["d"])) < 1e-6
        assert set(s["characters_present"]) <= set(chars)
    for m in meaning["motifs"]:
        assert all(o.get("line_id") in lines for o in m["occurrences"])
    for v in ev["visemes"]:
        assert v["voice_id"] in voices and (v["line_id"] is None or v["line_id"] in lines)
    for p in ev["phonemes"]:
        assert p["word_id"] in words or I.split_word_id(p["word_id"])[0] in lines


_REF = re.compile(r"^(beat|bar):(-?\d+)$")


def _resolve(src, synth, cache={}):
    m = _REF.match(src["id"])
    if m:
        kind, k = m.group(1), int(m.group(2))
        items = load_json(synth / src["file"])["items"]
        key = "beat_index" if kind == "beat" else "bar"
        return any(it[key] == k for it in items)
    doc = load_json(synth / src["file"])
    return any(it.get("id") == src["id"] for it in doc["items"])


def test_cues_and_derived_sources_resolve(ev, synth):
    for name in ("cues", "holds"):
        for it in ev[name]:
            assert _resolve(it["source"], synth), (name, it)
    for h in ev["hit_points"]:
        for s in h["sources"]:
            assert _resolve(s, synth), h
    cues = {c["id"]: c for c in ev["cues"]}
    for m in ev["moments"]:
        assert m["cue_id"] in cues and abs(cues[m["cue_id"]]["t"] - m["t"]) < 1e-6
    for c in ev["cues"]:
        if c["tier"] == 4:
            assert c["kind"] == "beat" and c["strength"] is None and c["lead_in_s"] is None
    t1 = sorted({c["t"] for c in ev["cues"] if c["tier"] == 1})
    for c in ev["cues"]:
        nxt = next((t for t in t1 if t > c["t"] + 1e-9), None)
        assert (c["next_major_in_s"] is None) == (nxt is None)
    drop = next(c for c in ev["cues"] if c["kind"] == "drop")
    build = next(r for r in ev["edm_roles"] if r["role"] == "build")
    assert abs(drop["lead_in_s"] - (drop["t"] - build["t"])) < 1e-6
    for m in ev["mood"]:
        assert any(s["id"] == m["section_id"] for s in ev["sections"])
