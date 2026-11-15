"""``mvh meaning --init / --edit`` helpers: the starter intent.md and the editor choice. Synthetic text only."""
from __future__ import annotations

import sys

import pytest

from mvh.stages.meaning import edit as E
from mvh.stages.meaning.intent import parse_intent

INTERVIEW = """# Interview: A Song

1. **What does this song mean to you?**

## Template (copy into meaning/intent.md)

Copy the block below.

```yaml
# mvh-intent v2: copy this block into meaning/intent.md
logline: ""
palette: []   # hex (#1b2a49) or colour words (night blue)
do_not:   # rules in your own words
sections:
  S01:   # intro#1 0:00.0-0:15.4
    t0: 0.021
    t1: 15.358
    feel: ""
```

Trailing prose.
"""


def test_template_is_the_fenced_block_without_its_fence():
    t = E.template_from_interview(INTERVIEW)
    assert t.startswith("# mvh-intent v2") and t.rstrip().endswith('feel: ""')
    assert "```" not in t and "Trailing prose" not in t and "Copy the block" not in t


def test_template_missing_is_an_error():
    with pytest.raises(E.EditError):
        E.template_from_interview("# Interview\n\nno template here\n")
    with pytest.raises(E.EditError):
        E.template_from_interview("## Template\n\nno fence\n")


def test_untouched_starter_answers_nothing():
    it = parse_intent(E.starter_text(INTERVIEW))
    assert not it["do_not"] and not it["notes"] and not it["palette"] and it["logline"] is None


def test_filled_starter_is_read_as_template_and_notes():
    text = E.starter_text(INTERVIEW).replace('logline: ""', 'logline: "A small light in an empty town"')
    text = text.replace("do_not:   # rules in your own words", "do_not:\n  - never show faces")
    text += "The town is flooded.\n"
    it = parse_intent(text)
    assert it["logline"] == "A small light in an empty town"
    assert it["do_not"] == ["never show faces"]
    assert it["notes"] == ["The town is flooded."]


def test_init_creates_once_and_never_overwrites(tmp_path):
    (tmp_path / "meaning").mkdir()
    with pytest.raises(E.EditError):
        E.init_intent(tmp_path)                       # no interview yet
    (tmp_path / "meaning" / "interview.md").write_text(INTERVIEW, encoding="utf-8")
    p, created = E.init_intent(tmp_path)
    assert created and p.name == "intent.md" and "mvh-intent v2" in p.read_text(encoding="utf-8")
    p.write_text("my own words\n", encoding="utf-8")
    p2, created2 = E.init_intent(tmp_path)
    assert p2 == p and not created2 and p.read_text(encoding="utf-8") == "my own words\n"


def _which(found):
    return lambda name: found.get(name)


def test_editor_order(monkeypatch):
    for k in ("MVH_EDITOR", "VISUAL", "EDITOR"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(E.shutil, "which", _which({"code": "/x/code", "vim": "/x/vim", "notepad": "/x/notepad"}))
    assert E.find_editor(interactive=True) == ["/x/code", "--wait"]            # VS Code first
    monkeypatch.setattr(E.shutil, "which", _which({"vim": "/x/vim", "notepad": "/x/notepad"}))
    assert E.find_editor(interactive=True) == ["/x/vim"]                       # then vim, in a terminal
    if sys.platform == "win32":
        assert E.find_editor(interactive=False) == ["/x/notepad"]              # no terminal: Notepad
    monkeypatch.setattr(E.shutil, "which", _which({}))
    if sys.platform != "win32":
        assert E.find_editor(interactive=True) is None


def test_configured_editor_wins_and_keeps_its_arguments(monkeypatch):
    monkeypatch.setattr(E.shutil, "which", _which({"code": "/x/code", "subl": "/x/subl", "nano": "/x/nano"}))
    monkeypatch.setenv("EDITOR", "nano")
    monkeypatch.setenv("MVH_EDITOR", "subl --wait")
    assert E.find_editor(interactive=True) == ["/x/subl", "--wait"]            # MVH_EDITOR before EDITOR
    assert E.find_editor("nano -w", interactive=True) == ["/x/nano", "-w"]     # --editor before the environment
    monkeypatch.setenv("MVH_EDITOR", "does-not-exist")
    with pytest.raises(E.EditError):
        E.find_editor(interactive=True)


def test_open_editor_reports_a_failing_editor(monkeypatch, tmp_path):
    f = tmp_path / "intent.md"
    f.write_text("x", encoding="utf-8")
    ok = [sys.executable, "-c", "import sys; sys.exit(0)"]
    bad = [sys.executable, "-c", "import sys; sys.exit(3)"]
    monkeypatch.setattr(E, "find_editor", lambda explicit=None: ok)
    assert E.open_editor(f)[-1] == str(f)
    monkeypatch.setattr(E, "find_editor", lambda explicit=None: bad)
    with pytest.raises(E.EditError):
        E.open_editor(f)
    monkeypatch.setattr(E, "find_editor", lambda explicit=None: None)
    with pytest.raises(E.EditError):
        E.open_editor(f)


def test_mvh_meaning_runs_every_stage_that_reads_the_meaning_files():
    """Editing intent.md makes voices stale (it reads the voice mapping), so `mvh meaning` must run it and what
    follows it, not only meaning and brief; the on-demand frames stage stays out."""
    from mvh.runner.spec import load_stage_specs
    from mvh.stages.meaning.cli import meaning_stages

    specs = load_stage_specs()
    names = meaning_stages(specs)
    assert {"voices", "lipsync", "meaning", "brief", "viewer"} <= set(names)
    assert "frames" not in names and "ingest" not in names and "lyrics" not in names
    assert names == [n for n in specs if n in set(names)]          # in the registry's (dependency) order
