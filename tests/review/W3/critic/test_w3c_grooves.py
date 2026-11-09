"""W3C-1 / W3C-2 (M2 choreo, R15): the per-bar groove matrix is present, but on real songs the groove ids do not
cluster and the syncopation index is about 0 even on plainly syncopated grooves.

A choreography agent uses groove_id to repeat a move whenever the drum pattern repeats, and syncopation to decide how
"off-beat" a passage should move. Measured on the integrator's max runs:
- Jeremy: 124 groove bars, 91 groove ids, 77 used by one bar only; 31 bars share the same kick/snare steps
  (kick 0/6/10/14, snare 4/12) and still get many ids.
  Versatile 60 ids / 80 bars, MEGAFAUNA 57 / 63, Newton 38 / 88 (synthetic: 12 / 26, truth 11).
- syncopation == 0 on 87 % of Jeremy's bars and 98 % of Newton's, although Jeremy's main beat has kicks on three
  off-beat 8ths (2&, 3&, 4&) and 85 of Newton's 88 bars have kick/snare onsets on off-beat 8ths.
  choreo.syncopation() only scores an onset followed by a rest on the next 16th step, so 8th-note syncopation
  (the common case: an '&' kick tied over the next beat) always scores 0.
"""

from __future__ import annotations

from collections import Counter

import pytest

REAL = ["jeremy", "megafauna", "versatile", "newton-vs-nye"]


def _skeleton(g):
    p = g["pattern"]
    return (tuple(i for i, v in enumerate(p["kick"]) if v > 0), tuple(i for i, v in enumerate(p["snare"]) if v > 0))


@pytest.mark.parametrize("slug", REAL)
def test_w3c_groove_ids_cluster_bars(real_folder, slug):
    f = real_folder(slug)
    gr = f.events("grooves")
    assert gr, "no groove bars"
    ids = Counter(g["groove_id"] for g in gr)
    singletons = sum(1 for n in ids.values() if n == 1)
    ratio = len(ids) / len(gr)
    assert ratio <= 0.35, (f"{slug}: {len(ids)} groove ids for {len(gr)} bars ({singletons} used by one bar only); "
                           "a groove id that is nearly unique per bar cannot drive 'repeat the move when the groove repeats'")


def test_w3c_identical_kick_snare_bars_share_a_groove(real_folder):
    f = real_folder("jeremy")
    gr = f.events("grooves")
    sk = Counter(_skeleton(g) for g in gr)
    top, n = sk.most_common(1)[0]
    assert n >= 8
    ids = Counter(g["groove_id"] for g in gr if _skeleton(g) == top)
    share = ids.most_common(1)[0][1] / n
    assert share >= 0.6, (f"jeremy: {n} bars with the same kick/snare steps {top} are spread over {len(ids)} groove ids "
                          f"(largest share {share:.2f})")


@pytest.mark.parametrize("slug", ["jeremy", "newton-vs-nye"])
def test_w3c_syncopation_sees_offbeat_kicks(real_folder, slug):
    f = real_folder(slug)
    gr = f.events("grooves")
    # bars with a kick/snare onset on an off-beat 8th (step 2, 6 or 10) and no kick/snare on the following beat
    # (Jeremy 71 such bars, 85 % with syncopation 0; Newton 27, 100 %; MEGAFAUNA 13, 15 %)
    synco = []
    for g in gr:
        p = g["pattern"]
        on = [max(p["kick"][k], p["snare"][k]) > 0 for k in range(16)]
        if any(on[k] and not on[k + 2] for k in (2, 6, 10)):
            synco.append(g["syncopation"])
    assert len(synco) >= 10, f"{slug}: only {len(synco)} syncopated bars found"
    zero = sum(1 for s in synco if not s) / len(synco)
    assert zero <= 0.2, (f"{slug}: {len(synco)} bars have an off-beat 8th kick/snare onset tied over the next beat, "
                         f"but syncopation is 0 on {zero:.0%} of them")


def test_w3c_syncopation_function_scores_eighth_note_syncopation():
    from mvh.stages.choreo import syncopation

    rock = {"kick": [0.0] * 16, "snare": [0.0] * 16, "hat": [0.0] * 16, "perc": [0.0] * 16}
    for k in (0, 6, 10, 14):
        rock["kick"][k] = 0.8
    for k in (4, 12):
        rock["snare"][k] = 0.8
    straight = {"kick": [0.0] * 16, "snare": [0.0] * 16, "hat": [0.0] * 16, "perc": [0.0] * 16}
    for k in (0, 8):
        straight["kick"][k] = 0.8
    for k in (4, 12):
        straight["snare"][k] = 0.8
    assert syncopation(straight) == 0.0
    assert syncopation(rock) > syncopation(straight), "kicks on 2&, 3&, 4& (each tied over the next beat) score 0"
