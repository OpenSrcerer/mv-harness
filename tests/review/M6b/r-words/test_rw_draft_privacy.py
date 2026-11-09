"""R-WORDS M6b F5 and F6 (major): draft text reaches places the privacy and quote rules forbid.

F5 (NF5, CONTRACT §1 "never ... error messages", D42): cites.check_claims reports a malformed citation id with
``{cid!r}`` and a bad motif occurrence with its raw ``line_id``. Both strings come from meaning/authored.json, where a
drafting LLM that puts a quote in the wrong key writes lyric text; the problem list becomes StageResult warnings,
which the runner copies into .cache/meaning/_mvh/done.json (verified with DevRun), manifest.json and run.json warnings
(runner/finalize.py) and the analyze stdout JSON. The builder's own rule (decisions M6b #9) is "Problems never quote text".

F6 (CONTRACT §12 / §1: lyric quotes in brief.md and meaning are <= 10 words; PLAN §8.4): only the ``quote`` field of a
citation is checked. A draft's free-text fields (logline, section meaning, theme text) are never compared with the
lyrics, and brief.md prints the logline in full, so a draft logline that quotes a whole verse puts > 10 consecutive
lyric words into the LLM entry point. (Synthetic, invented lyrics only.)
"""
from __future__ import annotations

import json

from rw_m6b_support import authored, brief_for, ngrams, source, synth_parts

from mvh.stages.meaning.stage import build

MARK = "ZQXMARKER sung words that must never reach a log"


def _bad_draft() -> dict:
    return {"schema": "mvh/files/meaning", "schema_version": "1.0.0-rc.1", "status": "draft",
            "themes": [{"text": "light", "source": "lyric", "cites": [{"id": MARK}]}],
            "motifs": [{"id": "M1", "name": "lanterns", "occurrences": [{"t": 9.0, "line_id": MARK}],
                        "provenance": {"source": "lyric", "status": "draft", "cites": []}}]}


def test_draft_citation_text_is_not_echoed_into_warnings():
    res = build(source(), None, _bad_draft(), {})
    leaked = [w for w in res["warnings"] + res["notes"] if "ZQXMARKER" in w]
    assert not leaked, f"{len(leaked)} warning(s) quote text from authored.json"


def _lyric_text() -> str:
    files, _ = synth_parts()
    return " ".join(ln["text"] for ln in files["lyrics/lyrics.json"]["lines"])


def test_draft_logline_quoting_a_verse_is_cut_before_brief():
    files, _ = synth_parts()
    lines = files["lyrics/lyrics.json"]["lines"]
    verse = " ".join(ln["text"] for ln in lines[:4])  # 17 words of the (invented) synthetic lyrics
    assert len(verse.split()) > 10
    dr = authored()
    dr["logline"] = f'"{verse}"'
    res = build(source(), None, dr, {})
    lyric_11 = ngrams(_lyric_text(), 11)
    brief = brief_for(res)
    n_brief = len(ngrams(brief, 11) & lyric_11)
    n_meaning = len(ngrams(json.dumps(res["meaning"], ensure_ascii=False), 11) & lyric_11)
    assert n_brief == 0, f"brief.md quotes more than 10 consecutive lyric words ({n_brief} 11-word runs)"
    assert n_meaning == 0, f"meaning.json quotes more than 10 consecutive lyric words ({n_meaning} 11-word runs)"
