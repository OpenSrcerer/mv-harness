"""Build a viewer folder from a contract fixture (upstream = tests/contract/<fixture>/), for browser checks.

    python tests/unit/viewer/build_view.py synth|real-jeremy|... <out dir>

The folder is the fixture (files hard-linked, ``_intermediate``/``_truth`` left out) plus a viewer.html written by the
real viewer stage (run against the fixture through a fake upstream) and ``lib/mvh.js``. Then ``mvh view <out dir>``.
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / "src"))

from viewer_support import ROOT, make_ctx  # noqa: E402

SKIP = {"_intermediate", "_truth", ".cache", ".done.json", "viewer.html", "frames"}


def link_tree(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for p in sorted(src.iterdir()):
        if p.name in SKIP:
            continue
        q = dst / p.name
        if p.is_dir():
            link_tree(p, q)
        elif not q.exists():
            try:
                os.link(p, q)
            except OSError:
                shutil.copy2(p, q)


def build(fixture: str, out: Path, params: dict | None = None) -> dict:
    src = ROOT / "tests" / "contract" / fixture
    from mvh.stages.viewer import run

    link_tree(src, out)
    (out / "lib").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "src" / "mvh" / "assets" / "mvh.js", out / "lib" / "mvh.js")
    ctx = make_ctx(params, root=src, slug=fixture.replace("real-", ""))
    t0 = time.perf_counter()
    res = run(ctx)
    (out / "viewer.html").write_text(ctx.writer.files["viewer.html"], encoding="utf-8", newline="\n")
    return {"seconds": round(time.perf_counter() - t0, 2), "summary": res.summary, "fallbacks": res.fallbacks, "warnings": res.warnings,
            "confidence": res.confidence, "html_mb": round((out / "viewer.html").stat().st_size / 1e6, 2)}


if __name__ == "__main__":
    import json

    print(json.dumps(build(sys.argv[1], Path(sys.argv[2])), indent=1))
