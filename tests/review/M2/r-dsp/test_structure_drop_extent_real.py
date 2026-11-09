"""R-DSP M2 round 3, finding F6-r3 (major, real song, opt-in -m real): after the F4-r2 fix, MEGAFAUNA's drop is cut
short by 36.6 s.

SPIKE (docs/spike/bench-music.md, megafauna): drop tags at 114.1 and 146.3 s, then a "loud plateau 146-217 s"; the drop
is the song's single big event. Round 2 marked the drop 141.8-212.7 s (up to the 3-bar outro). Round 3 marks it
141.8-176.1 s and labels the rest of the plateau (176.1 / 185.3 / 194.4 s, section energies 1.73 / 1.62 / 1.90 z, the
song's highest after the drop itself; build 0.95, everything else <= 0.62) 'inst'.

Cause: the bar at 151.0 s scores above the section cost in both rounds (r2 1.10 vs 0.80, r3 1.61 vs 1.11). In round 2
141.8 s was one 8-bar section; with the new agglomerative grouping (F4-r2) 151.0 s lands in group K (with 176.1 / 185.3)
instead of the drop opening's group J, the same-group merge no longer rejoins it, and the drop starts with a 4-bar
section. The drop extends over the following sections only while ``drive[j] >= drive[i] - 0.6`` with i the drop's FIRST
section; the first 4 bars alone are hotter (2.49 z vs 2.19 z for the 8 bars), so the bar rises from 1.59 to 1.89 and the
plateau falls out of the drop. Both groups now mix roles (J: 141.8 / 160.1 / 169.3 drop, 194.4 inst; K: 151.0 drop,
176.1 / 185.3 inst), and 151.0 s at 1.895 z is a drop while 194.4 s at 1.898 z is not. Neither ``split_min_novelty`` 0
nor ``repeat_adjacent_penalty`` 1.0 restores it (same 141.8-176.1 s drop): the extent rule, not one parameter, is fragile.

The W0 raw tracker outputs (tests/.cache/real/megafauna) are replayed instead of running inference."""
import numpy as np
import pytest
from tests.synth.m2.testing import REPO, events

SLUG = "megafauna"
CACHE = REPO / "tests" / ".cache" / "real" / SLUG
FX = REPO / "tests" / "contract" / f"real-{SLUG}"
PLATEAU = (146.3, 212.0)       # SPIKE loud plateau 146-217 s, up to the outro the stage itself finds (212.7 s)


@pytest.fixture(scope="module")
def rhythm_out(tmp_path_factory):
    if not (CACHE / "beat_this" / "logits_beat.npy").is_file() or not (FX / "_intermediate" / "ingest").is_dir():
        pytest.skip("W0 real-song cache / fixture for megafauna not present")
    from tests.synth.m2.ctx import run_stage

    import mvh.stages.rhythm.trackers as T

    bl = np.load(CACHE / "beat_this" / "logits_beat.npy").astype(np.float32).reshape(-1)
    dl = np.load(CACHE / "beat_this" / "logits_downbeat.npy").astype(np.float32).reshape(-1)
    act = np.load(CACHE / "madmom_dbn" / "rnn_activations.npy").astype(np.float32)
    mp = pytest.MonkeyPatch()
    mp.setattr(T, "beat_this_logits", lambda mono, sr, ck: (bl, dl))
    mp.setattr(T, "madmom_activations", lambda x: act)
    out = tmp_path_factory.mktemp("megafauna") / "rhythm"
    try:
        run_stage("rhythm", FX, out, slug=SLUG, threads=6)
    finally:
        mp.undo()
    return out


def _structure(rhythm_out, tmp, params):
    from tests.synth.m2.ctx import run_stage

    run_stage("structure", FX, tmp / "structure", overlays={"rhythm": rhythm_out}, slug=SLUG, threads=6, params=params)
    return events(tmp / "structure", "edm_roles"), events(tmp / "structure", "sections")


def _drop_cover(edm):
    a, b = PLATEAU
    cov = 0.0
    for e in edm:
        if e["role"] == "drop":
            cov += max(0.0, min(b, e["t"] + e["d"]) - max(a, e["t"]))
    return cov / (b - a)


def _show(edm, secs):
    return ([(e["role"], round(e["t"], 1), round(e["t"] + e["d"], 1)) for e in edm],
            [(round(s["t"], 1), s["n_bars"], s["label"], s["repeat_group"], s["energy"]) for s in secs if s["t"] > 120])


@pytest.mark.real
@pytest.mark.timeout(1800)
def test_drop_covers_the_loud_plateau(rhythm_out, tmp_path):
    edm, secs = _structure(rhythm_out, tmp_path, {})
    assert _drop_cover(edm) >= 0.9, _show(edm, secs)

