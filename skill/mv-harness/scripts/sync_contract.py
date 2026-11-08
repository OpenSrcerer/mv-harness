"""Regenerate skill/mv-harness/references/CONTRACT.md from docs/CONTRACT.md (the generated copy, PLAN §4.1).

    python skill/mv-harness/scripts/sync_contract.py          # write
    python skill/mv-harness/scripts/sync_contract.py --check  # exit 1 when the copy is stale
Stdlib only.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "docs" / "CONTRACT.md"
DST = Path(__file__).resolve().parents[1] / "references" / "CONTRACT.md"
HEADER = ("<!-- GENERATED copy of docs/CONTRACT.md (skill/mv-harness/scripts/sync_contract.py); do not edit. "
          "Agents: read only the sections you need "
          "(§2 time and frames, §3 IDs, §4 values, §9 helpers). -->\n\n")


def render() -> str:
    with open(SRC, encoding="utf-8") as fh:
        return HEADER + fh.read()


def main(argv: list[str]) -> int:
    want = render()
    if "--check" in argv:
        have = DST.read_text(encoding="utf-8") if DST.is_file() else ""
        if have != want:
            print(f"{DST} is stale: run python skill/mv-harness/scripts/sync_contract.py", file=sys.stderr)
            return 1
        return 0
    DST.parent.mkdir(parents=True, exist_ok=True)
    with open(DST, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(want)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
