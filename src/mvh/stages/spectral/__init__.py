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
    "1.2.0",
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
        # kick events (dsp.select_kick_events; one physical signature per route, see dsp.kick_route)
        "kick_gate": 0.5,               # the viz kick band (35-100 Hz) must be above its gate within 80 ms of the onset
        "kick_body_min_db": 1.0,        # every kick adds low-band energy (<= 400 Hz / 30-150 Hz excess or 30-160 Hz power rise)
        "kick_attack_db": 6.0,          # sweep: 90-250 Hz burst above the level before and 55-85 ms after ...
        "kick_glide": 1.25,             # ... with this pitch drop of the added 30-160 Hz energy (2-25 ms vs 40-75 ms after)
        "kick_click_db": 6.0,           # ... or a 1.5-5 kHz beater click this strong
        "kick_click_attack_db": 10.0,   # ... with this burst
        "kick_glide_strong": 1.6,       # ... or this strong a pitch drop (long 808-style kicks)
        "kick_attack_low_db": 4.5,      # ... with this burst
        "kick_body_ex_db": 6.5,         # body (acoustic kicks): 30-150 Hz onset >= this,
        "kick_body_add_db": 4.5,        # 30-160 Hz power rise >= this,
        "kick_body_decay_db": 8.0,      # decaying >= this within 60-90 ms (a bass note sustains),
        "kick_body_low_ex_db": 1.5,     # <= 400 Hz excess >= this,
        "kick_body_f_hz": 68.0,         # added energy centred at >= this (a bass note's sub sits lower)
        "kick_duck_click_db": 15.0,     # duck (sidechain-ducked bass, no low-band rise): attack_low + this click + glide_strong
        "kick_cb_click_db": 15.0,       # clicky body (acoustic kick over a held bass): beater click >= this,
        "kick_cb_attack_db": 3.5,       # ... burst >= this,
        "kick_cb_low_ex_db": 3.0,       # ... <= 400 Hz excess >= this,
        "kick_cb_body_ex_db": 4.5,      # ... 30-150 Hz onset >= this,
        "kick_cb_body_add_db": 3.0,     # ... 30-160 Hz power rise >= this
        "kick_s808_glide": 1.2,         # 808 (long sine kick over a bass): pitch drop >= this,
        "kick_s808_attack_db": 3.0,     # ... burst >= this,
        "kick_s808_body_ex_db": 5.5,    # ... 30-150 Hz onset >= this,
        "kick_s808_body_add_db": 5.0,   # ... 30-160 Hz power rise >= this,
        "kick_s808_low_ex_db": 2.5,     # ... <= 400 Hz excess >= this
        "kick_roll_attack_db": 12.0,    # roll: 40-150 ms after an accepted kick, a burst >= this
        "kick_roll_glide": 1.1,         # ... with a pitch drop >= this
        "kick_roll_gap_min_s": 0.04,
        "kick_roll_gap_max_s": 0.15,
        "kick_rel_db": 12.0,            # faint thumps: body power vs the local mix level > this below the median kick's
        "kick_quiet_conf": 0.7,         # ... and one > rel_db below the song's median kick body needs this kick_conf
        "kick_level_win_s": 1.5,        # local mix level: the quieter of the RMS 1.5 s before / after
        "kick_nms_low_step_db": 2.0,    # onset priority: an own <= 400 Hz / 90-200 Hz step >= this first, then the score
        "kick_nms_s": 0.02,             # one onset per 20 ms
        "kick_dedupe_s": 0.04,          # closer events keep the higher onset score
        "kick_fine_s": 0.005,           # reported onset: steepest <= 400 Hz (+ click) step within +-5 ms
        "kick_pad_s": 0.1,              # silence prepended for the analysis (a kick on the first sample has an onset)
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
