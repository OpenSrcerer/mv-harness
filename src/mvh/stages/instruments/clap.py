"""CLAP (Xenova/larger_clap_music_and_speech, quantized ONNX) for RELATIVE curves only (owner M3b).

docs/SPIKE.md: CLAP has low contrast (cosines about .2-.45) and its top prompt is often wrong, so it is never used as a
top-1 label. The stage uses it for (a) the split of ``synth`` presence into sub-types and (b) user-supplied terms, both as
curves measured against neutral prompts. Recipe (docs/spike/main.md §2): ``ClapFeatureExtractor`` at 48 kHz ->
``input_features [B,1,1001,64]`` -> audio model -> ``audio_embeds [B,512]``; tokenizer + text model (``input_ids``) ->
``text_embeds``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np

SR = 48000
CLAP_MODEL_ID = "clap_larger_music_speech_onnx"


class Clap:
    def __init__(self, files: dict[str, Path], threads: int = 3):
        import onnxruntime as ort
        from transformers import AutoTokenizer, ClapFeatureExtractor

        audio = next(p for k, p in files.items() if k.endswith("audio_model_quantized.onnx"))
        text = next(p for k, p in files.items() if k.endswith("text_model_quantized.onnx"))
        d = audio.parent.parent
        self.fe = ClapFeatureExtractor.from_pretrained(str(d))
        self.tok = AutoTokenizer.from_pretrained(str(d))
        so = ort.SessionOptions()
        so.intra_op_num_threads = int(threads)
        so.inter_op_num_threads = 1
        self.sa = ort.InferenceSession(str(audio), so, providers=["CPUExecutionProvider"])
        self.st = ort.InferenceSession(str(text), so, providers=["CPUExecutionProvider"])

    def text(self, prompts: Sequence[str]) -> np.ndarray:
        # The pinned text model has no attention_mask: encode each prompt alone (batch of 1, no padding) so an
        # embedding never depends on the other prompts in the call.
        rows = []
        for p in prompts:
            enc = self.tok([p], padding=False, return_tensors="np")
            rows.append(self.st.run(None, {"input_ids": enc["input_ids"].astype(np.int64)})[0][0])
        e = np.stack(rows)
        return (e / np.linalg.norm(e, axis=1, keepdims=True)).astype(np.float32)

    def audio_grid(self, y48: np.ndarray, n_frames: int, win_s: float = 10.0, step_s: float = 2.0) -> np.ndarray:
        """Unit audio embeddings on a 1 Hz grid [n_frames, 512]: windows of win_s centred every step_s seconds,
        linearly interpolated to every second (zero-padded outside the song)."""
        y = np.asarray(y48, np.float32).reshape(-1)
        w = int(win_s * SR)
        half = w // 2
        pad = np.concatenate([np.zeros(half, np.float32), y, np.zeros(w, np.float32)])
        centres = np.arange(0, max(n_frames, 1) + step_s, step_s)
        E = []
        for c in centres:
            s = int(round(c * SR))
            seg = pad[s: s + w]
            if float(np.abs(seg).max(initial=0.0)) < 1e-4:
                E.append(None)
                continue
            f = self.fe(seg, sampling_rate=SR, return_tensors="np")["input_features"].astype(np.float32)
            a = self.sa.run(None, {"input_features": f})[0][0]
            E.append(a / max(float(np.linalg.norm(a)), 1e-9))
        dim = next((e.size for e in E if e is not None), 512)
        M = np.stack([e if e is not None else np.zeros(dim, np.float32) for e in E]).astype(np.float32)
        ts = np.arange(n_frames, dtype=np.float64)
        out = np.stack([np.interp(ts, centres, M[:, j]) for j in range(dim)], axis=1)
        nrm = np.linalg.norm(out, axis=1, keepdims=True)
        return np.where(nrm > 1e-6, out / np.maximum(nrm, 1e-9), 0.0).astype(np.float32)
