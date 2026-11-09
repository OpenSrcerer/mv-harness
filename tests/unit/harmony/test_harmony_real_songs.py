"""Snapshots of the harmony stage on the four real W0 songs (no ground truth: tolerances and plausibility only).

Uses the cached lv-chordia decode in tests/.cache/real/<slug>/chords/ so the test does not re-run the 5-model ensemble, the real
S-KEY model and the real beat grids from tests/contract/real-<slug>. Run explicitly: pytest -m real tests/unit/harmony/test_real_songs.py
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from mvh.stages.harmony import core  # noqa: E402

pytestmark = [pytest.mark.real, pytest.mark.slow]

ROOT = Path(__file__).resolve().parents[3]
SONGS = {
    "megafauna": ROOT.parent / "viz" / "MEGAFAUNA.flac",
    "versatile": ROOT.parent / "viz" / "Versatile.flac",
    "jeremy": ROOT / "songs" / "Jeremy (Redux Version).flac",
    "newton-vs-nye": ROOT / "songs" / "Sir Isaac Newton vs Bill Nye.flac",
}
# acceptable global keys (tonal cluster of the W0 cross-tool evidence, docs/spike/bench-music.md section 3) per song
CLUSTER = {
    "megafauna": {"D minor", "A minor", "F major"},
    "versatile": {"A minor", "C major", "F major"},
    "jeremy": {"A minor", "A major"},
    "newton-vs-nye": {"A minor", "C major"},
}


@pytest.fixture(scope="module", params=sorted(SONGS))
def song(request, skey):
    slug = request.param
    fx = ROOT / "tests" / "contract" / f"real-{slug}"
    lvp = ROOT / "tests" / ".cache" / "real" / slug / "chords" / "chords.json"
    if not SONGS[slug].exists() or not (fx / "events" / "beats.json").exists() or not lvp.exists():
        pytest.skip(f"{slug}: song, fixture or cached chords missing")
    from mvh.io import audio as aio
    from mvh.testing import heavy

    def ev(n):
        return json.loads((fx / "events" / f"{n}.json").read_text(encoding="utf-8"))["items"]

    src = json.loads((fx / "meta" / "source.json").read_text(encoding="utf-8"))
    y = np.asarray(aio.decode(SONGS[slug], sr=22050, mono=True).samples, np.float32).reshape(-1)
    lv = json.loads(lvp.read_text(encoding="utf-8"))["segments"]
    dur = src["n_samples"] / src["sample_rate"]
    with heavy("m4-test"):
        res = core.analyse(y, dur, math.ceil(src["n_samples"] * 100 / src["sample_rate"]), ev("beats"), ev("bars"), lambda: lv, skey, {})
    return slug, res, dur


def test_chord_timeline_is_valid_and_plausible(song):
    slug, res, dur = song
    items = res.chords
    assert abs(items[0]["t"]) < 1e-9 and abs(items[-1]["t"] + items[-1]["d"] - dur) < 1e-3
    assert all(abs(a["t"] + a["d"] - b["t"]) < 1e-5 and a["d"] > 0 for a, b in zip(items, items[1:]))
    assert 0.03 <= res.summary["no_chord_share"] <= 0.25, res.summary          # W0: 4.5 % (jeremy) .. 22 % (newton-vs-nye)
    assert 25 <= res.summary["n_segments"] <= 120 and 3 <= res.summary["distinct_chords"] <= 14
    assert all(0.0 <= c["conf"] <= 1.0 for c in items)
    snapped = [c for c in items if c["beat_index"] is not None]
    assert len(snapped) / len(items) >= 0.8                                     # chord starts sit on beats


def test_global_key_is_in_the_tonal_cluster_with_honest_confidence(song):
    slug, res, _ = song
    g = res.key_meta["global"]
    assert g["key"] in CLUSTER[slug], (g, res.key_meta["methods"]["ensemble"]["alternatives"])
    assert 0.2 <= g["conf"] <= 0.97
    if slug in ("megafauna", "versatile"):                                      # ambiguous in W0: must not claim certainty
        assert g["conf"] <= 0.65 and res.key_meta["flags"]
    regions = res.key_regions
    assert abs(sum(r["d"] for r in regions) - res.chords[-1]["t"] - res.chords[-1]["d"]) < 1e-3
    assert all(b["t"] >= a["t"] + a["d"] - 1e-6 for a, b in zip(regions, regions[1:]))


def test_chroma_curve_is_normalised(song):
    _, res, _ = song
    c = res.chroma_curve
    assert c.shape[0] == 12 and np.isfinite(c).all() and 0.0 <= c.min() and c.max() <= 1.0
    live = c.max(axis=0) > 0
    assert live.mean() > 0.9 and abs(c.max(axis=0)[live].mean() - 1.0) < 0.05
