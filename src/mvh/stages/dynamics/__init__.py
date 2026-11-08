# ruff: noqa: E501  (long catalogue tables / docstrings)
"""dynamics stage (owner M1, PLAN §5 dynamics; SPIKE: adaptive thresholds plus bass and kick features).

Loud and quiet parts (``events/dynamics.json``: silence, quiet, soft, medium, loud, peak by mean short-term LU vs the
integrated loudness, boundaries from multi-feature Foote novelty with adaptive prominence plus silences, stops and
strong impacts, snapped to downbeats; a 4-bar-grid / allin1 fallback for limited masters), impacts (I), stops (X),
silences (Z), decay tails (Y), the ``dyn.intensity`` composite and ``dyn.novelty``. Each part carries additive evidence
(energy, bass, kick and onset density, brightness, loudness trend, a drop/build/breakdown ``role_hint`` for the
structure stage). ``meta/dynamics.json`` (additive, optional) summarises the loud and quiet parts for readers.

Deps, env and catalogue outputs are FROZEN by docs/CONTRACT.md (PLAN §3.2).
"""
from mvh.runner.spec import Output, StageResult, StageSpec, catalog_outputs

STAGE = StageSpec(
    "dynamics",
    ('loudness', 'spectral', 'rhythm'),
    "main",
    "1.0.0",
    override_keys=(),
    outputs=catalog_outputs("dynamics") + (
        Output("meta/dynamics.json", "json", None, required=False,
               description="readable summary of the loud and quiet parts (additive, M1)"),
    ),
    params={
        "novelty_rate_hz": 10,
        "novelty_halves_s": [4.0, 8.0],     # Foote kernel half-widths
        "novelty_rel_prom": 0.35,           # peak prominence >= 0.35 x median of the 8 strongest
        "min_segment_s": 4.0,               # novelty peak distance
        "min_part_s": 6.0,                  # parts shorter than 2 bars (3..6 s) are merged (silences excepted)
        "min_part_bars": 2,
        "min_parts_per_s": 45.0,            # fewer than duration / 45 parts -> fallback boundaries
        "fallback_keep_pct": 60.0,          # keep fallback candidates above this percentile of contrast ...
        "fallback_min_contrast": 0.8,       # ... and above this absolute contrast
        "merge_similarity": 1.2,            # same-level neighbours closer than this (median features) always merge
        "merge_max": 3.0,                   # ... and up to this distance while there are more than duration / 20 s parts
        "target_part_s": 20.0,
        "max_part_s": 30.0,                 # longer parts are split at their own strongest novelty peak ...
        "split_min_contrast": 1.2,          # ... when the feature contrast across it is at least this
        "split_min_side_s": 8.0,            # ... and both new parts last at least this long
        "contrast_span_s": 8.0,             # blocks compared on each side of a candidate boundary
        "level_scale_range_lu": 8.0,        # thresholds x clip(loudness range / 8 LU, 0.5, 1)
        "level_scale_min": 0.5,
        "snap_hard_s": 0.2,                 # event boundaries snap to a downbeat only within 0.2 s
        "level_thresholds_lu": [-12.0, -6.0, -2.0, 2.0],
        "silence_rel_lu": 30.0,             # silence: momentary below integrated - 30 LU ...
        "silence_cap_lufs": -45.0,          # ... and below -45 LUFS
        "silence_min_s": 0.5,               # shorter gaps between soft hits are not silences
        "impact_lu": 4.0,                   # impact score = max(dLU / 4, dBass / 6 dB, dBrightness / 0.5 oct)
        "impact_bass_db": 6.0,
        "decay_part_min_s": 2.0,            # decay tails this long (strength >= 0.5) start their own part
        "impact_boundary_strength": 0.85,   # impacts this strong are part boundaries
    },
    module="M1",
    description='Loud/quiet parts (adaptive multi-feature novelty, bar-grid fallback); impacts, stops, silences, decay tails; intensity.',
)


def run(ctx) -> StageResult:
    from .stage import run as _run

    return _run(ctx)
