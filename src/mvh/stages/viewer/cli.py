"""``mvh view <song>``: open the viewer in EDIT MODE (CONTRACT D35: verbs come from stages/<name>/cli.py)."""
from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path


def _resolve(song: str) -> Path | None:
    p = Path(song)
    if p.is_dir():
        return p
    import os

    from mvh.io.paths import repo_root

    root = Path(os.environ["MVH_OUT"]) if os.environ.get("MVH_OUT") else repo_root() / "out"
    q = root / song
    return q if q.is_dir() else None


def cmd_view(a: argparse.Namespace) -> int:
    from .server import make_server

    folder = _resolve(a.song)
    if folder is None:
        print(f"mvh: no song folder for {a.song!r} (give a folder or a slug under out/)", file=sys.stderr, flush=True)
        return 2
    if not (folder / "viewer.html").is_file():
        print(f"mvh: {folder} has no viewer.html: run `mvh analyze` first", file=sys.stderr, flush=True)
        return 2
    srv = make_server(folder, port=a.port, idle_timeout=a.idle_timeout, allow_rerun=not a.no_rerun, edit=not a.read_only)
    srv.start()
    print(json.dumps({"url": srv.url, "folder": str(srv.folder), "edit": srv.edit, "port": srv.port, "idle_timeout_s": srv.idle_timeout}), flush=True)
    print(f"mvh: viewer at {srv.url}  (Ctrl+C to stop; stops itself after {int(srv.idle_timeout)} s without a request)", file=sys.stderr, flush=True)
    if not a.no_open:
        try:
            webbrowser.open(srv.url)
        except Exception:  # noqa: BLE001
            pass
    try:
        reason = srv.wait()
    except KeyboardInterrupt:
        srv.shutdown()
        reason = "interrupted"
    print(f"mvh: viewer server stopped ({reason})", file=sys.stderr, flush=True)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("view", help="open the song viewer; edit mode saves corrections to overrides.json")
    p.add_argument("song", help="song folder, or a slug under out/")
    p.add_argument("--port", type=int, default=0, help="TCP port on 127.0.0.1 (0 = any free port)")
    p.add_argument("--idle-timeout", type=float, default=900.0, help="stop after this many seconds without a request (0 = never)")
    p.add_argument("--no-open", action="store_true", help="do not open a browser; just print the URL")
    p.add_argument("--read-only", action="store_true", help="serve the folder without edit mode")
    p.add_argument("--no-rerun", action="store_true", help="hide the Re-run button (the viewer still tells which stages will re-run)")
    p.set_defaults(func=cmd_view)
