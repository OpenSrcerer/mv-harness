"""separate_fast stage (PLAN §5 separate_fast, SPIKE "demucs-onnx"; owner M3a).

htdemucs 4-stem (vocals, drums, bass, other) through demucs-onnx on the ARRAY route with our own ORT session
(fp16 weights, ``mvh.sep.demucs``); ``htdemucs_6s`` (adds guitar, piano) in the draft profile. These stems feed
allin1 (which was trained on htdemucs stems) and act as an independent second opinion for stem_activity. They are
cache-only (``fast/<stem>.wav``, float32, at the song's sample rate, same length as the mix).

No stems-sum invariant here: the htdemucs stem sum differs from the mix by 2-10 % RMS (SPIKE); the measured
residual is recorded in ``fast/separation.json`` for information only.
"""

from __future__ import annotations

import numpy as np

from mvh.runner.spec import StageResult, StageSpec, catalog_outputs

STAGE = StageSpec(
    "separate_fast",
    ('ingest',),
    "main",
    "1.0.0",
    override_keys=(),
    outputs=catalog_outputs("separate_fast"),
    params={'model': 'htdemucs'},
    params_by_profile={'draft': {'model': 'htdemucs_6s'}},
    models=("demucs_onnx_htdemucs", "demucs_onnx_htdemucs_6s"),
    module="M3a",
    description='htdemucs 4-stem via demucs-onnx (htdemucs_6s in draft); feeds allin1.',
)


def run(ctx) -> StageResult:
    from mvh.sep import demucs, fit, invariants

    model = str(ctx.params.get("model", "htdemucs"))
    if model not in demucs.MODEL_IDS:
        from mvh.runner.spec import StageError

        raise StageError(f"separate_fast: unknown model {model!r} (htdemucs, htdemucs_6s)")
    mid = demucs.MODEL_IDS[model]
    h = ctx.model(mid)
    onnx = next(iter(h.files.values()))
    mix = ctx.audio("mix")
    n, sr, ch = int(mix.samples.shape[1]), int(mix.sr), int(mix.samples.shape[0])
    x44 = mix.samples if sr == demucs.SAMPLE_RATE else ctx.audio("mix", sr=demucs.SAMPLE_RATE).samples
    x44 = fit.stereo44(x44)
    ctx.log.info(f"separate_fast: {model} on {x44.shape[1] / demucs.SAMPLE_RATE:.1f} s, {ctx.threads} threads")
    stems44 = demucs.separate(x44, model, onnx, ctx.threads)
    stems: dict[str, np.ndarray] = {}
    meta_stems = {}
    for name in demucs.sources_of(model):
        a = fit.to_mix(stems44[name], demucs.SAMPLE_RATE, sr, n, ch, ctx.scratch / "fit")
        rel = f"fast/{name}.wav"
        ctx.writer.audio(rel, a, sr)
        stems[name] = a
        meta_stems[name] = {"model": mid, "file": rel}
    mix_x = np.asarray(mix.samples, dtype=np.float32)
    res = invariants.residual_db(mix_x, list(stems.values()))
    levels = {k: round(invariants.rms_dbfs(v) - invariants.rms_dbfs(mix_x), 2) for k, v in stems.items()}
    ctx.writer.json("fast/separation.json", {
        "variant": "fast", "degraded": False, "lead_backing_split": False,
        "stems": meta_stems,
        "models": [{"id": mid, "licence": h.licence}],
        "invariants": {"sum_error_db": round(res, 2)},
        "model": model, "stem_level_vs_mix_db": levels,
        "notes": ["array route with our own ORT session; song-level mean/std normalisation as demucs.separate",
                  "the htdemucs stem sum is not mass-conserving (2-10 % RMS): no sum gate on this stage"],
    })
    return StageResult(
        status="ok",
        summary={"model": model, "stems": sorted(stems), "sum_error_db": round(res, 2)},
        provenance={"models": [{"id": mid, "licence": h.licence, "revision": h.revision}],
                    "tools": [{"name": "demucs-onnx", "version": _version("demucs-onnx")},
                              {"name": "onnxruntime", "version": _version("onnxruntime")}]},
    )


def _version(dist: str) -> str:
    try:
        import importlib.metadata as md

        return md.version(dist)
    except Exception:  # noqa: BLE001
        return "unknown"


__all__ = ["STAGE", "run"]
