"""frames stage (contract v1, owner M6b, D19): ``frames/<fps>fps.csv`` on demand (``mvh frames``).

One row per video frame under the frame rule ``{fps, frame0, early}`` (CONTRACT §2): ``frame``, ``t`` = time_of(n),
then the requested curve channels sampled with their resample policies (never NaN), then event columns
(section_id, beat, downbeat, bar, beat_phase, count, sub, eight_id, line_id, singer, cue_tier, cue_id, hit).

Params: ``fps`` (24 | 23.976 | [24000, 1001] | "24000/1001" | a list of rates, or of {fps, frame0, early}),
``frame0``, ``early``, ``curves`` ([] = the default video set, ["*"] = every channel, patterns like "drums.*",
"spectrum128" = 128 spectrum columns), ``events`` ("default" | [] | a list of the event columns),
``format`` ("csv" | "deforum": also frames/<fps>fps.deforum.json keyframe strings).
"""
from mvh.contract.stages import ANALYSIS_STAGES
from mvh.runner.spec import Output, StageResult, StageSpec, catalog_outputs

STAGE = StageSpec(
    "frames",
    ANALYSIS_STAGES,
    "main",
    "1.1.0",
    override_keys=(),
    outputs=catalog_outputs("frames") + (
        Output("frames/{fps}fps.deforum.json", "json", None, required=False,
               description="Deforum/ComfyUI keyframe strings per channel ('0:(0.12), 1:(0.13), ...'); with format=deforum"),
    ),
    params={'fps': 30, 'frame0': 0, 'early': False, 'curves': [], 'events': 'default', 'format': 'csv'},
    trigger='on_demand',
    module="M6b",
    description='frames/<fps>fps.csv on demand (mvh frames --fps N [--frame0] [--curves]).',
)


def run(ctx) -> StageResult:
    from .stage import run as _run

    return _run(ctx)
