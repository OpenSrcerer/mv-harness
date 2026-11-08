# ruff: noqa: E501
"""R-CONTRACT (M6b) F1: the Remotion recipe in skill/mv-harness/references/RECIPES.md does not load what it uses.

A Remotion agent copies the recipe: ``load(staticFile('song/'), {include: [...]})``, then renders with
``song.count(t)`` and ``song.singerAt(t)`` (the recipe's own comment). In a browser (Remotion's renderer is Chromium,
no fs) every resource must be in ``include`` or ``ensure``d first, and the include list misses ``events:beats``
(count) and ``curves:vocal`` (singerAt's mouth_open), so both throw on the first frame.

The node script reads the include list straight out of RECIPES.md, loads the synthetic fixture through a fetch shim
(URL base, exactly the browser path of lib/mvh.js) and calls the two helpers.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SYNTH = ROOT / "tests" / "contract" / "synth"
RECIPES = ROOT / "skill" / "mv-harness" / "references" / "RECIPES.md"
LIB = ROOT / "src" / "mvh" / "assets" / "mvh.js"
SCRIPT = Path(__file__).with_name("remotion_recipe.mjs")


@pytest.fixture(scope="module")
def node() -> str:
    exe = shutil.which("node")
    if not exe:
        pytest.skip("node is not on PATH")
    if not (SYNTH / "manifest.json").is_file():
        pytest.skip("tests/contract/synth is not built")
    return exe


def test_remotion_recipe_include_covers_the_helpers_it_uses(node: str) -> None:
    p = subprocess.run([node, str(SCRIPT), str(RECIPES), str(SYNTH), str(LIB)], capture_output=True, text=True,
                       encoding="utf-8", timeout=120, check=False)
    out = (p.stdout.strip().splitlines() or ["{}"])[-1]
    res = json.loads(out)
    assert "include" in res, f"could not run the recipe: {p.stdout} {p.stderr}"
    assert not res["errors"], (
        "the Remotion recipe's load(..., {include}) list " + json.dumps(res["include"])
        + " does not cover the helpers the recipe tells the agent to call; in Remotion (browser) they throw: "
        + "; ".join(res["errors"]))
