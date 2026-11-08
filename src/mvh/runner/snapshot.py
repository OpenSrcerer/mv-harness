"""Determinism snapshots (NF1): hash every file of a song folder except the volatile ones, and diff two
snapshots.

    python -m mvh.runner.snapshot hash <song-folder> <out.json>
    python -m mvh.runner.snapshot diff <a.json> <b.json>        (exit 1 and list the files that differ)

Excluded: ``.cache/`` and ``run.json`` (volatile by contract). Stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

__all__ = ["snapshot", "diff", "main", "EXCLUDE"]

EXCLUDE = ("run.json",)


def snapshot(folder: Path | str) -> dict[str, str]:
    folder = Path(folder)
    out: dict[str, str] = {}
    for p in sorted(folder.rglob("*")):
        rel = p.relative_to(folder).as_posix()
        if not p.is_file() or rel.startswith(".cache/") or rel in EXCLUDE:
            continue
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for b in iter(lambda: fh.read(1 << 22), b""):
                h.update(b)
        out[rel] = h.hexdigest()
    return out


def diff(a: dict[str, str], b: dict[str, str]) -> list[str]:
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) == 3 and argv[0] == "hash":
        snap = snapshot(argv[1])
        Path(argv[2]).write_text(json.dumps(snap, indent=0, sort_keys=True) + "\n", encoding="utf-8")
        print(f"{len(snap)} files hashed")
        return 0 if snap else 1
    if len(argv) == 3 and argv[0] == "diff":
        a = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        b = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
        d = diff(a, b)
        for k in d:
            print(f"differs: {k}")
        print(f"{len(d)} of {len(set(a) | set(b))} files differ")
        return 1 if d else 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
