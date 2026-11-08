# ruff: noqa: E501  (long catalogue tables / docstrings)
"""Stage declarations and the stage interface (PLAN §3.2, §3.3). FROZEN at contract v1.

Every stage is a package ``mvh.stages.<name>`` whose ``__init__.py`` defines

    STAGE: StageSpec            # the declaration the runner builds the DAG from
    def run(ctx: Ctx) -> StageResult

The runner (W1b runtime builder) implements ``Ctx``, ``Upstream`` and ``Writer`` around these protocols.
Stage code must not touch the output folder directly: it reads only through ``ctx`` (which enforces the
declared deps) and writes only through ``ctx.writer`` (which enforces the declared outputs, validates
against the contract schemas, writes atomically and records provenance).

Stdlib + numpy only (worker rule, PLAN §3.3): this module is imported by the sep worker too.
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Mapping, Protocol, Sequence, runtime_checkable

from mvh.contract.ids import EVENTS_NAME_RE, SEMVER_RE, STAGE_NAME_RE

__all__ = [
    "Env", "OutputKind", "Status", "Trigger", "OUTPUT_KINDS", "Output", "ExternalInput", "StageSpec",
    "StageResult", "Ctx", "Upstream", "Writer", "EventFileLike", "Curve", "Audio", "ModelHandle", "HttpClient",
    "StageError", "UndeclaredDependency", "UndeclaredOutput", "MissingFixture",
    "load_stage_specs", "check_dag", "topo_order", "OVERRIDE_KEY_RE",
]

Env = Literal["main", "sep"]
OutputKind = Literal["curve", "matrix", "events", "table", "audio", "midi", "text", "json"]
Status = Literal["ok", "degraded", "skipped", "failed"]
Trigger = Literal["analyze", "on_demand"]
OUTPUT_KINDS: tuple[str, ...] = ("curve", "matrix", "events", "table", "audio", "midi", "text", "json")
#: override keys are "<section>.<field>" paths into overrides.json (see schema mvh/overrides)
OVERRIDE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
_PLACEHOLDER_RE = re.compile(r"\{(src|stem|sub|voice|fps)\}")


# ----------------------------------------------------------------------------------------- declarations
@dataclass(frozen=True)
class Output:
    """One declared output of a stage.

    path      Relative POSIX path. Public outputs are relative to the song folder ``out/<slug>/``;
              non-public ones (``public=False``) to the stage's cache dir (they never reach the song folder,
              downstream stages read them through ``ctx.upstream``). May contain the placeholders
              ``{src}``, ``{stem}``, ``{sub}``, ``{voice}``, ``{fps}`` for families of files.
              For ``kind='curve'`` the path is the curve *file* (``curves/core.f32``) the channels go to;
              the runner packs the file and ``curves/index.json`` from every stage's channels.
    kind      curve | matrix | events | table | audio | midi | text | json.
    schema    Contract schema id (``mvh/events/beats``) or None (audio, midi, free text).
    required  False for optional outputs (drum sub-stems, visemes, cover art, ...).
    public    False for intermediates (allin1 activations, separate_fast stems, the canonical WAV).
    events    The events name for ``kind='events'`` (``notes.{src}`` patterns allowed).
    restrict  ((placeholder, (values...)), ...): limits a pattern, e.g. notes.{src} to bass/piano/guitar/other.
    channels  For ``kind='curve'``/``'matrix'``: the channel ids (patterns allowed) this stage writes.
    """

    path: str
    kind: OutputKind
    schema: str | None = None
    required: bool = True
    public: bool = True
    events: str | None = None
    channels: tuple[str, ...] = ()
    description: str = ""
    restrict: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in OUTPUT_KINDS:
            raise ValueError(f"bad output kind {self.kind!r} for {self.path}")
        if self.path.startswith(("/", "\\")) or "\\" in self.path or ".." in self.path.split("/"):
            raise ValueError(f"output paths are relative POSIX paths: {self.path!r}")
        if self.kind == "events":
            if not self.events:
                raise ValueError(f"events output {self.path} needs an events name")
            if not EVENTS_NAME_RE.match(_PLACEHOLDER_RE.sub("x", self.events)):
                raise ValueError(f"bad events name {self.events!r}")
        if self.kind in ("curve", "matrix") and not self.channels:
            raise ValueError(f"{self.kind} output {self.path} must list its channels")

    @property
    def is_pattern(self) -> bool:
        return bool(_PLACEHOLDER_RE.search(self.path))

    def expand(self, **values: str) -> str:
        """Fill placeholders: Output('events/notes.{src}.json', ...).expand(src='bass')."""
        return _PLACEHOLDER_RE.sub(lambda m: values[m.group(1)], self.path)


@dataclass(frozen=True)
class ExternalInput:
    """A file outside the cache that a stage reads; its content hash goes into the cache key (NF2).

    path  Relative to the song folder (``meaning/intent.md``), or ``param:<name>`` for a path given on
          the CLI (``param:lyrics`` = ``--lyrics``), or ``http:<label>`` for cached network responses.
    """

    name: str
    path: str
    required: bool = False
    description: str = ""


@dataclass(frozen=True)
class StageSpec:
    """The declaration of one stage (PLAN §3.2). Positional order is frozen:
    ``StageSpec(name, deps, env, version, override_keys, outputs, params)``."""

    name: str
    deps: tuple[str, ...]
    env: Env
    version: str
    override_keys: tuple[str, ...] = ()
    outputs: tuple[Output, ...] = ()
    params: Mapping[str, Any] = field(default_factory=dict)
    # ---- keyword extras (all feed the cache key, NF2) ----
    params_by_profile: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    external_inputs: tuple[ExternalInput, ...] = ()
    models: tuple[str, ...] = ()          # ids in models.lock.json
    network: bool = False                  # uses the network (cached responses are hashed into the key)
    uses_ffmpeg: bool = False              # ffmpeg version + buildconf go into the key
    gpu: bool = False                      # may run on a GPU: the device class goes into the key
    trigger: Trigger = "analyze"           # 'on_demand' stages (frames) run only when asked for
    module: str = ""                       # owning build module (M1 ... M6b, W1b-runtime)
    description: str = ""

    def __post_init__(self) -> None:
        if not STAGE_NAME_RE.match(self.name):
            raise ValueError(f"bad stage name {self.name!r}")
        if self.env not in ("main", "sep"):
            raise ValueError(f"{self.name}: env must be 'main' or 'sep'")
        if not SEMVER_RE.match(self.version):
            raise ValueError(f"{self.name}: version must be semver, got {self.version!r}")
        if self.name in self.deps or len(set(self.deps)) != len(self.deps):
            raise ValueError(f"{self.name}: deps must be unique and must not include itself")
        for d in self.deps:
            if not STAGE_NAME_RE.match(d):
                raise ValueError(f"{self.name}: bad dep {d!r}")
        for k in self.override_keys:
            if not OVERRIDE_KEY_RE.match(k):
                raise ValueError(f"{self.name}: bad override key {k!r}")
        paths = [o.path for o in self.outputs if o.kind != "curve"]
        if len(set(paths)) != len(paths):
            raise ValueError(f"{self.name}: duplicate output paths")
        if self.trigger not in ("analyze", "on_demand"):
            raise ValueError(f"{self.name}: bad trigger")
        object.__setattr__(self, "params", MappingProxyType(dict(self.params)))
        object.__setattr__(self, "params_by_profile",
                           MappingProxyType({k: MappingProxyType(dict(v)) for k, v in self.params_by_profile.items()}))

    def output(self, path: str) -> Output:
        for o in self.outputs:
            if o.path == path:
                return o
        raise KeyError(path)

    def resolved_params(self, profile: str = "max", cli: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """defaults < profile overrides < CLI values (the runner hashes the result into the cache key)."""
        p = dict(self.params)
        p.update(self.params_by_profile.get(profile, {}))
        p.update(cli or {})
        return p


@dataclass
class StageResult:
    """What ``run(ctx)`` returns. Deterministic content only: timings go to run.json, set by the runner.

    status     ok | degraded (a fallback was used; outputs complete) | skipped (stage not applicable,
               e.g. no vocals: optional outputs absent, required outputs still written, possibly empty)
               | failed (the runner marks dependants pending).
    summary    Scalars for ``manifest.summary.<stage>`` (small: no arrays longer than ~16 items).
    warnings   Human-readable warnings (never lyric text).
    fallbacks  Machine tags of fallbacks used (``sep:cpu``, ``lead_vocals:=vocals``, ``chords:template``).
    provenance Extra provenance fields merged into every output's provenance block (tools, models, notes).
    """

    status: Status = "ok"
    summary: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    fallbacks: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None


# ----------------------------------------------------------------------------------------- data handles
@dataclass(frozen=True)
class Curve:
    """One channel of a curve file: ``values`` float32 at ``rate_hz`` (sample i centred at i / rate_hz)."""

    id: str
    values: Any            # numpy.ndarray[float32]
    rate_hz: float
    meta: Mapping[str, Any]   # the channel's curves/index.json entry (unit, range, norm, resample, special, ...)


@dataclass(frozen=True)
class Audio:
    """Decoded audio: ``samples`` float32 shaped [channels, n] at ``sr`` (decoded by ffmpeg only)."""

    samples: Any
    sr: int
    path: Path | None = None


@dataclass(frozen=True)
class ModelHandle:
    """A models.lock.json entry resolved to local files under %LOCALAPPDATA%\\mvh\\models."""

    id: str
    files: Mapping[str, Path]     # lock-file path -> local absolute path (verified sha256)
    sha256: Mapping[str, str]
    licence: str
    revision: str | None = None


@runtime_checkable
class EventFileLike(Protocol):
    name: str
    kind: str                      # 'event' | 'segment'
    fields: Mapping[str, Any]
    items: Sequence[Mapping[str, Any]]
    provenance: Mapping[str, Any]


class HttpClient(Protocol):
    """Cached, rate-limited HTTP for network stages. Responses are stored under the stage cache and their
    hashes go into the cache key. Offline (``--no-network``/``MVH_OFFLINE``) serves the cache or raises."""

    def get(self, url: str, *, params: Mapping[str, Any] | None = None,
            headers: Mapping[str, str] | None = None, min_interval_s: float = 0.0) -> Any: ...

    def post(self, url: str, *, data: bytes | None = None, json: Any = None,
             headers: Mapping[str, str] | None = None, min_interval_s: float = 0.0) -> Any: ...


class Upstream(Protocol):
    """Read-only view of one upstream stage's outputs (public and non-public)."""

    stage: str

    def path(self, rel: str) -> Path: ...                    # existing file path (raises if absent)
    def exists(self, rel: str) -> bool: ...
    def json(self, rel: str) -> Any: ...
    def text(self, rel: str) -> str: ...
    def table(self, rel: str) -> list[dict[str, str]]: ...  # CSV/TSV rows as strings (header = keys)
    def events(self, name: str) -> EventFileLike: ...
    def curve(self, channel_id: str) -> Curve: ...
    def matrix(self, file_id: str) -> tuple[Any, Mapping[str, Any]]: ...   # (array [frames x k], index entry)
    def audio(self, rel: str, *, sr: int | None = None, mono: bool = False) -> Audio: ...


class Writer(Protocol):
    """The only way a stage writes. Every call checks the path/name against ``STAGE.outputs``
    (raises UndeclaredOutput), validates JSON against the declared schema, writes atomically
    (temp + os.replace with retry), uses UTF-8, ``ensure_ascii=False`` and ``newline='\\n'``."""

    def events(self, name: str, items: Sequence[Mapping[str, Any]], *, kind: str | None = None,
               fields: Mapping[str, Mapping[str, Any]] | None = None,
               extra: Mapping[str, Any] | None = None) -> Path: ...
    def json(self, rel: str, obj: Any) -> Path: ...
    def text(self, rel: str, text: str) -> Path: ...
    def table(self, rel: str, rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> Path: ...
    def bytes(self, rel: str, data: bytes) -> Path: ...
    def copy(self, rel: str, src: Path) -> Path: ...
    def audio(self, rel: str, samples: Any, sr: int) -> Path: ...     # float32 [ch, n]; the parent encodes FLAC
    def midi(self, rel: str, data: bytes) -> Path: ...
    def curves(self, file_id: str, channels: Mapping[str, Any], *,
               meta: Mapping[str, Mapping[str, Any]] | None = None, rate_hz: float | None = None) -> None: ...
    def matrix(self, file_id: str, array: Any, *, meta: Mapping[str, Any] | None = None) -> None: ...


class Ctx(Protocol):
    """Everything a stage may use. Implemented by the runner (and by the sep worker for env='sep')."""

    spec: StageSpec
    slug: str
    params: Mapping[str, Any]       # StageSpec.resolved_params(profile, cli)
    profile: str                    # 'max' | 'draft'
    threads: int                    # already applied to OMP/BLAS/numba/torch/ORT/ctranslate2 by the runner
    device: str                     # 'cpu' | 'rocm' | 'vulkan'
    offline: bool
    scratch: Path                   # private temp dir, removed after the stage
    log: logging.Logger             # never log lyric text
    overrides: Mapping[str, Any]    # declared override keys only: {'rhythm.bpm': 123.0}; absent = not set
    writer: Writer

    def upstream(self, stage: str) -> Upstream: ...                 # raises UndeclaredDependency
    def events(self, name: str) -> EventFileLike: ...               # producer looked up in the catalog
    def curve(self, channel_id: str) -> Curve: ...                  # producer looked up in the registry
    def audio(self, name: str = "mix", *, sr: int | None = None, mono: bool = False) -> Audio: ...
    # name: 'mix' (canonical float32 decode; every stage may read it) or a stem name ('lead_vocals',
    # 'drums_kick', 'fast:vocals' for separate_fast stems); stems require the producing stage in deps.
    def model(self, model_id: str) -> ModelHandle: ...              # must be listed in STAGE.models
    def external(self, name: str) -> Path | None: ...               # declared ExternalInput; None if absent
    def http(self) -> HttpClient: ...                               # only when STAGE.network
    def ffmpeg(self) -> Path: ...
    # D29 (additive): env='sep' stages run inference in the sep worker env. ``inputs`` maps names to Audio,
    # (samples, sr) or float32 WAV paths; returns mvh.runner.sepworker.WorkerResult (.outputs, .read(rel),
    # .variant, .fallbacks). Variant order: rocm, then cpu; the parent encodes, validates and caches.
    def worker(self, inputs: Mapping[str, Any], *, params: Mapping[str, Any] | None = None,
               models: Sequence[str] | None = None, variants: Sequence[str] | None = None,
               timeout: float | None = None, hold_slot: bool | None = None) -> Any: ...


# ----------------------------------------------------------------------------------------- errors
class StageError(RuntimeError):
    """A stage failed in a way the runner should report (no traceback needed)."""


class UndeclaredDependency(StageError):
    pass


class UndeclaredOutput(StageError):
    pass


class MissingFixture(StageError):
    """A walking-skeleton stub could not find its fixture file in tests/contract/synth/."""


# ----------------------------------------------------------------------------------------- discovery
def load_stage_specs(package: str = "mvh.stages") -> dict[str, StageSpec]:
    """Import every ``<package>.<name>`` sub-package and collect its ``STAGE``. Registration is by
    convention: a stage exists iff its package defines STAGE (and STAGE.name equals the package name)."""
    pkg = importlib.import_module(package)
    specs: dict[str, StageSpec] = {}
    for m in sorted(pkgutil.iter_modules(pkg.__path__), key=lambda m: m.name):
        if not m.ispkg:
            continue
        mod = importlib.import_module(f"{package}.{m.name}")
        spec = getattr(mod, "STAGE", None)
        if spec is None:
            continue
        if not isinstance(spec, StageSpec) or spec.name != m.name:
            raise ValueError(f"{package}.{m.name}.STAGE must be a StageSpec named {m.name!r}")
        if not callable(getattr(mod, "run", None)):
            raise ValueError(f"{package}.{m.name} must define run(ctx)")
        specs[spec.name] = spec
    return specs


def check_dag(specs: Mapping[str, StageSpec]) -> None:
    """Raise ValueError on an unknown dep, a cycle, or an 'analyze' stage depending on an on-demand one."""
    for s in specs.values():
        for d in s.deps:
            if d not in specs:
                raise ValueError(f"{s.name} depends on unknown stage {d!r}")
            if s.trigger == "analyze" and specs[d].trigger == "on_demand":
                raise ValueError(f"{s.name} cannot depend on on-demand stage {d!r}")
    topo_order(specs)
    # one producer per path: an exact path or a pattern match claimed by two stages would be published twice
    from .ctx import output_regex

    exact: dict[str, str] = {}
    for s in specs.values():
        for o in s.outputs:
            if o.kind in ("curve", "matrix") and o.public or o.is_pattern:
                continue
            if o.path in exact and exact[o.path] != s.name:
                raise ValueError(f"{o.path} is declared by both {exact[o.path]} and {s.name}")
            exact[o.path] = s.name
    for s in specs.values():
        for o in s.outputs:
            if o.is_pattern and o.kind not in ("curve", "matrix"):
                rx = output_regex(o.path, o.restrict)
                for p, owner in exact.items():
                    if owner != s.name and rx.match(p):
                        raise ValueError(f"{s.name} output pattern {o.path} also matches {p} of {owner}")


def topo_order(specs: Mapping[str, StageSpec]) -> list[str]:
    """Deterministic topological order (Kahn; ties broken by name). Raises ValueError on a cycle."""
    indeg = {n: 0 for n in specs}
    users: dict[str, list[str]] = {n: [] for n in specs}
    for s in specs.values():
        for d in s.deps:
            if d in specs:
                indeg[s.name] += 1
                users[d].append(s.name)
    ready = sorted(n for n, k in indeg.items() if k == 0)
    order: list[str] = []
    while ready:
        n = ready.pop(0)
        order.append(n)
        for u in sorted(users[n]):
            indeg[u] -= 1
            if indeg[u] == 0:
                ready.append(u)
                ready.sort()
    if len(order) != len(specs):
        cyc = sorted(n for n, k in indeg.items() if k > 0)
        raise ValueError(f"stage graph has a cycle among: {cyc}")
    return order


# ----------------------------------------------------------------------------------------- catalogue
def catalog_outputs(stage: str) -> tuple[Output, ...]:
    """The frozen outputs of ``stage`` from mvh.contract.catalog / registry, as Output declarations.
    Stage packages declare ``outputs=catalog_outputs('<name>') + (extra Output(...), ...)``."""
    from mvh.contract import catalog, registry
    from mvh.contract.ids import PITCHED_SOURCES

    # concrete paths that other stages declare exactly: a {src} pattern must not claim them (D6: the vocals
    # stage owns events/notes.vocals.json and notes/vocals.mid; two producers would publish one path twice)
    others = {f.path for f in catalog.FILES if f.stage != stage} | {e.file for e in catalog.EVENTS if e.stage != stage}

    def restrict(path: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
        if "{src}" not in path:
            return ()
        ok = tuple(v for v in PITCHED_SOURCES if path.replace("{src}", v) not in others)
        return (("src", ok),) if ok != PITCHED_SOURCES else ()

    outs: list[Output] = []
    for f in catalog.files_of(stage):
        outs.append(Output(f.path, f.kind, ("mvh/" + f.schema) if f.schema else None, f.required, f.public,
                           channels=f.channels, description=f.description, restrict=restrict(f.path)))
    for e in catalog.events_of(stage):
        outs.append(Output(e.file, "events", "mvh/" + e.schema_id, e.required, True, events=e.name,
                           description=e.description, restrict=restrict(e.file)))
    for t in catalog.tables_of(stage):
        outs.append(Output(t.path, "table", "mvh/" + t.schema, True, True, description=t.description))
    by_file: dict[str, list[str]] = {}
    for c in registry.channels_of(stage):
        by_file.setdefault(c.file, []).append(c.id)
    for fid, ids in by_file.items():
        cf = registry.CURVE_FILES[fid]
        outs.append(Output(cf.path, "matrix" if cf.layout == "row-major" else "curve", None, True, True,
                           channels=tuple(ids), description=cf.description))
    return tuple(outs)


__all__.append("catalog_outputs")
