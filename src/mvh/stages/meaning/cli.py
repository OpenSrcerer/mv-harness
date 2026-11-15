"""``mvh meaning <song folder> [--edit | --init] [--editor CMD] [--draft agent|anthropic|off] [--overwrite-draft]``
(D35 module verb, PLAN §8).

Re-merges the user's ``meaning/intent.md`` and the draft ``meaning/authored.json`` into meaning.json (re-anchoring
per-section claims to the current sections, orphans to orphans.json), refreshes singing.json, lines.tsv, the
interview and brief.md. It runs every stage that reads ``meaning/intent.md`` or ``meaning/authored.json`` and the
stages downstream of them (voices, lipsync, meaning, brief, viewer); unchanged ones are cache hits.

``--draft anthropic`` first asks the Claude API to draft the gaps into ``meaning/authored.json`` (opt-in: sends the
lyrics too unless the song keeps them from agents). An existing authored.json is never replaced unless
``--overwrite-draft`` is given.

``--init`` creates ``meaning/intent.md`` from the interview's template when it does not exist, and stops. ``--edit``
does the same, opens the file in an editor (``--editor``, MVH_EDITOR / VISUAL / EDITOR, VS Code, vim, Notepad: see
edit.py), waits for it to close, then applies the answers. An existing intent.md is never rewritten.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

__all__ = ["register", "cmd_meaning", "meaning_stages"]


def meaning_stages(specs) -> list[str]:
    """The stages ``mvh meaning`` runs: every stage that reads a file under ``meaning/`` (intent.md, authored.json),
    plus everything downstream of one. voices reads intent.md too (the voice mapping, D51), so editing intent.md
    makes it stale; running only meaning and brief would then refuse with 'upstream not done: voices (stale)'.
    On-demand stages (frames) are left out."""
    names = {n for n, sp in specs.items()
             if any(str(e.path).startswith("meaning/") for e in (sp.external_inputs or ()))}
    names |= {n for n in ("meaning", "brief") if n in specs}
    grew = True
    while grew:
        grew = False
        for n, sp in specs.items():
            if n not in names and sp.trigger != "on_demand" and set(sp.deps) & names:
                names.add(n)
                grew = True
    return [n for n in specs if n in names]


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("meaning", help="re-merge intent.md + authored.json (re-anchor), refresh singing/lines/brief")
    p.add_argument("folder", help="song folder (out/<slug>) made by mvh analyze")
    p.add_argument("--edit", action="store_true",
                   help="create meaning/intent.md from the template if missing, open it in an editor, then apply it")
    p.add_argument("--init", action="store_true",
                   help="only create meaning/intent.md from the template (never replaces an existing file)")
    p.add_argument("--editor", default=None,
                   help='editor for --edit, e.g. "code --wait" (default: MVH_EDITOR, VISUAL, EDITOR, VS Code, vim, Notepad)')
    p.add_argument("--draft", choices=("agent", "anthropic", "off"), default=None,
                   help="anthropic: draft the gaps with the Claude API into meaning/authored.json first")
    p.add_argument("--overwrite-draft", action="store_true", help="allow --draft anthropic to replace authored.json")
    p.add_argument("--no-lyrics-to-agents", action="store_true", help="keep lyric text out of lines.tsv and drafts")
    p.add_argument("--threads", type=int, default=None)
    p.set_defaults(func=cmd_meaning)


def cmd_meaning(a: argparse.Namespace) -> int:
    from mvh.io import atomic
    from mvh.runner import run as rr
    from mvh.runner.spec import load_stage_specs

    folder = Path(a.folder)
    prev = rr.load_run_settings(folder)
    if not prev.get("params_ext", {}).get("input"):
        print(f"mvh meaning: {folder} is not a song folder made by mvh analyze", file=sys.stderr)
        return 2
    if a.init or a.edit:
        from .edit import EditError, init_intent, open_editor

        try:
            intent_path, created = init_intent(folder)
            print(f"mvh meaning: {'created' if created else 'found'} {intent_path}", file=sys.stderr)
            if not a.edit:
                print(json.dumps({"intent": str(intent_path), "created": created}, ensure_ascii=False))
                return 0
            cmd = open_editor(intent_path, a.editor)
            print(f"mvh meaning: edited with {Path(cmd[0]).name}; applying", file=sys.stderr)
        except EditError as e:
            print(f"mvh meaning: {e}", file=sys.stderr)
            return 2
    cli_params = {k: dict(v) for k, v in (prev.get("cli_params") or {}).items()}
    mp = cli_params.setdefault("meaning", {})
    if a.no_lyrics_to_agents:
        mp["lyrics_to_agents"] = False
    if a.draft:
        mp["draft"] = a.draft
    lyrics_ok = bool(mp.get("lyrics_to_agents", True))
    if a.draft == "anthropic":
        from .llm_draft import DraftError, draft_with_anthropic

        dst = folder / "meaning" / "authored.json"
        if dst.is_file() and not a.overwrite_draft:
            print("mvh meaning: meaning/authored.json exists; pass --overwrite-draft to replace it", file=sys.stderr)
            return 2
        try:
            doc = draft_with_anthropic(folder, lyrics_to_agents=lyrics_ok,
                                       log=lambda m: print(m, file=sys.stderr))
        except DraftError as e:
            print(f"mvh meaning: {e}", file=sys.stderr)
            return 1
        atomic.write_text(dst, json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    only = meaning_stages(load_stage_specs())
    s = rr.Settings(
        song=None, song_dir=folder.resolve(), slug=prev.get("slug") or folder.name,
        profile=prev.get("profile", "max"), threads=a.threads or rr._env_threads(), only=tuple(only),
        offline=True, heavy_locks=os.environ.get("MVH_HEAVY_LOCKS", "1") != "0",
        params_ext=dict(prev.get("params_ext", {})), cli_params=cli_params,
    )
    res = rr.analyze(s)
    m = folder / "meaning" / "meaning.json"
    status = None
    if m.is_file():
        with open(m, encoding="utf-8") as fh:
            status = json.load(fh).get("status")
    not_run = [n for n in ("meaning", "brief") if n in (res.get("pending") or [])]
    report = {"meaning": str(m), "status": status, "brief": res.get("brief"),
              "warnings": res.get("warnings", []), "failed": res.get("failed")}
    if not_run:
        # --only cannot run a stage whose upstream is stale or missing: the files on disk are the old ones
        report["not_run"] = not_run
        print(f"mvh meaning: {', '.join(not_run)} did not run (upstream not cached or stale); "
              "run `mvh analyze` on the folder first", file=sys.stderr)
    print(json.dumps(report, ensure_ascii=False))
    return 1 if (res.get("failed") or not_run) else 0
