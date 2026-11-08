# ruff: noqa: E501  (long catalogue tables / docstrings)
"""Schemas are valid and up to date; envelopes, curve files and the stub copy behave as specified."""
import json
import math

import numpy as np
import pytest
from jsonschema import Draft202012Validator

from mvh.contract import catalog, curvefile, events, fixture, gen, golden, schemas
from mvh.runner.spec import MissingFixture, StageSpec, catalog_outputs

SHA = "0" * 64
PROV = {"stage": "rhythm", "stage_version": "1.0.0", "contract_version": catalog.CONTRACT_VERSION, "key": SHA, "params": {},
        "models": [], "tools": [], "device": "cpu", "upstream": {}, "overrides_applied": [], "fallbacks": []}


def test_all_schemas_valid_and_unique():
    ids = set()
    for p in schemas.iter_schema_files():
        s = json.loads(p.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(s)
        assert s["$id"] not in ids
        ids.add(s["$id"])
        assert p.read_bytes().count(b"\r") == 0
    assert len(ids) == len(schemas.build_all())


def test_generated_artifacts_up_to_date():
    assert gen.main(["--check"]) == 0, "run: python -m mvh.contract.gen"
    assert golden.main(["--check"]) == 0, "run: python -m mvh.contract.golden"


def test_events_envelope_roundtrip(tmp_path):
    beats = [{"beat_index": i, "t": 0.5 * i + 1e-8, "bar": i // 4 + 1, "beat_in_bar": i % 4 + 1, "beats_in_bar": 4,
              "in_pulse": True, "strength": 0.8, "conf": 0.9} for i in range(8)]
    env = events.make_envelope("beats", list(reversed(beats)), PROV)
    assert [it["beat_index"] for it in env["items"]] == list(range(8))   # sorted by t
    assert env["items"][1]["t"] == 0.5                                    # rounded to 6 decimals
    assert schemas.validate(env, "mvh/events/beats") == []
    p = tmp_path / "beats.json"
    p.write_text(events.dumps_events(env), encoding="utf-8")
    ef = events.read_events(p)
    assert ef.name == "beats" and ef.kind == "event" and len(ef.items) == 8
    bad = json.loads(json.dumps(env))
    del bad["items"][3]["in_pulse"]
    assert schemas.validate(bad, "mvh/events/beats")


def test_segment_requires_d_and_notes_family():
    env = events.make_envelope("sections", [{"id": "S01", "t": 0.0, "label": "intro"}], PROV)
    errs = schemas.validate(env, "mvh/events/sections")
    assert any("'d' is a required property" in e for e in errs)
    n = events.make_envelope("notes.bass", [{"t": 1.0, "d": 0.5, "midi": 40, "name": "E2", "vel": 0.7, "conf": 0.9}], PROV)
    assert schemas.validate(n, "mvh/events/notes") == []
    n["name"] = "notes.kazoo"
    assert schemas.validate(n, "mvh/events/notes")


def test_manifest_and_overrides_examples():
    man = {
        "schema": "mvh/manifest", "schema_version": catalog.CONTRACT_VERSION, "mvh_version": "0.1.0",
        "contract_version": catalog.CONTRACT_VERSION, "slug": "jeremy",
        "source": {"file_name": "x.flac", "pcm_sha256": SHA, "duration_s": 316.587, "sample_rate": 44100, "channels": 2, "n_samples": 13961487},
        "timebase": {"unit": "s", "origin": "first sample of audio/mix.flac", "soundtrack": "audio/mix.flac", "curve_rate_hz": 100,
                     "frame_rule": "centred"},
        "status": {"stages": {"rhythm": "done"}, "meaning": "pending", "lyrics_grade": "B", "stems": True, "visemes": False, "flags": []},
        "summary": {"title": "T", "artist": "A", "duration_s": 316.587, "bpm": 104.2, "feel": "normal", "meter": "4/4", "key": "A major",
                    "integrated_lufs": -9.1, "lra_lu": 6.0, "true_peak_dbtp": 0.3, "vocal_range": {"low": "A2", "high": "E4"},
                    "instrumentation": ["electric_guitar"], "palette": ["#112233"]},
        "files": [{"path": "events/beats.json", "kind": "events", "stage": "rhythm"},
                  {"path": "lipsync/visemes.json", "kind": "events", "stage": "lipsync", "events": "visemes"}],
        "warnings": [],
    }
    assert schemas.validate(man, "mvh/envelope/manifest") == []
    man["timebase"]["curve_rate_hz"] = 50
    assert schemas.validate(man, "mvh/envelope/manifest")
    ov = {"rhythm": {"bpm": 104.0}, "structure": {"labels": [{"t": 30.0, "label": "chorus"}]},
          "lyrics": {"lines": {"L003": {"dt": -0.12}}, "words": {"L003.02": {"t": 31.2, "d": 0.3}}}, "voices": {"lines": {"L010": "V2"}}}
    assert schemas.validate(ov, "mvh/envelope/overrides") == []
    ov["voices"]["lines"]["L010"] = "Voice 2"
    assert schemas.validate(ov, "mvh/envelope/overrides")


def test_table_row_coercion():
    s = schemas.load("mvh/tables/beats")
    row = {"beat_index": "3", "t": "1.75", "bar": "1", "beat_in_bar": "4", "beats_in_bar": "4", "in_pulse": "1", "strength": "0.5",
           "section_id": "S01", "phrase_id": "", "eight_id": "E001", "count": "4", "accent": "0.2"}
    typed = schemas.coerce_row(row, s)
    assert typed["in_pulse"] is True and typed["phrase_id"] is None and typed["t"] == 1.75
    assert schemas.validate(typed, "mvh/tables/beats") == []
    assert s["x-columns"][0] == "beat_index"


def _fake_channels(n=50):
    return [curvefile.ChannelData("loud.short_term_lufs", np.linspace(-30, -10, n, dtype=np.float32)),
            curvefile.ChannelData("loud.short_term", np.linspace(0, 1, n, dtype=np.float32), {"lo": -30.0, "hi": -10.0}),
            curvefile.ChannelData("bands.bass", np.zeros(n, np.float32)),
            curvefile.ChannelData("vocal.midi", np.array([60.0, np.nan] * (n // 2), np.float32)),
            curvefile.ChannelData("spectrum128", np.full((n, 128), 7, np.uint8), {"band_edges_hz": list(range(129))})]


def test_curve_assemble_roundtrip(tmp_path):
    idx = curvefile.assemble(tmp_path, _fake_channels())
    assert schemas.validate(idx, "mvh/envelope/curves_index") == []
    core = [c["id"] for c in idx["channels"] if c["file"] == "core"]
    assert core == ["bands.bass", "loud.short_term", "loud.short_term_lufs"]       # registry order
    assert [c["offset_bytes"] for c in idx["channels"] if c["file"] == "core"] == [0, 200, 400]
    v, e = curvefile.read_channel(tmp_path, curvefile.read_index(tmp_path), "loud.short_term_lufs")
    assert v[0] == -30 and v[-1] == -10 and e["resample"] == "mean" and e["special"] == {"floor": -70.0}
    e2 = next(c for c in idx["channels"] if c["id"] == "loud.short_term")
    assert e2["norm"] == {"method": "p02-p99.5", "of": "loud.short_term_lufs", "lo": -30.0, "hi": -10.0}
    m, f = curvefile.read_matrix(tmp_path, idx)
    assert m.shape == (50, 128) and f["quant"]["scale"] == pytest.approx(1 / 255)
    raw = (tmp_path / "curves/core.f32").read_bytes()
    assert len(raw) == 3 * 50 * 4
    assert math.isnan(curvefile.read_channel(tmp_path, idx, "vocal.midi")[0][1])


def test_curve_assemble_rejects_bad_values(tmp_path):
    with pytest.raises(ValueError, match="NaN"):
        curvefile.assemble(tmp_path, [curvefile.ChannelData("bands.bass", np.array([np.nan], np.float32))], write=False)
    with pytest.raises(ValueError, match="inf"):
        curvefile.assemble(tmp_path, [curvefile.ChannelData("bands.bass_db", np.array([-np.inf], np.float32))], write=False)
    with pytest.raises(KeyError):
        curvefile.assemble(tmp_path, [curvefile.ChannelData("bands.nope", np.zeros(3, np.float32))], write=False)


class _Writer:
    def __init__(self):
        self.calls = []

    def copy(self, rel, src):
        self.calls.append(("copy", rel))

    def curves(self, fid, chans, meta=None):
        self.calls.append(("curves", fid, sorted(chans)))

    def matrix(self, fid, arr, meta=None):
        self.calls.append(("matrix", fid, arr.shape))


class _Ctx:
    def __init__(self, spec):
        self.spec = spec
        self.writer = _Writer()


def test_stub_copies_from_fixture(tmp_path, monkeypatch):
    fx = tmp_path / "synth"
    curvefile.assemble(fx, [curvefile.ChannelData(c, np.zeros(10, np.float32)) for c in
                            ("loud.momentary_lufs", "loud.momentary", "loud.short_term_lufs", "loud.short_term", "loud.rms_db",
                             "loud.rms", "loud.peak_db", "loud.crest_db", "bands.bass")])
    (fx / "meta").mkdir()
    (fx / "meta/loudness.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv(fixture.FIXTURE_ENV, str(fx))
    spec = StageSpec("loudness", ("ingest",), "main", "0.0.1-stub", outputs=catalog_outputs("loudness"))
    ctx = _Ctx(spec)
    res = fixture.run_stub(ctx)
    assert res.status == "ok"
    assert ("copy", "meta/loudness.json") in ctx.writer.calls
    curves = [c for c in ctx.writer.calls if c[0] == "curves"]
    assert curves and "bands.bass" not in curves[0][2] and "loud.crest_db" in curves[0][2]
    (fx / "meta/loudness.json").unlink()
    with pytest.raises(MissingFixture):
        fixture.run_stub(_Ctx(spec))


def test_stub_pattern_and_intermediate(tmp_path, monkeypatch):
    fx = tmp_path / "synth"
    (fx / "_intermediate/separate_fast/fast").mkdir(parents=True)
    for s in ("vocals", "drums"):
        (fx / f"_intermediate/separate_fast/fast/{s}.wav").write_bytes(b"RIFF")
    (fx / "_intermediate/separate_fast/fast/separation.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv(fixture.FIXTURE_ENV, str(fx))
    spec = StageSpec("separate_fast", ("ingest",), "main", "0.0.1-stub", outputs=catalog_outputs("separate_fast"))
    ctx = _Ctx(spec)
    fixture.run_stub(ctx)
    assert sorted(c[1] for c in ctx.writer.calls) == ["fast/drums.wav", "fast/separation.json", "fast/vocals.wav"]


def test_missing_fixture_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(fixture.FIXTURE_ENV, str(tmp_path / "nope"))
    spec = StageSpec("loudness", ("ingest",), "main", "0.0.1-stub", outputs=catalog_outputs("loudness"))
    with pytest.raises(MissingFixture, match="whole folder"):
        fixture.run_stub(_Ctx(spec))
