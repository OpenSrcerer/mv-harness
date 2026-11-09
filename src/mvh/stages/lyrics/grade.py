"""The measured alignment gate G1-G8 (docs/spike/bench-words.md §5) and the song grade.

| # | check | pass |
|---|---|---|
| G1 | lyrics_match_score (ASR LCS F1 vs the supplied text) | >= 0.70 |
| G2 | alignment coverage = words with MMS score >= 0.10 | >= 0.75 (< 0.60 triggers stable-ts) |
| G3 | mean token score | >= 0.30 |
| G4 | hard misses (word score < 0.01) | <= 0.12 |
| G5 | lines within 1 s of source start + global offset (source with line timings only) | >= 0.85 |
| G6 | offset report: > 0.15 s applied, > 3 s flags version_mismatch | report |
| G7 | bias-removed word-start agreement with ASR words (250 ms); ignored when |bias| > 0.5 s | >= 0.55 |
| G8 | onset lift (word starts vs vocal flux onsets) | >= 1.15 (informational) |

Grade: A = G1, G2, G3, G4, G5, G7 pass with G1 >= 0.80 and G2 >= 0.85; B = all pass; C = 1-2 fail (G1 never
alone); D = G1 fails or G2 < 0.60 after the fallback. G1 needs ASR evidence (M5-D20): with fewer than 8 ASR
words it does not apply; with a mean ASR word probability < 0.70 its failure is an ordinary fail (grade C at best). Checks that do not apply (no source timings, no ASR) are
skipped, never failed. The per-line mean score is NOT a gate (AUC ~0.5).
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

__all__ = ["THRESHOLDS", "onset_lift", "asr_agreement", "gate", "line_grade"]

THRESHOLDS = {"G1": 0.70, "G2": 0.75, "G2_fallback": 0.60, "G3": 0.30, "G4": 0.12, "G5": 0.85, "G7": 0.55, "G8": 1.15,
              "offset_apply": 0.15, "version_mismatch": 3.0, "G1_min_asr_words": 8, "G1_min_asr_p": 0.70}


def vocal_onsets(wav16k: np.ndarray) -> np.ndarray:
    import librosa

    hop = 160
    S = librosa.feature.melspectrogram(y=np.asarray(wav16k, np.float32), sr=16000, n_fft=512, hop_length=hop, n_mels=40,
                                       fmin=80, fmax=7600)
    L = librosa.power_to_db(S + 1e-10)
    flux = np.maximum(0, np.diff(L, axis=1)).mean(0)
    flux = np.convolve(flux, np.ones(3) / 3, mode="same")
    if not len(flux):
        return np.zeros(0)
    thr = np.percentile(flux, 75)
    pk = [i for i in range(2, len(flux) - 2) if flux[i] >= thr and flux[i] == flux[i - 2:i + 3].max()]
    return (np.array(pk, dtype=np.float64) + 1) * hop / 16000.0


def onset_lift(onsets: np.ndarray, starts: Sequence[float]) -> float | None:
    """Hit rate of word starts within 60 ms of a vocal onset, divided by the rate of the same starts shifted
    by ±0.35 / ±0.5 s (chance)."""
    st = np.asarray(list(starts), dtype=np.float64)
    if len(st) < 5 or len(onsets) < 5:
        return None
    on = np.sort(np.asarray(onsets))

    def hit(x: np.ndarray) -> float:
        j = np.clip(np.searchsorted(on, x), 1, len(on) - 1)
        d = np.minimum(np.abs(on[j] - x), np.abs(on[j - 1] - x))
        return float(np.mean(d <= 0.06))

    base = float(np.mean([hit(st + sh) for sh in (0.5, -0.5, 0.35, -0.35)]))
    return round(hit(st) / max(base, 1e-6), 3)


def asr_agreement(pairs: Sequence[tuple[float, float]]) -> dict[str, Any]:
    """pairs = (aligned word start, ASR word start) for LCS-matched words."""
    if len(pairs) < 5:
        return {"n": len(pairs), "bias_s": None, "within_250ms": None, "within_250ms_raw": None}
    d = np.array([a - b for a, b in pairs])
    bias = float(np.median(d))
    return {"n": len(pairs), "bias_s": round(bias, 3), "within_250ms_raw": round(float(np.mean(np.abs(d) < 0.25)), 4),
            "within_250ms": round(float(np.mean(np.abs(d - bias) < 0.25)), 4)}


def gate(m: dict[str, Any]) -> dict[str, Any]:
    """m: G1 lyrics_match_score|None, G2 coverage, G3 mean_token_score, G4 hard_miss, G5 lines_within_1s|None,
    offset_s, G7 agreement dict|None, G8 lift|None, fallback_used bool, transcribed bool, asr_mean_p."""
    th = THRESHOLDS
    checks: dict[str, dict[str, Any]] = {}

    def chk(name: str, value, ok, thr, applies=True):
        checks[name] = {"value": value, "threshold": thr, "pass": bool(ok) if applies and value is not None else None}

    g1 = m.get("G1")
    n_asr, asr_p = m.get("asr_words"), m.get("asr_mean_p")
    # M5-D20: G1 needs ASR evidence. Too few ASR words: not applicable. An unconfident ASR (mean word p < 0.70):
    # a G1 failure counts as an ordinary fail, not the "wrong text" verdict (grade D).
    g1_applies = g1 is not None and not (n_asr is not None and n_asr < th["G1_min_asr_words"])
    chk("G1", g1, g1 is not None and g1 >= th["G1"], th["G1"], g1_applies)
    g1_weak = bool(g1_applies and asr_p is not None and asr_p < th["G1_min_asr_p"])
    if g1 is not None and not g1_applies:
        checks["G1"]["note"] = "asr_insufficient"
    elif g1_weak:
        checks["G1"]["note"] = "asr_unreliable"
    chk("G2", m.get("G2"), (m.get("G2") or 0) >= th["G2"], th["G2"])
    chk("G3", m.get("G3"), (m.get("G3") or 0) >= th["G3"], th["G3"])
    chk("G4", m.get("G4"), m.get("G4") is not None and m["G4"] <= th["G4"], th["G4"])
    g5 = m.get("G5")
    chk("G5", g5, g5 is not None and g5 >= th["G5"], th["G5"], g5 is not None)
    off = m.get("offset_s")
    checks["G6"] = {"value": off, "threshold": th["offset_apply"], "pass": None,
                    "applied": bool(off is not None and abs(off) > th["offset_apply"]),
                    "version_mismatch": bool(off is not None and abs(off) > th["version_mismatch"])}
    ag = m.get("G7") or {}
    g7 = ag.get("within_250ms")
    g7_applies = g7 is not None and ag.get("bias_s") is not None and abs(ag["bias_s"]) <= 0.5
    chk("G7", g7, g7 is not None and g7 >= th["G7"], th["G7"], g7_applies)
    g8 = m.get("G8")
    checks["G8"] = {"value": g8, "threshold": th["G8"], "pass": None, "informational": True,
                    "above": (g8 >= th["G8"]) if g8 is not None else None}
    graded = ["G1", "G2", "G3", "G4", "G5", "G7"]
    fails = [k for k in graded if checks[k]["pass"] is False]
    g2 = m.get("G2") or 0.0
    if m.get("transcribed"):
        p = m.get("asr_mean_p") or 0.0
        core = [k for k in ("G2", "G3", "G4") if checks[k]["pass"] is False]
        if g2 < th["G2_fallback"] or p < 0.6:
            grade = "D"
        elif not core and p >= 0.85:
            grade = "B"
        else:
            grade = "C"
    elif ("G1" in fails and not g1_weak) or g2 < th["G2_fallback"]:
        grade = "D"
    elif not fails:
        grade = "A" if (g1 is not None and g1 >= 0.80 and g2 >= 0.85) else "B"
    elif len(fails) <= 2:
        grade = "C"
    else:
        grade = "D"
    return {"checks": checks, "grade": grade, "fails": fails}


def line_grade(conf: float) -> str:
    return "A" if conf >= 0.8 else "B" if conf >= 0.6 else "C" if conf >= 0.4 else "D"
