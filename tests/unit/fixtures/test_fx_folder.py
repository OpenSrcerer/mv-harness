"""The synthetic fixture folder is complete, schema-valid and internally consistent with the catalogue."""

import hashlib
import json

import numpy as np
import pytest
from tests.synth.stubrun import load_json

from mvh.contract import catalog, curvefile, registry, schemas
from mvh.contract.conventions import n_curve_frames
from mvh.contract.events import read_events

pytestmark = pytest.mark.timeout(600)


def test_done_json_matches_tree(synth):
    done = load_json(synth / ".done.json")
    assert done["validation_errors"] == []
    files = {
        p.relative_to(synth).as_posix(): p for p in synth.rglob("*") if p.is_file() and p.name != ".done.json"
    }
    assert set(files) == set(done["files"]), (
        "fixture folder differs from .done.json (stale or edited by hand)"
    )
    for rel, p in files.items():
        assert hashlib.sha256(p.read_bytes()).hexdigest() == done["files"][rel], rel


def _schema_for(rel: str):
    for f in catalog.FILES + catalog.RUNNER_FILES:
        if f.path == rel and f.schema:
            return "mvh/" + f.schema
    return None


def test_every_json_validates(synth):
    checked = 0
    for p in sorted(synth.rglob("*.json")):
        rel = p.relative_to(synth).as_posix()
        if rel.startswith(("schema/", "_truth/")) or p.name == ".done.json" or rel == "meaning/schema.json":
            continue
        doc = load_json(p)
        if rel.startswith("_intermediate/"):
            stage, sub = rel.split("/", 2)[1:]
            sid = {"allin1.json": "mvh/intermediate/allin1", "fast/separation.json": "mvh/files/separation"}[
                sub
            ]
        elif isinstance(doc, dict) and str(doc.get("schema", "")).startswith("mvh/events/"):
            sid = doc["schema"]
        else:
            sid = _schema_for(rel)
        assert sid, f"no schema known for {rel}"
        errs = schemas.validate(doc, sid)
        assert not errs, f"{rel}: {errs[:5]}"
        checked += 1
    assert checked >= 60


def test_tables_validate(synth):
    import csv

    for t in catalog.TABLES:
        paths = sorted(synth.glob(t.path.replace("{fps}", "*")))
        assert paths, t.path
        sch = schemas.load(t.schema)
        for p in paths:
            raw = p.read_bytes()
            assert not raw.startswith(b"\xef\xbb\xbf") and b"\r\n" not in raw, f"{p}: BOM or CRLF"
            with open(p, encoding="utf-8", newline="") as fh:
                rows = list(csv.DictReader(fh, delimiter=t.sep))
            assert rows, p
            assert list(rows[0])[: len(t.columns)] == [c.name for c in t.columns]
            for r in rows:
                errs = schemas.validate(schemas.coerce_row(r, sch), t.schema)
                assert not errs, (p.name, r, errs[:3])


def test_catalog_outputs_present(synth):
    """Every required file/events/table of every stage exists; every non-pattern channel is in the index."""
    from mvh.runner.spec import catalog_outputs

    index = curvefile.read_index(synth)
    ids = {c["id"] for c in index["channels"]}
    for stage in catalog.all_stages():
        for o in catalog_outputs(stage):
            if o.kind in ("curve", "matrix") and o.public:
                for ch in o.channels:
                    if "{" in ch:
                        assert any(registry.match_channel(i) is registry.CHANNELS[ch] for i in ids), (
                            stage,
                            ch,
                        )
                    else:
                        assert ch in ids, (stage, ch)
                continue
            base = synth if o.public else synth / "_intermediate" / stage
            if "{" in o.path:
                found = list(
                    base.glob(
                        o.path.replace("{src}", "*")
                        .replace("{stem}", "*")
                        .replace("{sub}", "*")
                        .replace("{fps}", "*")
                    )
                )
                assert found or not o.required, (stage, o.path)
            else:
                assert (base / o.path).exists() or not o.required, (stage, o.path)
    # optional outputs we promise anyway
    for rel in (
        "lipsync/visemes.json",
        "lipsync/phonemes.json",
        "artwork/cover.jpg",
        "meaning/intent.md",
        "meaning/authored.json",
        "_intermediate/allin1/embeddings.f32",
        *[f"stems/drums/{s}.flac" for s in ("kick", "snare", "toms", "hihat", "ride", "crash")],
    ):
        assert (synth / rel).exists(), rel


def test_events_envelopes(synth):
    for p in sorted(list((synth / "events").glob("*.json")) + list((synth / "lipsync").glob("*.json"))):
        e = read_events(p)
        ts = [it["t"] for it in e.items]
        assert ts == sorted(ts), f"{p.name} not sorted by t"
        if e.kind == "segment":
            assert all(it["d"] > 0 for it in e.items), p.name
        for it in e.items:
            for k in ("t", "d"):
                if isinstance(it.get(k), float):
                    assert round(it[k], 6) == it[k], (p.name, k)
        assert set(e.fields) >= {k for it in e.items for k in it}, f"{p.name}: undocumented fields"
        raw = p.read_bytes()
        assert b"\r\n" not in raw and b"NaN" not in raw and b"Infinity" not in raw


def test_curves_shape_and_values(synth):
    index = curvefile.read_index(synth)
    src = load_json(synth / "meta/source.json")
    for fid, f in index["files"].items():
        n = n_curve_frames(src["n_samples"], src["sample_rate"], int(f["rate_hz"]))
        assert f["n_frames"] == n, fid
        size = (synth / f["path"]).stat().st_size
        assert size == (n * f["n_channels"] * (1 if f["dtype"] == "u8" else 4)), fid
    for e in index["channels"]:
        if e["id"] == "spectrum128":
            continue
        v, _ = curvefile.read_channel(synth, index, e["id"])
        c = registry.channel(e["id"])
        assert not np.isinf(v).any(), e["id"]
        if not c.nan_aware:
            assert not np.isnan(v).any(), e["id"]
        lo, hi = c.range
        fin = v[np.isfinite(v)]
        assert fin.min() >= lo - 1e-6 and fin.max() <= hi + 1e-6, (
            e["id"],
            float(fin.min()),
            float(fin.max()),
        )
    midi, _ = curvefile.read_channel(synth, index, "vocal.midi")
    voiced, _ = curvefile.read_channel(synth, index, "vocal.voiced")
    assert np.array_equal(voiced == 1.0, np.isfinite(midi))
    assert errs_index(index) == []


def errs_index(index):
    return schemas.validate(index, "mvh/envelope/curves_index")


def test_manifest_lists_every_public_file(synth):
    man = load_json(synth / "manifest.json")
    listed = {f["path"] for f in man["files"]}
    on_disk = {p.relative_to(synth).as_posix() for p in synth.rglob("*") if p.is_file()}
    public = {r for r in on_disk if not r.startswith(("_", ".", "schema/")) and r != ".done.json"}
    assert listed == public
    for f in man["files"]:
        assert (synth / f["path"]).exists()
    assert json.dumps(man).count('"items"') == 0  # index only, no data arrays
