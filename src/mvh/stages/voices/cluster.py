"""Clustering speaker embeddings into voices (SPIKE: agglomerative, cosine, average linkage; the eigengap of the
normalised affinity Laplacian is only a LOWER bound for k; the user's character count wins).

Estimate (no intent, no hints): k = 1 when the two-cluster split is not a real split (centroid cosine >=
``same_voice_cos`` or silhouette < ``min_silhouette``); otherwise the k in [eigengap, k_max] with the best
cosine silhouette, or the eigengap bound itself when there are fewer than ``small_n`` items.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

__all__ = ["agglo", "eigengap", "silhouette", "centroids", "estimate_k", "relabel_first_appearance"]


def relabel_first_appearance(lab: Sequence[int]) -> np.ndarray:
    order: dict[int, int] = {}
    for x in lab:
        order.setdefault(int(x), len(order))
    return np.array([order[int(x)] for x in lab], dtype=np.int64)


def agglo(E: np.ndarray, k: int) -> np.ndarray:
    n = len(E)
    if k <= 1 or n <= 1:
        return np.zeros(n, dtype=np.int64)
    k = min(k, n)
    from sklearn.cluster import AgglomerativeClustering

    lab = AgglomerativeClustering(n_clusters=k, metric="cosine", linkage="average").fit_predict(E)
    return relabel_first_appearance(lab)


def eigengap(E: np.ndarray, kmax: int = 8) -> tuple[int, list[float]]:
    S = np.clip(E @ E.T, 0, None)
    np.fill_diagonal(S, 0)
    d = S.sum(1)
    d[d <= 0] = 1e-9
    L = np.eye(len(S)) - (S / np.sqrt(np.outer(d, d)))
    ev = np.sort(np.linalg.eigvalsh(L))[: kmax + 1]
    if len(ev) < 3:
        return 2, [round(float(x), 4) for x in ev]
    gaps = np.diff(ev)
    return int(np.argmax(gaps[1:]) + 2), [round(float(x), 4) for x in ev]


def silhouette(E: np.ndarray, lab: np.ndarray) -> float | None:
    if len(set(lab.tolist())) < 2 or len(set(lab.tolist())) >= len(E):
        return None
    from sklearn.metrics import silhouette_score

    return float(silhouette_score(E, lab, metric="cosine"))


def centroids(E: np.ndarray, lab: np.ndarray, w: np.ndarray | None = None) -> np.ndarray:
    k = int(lab.max()) + 1 if len(lab) else 0
    w = np.ones(len(E)) if w is None else np.asarray(w, dtype=np.float64)
    C = []
    for c in range(k):
        m = lab == c
        v = (E[m] * w[m][:, None]).sum(0) if m.any() else np.zeros(E.shape[1])
        C.append(v / (np.linalg.norm(v) + 1e-9))
    return np.asarray(C, dtype=np.float64)


def merge_minor(E: np.ndarray, lab: np.ndarray, w: np.ndarray, *, singleton_cos: float = 0.25, scatter_cos: float = 0.4,
                scatter_share: float = 0.15) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Estimate mode only: a cluster is folded into its nearest neighbour when it is a single item that is not
    clearly foreign (cosine to the nearest other centroid >= ``singleton_cos``), or when its items never form
    two consecutive lines, hold < ``scatter_share`` of the items and resemble another voice (cos >=
    ``scatter_cos``): one singer whose timbre changes on a few lines (Jeremy, MEGAFAUNA), not a second voice.
    A strongly foreign single item (an announcer) survives. Items are in time order."""
    merged: list[dict[str, Any]] = []
    lab = lab.copy()
    while True:
        k = int(lab.max()) + 1 if len(lab) else 0
        if k < 2:
            break
        C = centroids(E, lab, w)
        cand = None
        for c in range(k):
            idx = np.flatnonzero(lab == c)
            if not len(idx):
                continue
            others = [o for o in range(k) if o != c and np.any(lab == o)]
            if not others:
                continue
            cos = [float(C[c] @ C[o]) for o in others]
            near, ncos = others[int(np.argmax(cos))], max(cos)
            run2 = bool(np.any(np.diff(idx) == 1))
            share = len(idx) / len(lab)
            if (len(idx) == 1 and ncos >= singleton_cos) or (not run2 and share < scatter_share and ncos >= scatter_cos):
                if cand is None or len(idx) < cand[1]:
                    cand = (c, len(idx), near, ncos)
        if cand is None:
            break
        c, n, near, ncos = cand
        merged.append({"items": int(n), "cos_to_nearest": round(ncos, 4)})
        lab[lab == c] = near
        lab = relabel_first_appearance(lab)
    return lab, merged


def estimate_k(E: np.ndarray, w: np.ndarray, *, k_max: int = 8, same_voice_cos: float = 0.6,
               min_silhouette: float = 0.08, small_n: int = 24, min_best_silhouette: float = 0.2) -> tuple[int, dict[str, Any]]:
    n = len(E)
    info: dict[str, Any] = {"n_items": n}
    if n < 4:
        info["reason"] = "fewer than 4 items"
        return 1, info
    lab2 = agglo(E, 2)
    C2 = centroids(E, lab2, w)
    cos12 = float(C2[0] @ C2[1])
    s2 = silhouette(E, lab2)
    info.update({"k2_centroid_cos": round(cos12, 4), "k2_silhouette": round(s2, 4) if s2 is not None else None})
    k_eg, eigs = eigengap(E, k_max)
    info.update({"eigengap_k": k_eg, "laplacian_eigs": eigs})
    if cos12 >= same_voice_cos or (s2 is not None and s2 < min_silhouette):
        info["reason"] = "two-cluster split not separated (same voice)"
        return 1, info
    sil = {}
    for k in range(max(2, k_eg), min(k_max, n - 1) + 1):
        lab = agglo(E, k)
        s = silhouette(E, lab)
        if s is not None:
            sil[k] = round(s, 4)
    if 2 not in sil and s2 is not None:
        sil[2] = round(s2, 4)
    info["silhouette"] = {str(k): v for k, v in sorted(sil.items())}
    if sil and max(sil.values()) < min_best_silhouette:
        # no cluster structure (a one-singer song whose timbre drifts): a split here flips on tiny input changes
        info["reason"] = f"best silhouette < {min_best_silhouette}: no cluster structure (one voice; raise the count via intent/overrides)"
        return 1, info
    if n < small_n:
        # M5-D21: with few items the silhouette keeps rising with k (each extra cluster isolates one odd line);
        # take the eigengap lower bound itself and let the user raise the count (intent.md / overrides)
        info["reason"] = f"few items (< {small_n}): eigengap lower bound"
        return int(max(2, min(k_eg, n - 1))), info
    cands = {k: v for k, v in sil.items() if k >= max(2, k_eg)} or sil
    k = max(sorted(cands), key=lambda kk: (cands[kk], -kk)) if cands else 2
    info["reason"] = "max silhouette at k >= eigengap lower bound"
    return int(k), info
