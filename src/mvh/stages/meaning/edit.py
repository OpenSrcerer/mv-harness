"""Create ``meaning/intent.md`` from the interview's template and open it in an editor (``mvh meaning --init / --edit``).

The file is only ever CREATED here, when it does not exist: an existing intent.md is the user's and is never rewritten
(the viewer's managed block is the one exception, and that is the viewer's code, not this module).

Editor choice, first match wins:
  1. ``--editor CMD``, then the environment: ``MVH_EDITOR``, ``VISUAL``, ``EDITOR`` (a command line, e.g. ``code --wait``)
  2. VS Code (``code --wait``) when it is on PATH
  3. a terminal editor on PATH (``nvim``, ``vim``, ``vi``), only when stdin is a terminal
  4. Notepad on Windows
The call blocks until the editor closes the file, so the caller can apply the answers right after.
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

__all__ = ["EditError", "template_from_interview", "starter_text", "init_intent", "find_editor", "open_editor"]

_HINT = (
    "<!-- meaning/intent.md: what this song means to you. The questions are in meaning/interview.md.\n"
    "     1. Fill in the template below. Anything that MUST be obeyed goes there; do_not holds the only hard rules.\n"
    "        Empty fields mean 'no answer'. Keep each section's t0/t1 lines.\n"
    "     2. Write anything else as plain text under the template: agents read it as your notes, never as rules.\n"
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


def init_intent(folder: Path) -> tuple[Path, bool]:
    """Create ``<folder>/meaning/intent.md`` from the interview template when it does not exist.

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
    atomic.write_text(dst, text)
    return dst, True


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
