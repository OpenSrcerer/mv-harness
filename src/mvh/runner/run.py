"""The runner (PLAN §3.3): plan the DAG, compute NF2 keys, schedule stage processes on a core budget, cache,
publish, validate after every stage, finalize.

* Every stage runs in its own spawned process (``mvh.runner.child``) with the thread variables set in its
  environment before any import. ``n`` (threads per stage) is fixed: ``--threads`` / ``MVH_THREADS``
  (default 3),
  clamped to 6 for heavy stages; it is part of the cache key. The scheduler runs stages concurrently while
  the sum
  of their ``n`` fits the core budget (8 physical cores by default, ``--cores``), so ``n`` never depends on
  load.
* Heavy stages (non-stub stages with models) take a machine-wide heavy slot (``locks``); env='sep' stages
  take it
  inside ``ctx.worker`` instead. ``MVH_HEAVY_LOCKS=0`` disables slots (tests of the walking skeleton).
* A stage whose key has a done record is a cache hit. ``--force`` re-runs (all, or the listed stages);
  ``--from S``
  forces S and everything downstream; ``--only`` runs just the listed stages (their deps must be cached).
* Public outputs are hard-linked (copy fallback) from the cache into the song folder; user inputs
  (overrides.json, meaning/intent.md, meaning/authored.json) are never written or deleted.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from mvh.contract.catalog import CONTRACT_VERSION
from mvh.io import atomic, proc
from mvh.io.ffmpeg import child_env
from mvh.io.paths import home, repo_root

from . import locks
from . import overrides as ovr
from .cache import SongCache, diff_inputs, env_lock_hash, file_hash, key_of
from .spec import StageSpec, check_dag, load_stage_specs, topo_order
from .threads import thread_env

__all__ = [
    "Settings",
    "StageState",
    "Runner",
    "analyze",
    "status",
    "load_run_settings",
    "is_stub",
    "is_heavy",
    "DEFAULT_CORES",
    "DEFAULT_THREADS",
]

DEFAULT_CORES = 8
DEFAULT_THREADS = 3
#: published files at least this big are hard-linked from the cache instead of copied (stems, mix)
LINK_MIN_BYTES = 8 << 20


def is_stub(spec: StageSpec) -> bool:
    return "stub" in spec.version.split("-", 1)[-1] if "-" in spec.version else False


def is_heavy(spec: StageSpec) -> bool:
    return (spec.env == "sep" or bool(spec.models)) and not is_stub(spec)


def _env_threads() -> int:
    try:
        return max(1, int(os.environ.get("MVH_THREADS", DEFAULT_THREADS)))
    except ValueError:
        return DEFAULT_THREADS


@dataclass
class Settings:
    song: Path | None  # the input file (None: reuse the one recorded in the song folder)
    song_dir: Path
    slug: str
    profile: str = "max"
    threads: int = field(default_factory=_env_threads)
    cores: int = DEFAULT_CORES
    only: tuple[str, ...] | None = None
    force: tuple[str, ...] | bool = False  # True = all
    from_stage: str | None = None
    offline: bool = False
    heavy_locks: bool = True
    params_ext: dict[str, str] = field(default_factory=dict)  # param:<name> external inputs (input, lyrics)
    cli_params: dict[str, dict[str, Any]] = field(default_factory=dict)
    progress: Callable[[str], None] | None = None

    def say(self, msg: str) -> None:
        (self.progress or (lambda m: print(f"[mvh] {m}", file=sys.stderr, flush=True)))(msg)


@dataclass
class StageState:
    name: str
    status: str = "pending"  # done | degraded | skipped | failed | pending | stale (status) | running
    reason: str = ""
    key: str | None = None
    pre_key: str | None = None
    cache: str | None = None  # hit | miss | forced
    seconds: float | None = None
    wait_s: float | None = None  # W3 seam S08: time spent waiting for a heavy slot (part of seconds)
    threads: int = 0
    record: dict[str, Any] | None = None
    key_inputs: dict[str, Any] | None = None


RUN_SETTINGS = "_run.json"


def load_run_settings(song_dir: Path) -> dict[str, Any]:
    p = Path(song_dir) / ".cache" / RUN_SETTINGS
    if p.is_file():
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


class Runner:
    def __init__(self, settings: Settings, specs: Mapping[str, StageSpec] | None = None):
        self.s = settings
        if settings.song is not None:
            settings.params_ext.setdefault("input", str(Path(settings.song).resolve()))
        elif "input" not in settings.params_ext:
            prev = load_run_settings(settings.song_dir).get("params_ext", {}).get("input")
            if prev:
                settings.params_ext["input"] = prev
        self.specs = dict(specs) if specs is not None else load_stage_specs()
        check_dag(self.specs)
        self.order = topo_order(self.specs)
        self.cache = SongCache(settings.song_dir)
        self.overrides = ovr.load(settings.song_dir)
        self.states: dict[str, StageState] = {n: StageState(n) for n in self.order}
        self._ffmpeg: dict[str, Any] | None = None
        self._lock = threading.Lock()
        self.started = datetime.now(timezone.utc)
        self.warnings: list[str] = []

    # ------------------------------------------------------------------ keys
    def ffmpeg_info(self) -> dict[str, Any]:
        if self._ffmpeg is None:
            from mvh.io.ffmpeg import info

            self._ffmpeg = info()
        return self._ffmpeg

    def threads_for(self, spec: StageSpec) -> int:
        n = max(1, int(self.s.threads))
        if is_heavy(spec):
            n = min(n, locks.MAX_THREADS)
        return min(n, max(1, int(self.s.cores)))

    def device_class(self, spec: StageSpec) -> str:
        if not spec.gpu:
            return "cpu"
        if spec.env == "sep":
            from .sepworker import sep_python, variant_order

            for v in variant_order(spec.params.get("variant_order")):
                if sep_python(v) is not None:
                    return "rocm" if v == "rocm" else "cpu"
        return "cpu"

    def params_of(self, spec: StageSpec) -> dict[str, Any]:
        return spec.resolved_params(self.s.profile, self.s.cli_params.get(spec.name))

    def _external_hashes(self, spec: StageSpec) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for e in spec.external_inputs:
            if e.path.startswith("http:"):
                out[e.name] = "cached-responses"  # folded into the effective key after the run
                continue
            if e.path.startswith("param:"):
                v = self.s.params_ext.get(e.path[6:])
                p = Path(v) if v else None
            else:
                p = self.s.song_dir / e.path.split("#", 1)[0]
            if p is not None and p.is_file():
                out[e.name] = (
                    {"sha256": file_hash(p), "name": p.name} if e.path.startswith("param:") else file_hash(p)
                )
            else:
                out[e.name] = None
        return out

    def key_inputs(self, spec: StageSpec, upstream_keys: Mapping[str, str]) -> dict[str, Any]:
        from . import models as mdl

        model_shas: dict[str, list[str]] = {}
        for mid in spec.models:
            try:
                model_shas[mid] = [f["sha256"] for f in mdl.entry(mid)["files"]]
            except mdl.ModelError:
                model_shas[mid] = ["missing"]
        ki: dict[str, Any] = {
            "stage": spec.name,
            "version": spec.version,
            "contract": CONTRACT_VERSION,
            "params": self.params_of(spec),
            "threads": self.threads_for(spec),
            "models": model_shas,
            "upstream": dict(sorted(upstream_keys.items())),
            "overrides": ovr.subset(self.overrides, spec.override_keys),
            "external": self._external_hashes(spec),
            "env_lock": env_lock_hash(spec.env),
        }
        if spec.uses_ffmpeg:
            fi = self.ffmpeg_info()
            ki["ffmpeg"] = {"version": fi["version"], "buildconf": fi["buildconf"]}
        if spec.gpu:
            ki["device"] = self.device_class(spec)
        from .child import _stubbed

        if _stubbed(spec.name):
            ki["stub"] = True  # test seam (MVH_STAGE_STUBS): a stub result never shares a key with a real one
        return ki

    # ------------------------------------------------------------------ selection
    def descendants(self, stage: str) -> set[str]:
        out = {stage}
        changed = True
        while changed:
            changed = False
            for s in self.specs.values():
                if s.name not in out and any(d in out for d in s.deps):
                    out.add(s.name)
                    changed = True
        return out

    def ancestors(self, stage: str) -> set[str]:
        out: set[str] = set()
        todo = list(self.specs[stage].deps)
        while todo:
            d = todo.pop()
            if d not in out:
                out.add(d)
                todo.extend(self.specs[d].deps)
        return out

    def targets(self) -> list[str]:
        if self.s.only:
            unknown = [x for x in self.s.only if x not in self.specs]
            if unknown:
                raise ValueError(f"unknown stages: {unknown}")
            return [n for n in self.order if n in self.s.only]
        want = {n for n, sp in self.specs.items() if sp.trigger == "analyze"}
        return [n for n in self.order if n in want]

    def forced(self) -> set[str]:
        f: set[str] = set()
        if self.s.force is True:
            f = set(self.specs)
        elif self.s.force:
            unknown = [x for x in self.s.force if x not in self.specs]
            if unknown:
                raise ValueError(f"unknown stages: {unknown}")
            f = set(self.s.force)
        if self.s.from_stage:
            if self.s.from_stage not in self.specs:
                raise ValueError(f"unknown stage {self.s.from_stage!r}")
            f |= self.descendants(self.s.from_stage)
        return f

    # ------------------------------------------------------------------ status
    def resolve(self, name: str, done_keys: Mapping[str, str]) -> StageState:
        """Key + cache state of one stage given the effective keys of its deps (no running)."""
        spec = self.specs[name]
        st = self.states[name]
        missing = [d for d in spec.deps if d not in done_keys]
        if missing:
            what = ", ".join(f"{d} ({self.states[d].status})" for d in missing)
            if self.cache.stage(name).latest():
                st.status, st.reason = "stale", f"upstream not current: {what}"
            else:
                st.status, st.reason = "pending", f"upstream pending: {what}"
            return st
        ki = self.key_inputs(spec, {d: done_keys[d] for d in spec.deps})
        pre = key_of(ki)
        st.key_inputs, st.pre_key, st.threads = ki, pre, ki["threads"]
        sc = self.cache.stage(name)
        rec = sc.done(pre)
        if rec is not None:
            bad = self._damaged(sc.dir(pre), rec)
            if bad:
                st.status, st.reason = "stale", f"cache entry damaged ({bad}); it will be re-run"
                return st
            st.record, st.key = rec, rec.get("key", pre)
            st.status = {"ok": "done"}.get(rec.get("status", "ok"), rec.get("status", "done"))
            st.reason = "cached"
            return st
        failed = sc.failed()
        if failed and failed.get("pre_key") == pre:
            st.status, st.reason = "failed", failed.get("message", "failed")
            return st
        latest = sc.latest()
        if latest:
            st.status, st.reason = "stale", "; ".join(diff_inputs(latest.get("key_inputs"), ki))
        else:
            st.status, st.reason = "pending", "never run"
        return st

    @staticmethod
    def _damaged(entry_dir: Path, rec: Mapping[str, Any]) -> str:
        """Cheap integrity check of a cache entry on a hit: every output exists with the recorded size. (Small
        files are published by copy, so only the hard-linked big ones can be rewritten from the song folder.)"""
        for rel, info in rec.get("outputs", {}).items():
            p = entry_dir / rel
            try:
                size = p.stat().st_size
            except OSError:
                return f"{rel} missing"
            if "bytes" in info and size != int(info["bytes"]):
                return f"{rel} has {size} bytes, recorded {info['bytes']}"
        return ""

    def status(self) -> dict[str, StageState]:
        keys: dict[str, str] = {}
        for n in self.order:
            st = self.resolve(n, keys)
            if st.status in ("done", "degraded", "skipped") and st.key:
                keys[n] = st.key
        return self.states

    # ------------------------------------------------------------------ execution
    def _timebase(self, keys: Mapping[str, str]) -> dict[str, Any] | None:
        if "ingest" not in keys:
            return None
        d = self.cache.stage("ingest").dir(self.states["ingest"].pre_key or keys["ingest"])
        p = d / "meta" / "source.json"
        if not p.is_file():
            return None
        with open(p, encoding="utf-8") as fh:
            src = json.load(fh)
        return {
            "n_samples": int(src["n_samples"]),
            "sample_rate": int(src["sample_rate"]),
            "channels": int(src["channels"]),
        }

    def _job(
        self, spec: StageSpec, st: StageState, staging: Path, scratch: Path, keys: Mapping[str, str]
    ) -> dict[str, Any]:
        from . import models as mdl

        ups = {}
        for d in spec.deps:
            ds = self.states[d]
            ups[d] = {"dir": str(self.cache.stage(d).dir(ds.pre_key or keys[d])), "key": keys[d]}
        ing = self.states.get("ingest")
        models_prov = []
        for mid in spec.models:
            try:
                e = mdl.entry(mid)
                revs = {f.get("revision") for f in e["files"]}
                models_prov.append(
                    {
                        "id": mid,
                        "licence": e.get("licence", ""),
                        "revision": revs.pop() if len(revs) == 1 else None,
                    }
                )
            except mdl.ModelError:
                models_prov.append({"id": mid, "licence": "unknown", "revision": None})
        tools = []
        if spec.uses_ffmpeg:
            tools.append({"name": "ffmpeg", "version": self.ffmpeg_info()["version"]})
        return {
            "schema": "mvh/runner_job",
            "stage": spec.name,
            "stage_version": spec.version,
            "contract_version": CONTRACT_VERSION,
            "slug": self.s.slug,
            "song_dir": str(self.s.song_dir),
            "out_dir": str(staging),
            "scratch": str(scratch),
            "key": st.pre_key,
            "pre_key": st.pre_key,
            "params": self.params_of(spec),
            "profile": self.s.profile,
            "threads": st.threads,
            "device": self.device_class(spec),
            "offline": self.s.offline,
            "overrides": ovr.subset(self.overrides, spec.override_keys),
            "upstream": ups,
            "ingest_dir": str(self.cache.stage("ingest").dir(ing.pre_key))
            if ing and ing.pre_key and "ingest" in keys
            else None,
            "timebase": self._timebase(keys),
            "params_ext": dict(self.s.params_ext),
            "http_dir": str(self.cache.http / spec.name),
            "models_prov": models_prov,
            "tools": tools,
            "heavy_locks": bool(self.s.heavy_locks),
            "key_inputs": st.key_inputs,
        }

    def _child_env(self, n: int) -> dict[str, str]:
        env = child_env(None, **thread_env(n))
        src = str(repo_root() / "src")
        pp = [
            p
            for p in env.get("PYTHONPATH", "").split(os.pathsep)
            if p and os.path.normcase(p) != os.path.normcase(src)
        ]
        env["PYTHONPATH"] = os.pathsep.join([src] + pp)
        h = home()
        from . import models as mdl

        # audio-separator lets this variable override an explicit model_file_dir, so it must always point at
        # the folder `mvh models fetch` fills (an inherited value, e.g. from an old env script, is replaced)
        env["AUDIO_SEPARATOR_MODEL_DIR"] = str(mdl.separator_dir())
        for k, v in {
            "TORCH_HOME": h / "torch",
            "HF_HOME": h / "hf",
            "NUMBA_CACHE_DIR": h / "numba",
            "NLTK_DATA": h / "nltk",
            "XDG_CACHE_HOME": h / "models" / "xdg",
            "MVH_MODELS_DIR": h / "models",
        }.items():
            env.setdefault(k, str(v))
        env["HF_HUB_OFFLINE"] = "1"  # models come only from `mvh models fetch` (PLAN §3.3)
        env["TRANSFORMERS_OFFLINE"] = "1"
        if self.s.offline:
            env["MVH_OFFLINE"] = "1"
        env.pop("KMP_DUPLICATE_LIB_OK", None)
        return env

    def _execute(self, name: str, keys: Mapping[str, str]) -> StageState:
        spec = self.specs[name]
        st = self.states[name]
        sc = self.cache.stage(name)
        token = uuid.uuid4().hex[:8]
        staging = sc.staging(st.pre_key or "", token)
        scratch = self.cache.root / "_scratch" / f"{name}-{token}"
        atomic.rmtree_retry(staging)
        staging.mkdir(parents=True, exist_ok=True)
        scratch.mkdir(parents=True, exist_ok=True)
        job = self._job(spec, st, staging, scratch, keys)
        job_path = scratch / "job.json"
        with open(job_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(job, fh, ensure_ascii=False, indent=1)
        self.cache.logs.mkdir(parents=True, exist_ok=True)
        slot = None
        t0 = time.time()
        try:
            if self.s.heavy_locks and spec.env == "main" and is_heavy(spec):
                slot = locks.acquire(f"mvh:{self.s.slug}:{name}", gpu=False, threads=st.threads)
            st.wait_s = time.time() - t0
            with open(self.cache.logs / f"{name}.log", "w", encoding="utf-8", newline="\n") as lf:
                p = proc.popen(
                    [sys.executable, "-X", "utf8", "-m", "mvh.runner.child", job_path],
                    env=self._child_env(st.threads),
                    cwd=scratch,
                    stdout=lf,
                    stderr=lf,
                    stdin=subprocess.DEVNULL,
                )
                rc = p.wait()
        finally:
            if slot is not None:
                slot.release()
        st.seconds = time.time() - t0
        done_p = staging / "_mvh" / "done.json"
        if rc == 0 and done_p.is_file():
            with open(done_p, encoding="utf-8") as fh:
                rec = json.load(fh)
            final = sc.commit(staging, st.pre_key or "")
            st.record, st.key = rec, rec["key"]
            st.status = {"ok": "done"}.get(rec["status"], rec["status"])
            st.reason = ""
            sc.set_latest({"key": rec["key"], "pre_key": st.pre_key, "key_inputs": st.key_inputs,
                           # D64: what computing this entry cost, reported again on later cache hits
                           "computed": {"seconds": round(st.seconds, 3), "wait_s": round(st.wait_s or 0.0, 3)}})
            sc.set_failed(None)
            sc.prune({final.name})
        else:
            msg = f"exit {rc}"
            err_p = staging / "_mvh" / "error.json"
            if err_p.is_file():
                try:
                    with open(err_p, encoding="utf-8") as fh:
                        e = json.load(fh)
                    msg = f"{e.get('type')}: {e.get('message')}"
                except ValueError:
                    pass
            st.status, st.reason = "failed", msg
            sc.set_failed(
                {"pre_key": st.pre_key, "message": msg[:1000], "log": str(self.cache.logs / f"{name}.log")}
            )
            atomic.rmtree_retry(staging)
        atomic.rmtree_retry(scratch)
        return st

    def publish(self, name: str) -> list[str]:
        """Link the stage's public outputs from its cache into the song folder; drop stale ones."""
        st = self.states[name]
        rec = st.record or {}
        src_dir = self.cache.stage(name).dir(st.pre_key or "")
        pub = self.cache.published()
        new: list[str] = []
        for rel, info in sorted(rec.get("outputs", {}).items()):
            if not info.get("public", True):
                continue
            if rel in ovr.USER_INPUTS:
                raise RuntimeError(f"{name} tried to publish the user input {rel}")
            src = src_dir / rel
            dst = self.s.song_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            tmp = dst.with_name(f".{dst.name}.{uuid.uuid4().hex[:6]}.lnk")
            try:
                # small files are copied so an editor that saves in place cannot rewrite the cache (D30);
                # big audio files are hard-linked (no second copy of the stems) and size-checked on a hit
                if int(info.get("bytes", 0)) >= LINK_MIN_BYTES:
                    try:
                        os.link(src, tmp)
                    except OSError:
                        atomic.copy_file(src, tmp)
                else:
                    atomic.copy_file(src, tmp)
                atomic.replace_retry(tmp, dst)
            except PermissionError:
                # a reader (player, viewer, editor) holds the published file: keep the old version, warn
                with contextlib.suppress(OSError):
                    atomic.unlink_retry(tmp)
                self.warnings.append(
                    f"{name}: {rel} is open in another program; the song folder keeps its previous version "
                    "(close the program and run mvh analyze again)"
                )
            new.append(rel)
        for rel in pub.get(name, []):
            if rel not in new and rel not in ovr.USER_INPUTS:
                other = {r for n2, rels in pub.items() if n2 != name for r in rels}
                if rel in other:
                    continue  # another stage publishes this path now: never delete its file
                try:
                    atomic.unlink_retry(self.s.song_dir / rel)
                except PermissionError:
                    self.warnings.append(f"{name}: stale {rel} is open in another program; not removed")
        pub[name] = new
        self.cache.set_published(pub)
        return new

    def unpublish(self, name: str) -> None:
        pub = self.cache.published()
        other = {r for n2, rels in pub.items() if n2 != name for r in rels}
        for rel in pub.pop(name, []):
            if rel not in ovr.USER_INPUTS and rel not in other:
                try:
                    atomic.unlink_retry(self.s.song_dir / rel)
                except PermissionError:
                    self.warnings.append(f"{name}: {rel} is open in another program; not removed")
        self.cache.set_published(pub)

    def run(self) -> dict[str, StageState]:
        from . import validate as val

        targets = self.targets()
        forced = self.forced()
        tset = set(targets)
        needed = set(tset)
        if not self.s.only:
            for t in targets:
                needed |= self.ancestors(t)
        keys: dict[str, str] = {}
        if self.s.only:
            # --only: the deps of the selected stages must already be cached (resolved, never run)
            anc: set[str] = set()
            for t in targets:
                anc |= self.ancestors(t)
            for n in self.order:
                if n in anc and n not in tset:
                    st = self.resolve(n, keys)
                    if st.status in ("done", "degraded", "skipped") and st.key:
                        keys[n] = st.key
                        st.cache = "hit"
        remaining = [n for n in self.order if n in needed]
        running: dict[Future, str] = {}
        used = 0
        budget = max(1, int(self.s.cores))
        self.s.say(
            f"analyze {self.s.slug}: {len(remaining)} stages, threads={self.s.threads}, cores={budget}, "
            f"profile={self.s.profile}"
        )
        with ThreadPoolExecutor(max_workers=budget) as ex:
            while remaining or running:
                progressed = False
                for n in list(remaining):
                    spec = self.specs[n]
                    deps = spec.deps
                    if any(
                        d in remaining or any(r == d for r in running.values()) for d in deps if d in needed
                    ):
                        continue
                    bad = [d for d in deps if d not in keys]
                    st = self.states[n]
                    if bad:
                        st.status = "pending"
                        st.reason = "upstream not done: " + ", ".join(
                            f"{d} ({self.states[d].status})" for d in bad
                        )
                        if n in tset:
                            # W3 (M6b CR-8): never drop a selected stage silently (--only with a stale upstream)
                            self.s.say(f"{n}: not run - {st.reason}")
                        remaining.remove(n)
                        progressed = True
                        continue
                    self.resolve(n, keys)
                    want_run = n in tset and (n in forced or st.status not in ("done", "degraded", "skipped"))
                    if not want_run:
                        if st.status in ("done", "degraded", "skipped"):
                            st.cache = "hit"
                            keys[n] = st.key or ""
                            self.publish(n)
                            self.s.say(f"{n}: {st.status} (cache hit)")
                        else:
                            st.reason = st.reason or "not selected"
                            if self.s.only:
                                st.reason = f"not run with --only ({st.reason})"
                        remaining.remove(n)
                        progressed = True
                        continue
                    n_threads = st.threads or 1
                    if running and used + n_threads > budget:
                        continue
                    st.cache = "forced" if n in forced and st.record is not None else "miss"
                    st.status = "running"
                    remaining.remove(n)
                    used += n_threads
                    self.s.say(f"{n}: running (threads={n_threads})")
                    running[ex.submit(self._execute, n, dict(keys))] = n
                    progressed = True
                if not running:
                    if not progressed and remaining:
                        for n in remaining:
                            self.states[n].status, self.states[n].reason = "pending", "could not be scheduled"
                        remaining = []
                    continue
                done_set, _ = wait(list(running), return_when=FIRST_COMPLETED)
                for fu in done_set:
                    n = running.pop(fu)
                    used -= self.states[n].threads or 1
                    try:
                        st = fu.result()
                    except Exception as e:  # noqa: BLE001
                        st = self.states[n]
                        st.status, st.reason = "failed", f"runner error: {type(e).__name__}: {e}"
                    if st.status in ("done", "degraded", "skipped"):
                        pub_error = None
                        errs: list[str] = []
                        try:
                            pub = self.publish(n)
                            errs = val.validate_files(self.s.song_dir, pub)
                        except Exception as e:  # noqa: BLE001
                            pub_error = f"publish failed: {type(e).__name__}: {e}"
                        if pub_error:
                            # the stage result is fine and stays cached; only the song folder is behind
                            st.status, st.reason = "failed", pub_error
                            self.warnings.append(f"{n}: {pub_error}")
                        elif errs:
                            st.status, st.reason = "failed", "validation: " + "; ".join(errs[:3])
                            try:
                                self.cache.stage(n).set_failed(
                                    {"pre_key": st.pre_key, "message": st.reason[:1000]}
                                )
                                self.unpublish(n)
                                atomic.rmtree_retry(self.cache.stage(n).dir(st.pre_key or ""))
                            except OSError as e:
                                self.warnings.append(f"{n}: cleanup after a validation failure: {e}")
                        else:
                            keys[n] = st.key or ""
                    secs = f"{st.seconds:.1f}s" if st.seconds is not None else ""
                    self.s.say(f"{n}: {st.status} {secs}{(' - ' + st.reason) if st.reason else ''}")
        # stages outside this run's selection: report their cached state (for the manifest and mvh status)
        for n in self.order:
            st = self.states[n]
            if st.status == "pending" and not st.reason and n not in keys:
                self.resolve(n, keys)
                if st.status in ("done", "degraded", "skipped") and st.key:
                    keys[n] = st.key
        return self.states


def _write_run_settings(s: Settings) -> None:
    d = {
        "input": str(s.song) if s.song else None,
        "slug": s.slug,
        "profile": s.profile,
        "threads": s.threads,
        "params_ext": s.params_ext,
        "cli_params": s.cli_params,
    }
    atomic.write_text(
        s.song_dir / ".cache" / RUN_SETTINGS, json.dumps(d, ensure_ascii=False, indent=1) + "\n"
    )


def analyze(settings: Settings, specs: Mapping[str, StageSpec] | None = None) -> dict[str, Any]:
    """Run the pipeline and finalize the song folder; returns the CLI's result object."""
    from . import finalize

    settings.song_dir.mkdir(parents=True, exist_ok=True)
    r = Runner(settings, specs)
    _write_run_settings(settings)
    errs = ovr.validate(r.overrides) if r.overrides else []
    if errs:
        r.warnings.append("overrides.json does not match mvh/envelope/overrides: " + "; ".join(errs[:3]))
    r.run()
    out = finalize.finalize(r)
    return out


def status(
    song_dir: Path, *, profile: str | None = None, threads: int | None = None
) -> dict[str, StageState]:
    prev = load_run_settings(song_dir)
    s = Settings(
        song=None,
        song_dir=Path(song_dir),
        slug=prev.get("slug") or Path(song_dir).name,
        profile=profile or prev.get("profile", "max"),
        threads=threads or _env_threads(),  # what the next `mvh analyze` would use (D36), not the last run
        params_ext=dict(prev.get("params_ext", {})),
        cli_params=dict(prev.get("cli_params", {})),
    )
    r = Runner(s)
    return r.status()
