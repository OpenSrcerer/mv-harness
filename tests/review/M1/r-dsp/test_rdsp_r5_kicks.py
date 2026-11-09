"""R-DSP review round 5 (W3 verify, M1 spectral hits.kick) after fixer-m1-r4 added the kick routes "click" (beater click
>= 15 dB on a low-band onset), "duck" (attack, click >= 15 dB, pitch drop >= 1.6, no low-band rise) and "808" (pitch
drop >= 1.2 of the added energy).

Round 5 found that those routes passed only at the exact points the round-4 tests probe (R5-M1: 808 at 100 / 140 BPM,
acoustic at bass 0.7; R5-M2: a quiet lead chord hides the 15 dB click of the click / duck routes; R5-M4: quiet intros
of 808 / acoustic kicks), and that the click route invents kicks on kick-free material (R5-M3: a pluck bass with hats,
low piano chords, a snare on a new bass note).

REWRITTEN by user decision UD2 (W4; docs/contract/decisions/UD2.md, CONTRACT D79/D80). Agents now cut on the drum-stem
kick (events/drum_hits, drum = kick, quality-gated); hits.kick is the fallback for runs without drum stems and is tuned
for PRECISION over recall: the click route is off, the sweep route's click alternative needs a 12 dB burst, and a weak
(< 0.5 x typical attack) AND ambiguous (kick_conf < 0.8) event is dropped. Chasing full recall on these mix-only hard
textures kept trading one false-kick case for another, so:

* R5-M3 (kick-free textures) stays a hard target: <= 2 events (now 0 / 0 / 0; was 50 / 21 / 7);
* R5-M1, R5-M2, R5-M4 become precision targets: no invented kick (precision >= 0.95; at +-10 ms, or at +-30 ms where
  the 808's ~10 ms early anchor is a known timing limit, not an invented kick), with a recall regression guard far below
  today's value only where recall is still substantial. Measured recall (UD2 spectral 1.3.0, +-10 ms):
  808 100 BPM 0.77 (0.94 at +-30 ms), 808 140 BPM 0.25, acoustic bass 0.7 0.23, acoustic + lead chord 0.56,
  909 ducked + lead chord 0.04, fixture ducked + lead chord 0.67, quiet intro 808 0.75, acoustic over bass with a
  quiet intro 0.63 overall. The drum-stem kick covers these songs; the agent-facing source is in manifest
  summary.kick_source.
* The contract fixture kick stays a full F1 target (tests/unit/spectral, test_rdsp_kick_events)."""

from __future__ import annotations

import pytest
from rdsp_m1_support import f1, run_spectral
from rdsp_r4_signals import SR, duck_song, song
from rdsp_r5_signals import kick_free, with_bed


def _times(x, tmp_path, params=None) -> list[float]:
    ctx = run_spectral(x, SR, tmp_path, params)
    return [i["t"] for i in ctx.written_events("hits.kick")["items"]]


@pytest.mark.parametrize("kind,bpm,bass,tol,r_min", [("tr808", 100.0, 0.5, 0.030, 0.6), ("tr808", 140.0, 0.5, 0.010, 0.0),
                                                     ("acoustic", 120.0, 0.7, 0.010, 0.0)],
                         ids=["tr808-100bpm-bass0.5", "tr808-140bpm-bass0.5", "acoustic-120bpm-bass0.7"])
def test_r4_kick_designs_over_a_held_bass_at_other_tempos_and_levels(kind, bpm, bass, tol, r_min, tmp_path):
    """The round-4 mix (4-on-the-floor, 8th hats, one bass note per bar) at another tempo or bass level: no invented
    kick. (Round 5: tr808 100 BPM F1 0.809, 140 BPM 0.567, acoustic bass 0.7 0.829 under a recall target.)"""
    x, ref = song(kind, bpm=bpm, hats=True, bass=bass)
    f, p, r = f1(_times(x, tmp_path), ref, tol)
    assert p >= 0.95 and r >= r_min, (kind, bpm, bass, tol, round(f, 3), round(p, 3), round(r, 3))


def test_acoustic_kick_over_a_held_bass_with_a_quiet_lead_chord(tmp_path):
    """The round-4 acoustic case plus a sustained lead chord 19 dB below the kick peak: no invented kick. The fixture
    kick in the same mix keeps F1 >= 0.95."""
    x, ref = song("acoustic", hats=True, bass=0.5)
    f, p, r = f1(_times(with_bed(x, 0.1), tmp_path), ref, 0.010)
    assert p >= 0.95 and r >= 0.3, (round(f, 3), round(p, 3), round(r, 3))
    xf, reff = song("fixture", hats=True, bass=0.5)
    assert f1(_times(with_bed(xf, 0.1), tmp_path / "fixture"), reff, 0.010)[0] >= 0.95


@pytest.mark.parametrize("kind", ["tr909", "fixture"])
def test_ducked_sub_with_a_quiet_lead_chord(kind, tmp_path):
    """The round-4 sidechain-duck mix (bass 0.7) plus the quiet lead chord: no invented kick (the duck route needs a
    15 dB click the chord masks; a mix-only detector cannot tell a ducked kick from the duck itself there)."""
    x, ref = duck_song(kind, bass_gain=0.7)
    f, p, r = f1(_times(with_bed(x, 0.1), tmp_path), ref, 0.010)
    assert p >= 0.95, (kind, round(f, 3), round(p, 3), round(r, 3))


@pytest.mark.parametrize("kind", ["pluck_hats", "piano_low", "snare_bass"])
def test_no_kicks_on_kick_free_low_onsets_with_a_click(kind, tmp_path):
    """No kick in these mixes (same bound as test_rdsp_kick_events: <= 2). Round 5: pluck_hats 50 (click route 38, sweep
    12), piano_low 21 of 48 chords (all click route), snare_bass 7 of 24 snares (all click route). UD2: 0 / 0 / 0."""
    items = _times(kick_free(kind), tmp_path)
    assert len(items) <= 2, f"{kind}: {len(items)} kick events on kick-free material, e.g. {[round(t, 2) for t in items[:5]]}"


@pytest.mark.parametrize("kind,db,bass", [("tr808", -20.0, 0.0), ("acoustic", -14.0, 0.5)],
                         ids=["tr808-intro-20dB", "acoustic-over-bass-intro-14dB"])
def test_quiet_intro_kicks_of_other_designs_are_kept(kind, db, bass, tmp_path):
    """16 bars, bars 0-3 at ``db`` (a quiet intro), the rest at full level: no invented kick, in the intro or after it,
    and the intro's kicks are not all lost (recall guard 0.5 for the 808; the acoustic design over a bass is a click-route
    texture: precision only)."""
    gains = [10 ** (db / 20)] * 4 + [1.0] * 12
    x, ref = song(kind, bars=16, hats=True, bass=bass, gains=gains)
    est = _times(x, tmp_path)
    fi, pi, ri = f1([t for t in est if t < 8.4], ref[:16], 0.010)
    fl, pl, rl = f1([t for t in est if t >= 8.4], ref[16:], 0.010)
    assert pi >= 0.95 and pl >= 0.95, (kind, db, round(pi, 3), round(pl, 3))
    if kind == "tr808":
        assert ri >= 0.5 and rl >= 0.8, (kind, db, round(ri, 3), round(rl, 3))
