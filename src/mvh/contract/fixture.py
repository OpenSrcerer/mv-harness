"""Walking-skeleton stub behaviour: copy a stage's declared outputs from the contract fixture.

The fixture folder ``tests/contract/synth/`` (built by the W1b fixtures builder) is a complete song folder
(``out/<slug>/`` layout) plus ``_intermediate/<stage>/<path>`` for non-public outputs. Override its location
with the ``MVH_FIXTURE_DIR`` environment variable (e.g. ``tests/contract/real-jeremy``).

Stdlib + numpy (curve channels are re-read and handed to ``ctx.writer.curves`` so the runner packs them).
"""
from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path
from typing import Any

from . import registry
from .curvefile import read_channel, read_index, read_matrix

__all__ = ["fixture_dir", "run_stub", "FIXTURE_ENV"]

FIXTURE_ENV = "MVH_FIXTURE_DIR"
_REPO = Path(__file__).resolve().parents[3]
_PH = re.compile(r"\{[a-z]+\}")


def fixture_dir() -> Path:
    env = os.environ.get(FIXTURE_ENV)
    return Path(env) if env else _REPO / "tests" / "contract" / "synth"


def _missing(stage: str, what: str):
    from mvh.runner.spec import MissingFixture
    return MissingFixture(f"stub '{stage}': fixture missing {what} (fixture dir: {fixture_dir()}; "
                          f"the W1b fixtures builder creates tests/contract/synth/, or set {FIXTURE_ENV})")


def _channel_matches(cid: str, pattern: str) -> bool:
    return fnmatch.fnmatchcase(cid, _PH.sub("*", pattern))


def run_stub(ctx: Any):
    """Copy every declared output of ctx.spec from the fixture through ctx.writer. Missing required
    files raise MissingFixture; missing optional ones are skipped."""
    from mvh.runner.spec import StageResult

    spec = ctx.spec
    fx = fixture_dir()
    if not fx.is_dir():
        raise _missing(spec.name, "the whole folder")
    index = None
    copied = 0
    for out in spec.outputs:
        if out.kind in ("curve", "matrix") and out.public:
            if index is None:
                if not (fx / "curves/index.json").exists():
                    raise _missing(spec.name, "curves/index.json")
                index = read_index(fx)
            if out.kind == "matrix":
                fid = next(k for k, f in registry.CURVE_FILES.items() if f.path == out.path)
                if fid not in index["files"]:
                    raise _missing(spec.name, out.path)
                arr, finfo = read_matrix(fx, index, fid)
                meta = {k: finfo[k] for k in ("band_edges_hz",) if k in finfo}
                ctx.writer.matrix(fid, arr, meta=meta)
                copied += 1
                continue
            fid = next(k for k, f in registry.CURVE_FILES.items() if f.path == out.path)
            chans, metas = {}, {}
            for e in index["channels"]:
                if e["file"] == fid and any(_channel_matches(e["id"], p) for p in out.channels):
                    v, meta = read_channel(fx, index, e["id"])
                    chans[e["id"]] = v
                    metas[e["id"]] = meta
            for p in out.channels:
                if "{" not in p and p not in chans:
                    raise _missing(spec.name, f"curve channel {p}")
            if chans:
                ctx.writer.curves(fid, chans, meta=metas)
                copied += len(chans)
            continue
        base = fx if out.public else fx / "_intermediate" / spec.name
        if out.is_pattern or "{" in out.path:
            glob = _PH.sub("*", out.path)
            found = sorted(base.glob(glob))
            if getattr(out, "restrict", ()):
                from mvh.runner.ctx import output_regex

                rx = output_regex(out.path, out.restrict)
                found = [p for p in found if rx.match(p.relative_to(base).as_posix())]
            if not found and out.required:
                raise _missing(spec.name, f"{base / glob}")
            for src in found:
                ctx.writer.copy(src.relative_to(base).as_posix(), src)
                copied += 1
            continue
        src = base / out.path
        if src.exists():
            ctx.writer.copy(out.path, src)
            copied += 1
        elif out.required:
            raise _missing(spec.name, str(src))
    return StageResult(status="ok", summary={"stub": True, "copied": copied},
                       provenance={"notes": [f"walking-skeleton stub: outputs copied from {fx.name}"]})
