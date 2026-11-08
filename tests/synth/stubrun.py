# ruff: noqa: E501  (long data tables / docstrings in generated-fixture code)
"""A minimal in-memory Ctx/Writer to run the walking-skeleton stubs (mvh.contract.fixture.run_stub) without the runner.

Used by tests/unit/fixtures to prove that every stage's stub copies successfully from a fixture folder. The real
runner (W1b runtime) implements the full protocol; this one only supports what run_stub uses (copy, curves, matrix)
and enforces declared outputs the same way (an undeclared path raises UndeclaredOutput).
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from mvh.contract import curvefile
from mvh.runner.spec import StageSpec, UndeclaredOutput

__all__ = ["StubWriter", "StubCtx", "run_stage", "run_all", "assemble_curves"]

_PH = re.compile(r"\\\{(src|stem|sub|voice|fps|name)\\\}")


def _rx(path: str) -> re.Pattern[str]:
    return re.compile("^" + _PH.sub(r"[^/]+", re.escape(path)) + "$")


@dataclass
class StubWriter:
    spec: StageSpec
    out: Path
    copied: list[tuple[str, bool]] = field(default_factory=list)  # (rel, public)
    curves_: dict[str, dict[str, tuple[np.ndarray, Mapping[str, Any]]]] = field(default_factory=dict)
    matrices: dict[str, tuple[np.ndarray, Mapping[str, Any]]] = field(default_factory=dict)
    dry: bool = False  # True: check and record copies without writing (large real-song folders)

    def _declared(self, rel: str):
        for o in self.spec.outputs:
            if o.kind in ("curve",) or (o.kind == "matrix" and o.public):
                continue
            if _rx(o.path).match(rel):
                return o
        raise UndeclaredOutput(f"{self.spec.name}: undeclared output {rel}")

    def copy(self, rel: str, src: Path) -> Path:
        o = self._declared(rel)
        if self.dry:
            if not Path(src).is_file():
                raise FileNotFoundError(src)
            self.copied.append((rel, o.public))
            return Path(src)
        dst = self.out / rel if o.public else self.out / ".cache" / self.spec.name / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        self.copied.append((rel, o.public))
        return dst

    def curves(
        self,
        file_id: str,
        channels: Mapping[str, Any],
        *,
        meta: Mapping[str, Mapping[str, Any]] | None = None,
        rate_hz: float | None = None,
    ) -> None:
        d = self.curves_.setdefault(file_id, {})
        for cid, v in channels.items():
            d[cid] = (np.asarray(v), (meta or {}).get(cid, {}))

    def matrix(self, file_id: str, array: Any, *, meta: Mapping[str, Any] | None = None) -> None:
        self.matrices[file_id] = (np.asarray(array), dict(meta or {}))


@dataclass
class StubCtx:
    spec: StageSpec
    writer: StubWriter
    slug: str = "synth"
    params: Mapping[str, Any] = field(default_factory=dict)
    profile: str = "max"
    threads: int = 1
    device: str = "cpu"
    offline: bool = True


def run_stage(spec: StageSpec, run, out: Path, dry: bool = False):
    w = StubWriter(spec, out, dry=dry)
    res = run(StubCtx(spec, w))
    return res, w


def run_all(out: Path, fixture: Path | None = None) -> dict[str, tuple[Any, StubWriter]]:
    """Run the walking-skeleton stub behaviour (mvh.contract.fixture.run_stub) for every declared stage against
    `fixture` (MVH_FIXTURE_DIR), in topological order. Stages whose real ``run`` already replaced the stub are still
    exercised through run_stub with their current STAGE declaration (that is what the fixture must satisfy)."""
    from mvh.contract.fixture import run_stub
    from mvh.runner.spec import load_stage_specs, topo_order

    old = os.environ.get("MVH_FIXTURE_DIR")
    if fixture is not None:
        os.environ["MVH_FIXTURE_DIR"] = str(fixture)
    try:
        specs = load_stage_specs()
        res = {}
        for name in topo_order(specs):
            res[name] = run_stage(specs[name], run_stub, out)
        return res
    finally:
        if fixture is not None:
            if old is None:
                os.environ.pop("MVH_FIXTURE_DIR", None)
            else:
                os.environ["MVH_FIXTURE_DIR"] = old


def assemble_curves(out: Path, writers: list[StubWriter]) -> dict[str, Any]:
    """Pack every channel the stages handed over (the runner's finalize step) and return curves/index.json."""
    entries = []
    for w in writers:
        for fid, chans in w.curves_.items():
            for cid, (v, meta) in chans.items():
                m = {k: meta["norm"][k] for k in ("lo", "hi") if meta.get("norm") and k in meta["norm"]}
                entries.append(curvefile.ChannelData(cid, v, m or None))
        for fid, (arr, meta) in w.matrices.items():
            entries.append(
                curvefile.ChannelData(fid, arr, {k: v for k, v in meta.items() if k == "band_edges_hz"})
            )
    return curvefile.assemble(out, entries)


def load_json(p: Path) -> Any:
    """Small helper shared by the fixture tests (UTF-8 JSON)."""
    import json

    with open(p, encoding="utf-8") as fh:
        return json.load(fh)
