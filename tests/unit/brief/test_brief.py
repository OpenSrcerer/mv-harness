"""brief.md: CONTRACT §12 order and caps, traceability of every decimal, privacy, section zooms, overflow."""
from __future__ import annotations

import io
import json
import re
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from mvh.stages.brief.build import (
    MAX_TOKENS,
    SECTION_MAX_TOKENS,
    TARGET_TOKENS,
    gather,
    render_brief,
    render_section,
    tokens,
)
from mvh.stages.brief.trace import decimals_in, folder_values, untraceable_numbers
from mvh.stages.meaning.source import FolderSource

ROOT = Path(__file__).resolve().parents[3]


def _brief(dr) -> str:
    return (Path(dr.upstream["brief"]["dir"]) / "brief.md").read_text(encoding="utf-8")


def test_synth_brief_contract_order_and_caps(synth_run):
    dr, song = synth_run
    text = _brief(dr)
    assert tokens(text) <= TARGET_TOKENS <= MAX_TOKENS
    lines = text.splitlines()
    assert lines[0].startswith("# Lanterns on the Tide")
    assert re.match(r"^meaning: (user|draft|pending) · lyrics: (grade [A-D]|none|instrumental|ungraded) · "
                    r"stems: (hq|degraded|absent) · visemes: (yes|no) · flags: ", lines[2])
    order = [text.index(h) for h in ("| field | value |", "## Meaning", "## Sections", "## Choreography",
                                     "## Top moments")]
    assert order == sorted(order)
    assert lines[-1] == "Loaders and file catalogue: SKILL.md and CONTRACT.md (lib/mvh.js, lib/mvh_load.py)."
    for field in ("duration", "tempo", "meter", "key", "loudness", "vocal range", "instrumentation"):
        assert f"| {field} |" in text
    for sid in ("S01", "S02", "S03", "S04", "S05", "S06"):
        assert f"| {sid} |" in text
    assert "| C1 |" in text and "| C2 |" in text
    assert '"Never show fire burning a person or a boat."' in text  # verbatim do-not rules
    moments = [ln for ln in lines if re.match(r"^\| \d+ \| \d", ln)]
    assert 1 <= len(moments) <= 15
    assert "R02" in text and "drop" in text and "E000" in text


def test_synth_brief_numbers_trace_to_files(synth_run):
    dr, song = synth_run
    text = _brief(dr)
    toks = decimals_in(text)
    assert len(toks) > 30
    assert untraceable_numbers(text, folder_values(song)) == []
    # instrumentation percentages are coverage x 100 (meta/instruments.json)
    inst = json.loads((song / "meta/instruments.json").read_text(encoding="utf-8"))
    for s in inst["summary"][:3]:
        assert f"{s['instrument']} {float(s['coverage']) * 100:.0f}%" in text


def test_trace_checker_catches_invented_numbers(synth_run):
    _dr, song = synth_run
    assert untraceable_numbers("tempo 123.457 BPM", folder_values(song)) == ["123.457"]


def test_no_lyric_text(synth_run):
    dr, song = synth_run
    text = _brief(dr)
    lyr = json.loads((song / "lyrics/lyrics.json").read_text(encoding="utf-8"))
    for ln in lyr["lines"]:
        assert ln["text"] not in text


def test_section_zooms(synth_run):
    dr, song = synth_run
    d = gather(FolderSource(song))
    lyr = json.loads((song / "lyrics/lyrics.json").read_text(encoding="utf-8"))
    for s in d["ev_sections"]:
        z = render_section(d, s["id"])
        assert tokens(z) <= SECTION_MAX_TOKENS
        assert z.startswith(f"# {s['id']} ")
        assert not any(ln["text"] in z for ln in lyr["lines"])
        assert untraceable_numbers(z, folder_values(song)) == []
    z5 = render_section(d, "S05")
    for want in ("R02", "## Meaning", "## Lines", "L009", "## Counts", "## Cues", "## Hits"):
        assert want in z5
    zl = render_section(d, "S05", allow_lyrics=True)
    quotes = re.findall(r'"([^"]+)"', zl.split("## Lines", 1)[1].split("##", 1)[0])
    assert quotes and all(len(q.replace(" ...", "").split()) <= 10 for q in quotes)
    with pytest.raises(KeyError):
        render_section(d, "S99")


def test_cli_brief_section(synth_run):
    from mvh.cli import main

    _dr, song = synth_run
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["brief", str(song), "--section", "s03"])
    assert rc == 0 and buf.getvalue().startswith("# S03 chorus#1")
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["brief", str(song)])
    assert rc == 0 and "## Sections" in buf.getvalue()


def _fake(n_sections: int, unique_groups: bool) -> dict:
    secs = []
    for i in range(n_sections):
        secs.append({"id": f"S{i + 1:02d}", "t": 10.0 * i, "d": 10.0, "label": ["verse", "chorus"][i % 2],
                     "occurrence": i // 2 + 1, "occurrence_label": f"{['verse', 'chorus'][i % 2]}#{i // 2 + 1}",
                     "repeat_group": (f"G{i}" if unique_groups else "AB"[i % 2]), "start_bar": 4 * i + 1, "n_bars": 4})
    lines = [{"id": f"L{i + 1:03d}", "t": 10.0 * i + 1, "d": 3.0, "section_id": f"S{i + 1:02d}", "_text": None}
             for i in range(n_sections)]
    meaning = {"status": "user", "logline": "x", "characters": [],
               "sections": [{"section_id": s["id"], "feel": "a long and winding feeling text " * 3,
                             "provenance": {"status": "user"}} for s in secs]}
    moments = [{"rank": k + 1, "t": 10.0 * k, "cue_id": f"Q{k + 1:04d}", "kind": "section",
                "description": "word " * 30} for k in range(20)]
    return {"flags": [], "ev_sections": secs, "lines": lines, "meaning": meaning, "ev_moments": moments,
            "ev_mood": [{"section_id": s["id"], "valence": 0.5, "arousal": 0.5, "tags": ["epic"]} for s in secs]}


def test_overflow_collapses_then_trims():
    text, info = render_brief(_fake(120, unique_groups=False))
    assert info["tokens"] <= MAX_TOKENS and info["collapsed"]
    assert "x60" in text  # one row per repeat group
    text2, info2 = render_brief(_fake(300, unique_groups=True))
    assert info2["tokens"] <= MAX_TOKENS and info2["trimmed_rows"] > 0 and "omitted to fit 4k tokens" in text2
    assert text2.count("| 1") >= 1 and "## Top moments" in text2


def test_pending_and_orphans_lines():
    d = _fake(4, False)
    d["meaning"] = {"status": "pending", "characters": [], "sections": []}
    d["orphans"] = {"orphans": [{"old_section_id": "S09"}]}
    text, _ = render_brief(d)
    assert "meaning: pending" in text and "meaning/interview.md" in text
    assert "meaning:orphans=1" in text and "**Warning**" in text


def test_user_notes_and_the_obey_line_ud1(synth_run):
    """UD1 (D78): the user's free text reaches brief.md verbatim as notes (direction, never rules), the do-not line names
    the template as the only source of rules, and the brief says where anything that must be obeyed goes."""
    dr, _song = synth_run
    text = _brief(dr)
    assert "User notes (2, user-authored" in text and '"## The story Two figures keep a harbour town lit' in text
    assert "Do not (the user's words, from the intent template: the only hard rules)" in text
    assert "Anything that must be obeyed goes in the template of meaning/intent.md (do_not)" in text
    d = _fake(4, False)
    long_note = " ".join(f"w{i}" for i in range(300))
    d["meaning"] = {"status": "user", "characters": [], "sections": [], "notes": [long_note, "second note"],
                    "field_sources": {"notes": "user"}}
    t2, info = render_brief(d)
    assert '"w0 w1' in t2 and "w119 ..." in t2 and "w120" not in t2 and "- ... 1 more" in t2
    assert info["tokens"] <= MAX_TOKENS


REAL = ("megafauna", "versatile", "jeremy", "newton-vs-nye")


@pytest.mark.real
@pytest.mark.parametrize("slug", REAL)
def test_real_brief(tmp_path, m6b_runner, slug):
    fx = ROOT / "tests" / "contract" / f"real-{slug}"
    if not fx.is_dir():
        pytest.skip(f"{fx} missing")
    dr, song = m6b_runner(tmp_path, fx, intent=False, authored=False)
    text = _brief(dr)
    assert tokens(text) <= MAX_TOKENS
    secs = json.loads((fx / "events/sections.json").read_text(encoding="utf-8"))["items"]
    assert all(f"| {s['id']} |" in text for s in secs)
    assert untraceable_numbers(text, folder_values(song)) == []
    lyr = fx / "lyrics/lyrics.json"
    if lyr.is_file():
        for ln in json.loads(lyr.read_text(encoding="utf-8"))["lines"]:
            if len(ln["text"].split()) >= 3:
                assert ln["text"] not in text
    d = gather(FolderSource(song))
    for s in secs:
        assert tokens(render_section(d, s["id"])) <= SECTION_MAX_TOKENS
