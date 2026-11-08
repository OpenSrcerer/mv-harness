# ruff: noqa: E501  (long catalogue tables / docstrings)
"""spectral stage (owner M1, PLAN §5 spectral).

Offline, non-causal port of viz/js/audio.js on the canonical mix: physical band powers (viz bands, kick band, 7 fine
bands) in dBFS with per-song 0..1 twins, the viz-compatible bass/mid/high/level values, spectrum128 (viz bands as u8),
the kick/mid/high hit envelopes (raw and released) and their events refined on 400 Hz zero-phase envelopes, per-band
flux and flux onsets, timbre (centroid, roll-off, flatness, slope) and stereo (width, balance, correlation).
See ``dsp.py`` for what is ported verbatim and what is offline.

Deps, env and outputs are FROZEN by docs/CONTRACT.md (PLAN §3.2).
"""
from mvh.runner.spec import StageResult, StageSpec, catalog_outputs

STAGE = StageSpec(
    "spectral",
    ('ingest',),
    "main",
    "1.0.0",
    override_keys=(),
    outputs=catalog_outputs("spectral"),
    params={
        "gate_db": -46.0,               # viz kickGateDb (absolute floor for normal masters)
        "gate_rel_db": 30.0,            # relative kick gate: p95(kick band dB) - 30
        "gate_margin_db": 6.0,          # quiet masters: the absolute gate drops by how far the sample peak is below -6 dBFS
        "median_ref_s": 8.0,            # centred +-8 s median of attack sizes (offline hit reference)
        "hit_threshold": 0.35,          # viz hitThreshold
        "hit_release_s": 0.18,          # viz hitRelease
        "event_x_min": 0.3,             # weakest attack (vs typical) that may become an event with a crisp onset
        "event_rise_db": 3.0,           # 400 Hz envelope rise needed by a viz-strength attack
        "event_weak_rise_db": 6.0,      # ... and by a weaker one
        "weak_kick_conf": 0.75,         # weaker kick-band hits must also look like a drum kick (click + decay)
        "kick_viz_step_db": 3.0,        # kick band: 10 ms step of the <= 400 Hz envelope a viz-strength attack needs
        "kick_step_db": 5.0,            # ... a weaker attack needs this
        "kick_own_step_db": 6.5,        # a hit this soon after another kick (kick_refractory_s) needs the low band's own attack:
        "kick_own_excess_db": 3.5,      # a step >= kick_own_step_db to a level >= this many dB above the level 60..7 ms before
        "kick_refractory_s": 0.20,      # (the tail of a kick: bass beating, hats and cymbals do not have that attack)
        "kick_click_db": 15.0,          # low-band steps without a viz attack (double kicks) also need this >= 1 kHz click step
        "kick_roll_s": 0.15,            # ... and must sit this close to another kick (a roll; a lone step is a bass note with a hat on it)
        "kick_glide_min": 1.4,          # pitch drop (zero-crossing Hz 2-30 ms / 45-90 ms after the onset) of a drum kick body
        "kick_glide_hi": 1.7,           # a low-band step with a click and this pitch drop is a kick wherever it sits
        "strength_cap": 2.0,            # event strength = attack / typical attack, capped
        "onset_window_s": 0.8,          # centred flux-threshold window (viz: 48 frames at 60 fps)
        "onset_search_before_s": 0.1,   # onset refinement window around the flux peak (the low-band flux lags a kick sweep)
        "onset_search_after_s": 0.02,
        "onset_rise_db": 1.5,
    },
    module="M1",
    description='Offline non-causal port of viz/js/audio.js: bands, spectrum128, hit envelopes and events, flux onsets, timbre, stereo.',
)


def run(ctx) -> StageResult:
    from .stage import run as _run

    return _run(ctx)
