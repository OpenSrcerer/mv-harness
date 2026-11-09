"""R-DSP review round 5 (W3 verify, M1 spectral hits.kick) after fixer-m1-r4 added the kick routes "click" (beater click
>= 15 dB on a low-band onset), "duck" (attack, click >= 15 dB, pitch drop >= 1.6, no low-band rise) and "808" (pitch
drop >= 1.2 of the added energy).

The round-4 tests pass, but only at the exact points they test:

* R5-M1 (R4-M1 not fixed): the 808 route sits on its 1.2 pitch-drop threshold. The round-4 TR-808 mix passes at 120 BPM
  (F1 0.968) and fails at 100 BPM (0.809) and 140 BPM (0.567), same kick and bass level. The acoustic kick fails at
  bass 0.7 (F1 0.829; the round-4 evidence named bass 0.7). The click route needs a click >= 15 dB, which only exists
  when the 1.5-5 kHz band is near-empty before the kick: a quiet lead chord (peak 0.1 vs kick 0.9) drops the acoustic
  kick to R 0.58. (The sweep route, fixture kick, keeps 1.0 under the same bed.)
* R5-M2 (R4-M2 not fixed): the duck route needs the same 15 dB click. With the quiet lead chord, the TR-909 kick over a
  ducked sub scores R 0.04 and the fixture kick R 0.67. On the real songs the duck route fires once (MEGAFAUNA) and
  MEGAFAUNA's strong DrumSep kicks are still matched 0.22 (0.21 before the fix).
* R5-M4 (R4-M3 half fixed): a quiet section keeps only kicks with kick_conf >= 0.7 (song-global body reference).
* R5-M3 (new, regression from the click route): kick-free textures with a click-band transient on a low-band onset
  become kicks: a pluck bass with hats (50 kicks, 38 by the click route), low piano chords (21 of 48 chords, all click),
  a snare that starts a held bass note (7, all click).

PLAN §7: kick events F1 >= 0.95 at +-10 ms on synthetic one-shots, event time = the one-shot's sample onset."""

from __future__ import annotations

import pytest
from rdsp_m1_support import f1, run_spectral
from rdsp_r4_signals import SR, duck_song, song
from rdsp_r5_signals import kick_free, with_bed


def _times(x, tmp_path, params=None) -> list[float]:
    ctx = run_spectral(x, SR, tmp_path, params)
    return [i["t"] for i in ctx.written_events("hits.kick")["items"]]


@pytest.mark.parametrize("kind,bpm,bass", [("tr808", 100.0, 0.5), ("tr808", 140.0, 0.5), ("acoustic", 120.0, 0.7)],
                         ids=["tr808-100bpm-bass0.5", "tr808-140bpm-bass0.5", "acoustic-120bpm-bass0.7"])
def test_r4_kick_designs_over_a_held_bass_at_other_tempos_and_levels(kind, bpm, bass, tmp_path):
    """The round-4 mix (4-on-the-floor, 8th hats, one bass note per bar) at another tempo or bass level.
    Now: tr808 100 BPM F1 0.809, 140 BPM F1 0.567 (R 0.40; misses read pitch drop 1.04-1.12 < 1.2, centred 61-65 Hz
    < 68 Hz); acoustic at bass 0.7 F1 0.829 (R 0.71). The tested point (tr808 / acoustic, 120 BPM, bass 0.5): 0.968 / 1.0."""
    x, ref = song(kind, bpm=bpm, hats=True, bass=bass)
    f, p, r = f1(_times(x, tmp_path), ref, 0.010)
    assert f >= 0.95, (kind, bpm, bass, round(f, 3), round(p, 3), round(r, 3))


def test_acoustic_kick_over_a_held_bass_with_a_quiet_lead_chord(tmp_path):
    """The round-4 acoustic case that now passes (F1 1.0), plus a sustained lead chord 19 dB below the kick peak.
    Now: R 0.58 (the click route's 15 dB click is gone; the body route's 8 dB decay cannot happen over the bass). The
    fixture kick in the same mix keeps F1 1.0."""
    x, ref = song("acoustic", hats=True, bass=0.5)
    f, p, r = f1(_times(with_bed(x, 0.1), tmp_path), ref, 0.010)
    assert f >= 0.95, (round(f, 3), round(p, 3), round(r, 3))


@pytest.mark.parametrize("kind", ["tr909", "fixture"])
def test_ducked_sub_with_a_quiet_lead_chord(kind, tmp_path):
    """The round-4 sidechain-duck mix (bass 0.7, passes now at F1 1.0) plus the same quiet lead chord.
    Now: tr909 R 0.04, fixture R 0.67 (the duck route needs a 1.5-5 kHz click >= 15 dB above the 50-10 ms before)."""
    x, ref = duck_song(kind, bass_gain=0.7)
    f, p, r = f1(_times(with_bed(x, 0.1), tmp_path), ref, 0.010)
    assert f >= 0.95, (kind, round(f, 3), round(p, 3), round(r, 3))


@pytest.mark.parametrize("kind", ["pluck_hats", "piano_low", "snare_bass"])
def test_no_kicks_on_kick_free_low_onsets_with_a_click(kind, tmp_path):
    """No kick in these mixes (same bound as test_rdsp_kick_events: <= 2). Now: pluck_hats 50 (click route 38, sweep 12),
    piano_low 21 of 48 chords (all click route), snare_bass 7 of 24 snares (all click route)."""
    items = _times(kick_free(kind), tmp_path)
    assert len(items) <= 2, f"{kind}: {len(items)} kick events on kick-free material, e.g. {[round(t, 2) for t in items[:5]]}"


@pytest.mark.parametrize("kind,db,bass", [("tr808", -20.0, 0.0), ("acoustic", -14.0, 0.5)],
                         ids=["tr808-intro-20dB", "acoustic-over-bass-intro-14dB"])
def test_quiet_intro_kicks_of_other_designs_are_kept(kind, db, bass, tmp_path):
    """R5-M4 (R4-M3 only half fixed): 16 bars, bars 0-3 at ``db`` (a quiet intro), the rest at full level. The faint-thump
    filter is now relative to the local mix level, but an event > 12 dB below the SONG's median kick body must still have
    kick_conf >= kick_quiet_conf (0.7), and the 808 / click-route kicks read 0.4-0.69. Now: intro recall tr808 0.75,
    acoustic 0.875; the loud part 1.0 / 1.0; with kick_quiet_conf = 0: 1.0 / 1.0. (Fixture / 909 kicks, sweep route,
    conf ~1: 16 / 16.)"""
    gains = [10 ** (db / 20)] * 4 + [1.0] * 12
    x, ref = song(kind, bars=16, hats=True, bass=bass, gains=gains)
    est = _times(x, tmp_path)
    fi, pi, ri = f1([t for t in est if t < 8.4], ref[:16], 0.010)
    fl, _, rl = f1([t for t in est if t >= 8.4], ref[16:], 0.010)
    assert rl >= 0.95, ("loud part should pass", kind, round(fl, 3))
    assert ri >= 0.95, (kind, db, round(fi, 3), round(pi, 3), round(ri, 3))
