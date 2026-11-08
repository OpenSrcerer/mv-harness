# ruff: noqa: E501
"""lipsync stage (PLAN §5 lipsync, SPIKE, CONTRACT D16; owner M5).

``vocal.mouth_open`` (always; max over voices) and ``vocal.mouth_open.<V>`` (>= 2 voices): the lead-vocal
envelope gated by each voice's sustain-extended aligned words, with an ungated fallback for wordless vocals.
Rhubarb Lip Sync visemes per voice block (Should, decoration track) and g2p-en phonemes over the aligned words
(Could). Orchestration in ``core.py``.
"""
from mvh.runner.spec import StageResult, StageSpec, catalog_outputs

STAGE = StageSpec(
    "lipsync",
    ('lyrics', 'voices', 'separate_hq'),
    "main",
    "1.0.0",
    override_keys=(),
    outputs=catalog_outputs("lipsync"),
    params={'attack_ms': 10, 'release_ms': 60, 'pad_s': 0.08, 'hold_within_db': 20.0, 'max_hold_s': 1.5,
            'ungated_fallback': True, 'fallback_below_p95_db': 25.0, 'fallback_within_db': 10.0, 'fallback_min_s': 0.5,
            'visemes': True, 'rhubarb_block_gap_s': 2.0, 'phonemes': True},
    params_by_profile={"draft": {"visemes": False}},
    models=("rhubarb_lip_sync", "nltk_g2p_data"),
    module="M5",
    description='vocal.mouth_open (+ per voice); Rhubarb visemes and phonemes (Should).',
)


def run(ctx) -> StageResult:
    from .core import run as _run

    return _run(ctx)
