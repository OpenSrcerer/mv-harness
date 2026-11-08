# ruff: noqa: E501
"""Development harness (tests and builder runs): run the M6b stages in-process on a contract fixture folder.

``tests/contract/real-<slug>/`` only covers some upstream stages (no mood, cues, choreo, ...), so the runner cannot
take them end to end. This harness copies every upstream output the fixture *does* have into per-stage cache
dirs (tolerant stubs: absent files are skipped, audio is not copied), then runs the real ``meaning`` / ``brief`` /
``frames`` code through ``mvh.runner.child.run_stage`` exactly as the runner would (same Ctx, Writer, schema checks,
provenance and done.json). Upstreams with nothing in the fixture are left out, so the stages see them as absent.

    from mvh.stages.meaning.devrun import DevRun
    dr = DevRun(fixture_dir, work_dir); dr.run("meaning"); dr.run("brief"); dr.publish(song_dir)
"""
from __future__ import annotations

import dataclasses
import json
import shutil
from pathlib import Path
from typing import Any, Mapping

from mvh.contract import catalog, registry
from mvh.contract.curvefile import read_channel, read_index, read_matrix

__all__ = ["DevRun"]

_FAKE_KEY = "0" * 64


class DevRun:
    def __init__(self, fixture: Path | str, work: Path | str, *, song_dir: Path | str | None = None,
                 threads: int = 1):
        self.fx = Path(fixture)
        self.work = Path(work)
        self.work.mkdir(parents=True, exist_ok=True)
        self.song_dir = Path(song_dir) if song_dir else self.work / "song"
        self.song_dir.mkdir(parents=True, exist_ok=True)
        self.threads = threads
        self.upstream: dict[str, dict[str, Any]] = {}
        self.records: dict[str, dict[str, Any]] = {}
        src = self.fx / "meta" / "source.json"
        self.timebase = None
        if src.is_file():
            with open(src, encoding="utf-8") as fh:
                s = json.load(fh)
            self.timebase = {"n_samples": int(s["n_samples"]), "sample_rate": int(s["sample_rate"]),
                             "channels": int(s.get("channels", 2))}

    # ------------------------------------------------------------------ upstream copies
    def stub(self, stage: str) -> bool:
        """Copy ``stage``'s non-audio outputs from the fixture into a cache dir; False when it has none."""
        if stage in self.upstream:
            return True
        from mvh.runner.ctx import StageCtx, StageWriter
        from mvh.runner.spec import load_stage_specs

        spec = load_stage_specs()[stage]
        spec = dataclasses.replace(spec, outputs=tuple(o for o in spec.outputs if o.kind != "audio"))
        out = self.work / "cache" / stage
        if out.exists():
            shutil.rmtree(out)
        job = self._job(stage, spec, out, {})
        w = StageWriter(spec, out, job)
        ctx = StageCtx(spec, job, w, _quiet())
        n = _tolerant_copy(ctx, self.fx)
        if n == 0:
            shutil.rmtree(out, ignore_errors=True)
            return False
        done = {"stage": stage, "key": _FAKE_KEY, "status": "ok",
                "outputs": {rel: {k: v for k, v in info.items() if v is not None} for rel, info in w.written.items()},
                "curves": w.curves_meta, "matrices": w.matrices,
                "result": {"summary": {"stub": True}, "warnings": [], "fallbacks": [], "confidence": None}}
        (out / "_mvh").mkdir(parents=True, exist_ok=True)
        with open(out / "_mvh" / "done.json", "w", encoding="utf-8", newline="\n") as fh:
            json.dump(done, fh, ensure_ascii=False, indent=1)
        self.upstream[stage] = {"dir": str(out), "key": _FAKE_KEY}
        self.records[stage] = done
        return True

    # ------------------------------------------------------------------ our stages
    def run(self, stage: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Run the real stage code (via the runner's child entry point); returns its done record."""
        from mvh.runner.child import run_stage
        from mvh.runner.spec import load_stage_specs

        spec = load_stage_specs()[stage]
        for d in spec.deps:
            if d not in self.upstream:
                self.stub(d)
        out = self.work / "cache" / stage
        if out.exists():
            shutil.rmtree(out)
        p = spec.resolved_params("max", dict(params or {}))
        job = self._job(stage, spec, out, p)
        job["upstream"] = {d: v for d, v in self.upstream.items() if d in spec.deps}
        done = run_stage(job)
        self.upstream[stage] = {"dir": str(out), "key": done["key"]}
        self.records[stage] = done
        return done

    def publish(self, song_dir: Path | str | None = None) -> Path:
        """Assemble a song folder: fixture files (non-audio) + every stage dir's public outputs."""
        dst = Path(song_dir) if song_dir else self.song_dir
        dst.mkdir(parents=True, exist_ok=True)
        for st, info in self.upstream.items():
            root = Path(info["dir"])
            for rel in self.records[st].get("outputs", {}):
                if self.records[st]["outputs"][rel].get("public") is False:
                    continue
                (dst / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(root / rel, dst / rel)
        for rel in ("curves/index.json",):
            if (self.fx / rel).is_file():
                (dst / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(self.fx / rel, dst / rel)
        return dst

    def _job(self, stage: str, spec, out: Path, params: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "stage": stage, "stage_version": spec.version, "contract_version": catalog.CONTRACT_VERSION,
            "key": _FAKE_KEY, "pre_key": _FAKE_KEY, "params": dict(params), "device": "cpu", "upstream": {},
            "overrides": {}, "timebase": self.timebase, "song_dir": str(self.song_dir),
            "http_dir": str(self.work / "http"), "slug": "dev", "profile": "max", "threads": self.threads,
            "scratch": str(self.work / "scratch" / stage), "offline": True, "out_dir": str(out),
            "ingest_dir": None,
        }


def _quiet():
    import logging

    lg = logging.getLogger("mvh.devrun")
    lg.addHandler(logging.NullHandler())
    lg.propagate = False
    return lg


def _tolerant_copy(ctx, fx: Path) -> int:
    """Like mvh.contract.fixture.run_stub, but every absent output is skipped."""
    import re

    ph = re.compile(r"\{[a-z]+\}")
    spec = ctx.spec
    n = 0
    index = read_index(fx) if (fx / "curves/index.json").is_file() else None
    for out in spec.outputs:
        try:
            if out.kind in ("curve", "matrix") and out.public:
                if index is None:
                    continue
                fid = next(k for k, f in registry.CURVE_FILES.items() if f.path == out.path)
                if out.kind == "matrix":
                    if fid in index["files"]:
                        arr, finfo = read_matrix(fx, index, fid)
                        ctx.writer.matrix(fid, arr, meta={k: finfo[k] for k in ("band_edges_hz",) if k in finfo})
                        n += 1
                    continue
                import fnmatch

                chans, metas = {}, {}
                for e in index["channels"]:
                    if e["file"] == fid and any(fnmatch.fnmatchcase(e["id"], ph.sub("*", p)) for p in out.channels):
                        v, meta = read_channel(fx, index, e["id"])
                        chans[e["id"]], metas[e["id"]] = v, meta
                if chans:
                    ctx.writer.curves(fid, chans, meta=metas)
                    n += len(chans)
                continue
            base = fx if out.public else fx / "_intermediate" / spec.name
            if out.is_pattern:
                found = sorted(base.glob(ph.sub("*", out.path)))
                if out.restrict:
                    from mvh.runner.ctx import output_regex

                    rx = output_regex(out.path, out.restrict)
                    found = [p for p in found if rx.match(p.relative_to(base).as_posix())]
                for f in found:
                    ctx.writer.copy(f.relative_to(base).as_posix(), f)
                    n += 1
                continue
            if (base / out.path).is_file():
                ctx.writer.copy(out.path, base / out.path)
                n += 1
        except Exception:  # noqa: BLE001 - a malformed or partial fixture file is skipped like an absent one
            continue
    return n
