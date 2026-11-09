"""M5 in-process harness: run identity / lyrics / voices / lipsync through the runner's own child code
(``mvh.runner.child.run_stage``: real StageCtx, StageWriter, schema validation, provenance, done.json) with
upstream stages materialised from a contract fixture folder by the walking-skeleton copier (``run_stub``).

Why not ``mvh analyze``: the other modules replace their stubs while M5 is built, and ``tests/contract/real-*``
have no stem_activity outputs. Here every non-M5 dependency is ALWAYS the fixture copy, so results only depend
on M5 code. Missing stem_activity curves are synthesised from the stems (the PLAN rule: > -45 dBFS and within
18 dB of the mix, 300/500 ms hysteresis) and marked as such in their done.json.

    h = Harness(fixture=Path("tests/contract/synth"), work=tmp_path, input_audio=None)
    rec = h.run("lyrics", params={...}, params_ext={"lyrics": "..."})
    h.stage_dir("lyrics") / "lyrics/lyrics.json"
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Mapping

import numpy as np

REPO = Path(__file__).resolve().parents[3]
M5_STAGES = ("identity", "lyrics", "voices", "lipsync")

__all__ = ["Harness", "REPO", "M5_STAGES", "synth_activity", "slot"]


def slot(owner: str, threads: int = 6, poll: float = 2.0):
    """One machine-wide heavy slot (mvh.runner.locks, same files as mvh.testing.heavy) polled every ``poll`` s:
    the default 15 s poll loses every race against builders that re-acquire back to back."""
    from mvh.runner import locks

    return locks.heavy(owner, threads=threads, poll=poll)


def _spec(name: str):
    import importlib

    return importlib.import_module(f"mvh.stages.{name}").STAGE


def synth_activity(x: np.ndarray, sr: int, mix: np.ndarray, n_frames: int) -> tuple[np.ndarray, np.ndarray]:
    """(active 0/1, rms_db) at 100 Hz for one stem (mono arrays), PLAN stem_activity rule."""
    hop = sr / 100.0
    win = int(round(sr * 0.046))
    out_db = np.full(n_frames, -120.0, np.float32)
    mix_db = np.full(n_frames, -120.0, np.float32)
    xx = np.concatenate([np.zeros(win), x.astype(np.float64) ** 2, np.zeros(win)])
    mm = np.concatenate([np.zeros(win), mix.astype(np.float64) ** 2, np.zeros(win)])
    cx, cm = np.cumsum(xx), np.cumsum(mm)
    for i in range(n_frames):
        c = int(round(i * hop)) + win
        a, b = c - win // 2, c + win // 2
        e = (cx[b] - cx[a]) / max(1, b - a)
        f = (cm[b] - cm[a]) / max(1, b - a)
        out_db[i] = 10 * np.log10(max(e, 1e-12))
        mix_db[i] = 10 * np.log10(max(f, 1e-12))
    raw = (out_db > -45.0) & (out_db > mix_db - 18.0)
    act = np.zeros(n_frames, np.float32)
    on, cnt_on, cnt_off = False, 0, 0
    for i in range(n_frames):
        if raw[i]:
            cnt_on += 1
            cnt_off = 0
        else:
            cnt_off += 1
            cnt_on = 0
        if not on and cnt_on >= 30:
            on = True
            act[max(0, i - 29):i + 1] = 1
        elif on and cnt_off >= 50:
            on = False
            act[max(0, i - 49):i + 1] = 0
        if on:
            act[i] = 1
    return act, np.maximum(out_db, -120.0)


class Harness:
    def __init__(self, fixture: Path, work: Path, *, slug: str = "synth", input_audio: Path | None = None,
                 offline: bool = True, profile: str = "max", threads: int = 3,
                 overrides: Mapping[str, Any] | None = None, song_dir: Path | None = None):
        self.fx = Path(fixture)
        self.work = Path(work)
        self.slug = slug
        self.input = Path(input_audio) if input_audio else None
        self.offline = offline
        self.profile = profile
        self.threads = threads
        self.overrides = dict(overrides or {})
        self.song_dir = Path(song_dir) if song_dir else self.work / "song"
        self.song_dir.mkdir(parents=True, exist_ok=True)
        self.keys: dict[str, str] = {}
        with open(self.fx / "meta" / "source.json", encoding="utf-8") as fh:
            src = json.load(fh)
        self.timebase = {"n_samples": int(src["n_samples"]), "sample_rate": int(src["sample_rate"]),
                         "channels": int(src["channels"])}
        self.log = logging.getLogger("m5harness")

    # ------------------------------------------------------------------ paths
    def stage_dir(self, stage: str) -> Path:
        return self.work / "_stages" / stage

    def _job(self, spec, out: Path, params: Mapping[str, Any] | None, params_ext: Mapping[str, Any] | None,
             upstream: Mapping[str, Any], overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
        from mvh.contract.catalog import CONTRACT_VERSION
        from mvh.runner import models as mdl

        p = spec.resolved_params(self.profile, params or {})
        key = hashlib.sha256(json.dumps({"s": spec.name, "p": p, "u": sorted(upstream)}, sort_keys=True, default=str).encode()).hexdigest()
        models_prov = []
        for mid in spec.models:
            try:
                e = mdl.entry(mid)
                revs = {f.get("revision") for f in e["files"]}
                models_prov.append({"id": mid, "licence": e.get("licence", ""), "revision": revs.pop() if len(revs) == 1 else None})
            except Exception:  # noqa: BLE001
                models_prov.append({"id": mid, "licence": "unknown", "revision": None})
        ing = self.stage_dir("ingest")
        ovr = {k: v for k, v in (overrides if overrides is not None else self.overrides).items() if k in spec.override_keys}
        return {
            "schema": "mvh/runner_job", "stage": spec.name, "stage_version": spec.version,
            "contract_version": CONTRACT_VERSION, "slug": self.slug, "song_dir": str(self.song_dir),
            "out_dir": str(out), "scratch": str(self.work / "_scratch" / spec.name), "key": key, "pre_key": key,
            "params": p, "profile": self.profile, "threads": self.threads, "device": "cpu", "offline": self.offline,
            "overrides": ovr, "upstream": {d: {"dir": str(self.stage_dir(d)), "key": self.keys.get(d) or hashlib.sha256(d.encode()).hexdigest()} for d in upstream},
            "ingest_dir": str(ing) if (ing / "_mvh" / "done.json").is_file() else None,
            "timebase": self.timebase, "params_ext": dict(params_ext or {}),
            "http_dir": str(self.work / "_http" / spec.name), "models_prov": models_prov, "tools": [],
            "heavy_locks": False, "key_inputs": {},
        }

    # ------------------------------------------------------------------ upstream materialisation
    def materialise(self, stage: str) -> Path:
        """Copy a non-M5 stage's outputs from the fixture into a cache-like dir (with _mvh/done.json)."""
        out = self.stage_dir(stage)
        if (out / "_mvh" / "done.json").is_file():
            return out
        if stage == "ingest" and self.input is not None:
            return self._real_ingest()
        from mvh.contract.fixture import run_stub
        from mvh.runner.ctx import StageCtx, StageWriter
        from mvh.runner.spec import MissingFixture

        spec = _spec(stage)
        out.mkdir(parents=True, exist_ok=True)
        job = self._job(spec, out, None, None, {})
        writer = StageWriter(spec, out, job)
        ctx = StageCtx(spec, job, writer, self.log)
        old = os.environ.get("MVH_FIXTURE_DIR")
        os.environ["MVH_FIXTURE_DIR"] = str(self.fx)
        note = "fixture copy"
        try:
            run_stub(ctx)
        except MissingFixture:
            if stage != "stem_activity":
                raise
            self._synth_stem_activity(writer)
            note = "synthesised from the fixture stems (harness)"
        finally:
            if old is None:
                os.environ.pop("MVH_FIXTURE_DIR", None)
            else:
                os.environ["MVH_FIXTURE_DIR"] = old
        self._done(spec, out, writer, job, note)
        self.keys[stage] = job["key"]
        return out

    def _synth_stem_activity(self, writer) -> None:
        from mvh.io import audio as aio

        sep = self.materialise("separate_hq")
        n = -(-self.timebase["n_samples"] * 100 // self.timebase["sample_rate"])
        mix = aio.decode(self.fx / "_intermediate" / "ingest" / "canonical.wav", mono=True)
        chans: dict[str, np.ndarray] = {}
        for s in ("vocals", "lead_vocals", "backing_vocals"):
            p = sep / "stems" / f"{s}.flac"
            if not p.is_file():
                continue
            d = aio.decode(p, mono=True)
            act, db = synth_activity(d.samples[0], d.sr, mix.samples[0], n)
            chans[f"stem.{s}.active"] = act
            chans[f"stem.{s}.rms_db"] = db
        writer.curves("stems", chans)

    def _real_ingest(self) -> Path:
        from mvh.runner.child import run_stage

        spec = _spec("ingest")
        out = self.stage_dir("ingest")
        out.mkdir(parents=True, exist_ok=True)
        job = self._job(spec, out, None, {"input": str(self.input)}, {})
        job["timebase"] = None
        job["ingest_dir"] = None
        Path(job["scratch"]).mkdir(parents=True, exist_ok=True)
        run_stage(job)
        self.keys["ingest"] = job["key"]
        return out

    def _done(self, spec, out: Path, writer, job, note: str) -> None:
        outputs = {}
        for rel, info in sorted(writer.written.items()):
            p = out / rel
            if p.is_file():
                outputs[rel] = {**{k: v for k, v in info.items() if v is not None}, "bytes": p.stat().st_size}
        rec = {"schema": "mvh/runner_done", "stage": spec.name, "stage_version": spec.version, "key": job["key"],
               "status": "ok", "outputs": outputs, "curves": writer.curves_meta, "matrices": writer.matrices,
               "result": {"summary": {"harness": note}, "warnings": [], "fallbacks": [], "confidence": None},
               "provenance": {}, "http": {}, "worker_runs": []}
        p = out / "_mvh" / "done.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(rec, fh, ensure_ascii=False, indent=1)

    # ------------------------------------------------------------------ M5 stages
    def run(self, stage: str, *, params: Mapping[str, Any] | None = None, params_ext: Mapping[str, Any] | None = None,
            overrides: Mapping[str, Any] | None = None, fresh: bool = True, stub_deps: tuple[str, ...] = ()) -> dict[str, Any]:
        """Run one M5 stage through mvh.runner.child.run_stage; returns its done record. ``stub_deps``: M5
        dependencies to copy from the fixture instead of running (e.g. lipsync on the fixture's truth lyrics)."""
        import shutil

        from mvh.runner.child import run_stage

        spec = _spec(stage)
        self.materialise("ingest")
        for d in spec.deps:
            if d in stub_deps:
                self.materialise(d)
            elif d in M5_STAGES:
                if not (self.stage_dir(d) / "_mvh" / "done.json").is_file():
                    self.run(d)
            else:
                self.materialise(d)
        out = self.stage_dir(stage)
        if fresh and out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True, exist_ok=True)
        job = self._job(spec, out, params, params_ext, spec.deps, overrides)
        Path(job["scratch"]).mkdir(parents=True, exist_ok=True)
        rec = run_stage(job)
        self.keys[stage] = rec["key"]
        return rec

    def json(self, stage: str, rel: str) -> Any:
        with open(self.stage_dir(stage) / rel, encoding="utf-8") as fh:
            return json.load(fh)

    def curve(self, stage: str, cid: str) -> np.ndarray:
        from mvh.contract import registry

        c = registry.match_channel(cid)
        return np.fromfile(self.stage_dir(stage) / "_mvh" / "curves" / c.file / f"{cid}.f32", dtype="<f4")
