"""Key estimation: an ensemble of independent evidence sources, a sticky Viterbi over windows for key regions, and a
confidence derived from agreement. The S-KEY export is softmax(softmax(.)); the real probability is recovered and gates/weights its vote.

Evidence per key (24 indices, see theory.key_index), each turned into a z-scored vector so that they can be summed:
    skey       log-probability of the S-KEY ONNX model on 22.05 kHz mono peak-normalised audio
    ks         Krumhansl-Schmuckler correlation of the harmonic chroma sum
    temperley  Temperley profile correlation
    albrecht   Albrecht-Shanahan profile correlation
    chords     duration-weighted diatonic fit of the chord timeline (tonic chord bonus, first/last chord bonus)
    bass       bass pitch-class histogram (tonic and fifth)
    phrase     the chord a phrase (every 4th bar) starts on: loops start on their tonic
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np

from . import theory as T
from .chroma import ChromaFrames, aggregate

# weights of the evidence sources in the ensemble (z-score units). S-KEY and the chord model are the independent
# opinions (a learned key model and a learned chord model); the three profile methods share one chroma so together
# they count about one vote.
WEIGHTS = {"skey": 1.0, "ks": 0.45, "temperley": 0.35, "albrecht": 0.3, "chords": 1.0, "bass": 0.4, "phrase": 0.7}
# evidence that is not an independent opinion on the key (it only anchors the tonic): excluded from agreement/credit
ANCHORS = ("bass", "phrase")
Z_CAP = 3.0
RELATIVE_TIE_GAP = 3.0
BETA = 1.6            # emission sharpness in the Viterbi (per z-score unit)
SWITCH_COST = 12.0    # nats to leave the global key for an unrelated one
RELATED_COST = 9.0    # ... for a parallel / fifth neighbour (a relative key is the same pitch set: never a key change)


def zscore(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, np.float64)
    s = v.std()
    if s < 1e-12:
        return np.zeros_like(v)
    return (v - v.mean()) / s


def skey_log(probs: np.ndarray, keymap: Sequence[str]) -> np.ndarray:
    """S-KEY probabilities in keyMap order -> score in our index order. The score is the probability itself: it is what
    the old exported log-softmax(softmax) was linear in, so z-scoring it keeps the ensemble behaviour (a log of the
    now-sharp p would let a runner-up at 1e-4 dominate)."""
    out = np.full(24, 1.0 / 24)
    for i, name in enumerate(keymap):
        pc, mode = T.parse_key_label(name)
        out[T.key_index(pc, mode)] = float(probs[i])
    return out


def recover_probs(q: np.ndarray) -> np.ndarray:
    """The pinned ONNX export emits softmax(softmax(logits)); invert the outer softmax: p = log q - mean(log q) + 1/n."""
    q = np.maximum(np.asarray(q, np.float64).reshape(-1), 1e-12)
    lq = np.log(q)
    p = np.clip(lq - lq.mean() + 1.0 / q.size, 0.0, 1.0)
    s = p.sum()
    return p / s if s > 0 else np.full(q.size, 1.0 / q.size)


SKEY_MIN_PMAX = 0.2       # windows where S-KEY's own top probability is below this are guesses: no vote
SKEY_FULL_PMAX = 0.6      # ... and the vote reaches full weight at this top probability


def skey_weight(probs: np.ndarray | None) -> float:
    if probs is None:
        return 0.0
    m = float(np.max(probs))
    if m < SKEY_MIN_PMAX:
        return 0.0
    return float(np.clip((m - SKEY_MIN_PMAX) / (SKEY_FULL_PMAX - SKEY_MIN_PMAX), 0.25, 1.0))


class SKey:
    """S-KEY ONNX (22.05 kHz mono, peak-normalised, [1, samples] -> probs[24], a double softmax that recover_probs undoes)."""

    def __init__(self, onnx_path, config_path, threads: int = 3):
        import json

        import onnxruntime as ort

        so = ort.SessionOptions()
        so.intra_op_num_threads = max(1, int(threads))
        so.inter_op_num_threads = 1
        self.sess = ort.InferenceSession(str(onnx_path), so, providers=["CPUExecutionProvider"])
        cfg = json.loads(open(config_path, encoding="utf-8").read())
        self.keymap = list(cfg["keyMap"])

    def log_scores(self, y22: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """-> (log-scores in index order, raw probabilities in keyMap order)"""
        seg = np.asarray(y22, np.float32)
        seg = seg / (float(np.max(np.abs(seg))) + 1e-9)
        q = np.asarray(self.sess.run(None, {"audio": seg[None, :]})[0]).reshape(-1).astype(np.float64)
        p = recover_probs(q)
        return skey_log(p, self.keymap), p


# ------------------------------------------------------------------------------------------ evidence builders
def chroma_peak(chroma_sum: np.ndarray) -> float | None:
    """Peak/mean of a long-term chroma (12,): ~1 for a flat distribution, 2.5-3.5 for a tonal one."""
    c = np.asarray(chroma_sum, np.float64).reshape(-1)
    m = float(c.mean()) if c.size else 0.0
    return float(c.max() / m) if m > 1e-12 else None


def profile_evidence(chroma_sum: np.ndarray) -> dict[str, np.ndarray]:
    return {n: T.profile_scores(chroma_sum, maj, mnr) for n, (maj, mnr) in T.PROFILES.items()}


def chord_evidence(chords: Sequence[Mapping[str, Any]], t0: float, t1: float, first_last_bonus: bool = True) -> np.ndarray:
    """Duration-weighted diatonic fit of the chords inside [t0, t1)."""
    sc = np.zeros(24)
    total = 0.0
    seq: list[tuple[int, str, float]] = []
    for c in chords:
        a, b = max(float(c["t"]), t0), min(float(c["t"]) + float(c["d"]), t1)
        if b <= a or c.get("root_pc") is None:
            continue
        w = (b - a) * float(c.get("conf", 1.0)) ** 0.5
        total += w
        seq.append((int(c["root_pc"]), str(c["quality"]), w))
        for k in range(24):
            sc[k] += w * T.chord_key_fit(int(c["root_pc"]), str(c["quality"]), k)
    if total <= 0:
        return np.zeros(24)
    sc /= total
    if first_last_bonus and seq:
        # a progression that starts and ends on the same chord names its tonic (vi-IV-I-V loops read as A minor)
        for chord in (seq[0], seq[-1]):
            r, q, _ = chord
            base = "min" if q in ("min", "min7", "min9") else "maj"
            sc[T.key_index(r, "minor" if base == "min" else "major")] += 0.06
    return sc


def bass_evidence(cf: ChromaFrames, t0: float, t1: float) -> np.ndarray:
    h = aggregate(cf, t0, t1, which="bass")
    s = h.sum()
    if s <= 0:
        return np.zeros(24)
    h = h / s
    out = np.zeros(24)
    for k in range(24):
        tonic, mode = T.key_from_index(k)
        third = (tonic + (4 if mode == "major" else 3)) % 12
        out[k] = h[tonic] + 0.5 * h[(tonic + 7) % 12] + 0.25 * h[third]
    return out


def phrase_evidence(chords: Sequence[Mapping[str, Any]], bars: Sequence[Mapping[str, Any]], t0: float, t1: float, phrase_bars: int = 4) -> np.ndarray:
    """Tonic anchoring: chord at the start of every ``phrase_bars``-th bar inside [t0, t1)."""
    out = np.zeros(24)
    n = 0
    real = [b for b in bars if int(b.get("bar", 0)) >= 1 and b.get("in_pulse", True)]
    for b in real:
        if (int(b["bar"]) - 1) % phrase_bars:
            continue
        t = float(b["t"]) + 0.05
        if not (t0 <= t < t1):
            continue
        ch = next((c for c in chords if float(c["t"]) <= t < float(c["t"]) + float(c["d"])), None)
        if ch is None or ch.get("root_pc") is None:
            continue
        n += 1
        r, q = int(ch["root_pc"]), str(ch["quality"])
        fam = "min" if q in ("min", "min7", "min9", "dim", "hdim7", "dim7") else "maj"
        for k in range(24):
            tonic, mode = T.key_from_index(k)
            if r == tonic:
                out[k] += 1.0 if (fam == "min") == (mode == "minor") else 0.4
            elif r == (tonic + 7) % 12:
                out[k] += 0.25
    return out / n if n else out


@dataclass
class Evidence:
    """Per-method score vectors (index order) for one time range."""

    skey: np.ndarray | None = None
    ks: np.ndarray | None = None
    temperley: np.ndarray | None = None
    albrecht: np.ndarray | None = None
    chords: np.ndarray | None = None
    bass: np.ndarray | None = None
    phrase: np.ndarray | None = None
    skey_probs: np.ndarray | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def methods(self) -> dict[str, np.ndarray]:
        out = {n: getattr(self, n) for n in WEIGHTS if getattr(self, n) is not None and np.ptp(getattr(self, n)) > 1e-12}
        if "skey" in out and skey_weight(self.skey_probs) <= 0.0:
            del out["skey"]          # S-KEY is guessing here (low top probability)
        return out


def ensemble(ev: Evidence, weights: Mapping[str, float] = WEIGHTS) -> np.ndarray:
    """Weighted sum of z-scored evidence (24,)."""
    tot = np.zeros(24)
    for n, v in ev.methods().items():
        w = weights.get(n, 0.0) * (skey_weight(ev.skey_probs) if n == "skey" else 1.0)
        tot += w * np.clip(zscore(v), -Z_CAP, Z_CAP)
    # relative-key tie-break: a loop that starts its phrases on a chord names its tonic (vi-IV-I-V reads as vi), so when
    # the two leaders are relative keys and close, the one the phrases start on wins by a hair (the ambiguity is flagged)
    ph = ev.phrase
    if ph is not None and np.ptp(ph) > 1e-12:
        a, b = (int(i) for i in np.argsort(-tot)[:2])
        if T.key_relation(a, b) == "relative" and tot[a] - tot[b] < RELATIVE_TIE_GAP and ph[b] > ph[a] + 0.25:
            tot[b] = tot[a] + 0.05
    return tot


def posterior(score: np.ndarray, beta: float = 1.2) -> np.ndarray:
    e = np.exp(beta * (score - score.max()))
    return e / e.sum()


def top_keys(score: np.ndarray, n: int = 3) -> list[tuple[int, float]]:
    p = posterior(score)
    idx = np.argsort(-score)[:n]
    return [(int(i), float(p[i])) for i in idx]


# ------------------------------------------------------------------------------------------ agreement / confidence
_REL_CREDIT = {"exact": 1.0, "relative": 0.55, "parallel": 0.3, "fifth": 0.3, "other": 0.0}


def agreement_label(winners: Mapping[str, int], ref: int) -> str:
    """Overall agreement of the methods' top-1 keys with the ensemble winner: agree | relative | parallel | fifth | disagree
    (the weakest relation present; any method on an unrelated key means disagree)."""
    rels = {T.key_relation(w, ref) for w in winners.values()} - {"exact"}
    if not rels:
        return "agree"
    if "other" in rels:
        return "disagree"
    for r in ("fifth", "parallel", "relative"):
        if r in rels:
            return r
    return "disagree"


NO_TONAL_SHARE = 0.9        # lv-chordia no-chord share at/above which the span has no tonal evidence
TONAL_PEAK = 0.55           # mean top profile correlation (ks/temperley/albrecht) that proves a peaky, tonal chroma without chords
# R5-M1: profile correlations z-score the chroma, so they cannot see a FLAT distribution. The long-term chroma's
# peak/mean ratio can: band noise ~2.4, random 12-tone lines 1.4-1.7, tonal a-cappella stems 2.6-3.2
CHROMA_PEAK_MIN = 2.2
SKEY_CONFIRM_PMAX = 0.35    # S-KEY confirms a chord-less key only with at least this top probability
CHROMA_ONLY_CAP = 0.8       # a key from chroma alone (no chords) is never reported above this
CHROMA_ONLY_UNCONFIRMED_CAP = 0.5   # ... nor above this when S-KEY votes a neighbour key or abstains (R5-M2)
CHORD_SOURCE_FLOOR = 0.25   # chords/phrase count as an independent source only above this chord-covered share


def no_chord_share_in(chords: Sequence[Mapping[str, Any]], t0: float, t1: float) -> float:
    """Share of [t0, t1) not covered by a real chord (items with root_pc None are the N segments)."""
    span = max(t1 - t0, 1e-9)
    covered = sum(max(0.0, min(float(c["t"]) + float(c["d"]), t1) - max(float(c["t"]), t0)) for c in chords if c.get("root_pc") is not None)
    return float(np.clip(1.0 - covered / span, 0.0, 1.0))


def global_confidence(winner: int, evidence: Evidence, window_top: Sequence[int], score: np.ndarray, no_chord_share: float = 0.0) -> tuple[float, dict[str, Any]]:
    """Confidence from (a) the fraction of windows whose ensemble winner equals the global one, (b) the credit each
    method's own top-1 earns against the ensemble winner (exact 1, relative .55, parallel/fifth .3), (c) the ensemble
    margin to the runner-up. S-KEY's recovered probability only gates/weights its vote."""
    meth = {n: v for n, v in evidence.methods().items() if n not in ANCHORS}
    winners = {n: int(np.argmax(v)) for n, v in meth.items()}
    credit = np.mean([_REL_CREDIT[T.key_relation(w, winner)] for w in winners.values()]) if winners else 0.0
    if len(window_top):
        wa = float(np.mean([1.0 if w == winner else (0.5 if T.key_relation(w, winner) == "relative" else 0.0) for w in window_top]))
    else:
        wa = credit
    srt = np.sort(score)[::-1]
    margin = float(np.clip((srt[0] - srt[1]) / 2.5, 0.0, 1.0)) if srt.size > 1 else 0.0
    conf = 0.40 * wa + 0.35 * credit + 0.25 * margin
    flags: list[str] = []
    # ks/temperley/albrecht correlate the same chroma: together they are ONE source of evidence
    sources = {("profiles" if n in ("ks", "temperley", "albrecht") else n) for n in winners}
    prof = [float(np.max(evidence.methods()[n])) for n in ("ks", "temperley", "albrecht") if n in meth]
    prof_peak = float(np.mean(prof)) if prof else 0.0
    prof_agree = len(prof) == 3 and all(T.key_relation(winners[n], winner) in ("exact", "relative") for n in ("ks", "temperley", "albrecht") if n in winners)
    sk_rel = T.key_relation(winners["skey"], winner) if "skey" in winners else None
    sk_p = float(np.max(evidence.skey_probs)) if evidence.skey_probs is not None else 0.0
    skey_ok = sk_rel == "exact" and sk_p >= SKEY_CONFIRM_PMAX
    cpk = evidence.extra.get("chroma_peak") if evidence.extra else None
    peaked = cpk is None or float(cpk) >= CHROMA_PEAK_MIN
    # a-cappella / solo-voice / choral material has no CHORDS but a clearly peaked, unanimous chroma: that is a key.
    # Band noise, drones, risers and atonal lines give a flat chroma distribution or split profiles, so they stay gated
    chroma_key = no_chord_share >= NO_TONAL_SHARE and prof_peak >= TONAL_PEAK and prof_agree and peaked
    tonal_without_chords = chroma_key and skey_ok
    unconfirmed = chroma_key and not skey_ok and sk_rel in (None, "exact", "relative", "fifth")
    if no_chord_share >= NO_TONAL_SHARE and not (tonal_without_chords or unconfirmed):
        # the dedicated chord model hears no harmony here (noise, drone, riser, ambient pad) and the chroma is not peaked:
        # whatever S-KEY or the profiles hallucinate on it is not a key
        conf = min(conf, 0.3)
        flags += ["key:no_tonal_evidence", "key:low_confidence"]
    elif tonal_without_chords:
        sources -= {"chords", "phrase"}
        sources.add("skey")
        conf = min(conf, CHROMA_ONLY_CAP)
        flags.append("key:chroma_only")
    elif unconfirmed:
        # a peaked, unanimous chroma with S-KEY on a neighbour key (its usual error) or abstaining: a key, at low confidence
        sources = {"profiles", "chroma_peak"}
        conf = min(conf, CHROMA_ONLY_UNCONFIRMED_CAP)
        flags += ["key:chroma_only", "key:low_confidence"]   # (the fifth / relative ambiguity flag is added by core)
    elif (1.0 - no_chord_share) < CHORD_SOURCE_FLOOR:
        sources -= {"chords", "phrase"}
    if len(sources) < 2 and "key:no_tonal_evidence" not in flags:
        # one source alone agrees with itself trivially: no independent evidence, no confident key
        conf = min(conf, 0.25)
        flags += ["key:no_tonal_evidence", "key:low_confidence"]
    # the learned key model and the learned chord model are the two independent opinions: when they are not the same
    # key (nor relative) the answer is at best a coin flip between two candidates
    sk, ch = winners.get("skey"), winners.get("chords")
    if sk is not None and ch is not None and T.key_relation(sk, ch) not in ("exact", "relative"):
        conf = min(conf, 0.5)
        flags.append("key:models_disagree")
    if sk is not None and T.key_relation(sk, winner) not in ("exact",):
        flags.append("key:skey_differs")
    return float(np.clip(conf, 0.0, 0.97)), {"window_agreement": wa, "method_credit": float(credit), "margin": margin, "flags": flags,
                                             "winners": {n: int(w) for n, w in winners.items()}}


# ------------------------------------------------------------------------------------------ windows and regions
def window_grid(duration: float, win_s: float, hop_s: float) -> list[tuple[float, float]]:
    if duration <= win_s:
        return [(0.0, duration)]
    out = []
    t = 0.0
    while t + win_s <= duration + 1e-9:
        out.append((t, t + win_s))
        t += hop_s
    if out[-1][1] < duration - 1.0:
        out.append((duration - win_s, duration))
    return out


def viterbi_regions(emissions: np.ndarray, global_key: int, beta: float = BETA, switch_cost: float = SWITCH_COST,
                    related_cost: float = RELATED_COST, home_bonus: float = 1.0) -> np.ndarray:
    """Sticky Viterbi over windows. emissions [W, 24] (ensemble scores); transitions cost 0 to stay, ``related_cost``
    to a relative/parallel/fifth neighbour, ``switch_cost`` otherwise; the global key gets a small home bonus."""
    w = emissions.shape[0]
    cost = np.zeros((24, 24))
    for a in range(24):
        for b in range(24):
            if a != b:
                cost[a, b] = related_cost if T.key_relation(a, b) in ("parallel", "fifth") else switch_cost
    em = beta * emissions
    em[:, global_key] += home_bonus
    delta = np.zeros((w, 24))
    back = np.zeros((w, 24), int)
    delta[0] = em[0]
    for t in range(1, w):
        cand = delta[t - 1][:, None] - cost
        back[t] = np.argmax(cand, axis=0)
        delta[t] = cand[back[t], np.arange(24)] + em[t]
    path = np.zeros(w, int)
    path[-1] = int(np.argmax(delta[-1]))
    for t in range(w - 1, 0, -1):
        path[t - 1] = back[t, path[t]]
    return path


def regions_from_path(path: np.ndarray, windows: Sequence[tuple[float, float]], duration: float,
                      min_len_s: float = 20.0) -> list[tuple[float, float, int]]:
    """Window-level key path -> [(t0, t1, key)] with boundaries at the window hop midpoints; regions shorter than
    ``min_len_s`` are absorbed by their longer neighbour."""
    if not len(path):
        return []
    centres = [(a + b) / 2 for a, b in windows]
    segs: list[list[Any]] = []
    for i, k in enumerate(path):
        if segs and segs[-1][2] == int(k):
            continue
        t0 = 0.0 if i == 0 else (centres[i - 1] + centres[i]) / 2
        if segs:
            segs[-1][1] = t0
        segs.append([t0, duration, int(k)])
    changed = True
    while changed and len(segs) > 1:
        changed = False
        for i, s in enumerate(segs):
            if s[1] - s[0] < min_len_s:
                # absorb into the longer neighbour
                left = segs[i - 1] if i > 0 else None
                right = segs[i + 1] if i + 1 < len(segs) else None
                tgt = max((x for x in (left, right) if x is not None), key=lambda x: x[1] - x[0])
                if tgt is left:
                    left[1] = s[1]
                else:
                    right[0] = s[0]
                segs.pop(i)
                changed = True
                break
        # merge equal neighbours
        j = 0
        while j + 1 < len(segs):
            if segs[j][2] == segs[j + 1][2]:
                segs[j][1] = segs[j + 1][1]
                segs.pop(j + 1)
                changed = True
            else:
                j += 1
    return [(float(a), float(b), int(k)) for a, b, k in segs]
