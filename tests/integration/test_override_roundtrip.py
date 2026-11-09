"""R19 override round trip (W3 acceptance test, PLAN §12 W3), on REAL stages.

A copy of a finished `mvh analyze --profile max` folder (the integrator's runs in out/_wip/integrator/<slug>) is edited
the way the viewer edits it, through the edit server (`mvh view` -> ViewServer: POST /api/overrides and POST /api/intent
with the page token), then `mvh analyze <folder>` re-runs it. The test checks:

- ONLY the affected stages re-ran (run.json `cache`: every stage that is not downstream of an edited key or of
  meaning/intent.md is a cache hit; every edited stage re-ran);
- every edit shows up in the outputs:
  - a section boundary move (and no other boundary moves: W3C-6),
  - a downbeat edit (`rhythm.downbeat_phase`, synthetic song: second step),
  - a singer / voice mapping (viewer block: V1 -> C1 named by the user),
  - a pinned cue,
  - a per-section meaning edit, re-anchored by time overlap to the edited sections.

Slow (one structure-down re-run per song; the downbeat step re-runs everything below rhythm on the synthetic song).
Run: uv run --frozen --no-sync python -m pytest -q -m real tests/integration/test_override_roundtrip.py
Needs the integrator folders (skips when absent). Lyric text is never printed.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
RUNS = REPO / "out" / "_wip" / "integrator"
WORK = REPO / "out" / "_wip" / "integrator-r2" / "roundtrip"

pytestmark = [pytest.mark.real, pytest.mark.slow]


# ------------------------------------------------------------------------------------------------ helpers
def _json(p: Path) -> Any:
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _items(folder: Path, name: str) -> list[dict[str, Any]]:
    d = _json(folder / "events" / f"{name}.json")
    return d["items"] if isinstance(d, dict) else d


def _stage_specs() -> dict[str, Any]:
    from mvh.runner.spec import load_stage_specs

    return load_stage_specs()


def _downstream(seeds: set[str]) -> set[str]:
    specs = _stage_specs()
    out = set(seeds)
    changed = True
    while changed:
        changed = False
        for name, s in specs.items():
            if name not in out and set(s.deps) & out:
                out.add(name)
                changed = True
    return out


def _copy(slug: str, tag: str) -> Path:
    src = RUNS / slug
    if not (src / "run.json").is_file() or not (src / "viewer.html").is_file():
        pytest.skip(f"no finished integrator run in {src}")
    dst = WORK / f"{slug}-{tag}"
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)
    for f in ("overrides.json",):
        if (dst / f).exists():
            (dst / f).unlink()
    return dst


def _analyze(folder: Path, timeout: float = 5400.0) -> dict[str, Any]:
    env = dict(os.environ)
    env.pop("MVH_FIXTURE_DIR", None)
    env.pop("MVH_STAGE_STUBS", None)
    log = folder.parent / f"{folder.name}.analyze.log"
    with open(log, "w", encoding="utf-8") as fh:
        r = subprocess.run([sys.executable, "-m", "mvh.cli", "analyze", str(folder)], cwd=str(REPO), env=env,
                           stdout=subprocess.PIPE, stderr=fh, timeout=timeout, check=False)
    assert r.returncode == 0, f"mvh analyze failed ({r.returncode}); see {log}"
    return _json(folder / "run.json")


def _reran(run: dict[str, Any]) -> set[str]:
    return {n for n, s in run["stages"].items() if s.get("status") in ("done", "degraded") and s.get("cache") != "hit"}


def _ran(run: dict[str, Any]) -> set[str]:
    return {n for n, s in run["stages"].items() if s.get("status") in ("done", "degraded", "skipped")}


class _Viewer:
    """The edit server the viewer page talks to (`mvh view`), driven with the page's own requests."""

    def __init__(self, folder: Path):
        from mvh.stages.viewer.server import make_server

        self.srv = make_server(folder, port=0, idle_timeout=0, allow_rerun=False).start()

    def _req(self, method: str, path: str, body: Any = None) -> dict[str, Any]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.srv.url.rstrip("/") + path, data=data, method=method)
        req.add_header("X-MVH-Token", self.srv.token)
        req.add_header("Origin", self.srv.url.rstrip("/"))
        if data is not None:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=60) as r:   # noqa: S310 - 127.0.0.1 edit server
            return json.loads(r.read().decode("utf-8"))

    def overrides(self, doc: dict[str, Any]) -> dict[str, Any]:
        cur = self._req("GET", "/api/overrides")
        res = self._req("POST", "/api/overrides", {"overrides": doc, "etag": cur.get("etag")})
        assert res.get("ok"), res
        return res

    def intent(self, patch: dict[str, Any]) -> dict[str, Any]:
        res = self._req("POST", "/api/intent", patch)
        assert res.get("ok"), res
        return res

    def close(self) -> None:
        self.srv.shutdown()


def _bar_after(folder: Path, t: float) -> float:
    bars = [b for b in _items(folder, "bars") if b["bar"] >= 1]
    return min((b["t"] for b in bars if b["t"] > t + 0.05), default=t)


def _pick_move(folder: Path) -> tuple[float, float]:
    """A boundary that can move one bar later without touching its neighbours (>= 3 bars on each side)."""
    secs = _items(folder, "sections")
    bars = [b["t"] for b in _items(folder, "bars") if b["bar"] >= 1]
    for i in range(1, len(secs) - 1):
        a, t, b = secs[i - 1]["t"], secs[i]["t"], secs[i + 1]["t"]
        if sum(1 for x in bars if a <= x < t) >= 3 and sum(1 for x in bars if t <= x < b) >= 4:
            return t, _bar_after(folder, t)
    pytest.skip("no movable boundary")


def _edit_and_rerun(slug: str, tag: str) -> dict[str, Any]:
    folder = _copy(slug, tag)
    base_secs = _items(folder, "sections")
    base_starts = [round(s["t"], 3) for s in base_secs]
    t_old, t_new = _pick_move(folder)
    # a pinned cue on a beat in the middle of the song, away from every existing cue kind 'pinned'
    beats = [b["t"] for b in _items(folder, "beats")]
    t_pin = beats[len(beats) // 2 + 3]
    voices = _json(folder / "meta" / "voices.json").get("voices") or []
    v1 = voices[0]["id"] if voices else None
    # the section that will contain the moved boundary's new start
    target = next(s for s in base_secs if s["t"] <= t_new < s["t"] + s["d"] or abs(s["t"] - t_old) < 1e-3)
    vw = _Viewer(folder)
    try:
        res_o = vw.overrides({"structure": {"boundaries": [{"action": "move", "t": t_old, "to_t": t_new}]},
                              "cues": {"pinned": [{"t": t_pin, "note": "roundtrip pin"}]}})
        patch: dict[str, Any] = {"sections": {target["id"]: {"t0": target["t"], "t1": target["t"] + target["d"],
                                                             "label": target["label"], "meaning": "roundtrip meaning edit",
                                                             "feel": "roundtrip feel"}}}
        if v1:
            patch["voices"] = {v1: {"character_id": "C1", "name": "Roundtrip Keeper"}}
        res_i = vw.intent(patch)
    finally:
        vw.close()
    # the server's own answer names the stages to re-run (structure / cues closure and the intent readers)
    assert {"structure", "cues"} <= {a["stage"] for a in res_o["affected"]}
    assert {"voices", "meaning"} <= {a["stage"] for a in res_i["affected"]}
    run = _analyze(folder)
    return {"folder": folder, "run": run, "base_starts": base_starts, "t_old": t_old, "t_new": t_new, "t_pin": t_pin,
            "v1": v1, "target": target}


def _check_edits(r: dict[str, Any]) -> None:
    folder, run = r["folder"], r["run"]
    # ---- only the affected stages re-ran
    seeds = {"structure", "cues", "meaning"} | ({"voices"} if r["v1"] else set())
    down = _downstream(seeds)
    reran = _reran(run)
    assert {"structure", "cues", "meaning"} <= reran, sorted(reran)
    untouched = _ran(run) - down
    assert not (reran & untouched), f"stages re-ran that no edit affects: {sorted(reran & untouched)}"
    assert reran <= down, sorted(reran - down)
    # ---- boundary move, locally
    secs = _items(folder, "sections")
    starts = [round(s["t"], 3) for s in secs]
    assert any(abs(t - r["t_new"]) < 0.02 for t in starts), (r["t_new"], starts)
    assert not any(abs(t - r["t_old"]) < 0.02 for t in starts), (r["t_old"], starts)
    expect = sorted([t for t in r["base_starts"] if abs(t - r["t_old"]) >= 0.02] + [round(r["t_new"], 3)])
    assert [round(t, 2) for t in starts] == [round(t, 2) for t in expect], "a boundary the user did not touch moved"
    prov = _json(folder / "events" / "sections.json").get("provenance") or {}
    assert any(o["key"] == "structure.boundaries" for o in prov.get("overrides_applied") or [])
    # ---- pinned cue
    cues = _items(folder, "cues")
    assert any(abs(c["t"] - r["t_pin"]) < 0.06 and ("pinned" in (c.get("kinds") or []) or c.get("kind") == "pinned")
               for c in cues), "pinned cue missing"
    # ---- voice mapping
    meaning = _json(folder / "meaning" / "meaning.json")
    if r["v1"]:
        c1 = next((c for c in meaning["characters"] if c["id"] == "C1"), None)
        assert c1 is not None and c1["name"] == "Roundtrip Keeper" and r["v1"] in c1["voice_ids"], c1
        sing = [s for s in _items(folder, "singing") if s.get("voice_id") == r["v1"]]
        assert sing and all(s.get("character_id") == "C1" for s in sing)
    # ---- meaning edit, re-anchored to the edited sections by overlap
    t0, t1 = r["target"]["t"], r["target"]["t"] + r["target"]["d"]
    hit = [s for s in meaning["sections"] if s.get("meaning") == "roundtrip meaning edit"]
    assert hit, "the section meaning edit was lost"
    for s in hit:
        assert min(s["t1"], t1) - max(s["t0"], t0) > 0, (s["t0"], s["t1"], t0, t1)
        assert (s.get("field_sources") or {}).get("meaning") == "user", s.get("field_sources")
    # the brief and the viewer were rebuilt with the edits
    assert run["stages"]["brief"].get("cache") != "hit" and run["stages"]["viewer"].get("cache") != "hit"


# ------------------------------------------------------------------------------------------------ tests
def test_roundtrip_synthetic_song_sections_voices_cues_meaning_then_downbeat():
    r = _edit_and_rerun("synth", "rt")
    _check_edits(r)
    folder = r["folder"]
    # ---- step 2: a downbeat edit (one beat later), written as the viewer's grid panel writes it
    bars0 = [b["t"] for b in _items(folder, "bars") if b["bar"] >= 1]
    beats = _items(folder, "beats")
    ov = _json(folder / "overrides.json")
    ov.setdefault("rhythm", {})["downbeat_phase"] = 1
    vw = _Viewer(folder)
    try:
        res = vw.overrides(ov)
    finally:
        vw.close()
    assert "rhythm" in {a["stage"] for a in res["affected"]}
    run = _analyze(folder)
    reran = _reran(run)
    assert "rhythm" in reran
    upstream = {"ingest", "identity", "loudness", "spectral", "separate_fast", "separate_hq", "allin1", "stem_activity",
                "drums", "instruments"}
    assert not (reran & upstream), f"stages above rhythm re-ran: {sorted(reran & upstream)}"
    assert reran <= _downstream({"rhythm"}) | {"meaning", "voices"}
    bars1 = [b["t"] for b in _items(folder, "bars") if b["bar"] >= 1]
    ibi = sorted(b2["t"] - b1["t"] for b1, b2 in zip(beats, beats[1:]))[len(beats) // 2]
    # every downbeat moved by one beat (the same grid, a different bar phase)
    shifted = sum(1 for t in bars1 if any(abs(abs(t - b) - ibi) < 0.03 for b in bars0))
    assert shifted >= 0.8 * len(bars1), (len(bars1), shifted)
    prov = _json(folder / "events" / "beats.json").get("provenance") or {}
    assert any(o["key"] == "rhythm.downbeat_phase" for o in prov.get("overrides_applied") or [])
    # the user's earlier edits survive the re-run below rhythm (time-anchored)
    assert any(abs(s["t"] - r["t_new"]) < 0.6 for s in _items(folder, "sections"))
    assert any("pinned" in (c.get("kinds") or []) or c.get("kind") == "pinned" for c in _items(folder, "cues"))


@pytest.mark.parametrize("slug", ["newton-vs-nye"])
def test_roundtrip_real_song_sections_voices_cues_meaning(slug):
    _check_edits(_edit_and_rerun(slug, "rt"))
