"""The real-song adapter folders (tests/contract/real-<slug>/, built from the W0 cache) are valid for the stages they cover.

Skipped when the folders were not generated (they need tests/.cache/real/, which is gitignored). Never prints lyric text.
"""

import json
import os
from pathlib import Path

import pytest
from tests.synth import stubrun

from mvh.contract import catalog, schemas

REPO = Path(__file__).resolve().parents[3]
REAL = sorted((REPO / "tests" / "contract").glob("real-*/coverage.json"))

pytestmark = [
    pytest.mark.timeout(900),
    pytest.mark.skipif(
        not REAL, reason="real-* folders not generated (python -m tests.synth.build --only real)"
    ),
]


@pytest.mark.parametrize("cov_path", REAL, ids=[p.parent.name for p in REAL])
def test_real_folder_valid_and_stubs_copy(cov_path):
    with open(cov_path, encoding="utf-8") as fh:
        cov = json.load(fh)
    assert cov["errors"] == [] and cov["validation_errors"] == []
    root = cov_path.parent
    for p in sorted(root.rglob("*.json")):
        rel = p.relative_to(root).as_posix()
        if rel in ("coverage.json", ".done.json") or rel.startswith("_intermediate/"):
            continue
        with open(p, encoding="utf-8") as fh:
            doc = json.load(fh)
        sid = (
            doc.get("schema")
            if isinstance(doc, dict) and str(doc.get("schema", "")).startswith("mvh/events/")
            else None
        )
        if sid is None:
            sid = next(
                (
                    "mvh/" + f.schema
                    for f in catalog.FILES + catalog.RUNNER_FILES
                    if f.path == rel and f.schema
                ),
                None,
            )
        if sid:
            errs = schemas.validate(doc, sid)
            assert not errs, (rel, len(errs))  # no message content: may quote lyric text
    # every stage marked full copies through the stub without MissingFixture (dry: nothing is written)
    from mvh.contract.fixture import run_stub
    from mvh.runner.spec import load_stage_specs

    specs = load_stage_specs()
    old = os.environ.get("MVH_FIXTURE_DIR")
    os.environ["MVH_FIXTURE_DIR"] = str(root)
    try:
        for stage, status in cov["stages"].items():
            if status == "full" and stage in specs:
                res, w = stubrun.run_stage(specs[stage], run_stub, root, dry=True)
                assert res.status == "ok", stage
    finally:
        if old is None:
            os.environ.pop("MVH_FIXTURE_DIR", None)
        else:
            os.environ["MVH_FIXTURE_DIR"] = old
