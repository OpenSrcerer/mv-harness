"""Create ``meaning/intent.md`` from the interview's template and open it in an editor (``mvh meaning --init / --edit``),
and type a draft's suggestions into it (``--suggest``).

The file is CREATED here when it does not exist. An existing intent.md is the user's: it is only changed when the user
asks for it with ``--suggest``, and then only in two ways: empty template fields are filled with the draft's value
followed by the ``# suggestion`` marker, and lines that already carry the marker are refreshed. Every other byte stays
as it was. A marked line is not an answer (see intent.py, SUGGESTIONS), so nothing the user did not confirm becomes
theirs. (The viewer's managed block is the viewer's code, not this module.)

Editor choice, first match wins:
  1. ``--editor CMD``, then the environment: ``MVH_EDITOR``, ``VISUAL``, ``EDITOR`` (a command line, e.g. ``code --wait``)
  2. VS Code (``code --wait``) when it is on PATH
  3. a terminal editor on PATH (``nvim``, ``vim``, ``vi``), only when stdin is a terminal
  4. Notepad on Windows
The call blocks until the editor closes the file, so the caller can apply the answers right after.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

__all__ = ["EditError", "template_from_interview", "starter_text", "init_intent", "find_editor", "open_editor",
           "add_suggestions", "suggest_into", "suggestions_of"]

_HINT = (
    "<!-- meaning/intent.md: what this song means to you. The questions are in meaning/interview.md.\n"
    "     1. Fill in the template below. Anything that MUST be obeyed goes there; do_not holds the only hard rules.\n"
    "        Empty fields mean 'no answer'. Keep each section's t0/t1 lines.\n"
    "     2. Under 'sections', answer once per group first ('every section', then 'every drop', ...). Fill in a\n"
    "        single section only where it differs from its group.\n"
    "     3. A line that ends with '# suggestion' was typed in from a draft. It is NOT your answer yet: delete the\n"
    "        '# suggestion' marker to make it yours (change the text first if you like). Lines you leave marked\n"
    "        stay a draft, and agents see them labelled as a draft.\n"
    "     4. Write anything else as plain text under the template: agents read it as your notes, never as rules.\n"
    "     Then run:  mvh meaning <song folder>     (or save and close this file if you opened it with --edit) -->\n"
)

#: terminal editors tried when nothing is configured and VS Code is absent
_TERMINAL_EDITORS = ("nvim", "vim", "vi")


class EditError(RuntimeError):
    pass


def template_from_interview(interview_md: str) -> str:
    """The fenced ``yaml`` block under the interview's '## Template' heading, without its fence lines."""
    lines = interview_md.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith("## Template")), None)
    if start is None:
        raise EditError("meaning/interview.md has no '## Template' section")
    i = next((k for k in range(start, len(lines)) if lines[k].lstrip().startswith("```")), None)
    if i is None:
        raise EditError("meaning/interview.md has no fenced template block")
    j = next((k for k in range(i + 1, len(lines)) if lines[k].lstrip().startswith("```")), len(lines))
    body = "\n".join(lines[i + 1:j]).strip("\n")
    if not body.strip():
        raise EditError("the template block in meaning/interview.md is empty")
    return body


def starter_text(interview_md: str) -> str:
    """The first intent.md: a hint (an HTML comment, which the parser ignores) and the fenced template."""
    return _HINT + "\n```yaml\n" + template_from_interview(interview_md) + "\n```\n\n"


def _read_meaning(folder: Path) -> dict[str, Any]:
    try:
        with open(Path(folder) / "meaning" / "meaning.json", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def init_intent(folder: Path) -> tuple[Path, bool]:
    """Create ``<folder>/meaning/intent.md`` from the interview template when it does not exist. A new file gets
    the draft's suggestions (marked ``# suggestion``, so they are not answers) when the song has a draft.

    Returns (path, created). An existing file is returned untouched."""
    from mvh.io import atomic

    mdir = Path(folder) / "meaning"
    dst = mdir / "intent.md"
    if dst.is_file():
        return dst, False
    src = mdir / "interview.md"
    if not src.is_file():
        raise EditError(f"{src} does not exist yet: run `mvh analyze` on the song first")
    with open(src, encoding="utf-8") as fh:
        text = starter_text(fh.read())
    text, _n = add_suggestions(text, _read_meaning(folder))
    atomic.write_text(dst, text)
    return dst, True


# ---------------------------------------------------------------------------------------------- suggestions (D81)
#: per-section fields a suggestion can fill: (template key, meaning.json key)
_SEC_FIELDS = (("feel", "feel"), ("meaning", "meaning"), ("movement", "movement_hint"), ("camera", "camera_hint"),
               ("palette", "palette_hint"))
_EMPTY_VALUES = ("", '""', "''", "[]")


def _yaml_value(v: Any) -> str:
    from .docs import _q

    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_q(x) for x in v) + "]"
    return _q(v)


def suggestions_of(meaning: Mapping[str, Any]) -> dict[str, Any]:
    """What a draft suggests, read from meaning.json (fields whose source is ``draft``):
    ``song`` {key: value}, ``groups`` [(group key, field, value, section ids)] with 'all' first, ``sections``
    {(section id, field): value} and ``rules`` (do-not rules the draft suggests)."""
    fs = meaning.get("field_sources") or {}
    song: dict[str, Any] = {}
    for k in ("logline", "summary", "setting", "tone"):
        if fs.get(k) == "draft" and meaning.get(k):
            song[k] = meaning[k]
    if fs.get("themes") == "draft":
        themes = [str(t.get("text")) for t in meaning.get("themes") or [] if isinstance(t, dict) and t.get("text")]
        if themes:
            song["themes"] = themes
    if fs.get("palette") == "draft" and meaning.get("palette"):
        song["palette"] = list(meaning["palette"])
    groups = []
    for g in sorted(meaning.get("section_defaults") or [], key=lambda g: g.get("key") != "all"):
        for tk, mf in _SEC_FIELDS:
            if (g.get("field_sources") or {}).get(mf) == "draft" and g.get(mf):
                groups.append((str(g["key"]), tk, g[mf], list(g.get("section_ids") or [])))
    sections: dict[tuple[str, str], Any] = {}
    for s in meaning.get("sections") or []:
        for tk, mf in _SEC_FIELDS:
            if (s.get("field_sources") or {}).get(mf) == "draft" and s.get(mf):
                sections[(str(s["section_id"]), tk)] = s[mf]
    return {"song": song, "groups": groups, "sections": sections,
            "rules": [str(r) for r in meaning.get("suggested_do_not") or [] if str(r).strip()]}


def _canon(path: tuple[str, ...]) -> tuple[str, ...]:
    """A template key path with its group key normalised: ('sections', 'Every Drops', 'feel') -> (..., 'every drop', ...)."""
    from .anchor import group_key

    if len(path) >= 2 and path[0] == "sections":
        g = group_key(path[1])
        if g is not None:
            return ("sections", "every section" if g == "all" else f"every {g}", *path[2:])
    return path


def add_suggestions(text: str, meaning: Mapping[str, Any]) -> tuple[str, int]:
    """``text`` (an intent.md) with the draft's suggestions typed into its template: an EMPTY field gets the draft's
    value and the ``# suggestion`` marker, and a line that already carries the marker is refreshed (or emptied when
    the draft no longer suggests anything for it). Suggested do-not rules become marked items under ``do_not``.
    Fields the user filled in, free text and the viewer block are not touched.

    A suggestion shared by every section of a group goes to the group's entry (``every drop``) when the template
    has one, and is then not repeated on each section. Returns (new text, number of marked lines)."""
    from .intent import (
        _PATH_KEY,
        SUGGESTION_MARK,
        _cut_comment,
        _expand_indent,
        is_suggested,
        line_paths,
        template_regions,
    )

    sug = suggestions_of(meaning or {})
    lines, regions = template_regions(text)
    if not regions:
        return text, 0
    nl = "\r\n" if "\r\n" in text else "\n"
    info: dict[int, tuple[tuple[str, ...], str, bool]] = {}   # line -> (canonical path, 'indent key:', fillable)
    first: dict[tuple[str, ...], int] = {}
    rule_items: list[int] = []                                 # marked list items under the top-level do_not
    do_not_line: int | None = None
    for a, b in regions:
        paths = line_paths(lines[a:b])
        last: tuple[str, ...] = ()
        for k, p in enumerate(paths):
            i = a + k
            if p is None:
                if last == ("do_not",) and is_suggested(lines[i]):
                    rule_items.append(i)
                continue
            last = p
            e = _expand_indent(lines[i])
            head = e[:_PATH_KEY.match(e).end()]
            marked = is_suggested(lines[i])
            value = _cut_comment(e)[len(head):].strip()
            cp = _canon(p)
            info[i] = (cp, head, marked or value in _EMPTY_VALUES)
            first.setdefault(cp, i)
            if cp == ("do_not",) and do_not_line is None:
                do_not_line = i

    def slot(path: tuple[str, ...]) -> int | None:
        i = first.get(path)
        return i if i is not None and info[i][2] else None

    targets: dict[int, Any] = {}
    for k, v in sug["song"].items():
        i = slot((k,))
        if i is not None:
            targets[i] = v
    covered: dict[str, set[str]] = {}
    for gk, f, v, ids in sug["groups"]:
        i = slot(("sections", "every section" if gk == "all" else f"every {gk}", f))
        if i is not None and not set(ids) <= covered.get(f, set()):
            targets[i] = v
            covered.setdefault(f, set()).update(ids)
    for (sid, f), v in sug["sections"].items():
        i = slot(("sections", sid, f))
        if i is not None and sid not in covered.get(f, set()):
            targets[i] = v
    out: list[str] = []
    drop = set(rule_items)
    n = len(targets)
    for i, ln in enumerate(lines):
        if i in drop:
            continue
        if i in targets:
            out.append(f"{info[i][1]} {_yaml_value(targets[i])}{SUGGESTION_MARK}")
        elif i in info and is_suggested(ln):
            out.append(f"{info[i][1]} " + ("[]" if info[i][0][-1] in ("palette", "themes") else '""'))
        else:
            out.append(ln)
        if i == do_not_line and info[i][2] and not is_suggested(ln):
            out.extend(f"  - {_yaml_value(r)}{SUGGESTION_MARK}" for r in sug["rules"])
            n += len(sug["rules"])
    new = nl.join(out) + (nl if text.endswith(("\n", "\r")) else "")
    return new, n


def suggest_into(folder: Path) -> tuple[Path, bool, int]:
    """Create intent.md if needed, then type the draft's suggestions into its empty template fields.

    Returns (path, created, number of lines marked ``# suggestion``)."""
    from mvh.io import atomic

    dst, created = init_intent(folder)
    with open(dst, encoding="utf-8", newline="") as fh:
        text = fh.read()
    new, n = add_suggestions(text, _read_meaning(folder))
    if new != text:
        atomic.write_bytes(dst, new.encode("utf-8"))
    return dst, created, n


def _split(cmd: str) -> list[str]:
    parts = shlex.split(cmd, posix=(os.name != "nt"))
    return [p[1:-1] if len(p) >= 2 and p[0] == p[-1] and p[0] in "\"'" else p for p in parts]


def find_editor(explicit: str | None = None, *, interactive: bool | None = None) -> list[str] | None:
    """The editor command (argv without the file), or None when nothing usable is found."""
    for cand in (explicit, os.environ.get("MVH_EDITOR"), os.environ.get("VISUAL"), os.environ.get("EDITOR")):
        if cand and cand.strip():
            argv = _split(cand.strip())
            exe = shutil.which(argv[0]) or (argv[0] if Path(argv[0]).is_file() else None)
            if exe is None:
                raise EditError(f"editor not found: {argv[0]!r}")
            return [exe, *argv[1:]]
    code = shutil.which("code")
    if code:
        return [code, "--wait"]
    if interactive is None:
        interactive = bool(sys.stdin and sys.stdin.isatty())
    if interactive:
        for name in _TERMINAL_EDITORS:
            exe = shutil.which(name)
            if exe:
                return [exe]
    if os.name == "nt":
        notepad = shutil.which("notepad")
        if notepad:
            return [notepad]
    return None


def open_editor(path: Path, explicit: str | None = None) -> list[str]:
    """Open ``path`` and wait until the editor closes it. Returns the command that ran."""
    argv = find_editor(explicit)
    if argv is None:
        raise EditError("no editor found: set MVH_EDITOR (e.g. `code --wait`), or pass --editor")
    cmd = [*argv, str(path)]
    try:
        rc = subprocess.run(cmd, check=False).returncode
    except OSError as e:
        raise EditError(f"could not start the editor {argv[0]!r}: {e}") from e
    if rc != 0:
        raise EditError(f"the editor exited with code {rc}; nothing was applied")
    return cmd
