"""Seam S06 (M1 with M3a), resolved by user decision UD2 (CONTRACT D79). Two kick timelines exist: spectral's mix kick
(events/hits.kick) and DrumSep's kick stem (events/drum_hits, drum = kick). They used to disagree badly on MEGAFAUNA
(42 % / 23 % within 30 ms): its kick stem was mostly hat / percussion bleed (43 % of the gaps on the 71 ms 32nd-hat
grid, median vel 0.14) and the mix's low band cannot see its sidechained drop kicks.

Under UD2 agents read ONE kick: manifest summary.kick_source picks it per song (meta/drums.json has the evidence), the
drum-stem kick is bleed-gated first, and a low agreement raises the QA flag instead of failing. These tests check that
contract on the real runs: MEGAFAUNA (the hard case) gets a clean agent-facing kick and the QA flag; Newton (the easy
one) agrees >= 0.9 both ways without a flag. Numbers only, no lyric text.

The folder is the integrator's run when it was made with the UD2 code (it has meta/drums.json), else ud2-kick's
verification run (out/_wip/ud2-kick/<slug>); the test skips when neither exists."""

from __future__ import annotations

import bisect
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
FOLDERS = (REPO / "out" / "_wip" / "integrator", REPO / "out" / "_wip" / "ud2-kick")


def _folder(slug: str) -> Path:
    for base in FOLDERS:
        f = base / slug
        if (f / "manifest.json").is_file() and (f / "meta" / "drums.json").is_file():
            return f
    pytest.skip(f"no UD2 run for {slug} (meta/drums.json) in {[str(b) for b in FOLDERS]}")


def _json(f: Path, rel: str):
    with open(f / rel, encoding="utf-8") as fh:
        return json.load(fh)


def _share(a, b, tol=0.03):
    b = sorted(b)

    def near(t):
        i = bisect.bisect_left(b, t)
        return any(abs(b[j] - t) <= tol for j in (i - 1, i) if 0 <= j < len(b))

    return sum(1 for t in a if near(t)) / len(a) if a else None


def _agent_kicks(f: Path, man):
    ks = man["summary"]["kick_source"]
    if ks == "drums":
        return ks, [h for h in _json(f, "events/drum_hits.json")["items"] if h["drum"] == "kick"]
    return ks, [{"t": h["t"], "vel": h.get("env", 1.0)} for h in _json(f, "events/hits.kick.json")["items"]]


def test_real_megafauna_agent_kick_is_clean_and_the_disagreement_is_flagged():
    f = _folder("megafauna")
    man = _json(f, "manifest.json")
    meta = _json(f, "meta/drums.json")
    ks, kicks = _agent_kicks(f, man)
    assert man["summary"]["kick_source"] == meta["kick_source"]
    ts = sorted(k["t"] for k in kicks)
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    fast = sum(1 for g in gaps if g < 0.1) / len(gaps)
    vels = sorted(k["vel"] for k in kicks)
    # the raw kick stem had 43 % of its gaps on the 32nd-hat grid and a median vel of 0.14
    assert fast <= 0.25 and vels[len(vels) // 2] >= 0.3, (ks, len(ts), round(fast, 3), vels[len(vels) // 2])
    assert meta["drums"]["raw_fast_gap_share"] >= 0.3, "the gate's evidence: the raw stem was hat-grid bleed"
    a = man["summary"]["kick_agreement"]
    hk = sorted(h["t"] for h in _json(f, "events/hits.kick.json")["items"])
    dk = sorted(h["t"] for h in _json(f, "events/drum_hits.json")["items"] if h["drum"] == "kick")
    assert a["mix_in_drums"] == pytest.approx(_share(hk, dk), abs=0.002)
    assert a["drums_in_mix"] == pytest.approx(_share(dk, hk), abs=0.002)
    assert min(a["mix_in_drums"], a["drums_in_mix"]) < 0.75 and "qa:kick_sources_disagree" in man["status"]["flags"]


@pytest.mark.parametrize("slug,floor", [("newton-vs-nye", 0.9), ("versatile", 0.9), ("jeremy", 0.85), ("synth", 0.9)])
def test_real_clean_songs_use_the_drum_stem_and_agree(slug, floor):
    f = _folder(slug)
    man = _json(f, "manifest.json")
    assert man["summary"]["kick_source"] == "drums", _json(f, "meta/drums.json")["reason"]
    a = man["summary"]["kick_agreement"]
    assert a["mix_in_drums"] >= floor and a["drums_in_mix"] >= floor, a
    assert "qa:kick_sources_disagree" not in man["status"]["flags"]
