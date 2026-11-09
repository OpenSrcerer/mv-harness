"""R-PLATFORM round 5 (W3 verify) for M6a: the viewer after the edit -> re-run loop for section boundaries (seam R19).

The structure stage reports the overrides it applied ONE ENTRY PER EDIT in its provenance
(``{"key": "structure.boundaries", "value": {"action": "move", "t": .., "to_t": ..}}``, structure/__init__.py), and the
runner copies that list into ``events/sections.json`` (runner/child.py -> ``provenance_block(job, res.provenance)``).
The viewer's ``appliedOverrides()`` (data.js) keeps one value per key (the last edit, an object), and
``Edit.pendingBoundaries()`` (edit.js) calls ``.map`` on it. After the user moves, adds or removes a section boundary in
the viewer and re-runs, the served viewer shows only "The viewer could not load this song" and file:// paints a lane error
in Sections. Real evidence: out/_wip/critic-w3/rt-synth (the W3 critic's real round trip), copied to
out/_wip/r-platform-m6a-r5/rt-synth.

Synthetic and fast apart from the browser: the real structure stage on the synthetic fixture with one boundary override,
its provenance stamped exactly as the runner stamps it, then the real viewer in headless Edge.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from rp_support import ROOT, build_song_folder, build_viewer_html, drive

pytestmark = pytest.mark.usefixtures("browser_ok")

EDIT = {"action": "move", "t": 16.998, "to_t": 21.0}


def _folder_after_boundary_rerun(dest: Path, stamp: list | None = None) -> Path:
    import sys

    sys.path.insert(0, str(ROOT))
    from tests.synth.m2.ctx import run_stage
    from tests.synth.m2.testing import synth_ready

    from mvh.runner.ctx import provenance_block

    ov = {"structure.boundaries": [EDIT]}
    out = dest.parent / "structure-run"
    res, _ctx, _ = run_stage("structure", synth_ready(), out, overrides=ov)
    assert res.status == "ok"
    sec = json.loads((out / "events" / "sections.json").read_text(encoding="utf-8"))
    pv = sec["provenance"]
    job = {"stage": pv["stage"], "stage_version": pv["stage_version"], "contract_version": pv["contract_version"],
           "key": pv["key"], "params": pv["params"], "overrides": ov}
    # what runner/child.py does after run(): restamp every envelope with provenance_block(job, res.provenance, ...)
    sec["provenance"]["overrides_applied"] = provenance_block(job, res.provenance)["overrides_applied"]
    if stamp is not None:
        sec["provenance"]["overrides_applied"] = stamp   # a producer that reports one entry per edit (repeated keys)

    folder = build_song_folder(dest)
    tmp = folder / "events" / "sections.json.tmp"
    tmp.write_text(json.dumps(sec, ensure_ascii=False), encoding="utf-8", newline="\n")
    os.replace(tmp, folder / "events" / "sections.json")  # never write through the hard link into the fixture
    (folder / "overrides.json").write_text(json.dumps({"schema": "mvh/overrides", "schema_version": "1.0.0-rc.2",
                                                       "structure": {"boundaries": [EDIT]}}), encoding="utf-8", newline="\n")
    (folder / "viewer.html").write_text(build_viewer_html(root=folder), encoding="utf-8", newline="\n")
    return folder


def test_served_viewer_loads_after_a_section_boundary_edit_was_applied(tmp_path, synth_ok):
    """The documented loop: move a boundary in the viewer, re-run (structure applies it), open `mvh view` again."""
    from mvh.stages.viewer.server import make_server

    folder = _folder_after_boundary_rerun(tmp_path / "after rerun")
    applied = json.loads((folder / "events" / "sections.json").read_text(encoding="utf-8"))["provenance"]["overrides_applied"]
    # the runner's real stamp: one entry per key holding the edit list (structure 1.2.0, D68); before: one per edit
    assert applied in ([{"key": "structure.boundaries", "value": [EDIT]}], [{"key": "structure.boundaries", "value": EDIT}]), applied
    srv = make_server(folder, port=0, idle_timeout=0, allow_rerun=False).start()
    try:
        res = drive(srv.url, "errors", tmp_path / "prof")
    finally:
        srv.shutdown()
    assert res["state"] == "ready", f"edit mode shows the fatal page after the re-run: {(res.get('fatal') or '')[:200]}"
    assert res["laneErrors"] == [], f"lane errors: {res['laneErrors'][:2]}"


def test_file_mode_sections_lane_draws_after_a_section_boundary_edit_was_applied(tmp_path, synth_ok):
    folder = _folder_after_boundary_rerun(tmp_path / "after rerun file")
    res = drive((folder / "viewer.html").as_uri(), "errors", tmp_path / "prof")
    assert res["state"] == "ready", res.get("fatal")
    assert res["laneErrors"] == [], f"lane errors: {res['laneErrors'][:2]}"


def test_file_mode_sections_lane_draws_with_one_provenance_entry_per_edit(tmp_path, synth_ok):
    """integrator-r2: the contract type arr(obj({key, value})) allows repeated keys, so the viewer must tolerate a
    producer that reports one entry per edit (the pre-1.2.0 structure stamp), whatever structure does now."""
    stamp = [{"key": "structure.boundaries", "value": EDIT},
             {"key": "structure.boundaries", "value": {"action": "add", "t": 42.5}}]
    folder = _folder_after_boundary_rerun(tmp_path / "after rerun per edit", stamp=stamp)
    res = drive((folder / "viewer.html").as_uri(), "errors", tmp_path / "prof")
    assert res["state"] == "ready", res.get("fatal")
    assert res["laneErrors"] == [], f"lane errors: {res['laneErrors'][:2]}"
