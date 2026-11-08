# ruff: noqa: E501
"""Speaker embeddings (SPIKE: ECAPA primary, WeSpeaker ONNX fallback; identical partitions at k = 3 and 4).

* ECAPA-TDNN (SpeechBrain 1.1, VoxCeleb, 192-d): ``EncoderClassifier.from_hparams(source=<dir>, savedir=<scratch>,
  local_strategy=LocalStrategy.COPY, overrides={"pretrained_path": <dir>})`` (no symlink privilege here), arrays in;
* WeSpeaker ResNet34-LM (ONNX, 256-d): Kaldi fbank (80 mel, 25/10 ms, hamming, dither 0) on x * 32768, mean
  subtraction, ``feats [1, T, 80]`` -> ``embs``.

Long items are embedded as the mean of L2-normalised 3 s chunks (hop 1.5 s), so a 20 s rap verse does not
dilute into one blurred vector; the result is L2-normalised.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

import numpy as np

__all__ = ["Embedder", "load_embedder"]

SR = 16000


class Embedder:
    def __init__(self, name: str, fn: Callable[[np.ndarray], np.ndarray], dim: int):
        self.name, self._fn, self.dim = name, fn, dim

    def one(self, x: np.ndarray, chunk_s: float = 3.0, hop_s: float = 1.5) -> np.ndarray:
        x = np.asarray(x, dtype=np.float32)
        if len(x) < int(0.4 * SR):
            x = np.pad(x, (0, int(0.4 * SR) - len(x)))
        n, c, h = len(x), int(chunk_s * SR), int(hop_s * SR)
        if n <= int(1.5 * c):
            parts = [x]
        else:
            parts = [x[s:s + c] for s in range(0, n - c + 1, h)]
            if (n - c) % h:
                parts.append(x[n - c:])
        vs = []
        for p in parts:
            v = np.asarray(self._fn(p), dtype=np.float64).reshape(-1)
            vs.append(v / (np.linalg.norm(v) + 1e-9))
        m = np.mean(vs, axis=0)
        return (m / (np.linalg.norm(m) + 1e-9)).astype(np.float32)

    def many(self, xs: Sequence[np.ndarray]) -> np.ndarray:
        if not xs:
            return np.zeros((0, self.dim), np.float32)
        return np.stack([self.one(x) for x in xs])


def _ecapa(model_dir: Path, savedir: Path, threads: int) -> Embedder:
    import torch
    from speechbrain.inference.speaker import EncoderClassifier
    from speechbrain.utils.fetching import LocalStrategy

    torch.set_num_threads(max(1, threads))
    clf = EncoderClassifier.from_hparams(source=str(model_dir), savedir=str(savedir), run_opts={"device": "cpu"},
                                         local_strategy=LocalStrategy.COPY, overrides={"pretrained_path": str(model_dir)})
    clf.eval()

    def fn(x: np.ndarray) -> np.ndarray:
        with torch.inference_mode():
            return clf.encode_batch(torch.from_numpy(np.ascontiguousarray(x))[None]).squeeze().numpy()

    return Embedder("speechbrain-ecapa-voxceleb", fn, 192)


def _wespeaker(onnx_file: Path, threads: int) -> Embedder:
    import onnxruntime as ort
    import torch
    import torchaudio

    so = ort.SessionOptions()
    so.intra_op_num_threads = max(1, threads)
    so.inter_op_num_threads = 1
    sess = ort.InferenceSession(str(onnx_file), so, providers=["CPUExecutionProvider"])

    def fn(x: np.ndarray) -> np.ndarray:
        f = torchaudio.compliance.kaldi.fbank(torch.from_numpy(np.ascontiguousarray(x))[None, :] * 32768, num_mel_bins=80,
                                              frame_length=25, frame_shift=10, dither=0.0, sample_frequency=SR,
                                              window_type="hamming", use_energy=False)
        f = f - f.mean(0, keepdim=True)
        return sess.run(None, {"feats": f[None].numpy().astype(np.float32)})[0][0]

    return Embedder("wespeaker-resnet34-lm-onnx", fn, 256)


def load_embedder(ctx, prefer: str = "ecapa") -> tuple[Embedder, list[str], list[str]]:
    """(embedder, models used, fallbacks). ECAPA first; WeSpeaker when ECAPA cannot load."""
    fallbacks: list[str] = []
    order = ["ecapa", "wespeaker"] if prefer == "ecapa" else ["wespeaker", "ecapa"]
    last: Exception | None = None
    for name in order:
        try:
            if name == "ecapa":
                h = ctx.model("speechbrain_ecapa_voxceleb")
                d = next(p for k, p in h.files.items() if k.endswith("hyperparams.yaml")).parent
                e = _ecapa(d, Path(ctx.scratch) / "ecapa", ctx.threads)
                return e, [h.id], fallbacks
            h = ctx.model("wespeaker_resnet34_lm_onnx")
            f = next(p for k, p in h.files.items() if k.endswith(".onnx"))
            e = _wespeaker(f, ctx.threads)
            if name != order[0]:
                fallbacks.append("voices:wespeaker")
            return e, [h.id], fallbacks
        except Exception as ex:  # noqa: BLE001  (try the other model)
            last = ex
            continue
    raise RuntimeError(f"no speaker-embedding model could be loaded ({type(last).__name__})")
