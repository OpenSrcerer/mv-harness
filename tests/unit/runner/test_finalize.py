"""finalize: the manifest stays under its token cap deterministically."""

from __future__ import annotations

import json

from mvh.runner.finalize import dumps_manifest, fit_manifest


def _man(n_stage_items: int) -> dict:
    return {
        "schema": "mvh/manifest",
        "summary": {"stages": {f"s{i:02d}": {"k": "x" * (40 + i)} for i in range(n_stage_items)}},
        "status": {"flags": []},
        "warnings": [f"w{i} " + "y" * 50 for i in range(40)],
        "files": [{"path": f"events/e{i}.json", "kind": "events", "stage": "x"} for i in range(10)],
    }


def test_fit_manifest_trims_largest_summaries_first():
    m = fit_manifest(_man(200), budget=6000)
    txt = dumps_manifest(m)
    assert len(txt) <= 6000
    kept = m["summary"]["stages"]
    assert "manifest:stage_summaries_trimmed" in m["status"]["flags"]
    assert "s199" not in kept and (not kept or max(len(v["k"]) for v in kept.values()) < 240)
    json.loads(txt)
    assert fit_manifest(_man(200), budget=6000) == m                 # deterministic


def test_fit_manifest_leaves_small_manifests_alone():
    m = _man(3)
    m["warnings"] = ["one"]
    before = json.dumps(m, sort_keys=True)
    assert json.dumps(fit_manifest(m), sort_keys=True) == before
