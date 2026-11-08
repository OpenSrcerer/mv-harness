r"""Thin wrapper around ``mvh models`` (the only downloader since W1b; logic in src/mvh/runner/models.py).

    python scripts/fetch_models.py [--only ID,ID] [--env main|sep|ffmpeg] [--jobs N]   ->  mvh models fetch
    ...
    python scripts/fetch_models.py --verify [--only ID,ID]                               ->  mvh models
    verify ...
    python scripts/fetch_models.py --list                                                ->  mvh models list

Stdlib only (mvh.runner.models imports nothing else), so it also runs with the bare Python 3.12 before the
venv
exists. models.lock.json is authoritative: a file whose SHA-256 differs from the lock is an error and is never
re-pinned. Pinning NEW entries is a lock edit (a change request), not something this script does any more;
the W0
pinning spec lives in the history of this file.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="wrapper around: mvh models fetch|verify|list")
    ap.add_argument("--only")
    ap.add_argument("--env")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--verify", action="store_true", help="mvh models verify (re-hash against the lock)")
    ap.add_argument("--list", action="store_true", help="mvh models list")
    ap.add_argument("--lock-only", action="store_true", help="same as --verify (kept for W0 compatibility)")
    a = ap.parse_args(argv)
    from mvh.cli import main as mvh_main

    action = "list" if a.list else "verify" if (a.verify or a.lock_only) else "fetch"
    args = ["models", action]
    if a.only:
        args += ["--only", a.only]
    if action == "fetch":
        if a.env:
            args += ["--env", a.env]
        args += ["--jobs", str(a.jobs)]
    return mvh_main(args)


if __name__ == "__main__":
    sys.exit(main())
