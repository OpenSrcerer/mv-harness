"""R-DSP review round 4 (W3 verify, M1 spectral hits.kick) after fixer-m1-r3 replaced the kick selector with
evidence routes (dsp.kick_route: "sweep" = burst + pitch drop / click, "body" = 30-150 Hz onset that decays >= 8 dB in
90 ms, centred >= 68 Hz; every kick must ADD low-band energy; faint kicks > 12 dB below the song's median kick dropped).

The rules were tuned on one synthetic kick (tests/synth/dsp.kick). All of these pass without the bass / at full level
(F1 1.0); they fail on common mixes:

* R4-M1: an acoustic (rock) kick or a TR-808 kick over a held bass note (the kicks_over_bass texture the earlier rounds
  use with the fixture kick): acoustic R 0.42, 808 R 0.40 with events 11-21 ms early. The body route measures decay and
  centre frequency on the total band (the held bass prevents an 8 dB decay), and the sweep route needs a sweep that starts
  above ~150 Hz.
* R4-M2 (seam S06, re-raised): sidechain-ducked sub bass (EDM; MEGAFAUNA's drops). The bass ducks as the kick hits, so
  the low band does not rise and the "adds low-band energy" rule rejects kicks with attack 6-9 dB, glide ~2 and a
  49 dB click. Fixture kick R 0.5 (bass 0.7) / 0.0 (bass 1.0).
* R4-M3: kick_rel_db is relative to the GLOBAL median kick, so every kick of a section 14 dB quieter (an intro, a
  breakdown, a fade) is dropped: 0 / 16 (16 / 16 with kick_rel_db = 60).

PLAN §7: kick events F1 >= 0.95 at +-10 ms on synthetic one-shots, event time = the one-shot's sample onset.
UD2 (W4): the held-bass designs are now precision targets for the hits.kick fallback (see the test's docstring)."""

from __future__ import annotations

import pytest
from rdsp_m1_support import f1, run_spectral
from rdsp_r4_signals import SR, duck_song, song


def _times(x, tmp_path, params=None) -> list[float]:
    ctx = run_spectral(x, SR, tmp_path, params)
    return [i["t"] for i in ctx.written_events("hits.kick")["items"]]


@pytest.mark.parametrize("kind", ["acoustic", "tr808"])
def test_other_kick_designs_over_a_held_bass_note(kind, tmp_path):
    """Four-on-the-floor at 120 BPM, 8th hats, one bass note per bar starting with the downbeat (gain 0.5 vs kick 0.9).
    Round 4: acoustic F1 0.588 (R 0.417), tr808 F1 0.551; fixer-m1-r4 (click / 808 routes): 1.0 / 0.968.

    REWRITTEN by user decision UD2 (W4, docs/contract/decisions/UD2.md): agents cut on the drum-stem kick; hits.kick is
    the fallback and is tuned for PRECISION over recall. The click route that found these acoustic kicks also turned
    kick-free material into kicks (R5-M3), so it is off. Target now: no invented kick (precision >= 0.95 at +-10 ms)
    and, as a regression guard well under today's value, recall >= 0.5. Measured with the UD2 spectral 1.3.0:
    acoustic P 1.0 R 0.625, tr808 P 1.0 R 0.896. The fixture kick in the same mix keeps F1 1.0."""
    x, ref = song(kind, hats=True, bass=0.5)
    f, p, r = f1(_times(x, tmp_path), ref, 0.010)
    assert p >= 0.95 and r >= 0.5, (kind, round(f, 3), round(p, 3), round(r, 3))
    xf, reff = song("fixture", hats=True, bass=0.5)
    assert f1(_times(xf, tmp_path / "fixture"), reff, 0.010)[0] >= 0.95


@pytest.mark.parametrize("kind,bass", [("fixture", 0.7), ("fixture", 1.0), ("tr909", 0.7)],
                         ids=["fixture-bass0.7", "fixture-bass1.0", "tr909-bass0.7"])
def test_kicks_over_a_sidechain_ducked_sub_bass(kind, bass, tmp_path):
    """128 BPM four-on-the-floor over a continuous sub bass ducked 95 % at each kick (2 ms down, 180 ms recovery).
    Now: fixture F1 0.667 (bass 0.7) and 0.0 (bass 1.0); tr909 F1 0.118. At bass 0.4 all pass. Evidence at a rejected
    kick: attack 7.4 dB, glide 2.2, click 48.6 dB, but low_ex -3.4 / body_ex -2.5 / body_add -1.5 dB (< body_min_db 1)."""
    x, ref = duck_song(kind, bass_gain=bass)
    f, p, r = f1(_times(x, tmp_path), ref, 0.010)
    assert f >= 0.95, (kind, bass, round(f, 3), round(p, 3), round(r, 3))


def test_kicks_in_a_quiet_intro_are_kept(tmp_path):
    """16 bars of the fixture kick + hats: bars 0-3 at -14 dB (a quiet intro), the rest at full level. Now 0 / 16 intro
    kicks (all > 12 dB below the median kick body); with kick_rel_db = 60 all 16 are found. The loud part: F1 1.0."""
    gains = [10 ** (-14.0 / 20)] * 4 + [1.0] * 12
    x, ref = song("fixture", bars=16, hats=True, bass=0.0, gains=gains)
    est = [t for t in _times(x, tmp_path) if t < 8.4]
    f, p, r = f1(est, ref[:16], 0.010)
    assert r >= 0.95, (round(f, 3), round(p, 3), round(r, 3), len(est))
