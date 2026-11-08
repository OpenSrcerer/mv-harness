# ruff: noqa: E501  (long literals and docstrings)
"""The harmony and mood stage declarations honour the frozen catalogue (deps, env, outputs) and name real model ids."""
import json
from pathlib import Path

from mvh.runner.spec import catalog_outputs, check_dag, load_stage_specs

ROOT = Path(__file__).resolve().parents[3]


def _lock_ids():
    return {m["id"] for m in json.loads((ROOT / "models.lock.json").read_text(encoding="utf-8"))["models"]}


def test_harmony_declaration():
    specs = load_stage_specs()
    check_dag(specs)
    s = specs["harmony"]
    assert s.deps == ("ingest", "rhythm") and s.env == "main" and s.module == "M4" and not s.version.endswith("stub")
    assert tuple(o.path for o in s.outputs) == tuple(o.path for o in catalog_outputs("harmony"))
    assert set(s.models) <= _lock_ids() and {"skey_onnx", "lv_chordia_ismir2019_chordnet"} <= set(s.models)
    assert {"meta/key.json", "events/key.json", "events/chords.json", "curves/chroma12.f32"} <= {o.path for o in s.outputs}
    assert s.params["key_window_s"] == 30.0


def test_mood_declaration():
    specs = load_stage_specs()
    s = specs["mood"]
    assert s.deps == ("ingest", "structure") and s.env == "main" and s.module == "M4" and not s.version.endswith("stub")
    assert tuple(o.path for o in s.outputs) == tuple(o.path for o in catalog_outputs("mood"))
    assert set(s.models) <= _lock_ids() and {"essentia_msd_musicnn", "essentia_discogs_effnet"} <= set(s.models)
    assert {"meta/mood.json", "events/mood.json", "curves/mood_1hz.f32"} <= {o.path for o in s.outputs}
