"""W4A-KICKCURVE (M1/M3a drums, UD2 / D79): under the mix fallback the drums.kick curve is still the drum-stem kick.

UD2.1: ONE agent-facing kick (the viewer lane, lib, brief, frames). UD2.2: when the drum stem is not usable (or
``drums.kick_source = mix``) agents get ``hits.kick``. The drums stage then switches meta/drums.json to ``mix`` and
song.kicks() returns hits.kick, but ``drums.kick`` (written by ``core.envelopes(hits)`` from the drum-stem hits in
every case) still flashes on the drum-stem kicks. RECIPES.md's frame-accurate recipe
(``song.curve('drums.kick').frame(...)``, "never misses a hit"), the frames curve columns and choreo's accents read
that curve, so the agent is back to two disagreeing kick timelines.

Measured by running the real drums stage (mvh.runner.child.run_stage) on MEGAFAUNA's cached upstreams with
``kick_source = mix`` (out/_wip/r-adversary/drums_mix_devrun.py): 177 agent kicks, 316 drums.kick curve peaks;
47 % of the agent kicks have a curve peak within 30 ms, 28 % of the curve peaks an agent kick.

This test runs the drums stage (about 15 s, no models) and skips when no finished MEGAFAUNA folder with a stage
cache exists.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from w4a_support import newest_run


def _latest(cache: Path, stage: str) -> dict:
    with open(cache / stage / "latest.json", encoding="utf-8") as fh:
        k = json.load(fh)["key"]
    return {"dir": str(cache / stage / k), "key": k}


@pytest.mark.slow
def test_w4a_kick_curve_follows_the_agent_kick_under_mix_fallback(tmp_path):
    from mvh.contract import catalog
    from mvh.runner.child import run_stage
    from mvh.runner.spec import load_stage_specs

    song = newest_run("megafauna")
    if song is None:
        pytest.skip("no MEGAFAUNA max folder")
    cache = song / ".cache"
    spec = load_stage_specs()["drums"]
    need = list(spec.deps) + ["ingest"]
    if not all((cache / d / "latest.json").is_file() for d in need):
        pytest.skip("MEGAFAUNA folder has no stage cache for the drums upstreams")
    ups = {d: _latest(cache, d) for d in spec.deps}
    if not all(Path(u["dir"]).is_dir() for u in ups.values()):
        pytest.skip("stale cache pointers")
    with open(song / "meta/source.json", encoding="utf-8") as fh:
        src = json.load(fh)
    out = tmp_path / "drums"
    job = {
        "stage": "drums", "stage_version": spec.version, "contract_version": catalog.CONTRACT_VERSION,
        "key": "0" * 64, "pre_key": "0" * 64, "params": dict(spec.resolved_params("max", {"kick_source": "mix"})),
        "device": "cpu", "upstream": ups, "overrides": {},
        "timebase": {"n_samples": int(src["n_samples"]), "sample_rate": int(src["sample_rate"]),
                     "channels": int(src.get("channels", 2))},
        "song_dir": str(tmp_path / "song"), "http_dir": str(tmp_path / "http"), "slug": "megafauna",
        "profile": "max", "threads": 3, "scratch": str(tmp_path / "scratch"), "offline": True, "out_dir": str(out),
        "ingest_dir": _latest(cache, "ingest")["dir"],
    }
    run_stage(job)
    with open(out / "meta/drums.json", encoding="utf-8") as fh:
        assert json.load(fh)["kick_source"] == "mix"
    x = np.fromfile(out / "_mvh/curves/core/drums.kick.f32", dtype="<f4").astype(float)
    peaks = np.array([i / 100.0 for i in range(1, len(x) - 1) if x[i] > 0.1 and x[i] >= x[i - 1] and x[i] > x[i + 1]])
    with open(song / "events/hits.kick.json", encoding="utf-8") as fh:
        agent = np.array([h["t"] for h in json.load(fh)["items"]])
    assert len(agent) >= 50 and len(peaks) >= 50

    def share(a, b):
        return float(np.mean([np.min(np.abs(b - t)) <= 0.03 for t in a]))

    a_in_c, c_in_a = share(agent, peaks), share(peaks, agent)
    assert min(a_in_c, c_in_a) >= 0.8, (
        f"kick_source=mix: {len(agent)} agent kicks (hits.kick) vs {len(peaks)} drums.kick curve peaks; "
        f"{a_in_c:.2f} of the agent kicks have a curve peak within 30 ms, {c_in_a:.2f} of the peaks an agent kick")
