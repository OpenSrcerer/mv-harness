"""Transcription of lead_vocals (PLAN §5 lyrics 1.4, SPIKE):

* default: faster-whisper large-v3, int8 on CPU, ``cpu_threads = ctx.threads``, numpy array in (never a path),
  Silero VAD, ``word_timestamps``, ``condition_on_previous_text=False``, beam 5, temperature 0 only (sampling
  fallbacks are random and would break NF1 determinism);
* draft / flag: the ffmpeg ``whisper`` filter on Vulkan (ggml turbo q8_0, WITHOUT ``vad_model``: its Silero
  step drifts past EOF), relative model name and destination with ``cwd`` = the model folder.

``filter_segments`` is the hallucination filter (non-lyric tags, n-gram loops, low unique-word ratio,
compression/logprob, no-speech, zero-length words, low word probability, outside the vocal activity mask).
Segments are plain dicts: {start, end, text, avg_logprob, no_speech_prob, compression_ratio,
words: [{w, start, end, p}]}. Text never reaches a log.
"""

from __future__ import annotations

import collections
import difflib
import json
import os
import re
from pathlib import Path
from typing import Any, Sequence

import numpy as np

__all__ = ["transcribe", "filter_segments", "match_score", "ffmpeg_whisper", "asr_words", "load_model",
           "uncovered_regions", "transcribe_regions"]

# credit strings: never sung, dropped unconditionally
NONLYRIC = re.compile(r"^\s*[\(\[\*♪].*[\)\]\*♪]\s*$|subtitles?\s+(?:by|made)|amara\.org|"
                      r"thank(?:s|\s+you)\s+(?:so\s+much\s+)?for\s+(?:watching|listening|viewing)|"
                      r"\bsubscribe\b|♪|\b(?:transcribed|captioned|translated|subtitled)\s+by\b|otter\.ai|"
                      r"\bwww\.|https?:|\.(?:com|org|net)\b|\bcopyright\b[^.]{0,40}\b(?:19|20)\d{2}\b|©", re.I)
# generic phrases that are also ordinary lyrics: dropped only with a second signal (see _generic_suspect)
NONLYRIC_GENERIC = re.compile(r"please\s+(?:like|share)|see\s+you\s+(?:in\s+the\s+)?next|\bcopyright\b|"
                              r"^\W*(?:thank\s+you(?:\s+very\s+much)?|thanks|bye(?:[\s,.!-]+bye)*|goodbye)\W*$", re.I)
NONLYRIC_SHORT = re.compile(r"\b(music|applause|instrumental|silence|laughter|outro|intro)\b", re.I)


def load_model(model_dir: Path | str, threads: int):
    from faster_whisper import WhisperModel

    return WhisperModel(str(model_dir), device="cpu", compute_type="int8", cpu_threads=max(1, int(threads)), num_workers=1)


def _segments(segs_it, shift: float = 0.0) -> list[dict[str, Any]]:
    segs = []
    for s in segs_it:
        segs.append({"start": float(s.start) + shift, "end": float(s.end) + shift, "text": s.text,
                     "avg_logprob": float(s.avg_logprob), "no_speech_prob": float(s.no_speech_prob),
                     "compression_ratio": float(s.compression_ratio),
                     "words": [{"w": w.word, "start": float(w.start) + shift, "end": float(w.end) + shift,
                                "p": float(w.probability)} for w in (s.words or [])]})
    return segs


def transcribe(audio16k: np.ndarray, model_dir: Path | str, threads: int, *, language: str | None = None,
               vad: bool = True, beam_size: int = 5, model: Any = None) -> dict[str, Any]:
    m = model if model is not None else load_model(model_dir, threads)
    kw: dict[str, Any] = dict(word_timestamps=True, condition_on_previous_text=False, beam_size=beam_size,
                              temperature=0.0, vad_filter=vad)
    segs_it, info = m.transcribe(np.ascontiguousarray(audio16k, dtype=np.float32), language=language, **kw)
    segs = _segments(segs_it)
    return {"engine": "faster-whisper large-v3 int8", "language": info.language,
            "language_prob": float(info.language_probability), "segments": segs, "vad": vad}


def uncovered_regions(segs: Sequence[dict[str, Any]], active: np.ndarray, rate: float = 100.0, min_s: float = 6.0,
                      pad_s: float = 0.5, bridge_s: float = 1.0) -> list[tuple[float, float]]:
    """Spans of lead-vocal activity (>= ``min_s``) that no ASR segment covers (segments padded by ``pad_s``; active
    runs closer than ``bridge_s`` are joined). Silero VAD can reject long sung passages (Jeremy: nothing after
    172 s of 285 s of singing); these spans get a second, VAD-free pass (M5-D50)."""
    act = np.asarray(active, dtype=np.float32) > 0.5
    n = len(act)
    if not n:
        return []
    cov = np.zeros(n, dtype=bool)
    for s in segs:
        a, b = int(max(0.0, s["start"] - pad_s) * rate), int((s["end"] + pad_s) * rate) + 1
        cov[max(0, a):min(n, b)] = True
    cand = act & ~cov
    runs: list[list[int]] = []
    i = 0
    while i < n:
        if not cand[i]:
            i += 1
            continue
        j = i
        while j < n and cand[j]:
            j += 1
        if runs and i - runs[-1][1] <= bridge_s * rate and not cov[runs[-1][1]:i].any():
            runs[-1][1] = j
        else:
            runs.append([i, j])
        i = j
    return [(a / rate, b / rate) for a, b in runs if (b - a) >= min_s * rate]


def transcribe_regions(audio16k: np.ndarray, regions: Sequence[tuple[float, float]], model: Any, *,
                       language: str | None, beam_size: int = 5, context_s: float = 1.0,
                       sr: int = 16000) -> list[dict[str, Any]]:
    """VAD-free transcription of each region (with ``context_s`` audio on both sides), times shifted back to the
    song clock; segments whose middle lies outside the region are discarded (the context belongs to neighbours)."""
    out: list[dict[str, Any]] = []
    x = np.ascontiguousarray(audio16k, dtype=np.float32)
    kw: dict[str, Any] = dict(word_timestamps=True, condition_on_previous_text=False, beam_size=beam_size,
                              temperature=0.0, vad_filter=False)
    for a, b in regions:
        t0 = max(0.0, a - context_s)
        t1 = min(len(x) / sr, b + context_s)
        segs_it, _info = model.transcribe(x[int(t0 * sr):int(t1 * sr)], language=language, **kw)
        for s in _segments(segs_it, shift=t0):
            mid = 0.5 * (s["start"] + s["end"])
            if a <= mid <= b:
                out.append(s)
    return out


def _generic_suspect(s: dict[str, Any], active: np.ndarray | None, rate: float) -> bool:
    """A segment with an ordinary-lyric-looking outro phrase is a hallucination only with a second signal: weak
    confidence (alone, or a high no-speech probability together with a mediocre logprob), little vocal activity,
    or a place at the very start / end of the audio. A confident segment in the middle of active vocals is sung
    text. no_speech_prob alone is no signal: faster-whisper computes it once per 30 s window and singing raises it
    (0.4-0.8 on confident sung segments of the real songs, M5-D47)."""
    if s["avg_logprob"] < -1.0 or (s["no_speech_prob"] > 0.6 and s["avg_logprob"] < -0.7):
        return True
    ps = [x.get("p") for x in s["words"] if x.get("p") is not None]
    if ps and float(np.mean(ps)) < 0.6:
        return True
    if active is not None and len(active):
        a, b = int(s["start"] * rate), max(int(s["start"] * rate) + 1, int(s["end"] * rate))
        seg = active[max(0, a):min(len(active), b)]
        if len(seg) and float(np.mean(seg)) < 0.5:
            return True
        dur = len(active) / rate
        if s["start"] < 1.0 or s["end"] > dur - 1.0:
            return True
    return False


def filter_segments(segs: Sequence[dict[str, Any]], active: np.ndarray | None = None, rate: float = 100.0,
                    min_word_p: float = 0.0) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Hallucination filter. ``active``: optional 0/1 lead-vocal activity at ``rate`` Hz; a segment whose
    span is < 20 % active is dropped (whisper hears words in reverb tails and instrumentals)."""
    kept, dropped = [], collections.Counter()
    for s in segs:
        w = [x["w"].strip().lower() for x in s["words"] if x["w"].strip()]
        if not w:
            dropped["empty"] += 1
            continue
        if (NONLYRIC.search(s["text"]) or (len(w) <= 3 and NONLYRIC_SHORT.search(s["text"]))
                or (NONLYRIC_GENERIC.search(s["text"]) and _generic_suspect(s, active, rate))):
            dropped["non_lyric_tag"] += 1
            continue
        grams = collections.Counter(tuple(w[i:i + 3]) for i in range(len(w) - 2))
        if grams and grams.most_common(1)[0][1] >= 3 and len(w) >= 6:
            dropped["ngram_loop"] += 1
            continue
        if len(w) >= 8 and len(set(w)) / len(w) < 0.3:
            dropped["low_unique_ratio"] += 1
            continue
        if s["compression_ratio"] > 2.4 and s["avg_logprob"] < -1.0:
            dropped["compress_logprob"] += 1
            continue
        if s["no_speech_prob"] > 0.8 and s["avg_logprob"] < -1.0:
            dropped["no_speech"] += 1
            continue
        if sum(1 for x in s["words"] if x["end"] - x["start"] < 0.02) / len(w) > 0.5:
            dropped["zero_dur_words"] += 1
            continue
        ps = [x.get("p") for x in s["words"] if x.get("p") is not None]
        if ps and float(np.mean(ps)) < max(min_word_p, 0.0):
            dropped["low_word_prob"] += 1
            continue
        if active is not None and len(active):
            a, b = int(s["start"] * rate), max(int(s["start"] * rate) + 1, int(s["end"] * rate))
            seg = active[max(0, a):min(len(active), b)]
            if len(seg) and float(np.mean(seg)) < 0.2:
                dropped["inactive_vocals"] += 1
                continue
        kept.append(s)
    return kept, dict(sorted(dropped.items()))


def asr_words(segs: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten to normalised comparison words [{n, start, end, p}] (a whisper token may hold 2 words)."""
    from .text import norm_words

    out = []
    for s in segs:
        for w in s["words"]:
            for x in norm_words(w["w"]):
                out.append({"n": x, "start": w["start"], "end": w["end"], "p": w.get("p")})
    return out


def canonicalise(aw: Sequence[dict[str, Any]], ref: Sequence[tuple[float, str]], *, window_s: float = 3.0,
                 min_ratio: float = 80.0, min_len: int = 4) -> tuple[list[str], int]:
    """ASR comparison words with near-misses snapped to the text (M5-D53): an ASR word of >= ``min_len`` letters
    that is not in the text within ``window_s`` but is a close spelling of a text word there (rapidfuzz ratio >=
    ``min_ratio``: 'spoken'/'spoke', 'colour'/'color', a sung vowel heard differently) counts as that word.
    Returns (words, number snapped). Wrong-text controls (jeremy ASR vs newton text and back) do not move."""
    from rapidfuzz import fuzz

    times = np.asarray([t for t, _ in ref], dtype=np.float64)
    order = np.argsort(times, kind="stable")
    ts = times[order]
    out: list[str] = []
    n_snap = 0
    for w in aw:
        n = w["n"]
        if len(n) < min_len or not len(ts):
            out.append(n)
            continue
        a, b = np.searchsorted(ts, w["start"] - window_s), np.searchsorted(ts, w["start"] + window_s, side="right")
        cands = sorted({ref[int(order[k])][1] for k in range(a, b)})
        if n in cands:
            out.append(n)
            continue
        best_sc, best = 0.0, None
        for c in cands:
            if len(c) >= min_len:
                sc = fuzz.ratio(n, c)
                if sc > best_sc:
                    best_sc, best = sc, c
        if best is not None and best_sc >= min_ratio:
            out.append(best)
            n_snap += 1
        else:
            out.append(n)
    return out, n_snap


def match_score(asr: Sequence[str], ref: Sequence[str]) -> dict[str, Any]:
    """LCS precision / recall / F1 of ASR words against the supplied text (lyrics_match_score = F1)."""
    if not asr or not ref:
        return {"lcs_matched": 0, "precision": 0.0, "recall": 0.0, "f1": 0.0}
    sm = difflib.SequenceMatcher(None, list(asr), list(ref), autojunk=False)
    m = sum(b.size for b in sm.get_matching_blocks())
    p, r = m / len(asr), m / len(ref)
    return {"lcs_matched": m, "precision": round(p, 4), "recall": round(r, 4),
            "f1": round(2 * p * r / max(1e-9, p + r), 4)}


def lcs_pairs(a: Sequence[str], b: Sequence[str]) -> list[tuple[int, int]]:
    sm = difflib.SequenceMatcher(None, list(a), list(b), autojunk=False)
    return [(blk.a + k, blk.b + k) for blk in sm.get_matching_blocks() for k in range(blk.size)]


def ffmpeg_whisper(wav: Path, ggml_model: Path, scratch: Path, *, language: str | None = "en",
                   use_gpu: bool = True, timeout: float = 1800.0) -> dict[str, Any]:
    """The ffmpeg 9 ``whisper`` filter (draft path). No VAD. Returns the same segment shape (p = None)."""
    from mvh.io.ffmpeg import run_ffmpeg

    mdir = ggml_model.parent
    dest_name = f"mvh-whisper-{os.getpid()}.json"
    dest = mdir / dest_name
    opts = [f"model={ggml_model.name}", f"language={language or 'auto'}", "queue=20", f"use_gpu={1 if use_gpu else 0}",
            "max_len=1", "format=json", f"destination={dest_name}"]
    try:
        r = run_ffmpeg(["-i", str(wav), "-af", "whisper=" + ":".join(opts), "-f", "null", "-"], cwd=str(mdir),
                       timeout=timeout, loglevel="error")
        if r.returncode != 0 or not dest.is_file():
            raise RuntimeError(f"ffmpeg whisper failed (exit {r.returncode})")
        raw = dest.read_text(encoding="utf-8", errors="replace")
    finally:
        try:
            dest.unlink()
        except OSError:
            pass
    items = []
    for ln in raw.splitlines():
        ln = ln.strip().rstrip(",")
        if not ln or ln in ("[", "]"):
            continue
        try:
            items.append(json.loads(ln))
        except ValueError:
            continue
    segs = []
    last = -1.0
    for it in items:
        t0, t1 = float(it.get("start", 0)) / 1000.0, float(it.get("end", 0)) / 1000.0
        txt = str(it.get("text") or "").strip()
        if not txt or t1 - t0 > 2.0 or t0 < last - 0.05:    # long items and non-monotonic starts are unreliable
            continue
        last = t0
        segs.append({"start": t0, "end": t1, "text": txt, "avg_logprob": -0.5, "no_speech_prob": 0.0,
                     "compression_ratio": 1.0, "words": [{"w": txt, "start": t0, "end": t1, "p": None}]})
    # regroup single words into pseudo-segments split on gaps > 1 s (for the filter and expansion)
    grouped: list[dict[str, Any]] = []
    for s in segs:
        if grouped and s["start"] - grouped[-1]["end"] <= 1.0:
            g = grouped[-1]
            g["end"] = s["end"]
            g["text"] += " " + s["text"]
            g["words"] += s["words"]
        else:
            grouped.append(dict(s, words=list(s["words"])))
    return {"engine": f"ffmpeg whisper {ggml_model.name}", "language": language, "language_prob": None,
            "segments": grouped, "vad": False}
