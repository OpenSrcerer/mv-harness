# ruff: noqa: E501  (long docstrings and tables)
"""demucs-onnx through the array route (docs/spike/main.md §2): our own ORT session + the library's
``_chunked_separate_single`` (private but stable in 0.3.4). Its public ``separate()`` reads paths through
libsndfile, which fails on Versatile.flac and breaks the "never hand a file path to a model" rule.

Like ``demucs.separate`` (the pipeline allin1 was trained on), the song is normalised by the mean/std of its mono
reference before inference and the stems are scaled back afterwards. Main env only (onnxruntime, demucs_onnx are
imported lazily).
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import numpy as np

__all__ = ["MODEL_IDS", "SAMPLE_RATE", "sources_of", "separate"]

SAMPLE_RATE = 44100
#: profile model name -> models.lock.json id
MODEL_IDS = {"htdemucs": "demucs_onnx_htdemucs", "htdemucs_6s": "demucs_onnx_htdemucs_6s"}


def sources_of(model: str) -> tuple[str, ...]:
    from demucs_onnx._hub import MODEL_REGISTRY

    return tuple(MODEL_REGISTRY[model].sources)


def separate(mix44: np.ndarray, model: str, onnx_path: Path | str, threads: int) -> dict[str, np.ndarray]:
    """mix44: float32 [2, n] at 44.1 kHz. Returns {stem: float32 [2, n]}."""
    import onnxruntime as ort
    from demucs_onnx.inference import _chunked_separate_single

    x = np.asarray(mix44, dtype=np.float32)
    if x.ndim != 2 or x.shape[0] != 2:
        raise ValueError(f"demucs expects [2, n], got {x.shape}")
    ref = x.mean(axis=0, dtype=np.float64)
    mean = float(ref.mean())
    std = float(ref.std())
    if not np.isfinite(std) or std < 1e-8:
        std = 1.0
    xin = ((x - mean) / std).astype(np.float32)
    so = ort.SessionOptions()
    so.intra_op_num_threads = max(1, int(threads))
    so.inter_op_num_threads = 1
    so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    sess = ort.InferenceSession(str(onnx_path), sess_options=so, providers=["CPUExecutionProvider"])
    out: Mapping[str, np.ndarray] = _chunked_separate_single(sess, sources_of(model), xin, progress=False)
    return {k: (v.astype(np.float64) * std + mean).astype(np.float32) for k, v in out.items()}
