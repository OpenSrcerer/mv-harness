"""W3C-6 (M2 structure, R19): moving one section boundary in the viewer moves other boundaries that the user did not touch.

The R19 round trip works mechanically. I ran it on a copy of the synthetic folder (out/_wip/critic-w3/rt-synth,
rt_step.ps1, current code): after `overrides.json` structure.boundaries [{move 17.0 -> 21.0}] + labels [{4.0: intro}]:
- only structure and its dependants re-ran;
- the label and the moved boundary appeared;
- lyrics and singing got the new section_ids;
- meaning re-anchored 3 claims (`status: user`, no orphans).

But the untouched build boundary at 25.0 s (the generator truth, and the start of edm_roles R01 'build') moved to
29.0 s, and the build shrank from 7.5 s to 3.5 s. structure turns a move into forced/forbidden bars and re-runs the
global DP, so the whole segmentation may change. A user who corrects one boundary has to re-check every other one, and
correct boundaries can be lost.

With the fixture's exact upstream the DP happens to keep the other boundaries (the control test below passes). The
effect shows with the upstream the real pipeline produces. This test uses the recorded real allin1, harmony and
dynamics of the synthetic song, the same data as tests/review/M2/r-dsp/test_structure_real_upstream.py.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

DATA = Path(__file__).resolve().parents[2] / "M2" / "r-dsp" / "data"
DYN_NOVELTY_OFFSET = 1288200      # byte offset of dyn.novelty in curves/core.f32 (see the M2 r-dsp test)


def _bounds(path):
    from tests.synth.m2.testing import events

    return [round(s["t"], 3) for s in events(path, "sections")]


def _real_upstream_fixture(root: Path) -> Path:
    from tests.synth.m2.testing import synth_ready

    if not (DATA / "synth_real_allin1.npz").is_file() or not (DATA / "synth_real_harmony_dynamics.npz").is_file():
        pytest.skip("recorded real upstream for the synthetic song is missing")
    fx = synth_ready()
    fx2 = root / "fx"
    shutil.copytree(fx, fx2, ignore=shutil.ignore_patterns("stems", "frames", "viewer.html", "lyrics", "lipsync"))
    z = np.load(DATA / "synth_real_allin1.npz")
    a1 = fx2 / "_intermediate" / "allin1"
    with open(a1 / "allin1.json", "w", encoding="utf-8") as fh:
        json.dump(json.loads(bytes(z["doc"]).decode("utf-8")), fh)
    z["activations"].astype("<f4").tofile(a1 / "activations.f32")
    z["embeddings"].astype("<f4").tofile(a1 / "embeddings.f32")
    r = np.load(DATA / "synth_real_harmony_dynamics.npz")
    (fx2 / "curves" / "chroma12.f32").unlink()
    r["chroma12"].astype("<f4").tofile(fx2 / "curves" / "chroma12.f32")
    core = np.fromfile(fx2 / "curves" / "core.f32", dtype="<f4")
    k = DYN_NOVELTY_OFFSET // 4
    core[k:k + len(r["dyn_novelty"])] = r["dyn_novelty"]
    (fx2 / "curves" / "core.f32").unlink()
    core.astype("<f4").tofile(fx2 / "curves" / "core.f32")
    for name, text in json.loads(bytes(r["events"]).decode("utf-8")).items():
        (fx2 / "events" / f"{name}.json").unlink()
        with open(fx2 / "events" / f"{name}.json", "w", encoding="utf-8") as fh:
            fh.write(text)
    return fx2


def _check_moves(fx: Path, root: Path, bar: float = 2.0):
    from tests.synth.m2.ctx import run_stage

    res0, _, _ = run_stage("structure", fx, root / "base")
    assert res0.status in ("ok", "degraded")
    before = _bounds(root / "base")
    problems = []
    n = 0
    for i, b in enumerate(before[1:], start=1):
        nxt = before[i + 1] if i + 1 < len(before) else 1e9
        if nxt - b < 4 * bar:
            continue
        dst = round(b + 2 * bar, 3)              # the user drags the boundary two bars later
        n += 1
        out = root / f"edit{i}"
        run_stage("structure", fx, out, overrides={"structure.boundaries": [{"t": b, "action": "move", "to_t": dst}]})
        after = _bounds(out)
        kept = [x for x in before if abs(x - b) > bar and abs(x - dst) > bar]
        lost = [x for x in kept if not any(abs(x - a) < 0.3 for a in after)]
        added = [a for a in after if abs(a - dst) > 0.3 and not any(abs(a - x) < 0.3 for x in before)]
        if lost or added or not any(abs(a - dst) < 0.3 for a in after):
            problems.append(f"move {b}->{dst}: lost {lost}, new {added}")
    assert n >= 2, f"too few movable boundaries in {before}"
    return before, problems


def test_w3c_moving_one_boundary_keeps_the_others_real_upstream(tmp_path):
    fx = _real_upstream_fixture(tmp_path)
    before, problems = _check_moves(fx, tmp_path)
    assert not problems, f"sections {before}: " + "; ".join(problems)


def test_w3c_moving_one_boundary_keeps_the_others_fixture_upstream(tmp_path):
    from tests.synth.m2.testing import synth_ready

    before, problems = _check_moves(synth_ready(), tmp_path)
    assert not problems, f"sections {before}: " + "; ".join(problems)
