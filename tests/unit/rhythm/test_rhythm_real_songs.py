"""Real-song snapshot tests for the M2 chain rhythm -> structure -> choreo -> cues (opt-in: -m real or MVH_REAL_TESTS=1).

Upstream stages come from tests/contract/real-<slug> (the W0 data: ingest, separation, spectral, allin1, harmony ...;
no dynamics / drums / stem_activity, so structure / choreo / cues run their documented fallbacks). rhythm runs the real
trackers (beat_this, madmom-infer) inside a heavy slot. Snapshots are the builder-m2 runs of 2026-11-08 with tolerances,
never exact values; nothing here reads or prints lyric text.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from tests.synth.m2.testing import REPO, doc, events, validate_all

SNAP = {
    # bpm +- tol; downbeat phase flags expected from the SPIKE (madmom one beat off on 2 of 4 songs); EDM drops (s)
    "megafauna": {"bpm": 105.13, "tol": 1.5, "alt_near": [140.0], "phase_off": set(), "drops": [141.8], "labeling": "structural"},
    "versatile": {"bpm": 130.25, "tol": 0.5, "alt_near": [], "phase_off": {"madmom:-1"}, "drops": [84.9, 162.5], "labeling": "allin1"},
    "jeremy": {"bpm": 107.15, "tol": 0.5, "alt_near": [], "phase_off": set(), "drops": [], "labeling": "allin1"},
    "newton-vs-nye": {"bpm": 137.98, "tol": 1.0, "alt_near": [], "phase_off": {"madmom:-1"}, "drops": [], "labeling": "allin1"},
}


@pytest.mark.real
@pytest.mark.timeout(5400)
@pytest.mark.parametrize("slug", list(SNAP))
def test_real_song_chain_snapshot(tmp_path, slug):
    from tests.synth.m2.ctx import run_stage

    from mvh.testing import heavy

    fx = REPO / "tests" / "contract" / f"real-{slug}"
    if not (fx / "_intermediate" / "ingest").is_dir():
        pytest.skip(f"real fixture {fx.name} not present")
    overlays: dict = {}
    with heavy("pytest-m2-real", threads=6):
        res, _, _ = run_stage("rhythm", fx, tmp_path / "rhythm", slug=slug, threads=6)
    assert res.status in ("ok", "degraded"), res
    overlays["rhythm"] = tmp_path / "rhythm"
    for st in ("structure", "choreo", "cues"):
        r, _, _ = run_stage(st, fx, tmp_path / st, overlays=dict(overlays), slug=slug, threads=6)
        assert r.status in ("ok", "degraded"), (st, r)
        overlays[st] = tmp_path / st
    check_chain(tmp_path, slug)


def check_chain(root: Path, slug: str) -> None:
    """Snapshot assertions on a chain output folder <root>/{rhythm,structure,choreo,cues} (also usable on a kept run)."""
    tmp_path = Path(root)
    snap = SNAP[slug]
    for st in ("rhythm", "structure", "choreo", "cues"):
        assert validate_all(tmp_path / st) == [], st

    # ---- rhythm: tempo octave, meter, downbeat vote, alternatives kept for the override
    tempo = doc(tmp_path / "rhythm", "meta/tempo.json")
    assert abs(tempo["bpm"] - snap["bpm"]) <= snap["tol"], tempo["bpm"]
    assert tempo["meter"]["beats_per_bar"] == 4
    alts = [c["bpm"] for c in tempo["arbitration"]["rows"]]
    for a in snap["alt_near"]:
        assert any(abs(b - a) <= 6.0 for b in alts), (a, alts)
    qa_flags = tempo["qa"]["flags"]
    flags = {f.split(":", 1)[1] for f in qa_flags if f.startswith("downbeat_phase_off:")}
    assert snap["phase_off"] <= flags, flags
    assert ("tempo_trackers_disagree" in qa_flags) == (slug == "megafauna")
    assert len(tempo["downbeat_vote"]["voters"]) == 3
    beats = events(tmp_path / "rhythm", "beats")
    assert [b["beat_index"] for b in beats] == list(range(len(beats)))
    ibi = [b2["t"] - b1["t"] for b1, b2 in zip(beats, beats[1:]) if b1["in_pulse"] and b2["in_pulse"]]
    med = sorted(ibi)[len(ibi) // 2]
    assert abs(60.0 / med - tempo["bpm"]) <= 2.0
    # ---- structure: plausible section count, labels, EDM drops where the music drops
    sec = events(tmp_path / "structure", "sections")
    assert 8 <= len(sec) <= 26, len(sec)
    assert doc(tmp_path / "structure", "meta/structure.json")["labeling"] == snap["labeling"]
    drops = [r["t"] for r in events(tmp_path / "structure", "edm_roles") if r["role"] == "drop"]
    for d in snap["drops"]:
        assert any(abs(t - d) <= 4.0 for t in drops), (d, drops)
    if not snap["drops"]:
        assert len(drops) <= 1, drops
    # ---- choreo: E000 lead-in, eight-counts tile the bars, groove ids
    counts = events(tmp_path / "choreo", "counts")
    assert counts[0]["id"] == "E000" and counts[0]["lead_in"]
    assert sum(1 for c in counts if c["id"] != "E000") >= 0.8 * len(doc(tmp_path / "rhythm", "events/bars.json")["items"]) / 2
    # ---- cues: one cue per time (D37), all tiers cite a source, tier 1 holds the section starts
    cues = events(tmp_path / "cues", "cues")
    ts = [c["t"] for c in cues]
    assert len(ts) == len(set(ts)) and ts == sorted(ts)
    assert all(c.get("source") for c in cues)
    assert sum(1 for c in cues if c["tier"] == 1) >= len(sec) - 2
