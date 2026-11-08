# ruff: noqa: E501  (long catalogue tables / docstrings)
"""lyrics stage (PLAN §5 lyrics, SPIKE, docs/spike/bench-words.md; owner M5).

Source cascade (user ``--lyrics`` > embedded tags > LRCLIB > faster-whisper transcription), ASR evidence on
lead_vocals, MMS_FA word alignment (torchaudio ``forced_align``; vendored Viterbi fallback; stable-ts below 0.60
coverage) with global offset detection and line-window constraints, repeat expansion that only adds lines,
confidence per word/line, the measured G1-G8 gate and an A-D grade, and the LRC (A2) / VTT / SRT / ASS exports.
The orchestration lives in ``core.py``; see ``docs/contract/decisions/M5.md`` for the contract additions.

Lyric text stays in ``lyrics/*``: never in logs, warnings, the summary, provenance or errors (NF5).
"""
from mvh.runner.spec import ExternalInput, StageResult, StageSpec, catalog_outputs

STAGE = StageSpec(
    "lyrics",
    ('identity', 'separate_hq', 'stem_activity', 'structure'),
    "main",
    "1.0.0",
    override_keys=('lyrics.lines', 'lyrics.words'),
    outputs=catalog_outputs("lyrics"),
    params={'window_s': 30.0, 'context_s': 2.0, 'stable_ts_below_coverage': 0.6, 'stable_ts': True,
            'line_slack_s': 2.5, 'lrclib': True, 'lrclib_max_dd_s': 2.0, 'lrclib_max_dd_flag_s': 5.0,
            'asr': 'faster_whisper', 'asr_vad': True, 'asr_vad_retry': True, 'asr_vad_retry_wps': 0.15, 'asr_beam': 5, 'asr_min_seg_p': 0.25, 'min_active_s': 2.0,
            'min_transcribed_words': 8, 'min_anchor_frac': 0.25, 'expand': True, 'asr_only_lines': True,
            'ggml_model': 'ggml.whisper-large-v3-turbo-q8_0'},
    params_by_profile={"draft": {"asr": "ffmpeg_whisper", "stable_ts": False}},
    external_inputs=(ExternalInput("lyrics", "param:lyrics", False, "--lyrics file"), ExternalInput("lrclib", "http:lrclib"),),
    models=("faster_whisper_large_v3", "mms_fa", "ggml.whisper-large-v3-turbo-q8_0"),
    network=True,
    uses_ffmpeg=True,
    module="M5",
    description='Source cascade (user, tags, LRCLIB, faster-whisper), MMS_FA word alignment, confidence and grade, exports.',
)


def run(ctx) -> StageResult:
    from .core import run as _run

    return _run(ctx)
