# ruff: noqa: E501  (long literals and docstrings)
"""Mood analysis core (numpy on top of the ONNX heads): 1 Hz valence/arousal/tag curves and section summaries.

Scale: the emoMusic and DEAM heads output valence and arousal on a 1..9 scale; (x - 1) / 8 maps them to 0..1 (0.5 is the
scale midpoint = neutral). Arousal is fairly reliable (Pearson ~0.77-0.82 on the heads' own test sets); valence is not (the
two heads routinely disagree by 0.1-0.2 on real music), so valence confidence is capped at 0.5 and falls with the head
disagreement. Mood is a hint: the user's meaning wins.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from . import frontend as F

AROUSAL_BASE_CONF = 0.80
VALENCE_BASE_CONF = 0.45
VALENCE_CONF_CAP = 0.50
SILENCE_DB = -70.0


def scale01(x: np.ndarray) -> np.ndarray:
    return np.clip((np.asarray(x, np.float64) - 1.0) / 8.0, 0.0, 1.0)


def _pick(m: Mapping[str, Any], name: str):
    return next(v for k, v in m.items() if str(k).replace("\\", "/").endswith(name))


class Heads:
    """The five Essentia ONNX models (CPU, explicit local paths)."""

    def __init__(self, musicnn_files: Mapping[str, Any], effnet_files: Mapping[str, Any], threads: int = 3):
        import json

        import onnxruntime as ort

        so = ort.SessionOptions()
        so.intra_op_num_threads = max(1, int(threads))
        so.inter_op_num_threads = 1

        def sess(p):
            return ort.InferenceSession(str(p), so, providers=["CPUExecutionProvider"])

        self.musicnn = sess(_pick(musicnn_files, "msd-musicnn-1.onnx"))
        self.emo = sess(_pick(musicnn_files, "emomusic-msd-musicnn-2.onnx"))
        self.deam = sess(_pick(musicnn_files, "deam-msd-musicnn-2.onnx"))
        self.effnet = sess(_pick(effnet_files, "discogs-effnet-bsdynamic-1.onnx"))
        self.mtg = sess(_pick(effnet_files, "mtg_jamendo_moodtheme-discogs-effnet-1.onnx"))
        with open(_pick(effnet_files, "mtg_jamendo_moodtheme-discogs-effnet-1.json"), encoding="utf-8") as fh:
            self.classes = list(json.load(fh)["classes"])
        self.emo_input = self.emo.get_inputs()[0].name
        self.deam_input = self.deam.get_inputs()[0].name
        self.mtg_input = self.mtg.get_inputs()[0].name

    def run(self, y16: np.ndarray, batch: int = 32) -> "Raw":
        x = F.log_mel(y16)
        P, s1 = F.make_patches(x, F.MUSICNN_PATCH, F.MUSICNN_HOP)
        emb = np.concatenate([self.musicnn.run(["embeddings"], {"melspectrogram": P[i:i + batch]})[0] for i in range(0, len(P), batch)])
        emo = np.concatenate([self.emo.run(None, {self.emo_input: emb[i:i + 256]})[0] for i in range(0, len(emb), 256)])
        deam = np.concatenate([self.deam.run(None, {self.deam_input: emb[i:i + 256]})[0] for i in range(0, len(emb), 256)])
        P2, s2 = F.make_patches(x, F.EFFNET_PATCH, F.EFFNET_HOP)
        emb2 = np.concatenate([self.effnet.run(["embeddings"], {"melspectrogram": P2[i:i + batch]})[0] for i in range(0, len(P2), batch)])
        tags = np.concatenate([self.mtg.run(None, {self.mtg_input: emb2[i:i + 256]})[0] for i in range(0, len(emb2), 256)])
        return Raw(emo.astype(np.float32), deam.astype(np.float32), F.patch_centres_s(s1, F.MUSICNN_PATCH),
                   tags.astype(np.float32), F.patch_centres_s(s2, F.EFFNET_PATCH), self.classes)


@dataclass
class Raw:
    emo: np.ndarray            # [N, 2] (valence, arousal) 1..9
    deam: np.ndarray           # [N, 2]
    t1: np.ndarray             # [N] patch centres (s)
    tags: np.ndarray           # [M, 56] probabilities
    t2: np.ndarray             # [M]
    classes: list[str]


@dataclass
class Curves:
    valence: np.ndarray
    arousal: np.ndarray
    val_emo: np.ndarray
    val_deam: np.ndarray
    aro_emo: np.ndarray
    aro_deam: np.ndarray
    tags: np.ndarray           # [56, n]
    silent: np.ndarray         # [n] bool
    classes: list[str]
    rate_hz: float = 1.0


def silence_mask(y16: np.ndarray, n: int, sr: int = F.SR) -> np.ndarray:
    """Seconds (centred at i) whose RMS is below SILENCE_DB."""
    y = np.asarray(y16, np.float64)
    out = np.zeros(n, bool)
    thr = 10 ** (SILENCE_DB / 20)
    for i in range(n):
        a, b = max(0, int((i - 0.5) * sr)), min(len(y), int((i + 0.5) * sr))
        out[i] = True if b <= a else float(np.sqrt(np.mean(y[a:b] ** 2))) < thr
    return out


def to_curves(raw: Raw, n: int, silent: np.ndarray) -> Curves:
    """Interpolate the patch predictions to 1 Hz (sample i centred at i s). Digital-silence seconds read neutral (0.5 / 0)."""
    tq = np.arange(n, dtype=np.float64)
    ve, ae = scale01(raw.emo[:, 0]), scale01(raw.emo[:, 1])
    vd, ad = scale01(raw.deam[:, 0]), scale01(raw.deam[:, 1])
    cv_e, ca_e, cv_d, ca_d = (np.interp(tq, raw.t1, v) for v in (ve, ae, vd, ad))
    tags = np.stack([np.interp(tq, raw.t2, raw.tags[:, j]) for j in range(raw.tags.shape[1])])
    val, aro = 0.5 * (cv_e + cv_d), 0.5 * (ca_e + ca_d)
    for arr in (val, aro, cv_e, cv_d, ca_e, ca_d):
        arr[silent] = 0.5
    tags[:, silent] = 0.0
    f32 = np.float32
    return Curves(val.astype(f32), aro.astype(f32), cv_e.astype(f32), cv_d.astype(f32), ca_e.astype(f32), ca_d.astype(f32),
                  np.clip(tags, 0, 1).astype(f32), silent, raw.classes)


def _conf(base: float, cap: float, head_gap: float, within_std: float, k_gap: float, k_std: float) -> float:
    return float(np.clip(base - k_gap * head_gap - k_std * within_std, 0.05, cap))


def summarise(c: Curves, t0: float, d: float, top_tags: int = 3, min_tag_p: float = 0.08) -> dict[str, Any]:
    """Mood of [t0, t0 + d): mean values, per-head values, confidences, top tags. Samples whose centre lies inside the
    span are averaged; a span with none (under one second) uses the nearest sample."""
    n = c.valence.shape[0]
    a = max(int(np.ceil(t0 - 1e-9)), 0)
    b = min(int(np.ceil(t0 + d - 1e-9)), n)
    if b <= a:
        a = min(max(int(round(t0 + d / 2)), 0), n - 1)
        b = a + 1
    sl = slice(a, b)
    live = ~c.silent[sl]
    if not live.any():
        return {"valence": 0.5, "arousal": 0.5, "valence_conf": 0.0, "arousal_conf": 0.0, "tags": [], "tag_p": [],
                "valence_emomusic": 0.5, "valence_deam": 0.5, "arousal_emomusic": 0.5, "arousal_deam": 0.5, "silent": True}

    def m(x):
        return float(np.mean(x[sl][live]))

    def s(x):
        return float(np.std(x[sl][live])) if live.sum() > 1 else 0.0

    gap_v = float(np.mean(np.abs(c.val_emo[sl] - c.val_deam[sl])[live]))
    gap_a = float(np.mean(np.abs(c.aro_emo[sl] - c.aro_deam[sl])[live]))
    short = 1.0 if live.sum() >= 3 else 0.8          # a 1-2 s section is a single noisy patch
    tp = c.tags[:, sl][:, live].mean(axis=1)
    order = [int(i) for i in np.argsort(-tp, kind="stable")]
    keep = [i for i in order[:top_tags] if tp[i] >= min_tag_p] or order[:1]
    return {
        "valence": m(c.valence), "arousal": m(c.arousal),
        "valence_conf": _conf(VALENCE_BASE_CONF, VALENCE_CONF_CAP, gap_v, s(c.valence), 1.5, 0.5) * short,
        "arousal_conf": _conf(AROUSAL_BASE_CONF, 0.9, gap_a, s(c.arousal), 2.5, 1.0) * short,
        "tags": [c.classes[i] for i in keep], "tag_p": [round(float(tp[i]), 4) for i in keep],
        "valence_emomusic": m(c.val_emo), "valence_deam": m(c.val_deam),
        "arousal_emomusic": m(c.aro_emo), "arousal_deam": m(c.aro_deam), "silent": False,
    }


def global_summary(c: Curves, n_tags: int = 8) -> dict[str, Any]:
    return summarise(c, 0.0, float(c.valence.shape[0]), top_tags=n_tags, min_tag_p=0.0)
