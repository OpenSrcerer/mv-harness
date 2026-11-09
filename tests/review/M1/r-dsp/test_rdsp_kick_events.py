"""R-DSP review (M1 spectral): hits.kick events against exact one-shot truth (PLAN §7: kick events F1 >= 0.95 at
+-10 ms, event time = the one-shot's first sample) in the textures the builder's tests leave out: a bass note that
starts WITH the kick, the contract fixture song itself, and kick-free material."""

from __future__ import annotations

import numpy as np
import pytest
from rdsp_m1_support import SR, f1, kicks_over_bass, run_spectral, synth_song


def _kick_times(ctx) -> list[float]:
    return [float(it["t"]) for it in ctx.written_events("hits.kick")["items"]]


def test_kick_events_over_a_bass_note_that_starts_with_the_kick(tmp_path):
    """Four-on-the-floor kicks (tests/synth/dsp.kick, the fixture's kick) over one sustained bass note per bar starting
    on the downbeat kick, at the fixture's relative gains. Every kick also gets a second, weak 'kick' 40-160 ms later:
    the weak-hit path (x >= 0.3, >= 6 dB step) accepts it because kick_confidence() measured inside the previous kick's
    click and decay reads 1.0, and the 40 ms de-duplication is shorter than a kick. The real viz/js/audio.js registers
    ~55 hits here; the stage emits ~119 events."""
    x, ref = kicks_over_bass(bass_gain=0.6)
    ctx = run_spectral(x, SR, tmp_path / "s")
    est = _kick_times(ctx)
    f, p, r = f1(est, ref, 0.010)
    assert f >= 0.95, f"kick events F1 {f:.3f} (P {p:.3f}, R {r:.3f}): {len(est)} events for {len(ref)} kicks"


def test_kick_events_quiet_bass_note_still_doubles(tmp_path):
    """Same texture with the bass 12 dB lower (bass_gain 0.15): the duplicates are not caused by a loud bass."""
    x, ref = kicks_over_bass(bass_gain=0.15)
    ctx = run_spectral(x, SR, tmp_path / "s")
    est = _kick_times(ctx)
    f, p, r = f1(est, ref, 0.010)
    refa = np.asarray(ref)
    late = sorted(round(float(t - refa[np.argmin(np.abs(refa - t))]), 3) for t in est if np.min(np.abs(refa - t)) > 0.010)
    assert p >= 0.95, f"precision {p:.3f} (F1 {f:.3f}); unmatched events relative to the nearest kick (s): {late[:12]}"


def test_kick_events_on_the_contract_fixture_song(synth_ok, tmp_path):
    """The scored synthetic song (tests/contract/synth, 85 kicks): 143 kick events, precision 0.55 at +-10 ms; 33 of the
    58 extra events sit 20-200 ms after a real kick."""
    x, sr, truth, _ = synth_song()
    ref = [h["t"] for h in truth["drum_hits"] if h["inst"] == "kick"]
    ctx = run_spectral(x, sr, tmp_path / "s")
    est = _kick_times(ctx)
    f, p, r = f1(est, ref, 0.010)
    assert p >= 0.85 and r >= 0.9, f"fixture song kick events: P {p:.3f} R {r:.3f} F1 {f:.3f} ({len(est)} events, {len(ref)} kicks)"


def _kickless(kind: str, dur: float = 20.0) -> np.ndarray:
    from tests.synth import dsp
    from tests.synth.m1.signals import _faded

    sr = SR
    x = np.zeros((2, int(dur * sr)))
    t, k = 0.5, 0
    while t < dur - 1.0:
        if kind == "piano":
            dsp.place(x, dsp.pan(dsp.piano_note([57, 60, 64, 62][k % 4], 0.45, 0.8, sr), 0.0), int(t * sr))
        else:
            dsp.place(x, dsp.pan(_faded(dsp.hihat(0.6, False, sr), sr) * 0.3, 0.3), int(t * sr))
            dsp.place(x, dsp.pan(_faded(dsp.hihat(0.4, False, sr), sr) * 0.3, 0.3), int((t + 0.25) * sr))
            if k % 2 == 1:
                dsp.place(x, dsp.pan(_faded(dsp.snare(0.8, sr), sr) * 0.55, 0.0), int(t * sr))
        t += 0.5
        k += 1
    x += 10 ** (-70 / 20) * np.random.default_rng(1).standard_normal(x.shape)
    return x * 10 ** (-1 / 20) / np.max(np.abs(x))


@pytest.mark.parametrize("kind", ["piano", "snare_hats"])
def test_no_kick_events_on_kick_free_material(kind, tmp_path):
    """A piano part (A3-E4) or snares + hats, mastered to -1 dBFS peak, contain no kick. viz/js/audio.js registers 0
    kick hits (absolute -46 dB gate); with PLAN §5's gate max(-46, p95 - 30) the stage also finds 0. The stage's extra
    'quiet-master' rule (gate = p95 - 20 when p95 < -26) reads a kick-free song as a quiet master and drops the gate to
    ~-90 dB, so every piano note (37) or snare (19) becomes a kick event flagged viz=true, and the run warns 'quiet master'."""
    x = _kickless(kind)
    ctx = run_spectral(x, SR, tmp_path / "s")
    items = ctx.written_events("hits.kick")["items"]
    assert len(items) <= 2, f"{kind}: {len(items)} kick events on kick-free material, e.g. {[(round(i['t'], 2), i['viz'], i['db']) for i in items[:4]]}"
