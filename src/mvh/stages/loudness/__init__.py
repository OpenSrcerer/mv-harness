"""loudness stage (owner M1, PLAN §5 loudness).

EBU R128 on the canonical mix: centred momentary (0.4 s) and short-term (3 s) LUFS curves (pyloudnorm K-weighting),
integrated loudness (BS.1770-4), LRA (EBU Tech 3342), true peak (4x oversampling), sample peak, PLR, clipping, and
RMS / peak / crest curves; ffmpeg ``ebur128`` is an independent cross-check (warning when the integrated values differ
by more than 0.5 LU). ``meta/loudness.json`` also names the loudest and quietest moments (see ``r128.py``).

Deps, env and outputs are FROZEN by docs/CONTRACT.md (PLAN §3.2).
"""
from mvh.runner.spec import StageResult, StageSpec, catalog_outputs

STAGE = StageSpec(
    "loudness",
    ('ingest',),
    "main",
    "1.0.0",
    override_keys=(),
    outputs=catalog_outputs("loudness"),
    params={
        "crosscheck_tol_lu": 0.5,     # warn when |integrated - ffmpeg ebur128| exceeds this
        "true_peak_tol_db": 0.5,      # warn when |true peak - ffmpeg ebur128| exceeds this
        "rms_window": 0,              # samples; 0 = the spectral analyser size (2048 at 44.1/48 kHz, 46 ms)
        "limited_lra_lu": 7.0,        # QA flag limited_master: LRA below this ...
        "limited_plr_db": 9.0,        # ... and PLR below this
        "clip_warn_samples": 100,     # QA flag clipping above this many full-scale samples
    },
    uses_ffmpeg=True,
    module="M1",
    description='Momentary/short-term LUFS (pyloudnorm, centred), integrated, LRA; ffmpeg ebur128 cross-check and true peak; RMS/peak/crest.',
)


def run(ctx) -> StageResult:
    from .stage import run as _run

    return _run(ctx)
