# ruff: noqa: E501  (long numeric tables / docstrings)
"""CED-base (AudioSet, 527 labels) ONNX tagger on 16 kHz mono arrays (owner M3b; also used by the notes stage).

Recipe (docs/SPIKE.md, docs/spike/bench-music.md §5): input ``waveform [B, samples]`` float32 at 16 kHz; the ONNX output is
ALREADY a probability (the export ends in a sigmoid): never apply another sigmoid. Labels come from the model's
``config.json`` ``id2label``.

Frames follow the contract's 1 Hz grid: frame i is centred at i s and its window is [i - win/2, i + win/2) (zero-padded
outside the song), so ``probs[i]`` is the tag probability "around second i".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import numpy as np

SR = 16000
CED_MODEL_ID = "ced_base_onnx"
_SILENT_PEAK = 10 ** (-70 / 20)  # windows whose peak is below -70 dBFS are not run (probabilities 0)


class CedTagger:
    """One ONNX session; ``frames(y)`` tags a whole signal on the 1 Hz grid."""

    def __init__(self, model_dir_files: dict[str, Path], threads: int = 3, batch: int = 16):
        import onnxruntime as ort

        onnx = next(p for k, p in model_dir_files.items() if k.endswith("model.onnx"))
        cfg = next(p for k, p in model_dir_files.items() if k.endswith("/config.json") or k == "config.json")
        with open(cfg, encoding="utf-8") as fh:
            c = json.load(fh)
        self.labels: list[str] = [c["id2label"][str(i)] for i in range(len(c["id2label"]))]
        self.index = {lab: i for i, lab in enumerate(self.labels)}
        so = ort.SessionOptions()
        so.intra_op_num_threads = int(threads)
        so.inter_op_num_threads = 1
        self.sess = ort.InferenceSession(str(onnx), so, providers=["CPUExecutionProvider"])
        self.input = self.sess.get_inputs()[0].name
        self.batch = int(batch)

    def idx(self, labels: Sequence[str]) -> list[int]:
        missing = [lab for lab in labels if lab not in self.index]
        if missing:
            raise KeyError(f"CED has no labels {missing}")
        return [self.index[lab] for lab in labels]

    def frames(self, y: np.ndarray, n_frames: int, win_s: float = 4.0, hop_s: float = 1.0) -> np.ndarray:
        """Probabilities [n_frames, 527] (float32) for windows centred at i * hop_s."""
        y = np.asarray(y, dtype=np.float32).reshape(-1)
        w = int(round(win_s * SR))
        half = w // 2
        pad = np.concatenate([np.zeros(half, np.float32), y, np.zeros(w, np.float32)])
        out = np.zeros((n_frames, len(self.labels)), np.float32)
        todo: list[int] = []
        for i in range(n_frames):
            s = int(round(i * hop_s * SR))  # = (centre - half) + half in the padded signal
            seg = pad[s: s + w]
            if seg.size and float(np.abs(seg).max()) >= _SILENT_PEAK:
                todo.append(i)
        for k in range(0, len(todo), self.batch):
            ids = todo[k: k + self.batch]
            x = np.stack([pad[int(round(i * hop_s * SR)): int(round(i * hop_s * SR)) + w] for i in ids])
            p = self.sess.run(None, {self.input: x})[0]
            out[ids] = np.clip(p, 0.0, 1.0).astype(np.float32)  # already probabilities (no sigmoid)
        return out


def n_frames_1hz(n_samples: int, sr: int) -> int:
    """Contract frame count for a 1 Hz file: ceil(n_samples * 1 / sr)."""
    return -(-int(n_samples) // int(sr))
