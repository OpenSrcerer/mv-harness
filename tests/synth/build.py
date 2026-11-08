# ruff: noqa: E501  (long data tables / docstrings in generated-fixture code)
"""Regenerate the test fixtures deterministically.

    uv run --frozen --no-sync python -m tests.synth.build                 # synth folder (+ real-* adapters if the W0 cache exists)
    uv run --frozen --no-sync python -m tests.synth.build --only synth    # just tests/contract/synth/
    uv run --frozen --no-sync python -m tests.synth.build --only real     # just tests/contract/real-*/
    uv run --frozen --no-sync python -m tests.synth.build --check         # rebuild synth into a temp dir, compare with .done.json

The synth folder ends with ``.done.json`` (sha256 of every file, no timestamps): a rerun is byte-identical.
Exit code 0 on success; 1 when a schema validation error or a --check mismatch occurs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

SYNTH_DIR = REPO / "tests" / "contract" / "synth"


def tree_hashes(root: Path) -> dict[str, str]:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name != ".done.json":
            out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def build_synth(out: Path, log=print) -> dict:
    from mvh.contract.catalog import CONTRACT_VERSION

    from .song import score
    from .song.folder import build_folder

    t0 = time.time()
    res = build_folder(out, log=log)
    hashes = tree_hashes(out)
    done = {
        "generator": "tests.synth.build",
        "generator_version": score.GENERATOR_VERSION,
        "contract_version": CONTRACT_VERSION,
        "slug": "synth",
        "n_files": len(hashes),
        "validation_errors": res["errors"],
        "files": hashes,
    }
    (out / ".done.json").write_text(
        json.dumps(done, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    log(
        f"synth: {len(hashes)} files, {len(res['errors'])} validation errors, {time.time() - t0:.1f} s -> {out}"
    )
    for e in res["errors"][:40]:
        log(f"  INVALID {e}")
    return done


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tests.synth.build")
    ap.add_argument("--only", choices=["synth", "real", "all"], default="all")
    ap.add_argument("--out", type=Path, default=SYNTH_DIR)
    ap.add_argument(
        "--check",
        action="store_true",
        help="rebuild synth in a temp dir and compare with the existing .done.json",
    )
    a = ap.parse_args(argv)
    rc = 0
    if a.check:
        ref = json.loads((a.out / ".done.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="mvh-fx-") as td:
            done = build_synth(Path(td) / "synth")
        diff = sorted(
            k for k in set(ref["files"]) | set(done["files"]) if ref["files"].get(k) != done["files"].get(k)
        )
        print(f"check: {len(diff)} differing files")
        for k in diff[:50]:
            print("  DIFF", k)
        return 1 if diff else 0
    if a.only in ("synth", "all"):
        done = build_synth(a.out)
        rc |= 1 if done["validation_errors"] else 0
    if a.only in ("real", "all"):
        from .real import build_all_real

        rc |= build_all_real()
    return rc


if __name__ == "__main__":
    sys.exit(main())
