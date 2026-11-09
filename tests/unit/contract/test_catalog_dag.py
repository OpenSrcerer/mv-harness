"""The stage DAG built from the stubs matches PLAN §3.2, and the catalogue / Consumed-by matrix are consistent."""
import re

import pytest

import mvh
from mvh.contract import catalog, registry, schemas
from mvh.contract.stages import ANALYSIS_STAGES, STAGE_NAMES
from mvh.runner.spec import StageSpec, check_dag, load_stage_specs, topo_order

# PLAN §3.2, transcribed by hand ("separate_*" = separate_fast + separate_hq; "all" = every analysis stage)
PLAN_DEPS = {
    "ingest": set(),
    "identity": {"ingest"},
    "separate_fast": {"ingest"},
    "separate_hq": {"ingest"},
    "allin1": {"separate_fast"},
    "spectral": {"ingest"},
    "loudness": {"ingest"},
    "rhythm": {"ingest", "allin1", "spectral"},
    "harmony": {"ingest", "rhythm"},
    "dynamics": {"loudness", "spectral", "rhythm"},
    "structure": {"allin1", "rhythm", "harmony", "dynamics"},
    "stem_activity": {"ingest", "separate_fast", "separate_hq"},
    "drums": {"separate_hq", "stem_activity", "spectral"},  # W4 UD2 (D79): the kick-source choice compares hits.kick
    "instruments": {"ingest", "separate_fast", "separate_hq", "stem_activity"},
    "notes": {"separate_hq", "stem_activity", "rhythm"},
    "vocals": {"separate_hq", "stem_activity", "instruments", "rhythm", "lyrics"},  # W3 CR-M3b-1 (D67)
    "mood": {"ingest", "structure"},
    "lyrics": {"identity", "ingest", "separate_hq", "stem_activity", "structure"},   # W3 CR-M5-1 (D32 embedded lyrics)
    "voices": {"lyrics", "separate_hq", "stem_activity"},
    "lipsync": {"lyrics", "voices", "separate_hq"},
    "choreo": {"rhythm", "structure", "drums", "spectral", "vocals", "harmony", "dynamics"},
    "cues": {"choreo", "structure", "dynamics", "rhythm", "drums"},
    "meaning": {"identity", "lyrics", "voices", "structure", "mood", "vocals", "instruments", "cues"},
    "brief": set(ANALYSIS_STAGES),
    "viewer": set(ANALYSIS_STAGES),
    "frames": set(ANALYSIS_STAGES),
}


@pytest.fixture(scope="module")
def specs():
    return load_stage_specs()


def test_every_stage_has_a_stub(specs):
    assert set(specs) == set(STAGE_NAMES) == set(PLAN_DEPS)


def test_deps_match_plan(specs):
    for name, s in specs.items():
        assert set(s.deps) == PLAN_DEPS[name], name


def test_dag_acyclic_and_ordered(specs):
    check_dag(specs)
    order = topo_order(specs)
    pos = {n: i for i, n in enumerate(order)}
    for s in specs.values():
        for d in s.deps:
            assert pos[d] < pos[s.name]
    assert order[0] == "ingest"


def test_cycle_detected():
    a = StageSpec("a", ("b",), "main", "1.0.0")
    b = StageSpec("b", ("a",), "main", "1.0.0")
    with pytest.raises(ValueError, match="cycle"):
        check_dag({"a": a, "b": b})
    with pytest.raises(ValueError, match="unknown"):
        check_dag({"a": a})


def test_envs_and_triggers(specs):
    assert specs["separate_hq"].env == "sep"
    assert all(s.env == "main" for n, s in specs.items() if n != "separate_hq")
    assert specs["frames"].trigger == "on_demand"
    assert all(s.trigger == "analyze" for n, s in specs.items() if n != "frames")


def test_outputs_have_schemas_on_disk(specs):
    on_disk = {p.relative_to(schemas.SCHEMA_DIR).as_posix()[:-len(".schema.json")] for p in schemas.iter_schema_files()}
    for s in specs.values():
        for o in s.outputs:
            if o.schema:
                assert schemas.short_id(o.schema) in on_disk, (s.name, o.path, o.schema)
    for f in catalog.RUNNER_FILES:
        if f.schema:
            assert f.schema in on_disk


def test_every_catalog_entry_has_a_real_producer(specs):
    for f in catalog.FILES:
        assert f.stage in specs, f.path
    for e in catalog.EVENTS:
        assert e.stage in specs, e.name
    for t in catalog.TABLES:
        assert t.stage in specs, t.path
    for c in registry.CHANNELS.values():
        assert c.stage in specs, c.id
        assert c.file in registry.CURVE_FILES
        assert c.resample in ("linear", "mean", "max", "hold")


def test_public_paths_unique():
    paths = [f.path for f in catalog.FILES + catalog.RUNNER_FILES if f.public] + [e.file for e in catalog.EVENTS] + \
            [t.path for t in catalog.TABLES]
    assert len(paths) == len(set(paths))


def test_override_keys(specs):
    for s in specs.values():
        for k in s.override_keys:
            assert catalog.OVERRIDE_KEYS[k] == s.name, (s.name, k)
    declared = {k for s in specs.values() for k in s.override_keys}
    assert declared == set(catalog.OVERRIDE_KEYS)
    props = catalog.OVERRIDES["properties"]
    for k in catalog.OVERRIDE_KEYS:
        sec, fld = k.split(".")
        assert fld in props[sec]["properties"], k


def _resolve(target: str):
    """(producer stage or None, required-field set or None) for a Consumed-by target."""
    kind, _, rest = target.partition(":")
    if kind == "events":
        if rest == "*":
            return None, None
        e = catalog.event_def(rest)
        return e.stage, {f.name for f in e.fields if f.required}
    if kind == "file":
        prod = catalog.producer_of_file(rest)
        f = next(x for x in catalog.FILES + catalog.RUNNER_FILES if x.path == rest)
        req = set(catalog.FILE_SCHEMAS[f.schema]["required"]) if f.schema in catalog.FILE_SCHEMAS else None
        return prod, req
    if kind == "intermediate":
        stage, _, path = rest.partition("/")
        f = next(x for x in catalog.FILES if x.stage == stage and x.path == path)
        assert not f.public
        req = set(catalog.FILE_SCHEMAS[f.schema]["required"]) if f.schema else None
        return stage, req
    if kind == "curve":
        if rest == "*":
            return None, None
        cid = rest.replace("{pc}", "0").replace("{drum}", "kick").replace("{stem}", "bass")
        return registry.channel(cid).stage, None
    if kind == "matrix":
        return "spectral", None
    if kind == "audio":
        if rest in ("mix",):
            return "ingest", None
        if rest == "preview":
            return "ingest", None
        if rest.startswith("fast:"):
            return "separate_fast", None
        return "separate_hq", None
    if kind == "ext":
        return None, None
    raise AssertionError(target)


def test_consumed_by_matches_deps_and_frozen_fields(specs):
    assert set(catalog.CONSUMES) == set(specs)
    for stage, reads in catalog.CONSUMES.items():
        allowed = set(specs[stage].deps)
        for target, fields in reads:
            prod, req = _resolve(target)
            if prod is None:
                continue
            if target == "audio:mix":
                continue   # D8: every stage may read the canonical mix
            assert prod in allowed, f"{stage} reads {target} from {prod}, which is not in its deps"
            if req is not None:
                missing = set(fields) - req
                assert not missing, f"{stage} consumes non-frozen fields {missing} of {target}"


def test_versions_agree():
    assert mvh.CONTRACT_VERSION == catalog.CONTRACT_VERSION


def test_registry_patterns():
    assert registry.channel("stem.drums_kick.level").id == "stem.{stem}.level"
    assert registry.channel("vocal.mouth_open.V3").id == "vocal.mouth_open.{voice}"
    assert registry.match_channel("stem.nope.level") is None
    assert registry.channel("vocal.midi").nan_aware
    twins = [c for c in registry.CHANNELS.values() if c.twin and "{" not in c.id]
    for c in twins:
        assert registry.channel(c.twin), c.id
    e = registry.index_entry(registry.channel("stem.bass.level"), "stem.bass.level")
    assert e["twin"] == "stem.bass.rms_db" and e["norm"]["of"] == "stem.bass.rms_db"


def test_no_stage_is_still_a_stub(specs):
    """W3: every walking-skeleton stub has been replaced by a real implementation (PLAN §12 W3 step 1).
    The stub copier itself (mvh.contract.fixture.run_stub) stays covered by test_schemas_io.py."""
    import importlib
    import inspect

    for name in specs:
        mod = importlib.import_module(f"mvh.stages.{name}")
        src = inspect.getsource(mod.run)
        assert "run_stub" not in src, f"{name}.run still delegates to the fixture copier"
        assert re.match(r"^\d+\.\d+\.\d+", mod.STAGE.version), name
