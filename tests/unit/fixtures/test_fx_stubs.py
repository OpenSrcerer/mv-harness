# ruff: noqa: E501  (long data tables / docstrings in generated-fixture code)
"""A stub run of every stage succeeds against the synthetic fixture, and the runner-style curve packing reproduces it."""

import numpy as np
import pytest
from tests.synth import stubrun

from mvh.contract import curvefile

pytestmark = pytest.mark.timeout(600)


@pytest.fixture(scope="module")
def stub_run(synth, tmp_path_factory):
    out = tmp_path_factory.mktemp("stubrun")
    return out, stubrun.run_all(out, synth)


def test_every_stage_stub_succeeds(stub_run):
    out, res = stub_run
    from mvh.contract.stages import STAGE_NAMES

    assert set(res) == set(STAGE_NAMES)
    for name, (r, w) in res.items():
        assert r.status == "ok", name
        assert r.summary["copied"] > 0, name


def test_every_public_file_copied(stub_run, synth):
    out, res = stub_run
    copied = {rel for _, w in res.values() for rel, public in w.copied if public}
    expected = {p.relative_to(synth).as_posix() for p in synth.rglob("*") if p.is_file()}
    expected = {
        r
        for r in expected
        if not r.startswith(("_", ".", "schema/", "curves/"))
        and r not in ("manifest.json", "run.json", "meaning/intent.md", "meaning/authored.json")
    }
    assert expected == copied


def test_intermediates_copied(stub_run):
    out, res = stub_run
    inter = {(n, rel) for n, (_, w) in res.items() for rel, public in w.copied if not public}
    assert ("ingest", "canonical.wav") in inter
    assert (
        ("allin1", "allin1.json") in inter
        and ("allin1", "activations.f32") in inter
        and ("allin1", "embeddings.f32") in inter
    )
    assert {("separate_fast", f"fast/{s}.wav") for s in ("vocals", "drums", "bass", "other")} <= inter
    assert ("separate_fast", "fast/separation.json") in inter


def test_curve_repack_is_identical(stub_run, synth):
    out, res = stub_run
    idx = stubrun.assemble_curves(out, [w for _, w in res.values()])
    ref = curvefile.read_index(synth)
    assert idx == ref
    for fid, f in ref["files"].items():
        assert (out / f["path"]).read_bytes() == (synth / f["path"]).read_bytes(), fid


def test_each_file_copied_by_one_stage(stub_run):
    out, res = stub_run
    seen = {}
    for name, (_, w) in res.items():
        for rel, public in w.copied:
            if public:
                seen.setdefault(rel, []).append(name)
    dup = {k: v for k, v in seen.items() if len(v) > 1}
    assert not dup, dup


def test_stub_writer_rejects_undeclared(synth, tmp_path):
    from mvh.runner.spec import UndeclaredOutput, load_stage_specs

    spec = load_stage_specs()["loudness"]
    w = stubrun.StubWriter(spec, tmp_path)
    with pytest.raises(UndeclaredOutput):
        w.copy("meta/tempo.json", synth / "meta/tempo.json")
    w.copy("meta/loudness.json", synth / "meta/loudness.json")
    assert np.array_equal(
        np.frombuffer((tmp_path / "meta/loudness.json").read_bytes(), np.uint8),
        np.frombuffer((synth / "meta/loudness.json").read_bytes(), np.uint8),
    )
