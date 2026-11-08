# ruff: noqa: E501  (long catalogue tables / docstrings)
"""voices stage (PLAN §5 voices, SPIKE; owner M5).

Speaker embeddings (SpeechBrain ECAPA, WeSpeaker ONNX fallback) per aligned lyric line and per word chunk of
long lines on lead_vocals, clustered into V1..Vn (agglomerative, cosine). k comes from the user (intent.md count
or per-line assignments, overrides ``voices.lines``) first, then from speaker labels in the lyrics source, then
from an estimate (eigengap lower bound + silhouette). Duet spans come from backing_vocals. The user maps voices
to characters in the viewer / intent.md. Orchestration in ``core.py``.
"""
from mvh.runner.spec import ExternalInput, StageResult, StageSpec, catalog_outputs

STAGE = StageSpec(
    "voices",
    ('lyrics', 'separate_hq', 'stem_activity'),
    "main",
    "1.0.0",
    override_keys=('voices.lines',),
    outputs=catalog_outputs("voices"),
    params={'model': 'ecapa', 'min_item_s': 1.0, 'split_s': 8.0, 'chunk_s': 4.0, 'k_max': 8, 'same_voice_cos': 0.6,
            'min_silhouette': 0.08, 'review_below': 0.5, 'backing_spans': True, 'backing_rel_db': -15.0,
            'backing_min_sim': 0.25, 'activity_gap_s': 0.35, 'merge_minor': True, 'small_n': 24},
    external_inputs=(ExternalInput("intent", "meaning/intent.md", False, "character count and voice mapping"),),
    models=("speechbrain_ecapa_voxceleb", "wespeaker_resnet34_lm_onnx"),
    module="M5",
    description='Speaker embeddings per aligned line/word span, clustered into V1..Vn; a proposed voice per line.',
)


def run(ctx) -> StageResult:
    from .core import run as _run

    return _run(ctx)
