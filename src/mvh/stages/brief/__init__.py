"""brief stage (contract v1, owner M6b): brief.md, the LLM entry point (CONTRACT §12, PLAN §4.7).

<= 4k tokens (target 2.5k; characters / 4), every number traceable to the file its block names, no lyric text.
``mvh brief <song folder> [--section S05] [--lyrics]`` prints the brief or a <= 1.5k-token zoom of one section
(``mvh.stages.brief.cli``).
"""
from mvh.contract.stages import ANALYSIS_STAGES
from mvh.runner.spec import StageResult, StageSpec, catalog_outputs

STAGE = StageSpec(
    "brief",
    ANALYSIS_STAGES,
    "main",
    "1.1.0",
    override_keys=(),
    outputs=catalog_outputs("brief"),
    params={'max_tokens': 4000, 'target_tokens': 2500},
    module="M6b",
    description='brief.md (<= 4k tokens) and the --section zooms.',
)


def run(ctx) -> StageResult:
    from mvh.stages.meaning.source import CtxSource

    from .build import flags_from_records, gather, render_brief

    src = CtxSource(ctx)
    recs = src.records()
    tempo = src.json("meta/tempo.json")
    key = src.json("meta/key.json")
    d = gather(src, flags_from_records(recs, tempo, key))
    text, info = render_brief(d, int(ctx.params.get("max_tokens", 4000)), int(ctx.params.get("target_tokens", 2500)))
    ctx.writer.text("brief.md", text)
    missing = [m for m in src.missing if m not in ("events:visemes",)]
    warnings = []
    if info["tokens"] > int(ctx.params.get("max_tokens", 4000)):
        warnings.append(f"brief.md is {info['tokens']} tokens (cap {ctx.params.get('max_tokens', 4000)})")
    if info["trimmed_rows"]:
        warnings.append(f"brief.md: {info['trimmed_rows']} section rows omitted to fit the token cap")
    return StageResult(
        status="ok" if not missing else "degraded",
        summary={"tokens": info["tokens"], "collapsed": info["collapsed"], "compact": info["compact"],
                 "n_sections": info["n_sections"], "missing_inputs": len(missing)},
        warnings=warnings,
        fallbacks=["brief:missing_inputs"] if missing else [],
        provenance={"notes": [f"missing inputs: {', '.join(missing[:20])}"] if missing else []},
        confidence=1.0 if not missing else 0.7,
    )
