"""``mvh brief <song folder> [--section S05] [--lyrics]`` (D35 module verb).

Without ``--section``: prints brief.md (or renders it from the folder when absent). With ``--section``: a <= 1.5k-token
zoom of one section (rows, lines by id, counts, hits, cues, meaning). ``--lyrics`` adds quotes of <= 10 words per
line, unless the song was analysed with lyrics kept from agents (``meaning.lyrics_to_agents=false``).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

__all__ = ["register", "cmd_brief"]


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("brief", help="print brief.md or a <= 1.5k-token zoom of one section (--section S05)")
    p.add_argument("folder", help="song folder (out/<slug>)")
    p.add_argument("--section", help="section id, e.g. S05")
    p.add_argument("--lyrics", action="store_true", help="quote <= 10 words of each line in the zoom")
    p.set_defaults(func=cmd_brief)


def _lyrics_allowed(folder: Path) -> bool:
    p = folder / ".cache" / "_run.json"
    if not p.is_file():
        return True
    try:
        with open(p, encoding="utf-8") as fh:
            prev = json.load(fh)
    except ValueError:
        return True
    return bool(((prev.get("cli_params") or {}).get("meaning") or {}).get("lyrics_to_agents", True))


def cmd_brief(a: argparse.Namespace) -> int:
    from mvh.stages.meaning.source import FolderSource

    from .build import gather, render_brief, render_section

    folder = Path(a.folder)
    if not folder.is_dir():
        print(f"mvh brief: no such folder: {folder}", file=sys.stderr)
        return 2
    src = FolderSource(folder)
    if not a.section and (folder / "brief.md").is_file():
        with open(folder / "brief.md", encoding="utf-8") as fh:
            sys.stdout.write(fh.read())
        return 0
    flags = list(((src.manifest().get("status") or {}).get("flags")) or [])
    d = gather(src, flags)
    if not a.section:
        text, _info = render_brief(d)
        sys.stdout.write(text)
        return 0
    allow = bool(a.lyrics) and _lyrics_allowed(folder)
    if a.lyrics and not allow:
        print("mvh brief: lyrics are kept from agents for this song (--no-lyrics-to-agents); ids only", file=sys.stderr)
    try:
        text = render_section(d, a.section.strip().upper(), allow_lyrics=allow)
    except KeyError as e:
        print(f"mvh brief: {e.args[0]}", file=sys.stderr)
        return 2
    sys.stdout.write(text)
    return 0
