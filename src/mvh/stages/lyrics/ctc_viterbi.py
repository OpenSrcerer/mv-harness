"""Vendored CTC forced alignment (Viterbi), numpy only: the fallback when torchaudio's compiled
``forced_align`` is unavailable or fails (PLAN §3.1 "Forced alignment"). Golden-tested against torchaudio in
tests/unit/lyrics/test_ctc_viterbi.py (same best-path score, same frame labels on random emissions).

Semantics follow ``torchaudio.functional.forced_align(log_probs[1, T, C], targets[1, L], blank)``: returns the
per-frame label path (blank or target token) and the per-frame log-probability of that label; the tie rules of
the torchaudio CPU kernel are reproduced (prefer staying, then a skip over a blank only when strictly better).
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

__all__ = ["forced_align", "merge_tokens", "TokenSpan"]

NEG = -1e30


def forced_align(log_probs: np.ndarray, targets: Sequence[int], blank: int = 0) -> tuple[np.ndarray, np.ndarray]:
    lp = np.asarray(log_probs, dtype=np.float64)
    if lp.ndim == 3:
        lp = lp[0]
    tg = np.asarray(list(targets), dtype=np.int64)
    T, _ = lp.shape
    L = len(tg)
    if L == 0:
        lab = np.full(T, blank, dtype=np.int64)
        return lab, lp[np.arange(T), lab].astype(np.float32)
    repeats = int(np.sum(tg[1:] == tg[:-1]))
    if T < L + repeats:
        raise ValueError(f"targets length {L} (+{repeats} repeats) is too long for {T} frames")
    S = 2 * L + 1
    ext = np.full(S, blank, dtype=np.int64)
    ext[1::2] = tg
    can_skip = np.zeros(S, dtype=bool)
    for s in range(3, S, 2):
        can_skip[s] = ext[s] != ext[s - 2]
    # feasibility windows (as the torchaudio kernel): states reachable at t and able to finish by T-1
    alpha = np.full(S, NEG)
    alpha[0] = lp[0, ext[0]]
    alpha[1] = lp[0, ext[1]]
    back = np.zeros((T, S), dtype=np.int8)
    # minimal number of frames needed to emit states >= s until the end (for pruning)
    steps = np.zeros(S, dtype=np.int64)   # fewest transitions from state s to a final state (S-2 or S-1)
    for s in range(S - 3, -1, -1):
        best_next = steps[s + 1]
        if s + 2 < S and can_skip[s + 2]:
            best_next = min(best_next, steps[s + 2])
        steps[s] = 1 + best_next
    need = steps + 1
    idx = np.arange(S)
    for t in range(1, T):
        x0 = alpha
        x1 = np.concatenate(([NEG], alpha[:-1]))
        x2 = np.concatenate(([NEG, NEG], alpha[:-2]))
        x2 = np.where(can_skip, x2, NEG)
        pick2 = (x2 > x1) & (x2 > x0)
        pick1 = (~pick2) & (x1 > x0) & (x1 > x2)
        best = np.where(pick2, x2, np.where(pick1, x1, x0))
        bp = np.where(pick2, 2, np.where(pick1, 1, 0)).astype(np.int8)
        new = best + lp[t, ext]
        reach = idx <= 2 * t + 1
        finish = need <= (T - t)
        new = np.where(reach & finish & (best > NEG / 2), new, NEG)
        back[t] = bp
        alpha = new
    if S == 1:
        s = 0
    else:
        s = S - 1 if alpha[S - 1] > alpha[S - 2] else S - 2
    if alpha[s] <= NEG / 2:
        raise ValueError("no valid CTC path")
    path = np.empty(T, dtype=np.int64)
    for t in range(T - 1, -1, -1):
        path[t] = ext[s]
        if t > 0:
            s -= int(back[t, s])
    return path, lp[np.arange(T), path].astype(np.float32)


class TokenSpan:
    __slots__ = ("token", "start", "end", "score")

    def __init__(self, token: int, start: int, end: int, score: float):
        self.token, self.start, self.end, self.score = token, start, end, score

    def __repr__(self) -> str:
        return f"TokenSpan({self.token}, {self.start}, {self.end}, {self.score:.3f})"


def merge_tokens(path: np.ndarray, frame_probs: np.ndarray, blank: int = 0) -> list[TokenSpan]:
    """Like torchaudio.functional.merge_tokens: consecutive equal non-blank labels form one span;
    score = mean frame probability of the span (pass probabilities, not log-probabilities)."""
    out: list[TokenSpan] = []
    T = len(path)
    t = 0
    while t < T:
        tok = int(path[t])
        if tok == blank:
            t += 1
            continue
        u = t
        while u + 1 < T and int(path[u + 1]) == tok:
            u += 1
        out.append(TokenSpan(tok, t, u + 1, float(np.mean(frame_probs[t:u + 1]))))
        t = u + 1
    return out
