# ruff: noqa: E501
"""MMS_FA forced alignment of lyric words to lead_vocals (PLAN §5 lyrics 2, SPIKE recipe).

* emissions: the MMS_FA model (torchaudio pipeline, local ``model.pt``, ``with_star=False``) over 16 kHz mono in
  30 s windows with >= 6 s of context on each side (320-sample aligned, so 20 ms frames stitch exactly), per-window
  zero-mean unit-variance, log-softmax;
* alignment: ``torchaudio.functional.forced_align`` (compiled op) per line group (consecutive lines spanning
  <= 30 s, split on gaps > 12 s), window = [first start - ctx, last end + ctx] + the global offset; the vendored
  ``ctc_viterbi`` when the op is missing or fails;
* group windows end at the next group's first expected start (no spill into the next group);
* line-window constraint: a line whose start lands more than ``slack`` from its expected start is re-aligned
  alone in [expected - slack, next expected + slack] clipped to the neighbouring lines' placements, and kept if
  its mean token score improves;
* order repair: adjacent (non-backing) lines whose words interleave are re-aligned together, which is monotone
  by construction.

Words are lists of MMS token ids; a word with no tokens (punctuation, an unknown script) is skipped here and
interpolated by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np

__all__ = ["FR", "SR", "MmsAligner", "align_window", "align_groups", "groups"]

FR = 0.02       # seconds per emission frame
SR = 16000
SEAM_PRE_S = 3.0   # frames this long before a window seam are re-evaluated with long context (A2)
SEAM_POST_S = 0.5
SEAM_CTX_S = 8.0
SEAM_MARGIN_S = 0.15  # how far a group window may reach into the neighbouring group


class MmsAligner:
    def __init__(self, model_file: Path | str, threads: int = 3):
        import torch
        import torchaudio

        torch.set_num_threads(max(1, int(threads)))
        bundle = torchaudio.pipelines.MMS_FA
        self.model = bundle.get_model(with_star=False, dl_kwargs={"model_dir": str(Path(model_file).parent)}).eval()
        self.dictionary = bundle.get_dict(star=None)

    def _chunk(self, x: np.ndarray, a0: int, a1: int, k0: int, k1: int) -> np.ndarray:
        """Frames [k0, k1) (in samples, absolute) of the model run on x[a0:a1]."""
        import torch

        seg = x[a0:a1]
        if len(seg) < 800:
            seg = np.pad(seg, (0, 800 - len(seg)))
        t = torch.from_numpy(seg).float()
        t = (t - t.mean()) / (t.std() + 1e-7)
        with torch.inference_mode():
            em, _ = self.model(t[None])
            lp = torch.log_softmax(em, -1)[0].numpy()
        f_lo = (k0 - a0) // 320
        f_hi = f_lo + (k1 - k0) // 320
        chunk = lp[f_lo:f_hi]
        if len(chunk) < f_hi - f_lo:   # model frames run short at the very end: repeat the last frame
            chunk = np.concatenate([chunk, np.repeat(lp[-1:], f_hi - f_lo - len(chunk), axis=0)])
        return chunk

    def emissions(self, wav: np.ndarray, win_s: float = 30.0, ctx_s: float = 2.0) -> np.ndarray:
        """Log-probabilities per 20 ms frame: the SPIKE recipe (``win_s`` windows with ``ctx_s`` of context each side,
        central frames kept; the grade gate G1-G8 is calibrated on it) with the frames just before each seam, which
        have little context after them (R-WORDS A2), replaced by frames of a window centred on the seam
        (``SEAM_CTX_S`` of context on both sides). Everywhere else the frames equal the plain recipe."""
        x = np.asarray(wav, dtype=np.float32)
        n = len(x)
        hop, ctx = int(win_s * SR), int(ctx_s * SR)
        hop -= hop % 320
        ctx -= ctx % 320
        parts = []
        n_frames = n // 320
        for s in range(0, n, hop):
            a0, a1 = max(0, s - ctx), min(n, s + hop + ctx)
            parts.append(self._chunk(x, a0, a1, s, s + min(hop, n - s)))
        out = np.concatenate(parts).astype(np.float32) if parts else np.zeros((0, len(self.dictionary)), np.float32)
        out = out[:n_frames] if len(out) > n_frames else out
        pre, post, sctx = int(SEAM_PRE_S * SR), int(SEAM_POST_S * SR), int(SEAM_CTX_S * SR)
        pre -= pre % 320
        post -= post % 320
        sctx -= sctx % 320
        for s in range(hop, n, hop):
            k0, k1 = max(0, s - pre), min(n, s + post)
            k1 -= (k1 - k0) % 320
            if k1 - k0 < 320:
                continue
            a0, a1 = max(0, k0 - sctx), min(n, k1 + sctx)
            fl = k0 // 320
            seam = self._chunk(x, a0, a1, k0, k1)
            out[fl:fl + len(seam)] = seam[:max(0, len(out) - fl)]
        return out


_TA_OK: bool | None = None


def _torch_align(seg: np.ndarray, flat: list[int]):
    import torch
    import torchaudio.functional as F

    ali, sc = F.forced_align(torch.from_numpy(seg).float()[None], torch.tensor([flat], dtype=torch.int32), blank=0)
    return ali[0].numpy().astype(np.int64), sc[0].numpy().astype(np.float32)


def align_window(logp: np.ndarray, f0: int, f1: int, toks: Sequence[Sequence[int]], *, engine: list[str] | None = None) -> list[dict[str, Any]]:
    """Align words (token lists, none empty) inside frames [f0, f1). Returns per word {start, end, score,
    tok_scores}; raises ValueError when the window is too short."""
    global _TA_OK
    from . import ctc_viterbi as V

    f0, f1 = max(0, int(f0)), min(len(logp), int(f1))
    flat = [t for w in toks for t in w]
    if not flat:
        return []
    if len(flat) > f1 - f0:
        raise ValueError("fewer frames than tokens")
    seg = logp[f0:f1]
    path = scores = None
    if _TA_OK is None:
        try:
            import torchaudio._extension as ext

            _TA_OK = bool(getattr(ext, "_IS_ALIGN_AVAILABLE", True))
        except Exception:  # noqa: BLE001
            _TA_OK = False
    if _TA_OK:
        try:
            path, scores = _torch_align(seg, flat)
            if engine is not None:
                engine.append("torchaudio")
        except Exception:  # noqa: BLE001  (fall through to the vendored Viterbi)
            path = None
    if path is None:
        path, scores = V.forced_align(seg, flat, blank=0)
        if engine is not None:
            engine.append("vendored")
    spans = V.merge_tokens(path, np.exp(scores), blank=0)
    if len(spans) != len(flat):
        raise ValueError(f"span/token mismatch {len(spans)}/{len(flat)}")
    out, k = [], 0
    for w in toks:
        sp = spans[k:k + len(w)]
        k += len(w)
        out.append({"start": (f0 + sp[0].start) * FR, "end": (f0 + sp[-1].end) * FR,
                    "score": float(np.mean([s.score for s in sp])), "tok_scores": [float(s.score) for s in sp]})
    return out


def groups(starts: Sequence[float], ends: Sequence[float], max_span: float = 30.0, max_gap: float = 12.0) -> list[list[int]]:
    g: list[list[int]] = []
    cur: list[int] = []
    for i in range(len(starts)):
        if cur and (ends[i] - starts[cur[0]] + 4 > max_span or starts[i] - ends[cur[-1]] > max_gap):
            g.append(cur)
            cur = []
        cur.append(i)
    if cur:
        g.append(cur)
    return g


@dataclass
class AlignNotes:
    groups: int = 0
    group_fail: int = 0
    group_split: int = 0
    tokens_per_frame_max: float = 0.0
    line_realigned: int = 0
    line_realign_accepted: int = 0
    crossings: int = 0
    crossings_fixed: int = 0
    crossings_left: int = 0
    lines_off_gt2s: int = 0
    engine: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        eng = sorted(set(self.engine))
        return {"groups": self.groups, "group_fail": self.group_fail, "group_split": self.group_split,
                "tokens_per_frame_max": round(self.tokens_per_frame_max, 3), "line_realigned": self.line_realigned,
                "line_realign_accepted": self.line_realign_accepted, "crossings": self.crossings,
                "crossings_fixed": self.crossings_fixed, "crossings_left": self.crossings_left,
                "lines_off_gt2s": self.lines_off_gt2s, "engine": eng}


def align_groups(logp: np.ndarray, starts: Sequence[float], ends: Sequence[float], line_toks: Sequence[Sequence[Sequence[int]]],
                 *, offset: float = 0.0, ctx: float = 2.0, slack: float = 2.5, max_span: float = 30.0,
                 max_gap: float = 12.0, backing: Sequence[bool] | None = None
                 ) -> tuple[list[list[dict[str, Any] | None]], AlignNotes]:
    """Align every line's (non-empty) words. ``starts``/``ends``: expected line times (source clock);
    ``offset`` is added to them. ``backing``: lines allowed to overlap their neighbours (excluded from the order
    checks). Returns per line a list (one entry per word of line_toks[i]) and notes."""
    T = len(logp)
    n_lines = len(line_toks)
    notes = AlignNotes()
    res: list[list[dict[str, Any] | None]] = [[None] * len(w) for w in line_toks]
    back = [bool(b) for b in backing] if backing is not None else [False] * n_lines

    def run_group(g: list[int], t0: float, t1: float) -> bool:
        idx = [(li, wi) for li in g for wi, tk in enumerate(line_toks[li]) if tk]
        if not idx:
            return True
        f0, f1 = max(0, int(t0 / FR)), min(T, int(np.ceil(t1 / FR)))
        toks = [line_toks[li][wi] for li, wi in idx]
        notes.tokens_per_frame_max = max(notes.tokens_per_frame_max, sum(map(len, toks)) / max(1, f1 - f0))
        try:
            al = align_window(logp, f0, f1, toks, engine=notes.engine)
        except ValueError:
            return False
        for (li, wi), a in zip(idx, al):
            res[li][wi] = a
        return True

    gl = groups(list(starts), list(ends), max_span, max_gap)
    for gi, g in enumerate(gl):
        notes.groups += 1
        t0 = starts[g[0]] + offset - ctx
        t1 = ends[g[-1]] + offset + ctx
        # a group never reaches past the neighbouring group's first expected start (R-WORDS A)
        if gi > 0:
            t0 = max(t0, ends[gl[gi - 1][-1]] + offset - SEAM_MARGIN_S)
        if gi + 1 < len(gl):
            t1 = min(t1, starts[gl[gi + 1][0]] + offset + SEAM_MARGIN_S)
        t1 = max(t1, t0 + 0.2)
        if not run_group(g, t0, t1):
            notes.group_fail += 1
            # too dense for the window: widen, then fall back to single lines with wide windows
            if not run_group(g, t0 - 2 * ctx, t1 + 2 * ctx):
                notes.group_split += 1
                for li in g:
                    run_group([li], starts[li] + offset - 3 * ctx, ends[li] + offset + 3 * ctx)

    def span(li: int) -> tuple[float, float] | None:
        ws = [r for r in res[li] if r is not None]
        return (ws[0]["start"], max(r["end"] for r in ws)) if ws else None

    def neighbours(first: int, last: int) -> tuple[float, float]:
        """Time bounds from the nearest placed non-backing line before ``first`` / after ``last``."""
        lo, hi = 0.0, T * FR
        for k in range(first - 1, -1, -1):
            sp = None if back[k] else span(k)
            if sp:
                lo = sp[1]
                break
        for k in range(last + 1, n_lines):
            sp = None if back[k] else span(k)
            if sp:
                hi = sp[0]
                break
        return lo, hi

    def realign(lines_: list[int], lo: float, hi: float) -> list[list[dict[str, Any]]] | None:
        idx = [[wi for wi, tk in enumerate(line_toks[li]) if tk] for li in lines_]
        toks = [line_toks[li][wi] for li, ws in zip(lines_, idx) for wi in ws]
        f0, f1 = int(max(0.0, lo) / FR), min(T, int(np.ceil(hi / FR)))
        if not toks or f1 - f0 < len(toks):
            return None
        try:
            al = align_window(logp, f0, f1, toks, engine=notes.engine)
        except ValueError:
            return None
        out, k = [], 0
        for ws in idx:
            out.append(al[k:k + len(ws)])
            k += len(ws)
        return out

    # per-line window constraint, clipped to the neighbouring lines so a repeat cannot snap onto their audio
    for li, toks in enumerate(line_toks):
        ws = [r for r in res[li] if r is not None]
        exp = starts[li] + offset
        dev = abs(ws[0]["start"] - exp) if ws else 99.0
        if dev <= slack or not any(toks):
            continue
        notes.line_realigned += 1
        lo, hi = max(0.0, exp - slack), ends[li] + offset + slack
        if not back[li]:
            nlo, nhi = neighbours(li, li)
            lo, hi = max(lo, nlo), min(hi, nhi)
        al = realign([li], lo, hi)
        if al is None:
            continue
        old = float(np.mean([r["score"] for r in ws])) if ws else -1.0
        if float(np.mean([a["score"] for a in al[0]])) > old:
            notes.line_realign_accepted += 1
            for wi, a in zip([wi for wi, tk in enumerate(toks) if tk], al[0]):
                res[li][wi] = a

    # order repair: words of adjacent lines must not interleave
    order = [li for li in range(n_lines) if not back[li]]
    for _ in range(2):
        changed = False
        for a_i, b_i in zip(order, order[1:]):
            sa, sb = span(a_i), span(b_i)
            if not sa or not sb or sa[1] <= sb[0] + 0.1:
                continue
            notes.crossings += 1
            lo, _h = neighbours(a_i, a_i)
            _l, hi = neighbours(b_i, b_i)
            lo = max(lo, starts[a_i] + offset - slack)
            hi = min(hi, ends[b_i] + offset + slack)
            al = realign([a_i, b_i], lo, hi)
            old = [r["score"] for li in (a_i, b_i) for r in res[li] if r is not None]
            if al is not None and float(np.mean([x["score"] for ln in al for x in ln])) >= 0.6 * float(np.mean(old)):
                for li, ln in zip((a_i, b_i), al):
                    for wi, a in zip([wi for wi, tk in enumerate(line_toks[li]) if tk], ln):
                        res[li][wi] = a
                notes.crossings_fixed += 1
                changed = True
        if not changed:
            break
    for a_i, b_i in zip(order, order[1:]):
        sa, sb = span(a_i), span(b_i)
        if sa and sb and sa[1] > sb[0] + 0.1:
            notes.crossings_left += 1
    for li in range(n_lines):
        sp = span(li)
        if sp and not back[li] and abs(sp[0] - (starts[li] + offset)) > 2.0:
            notes.lines_off_gt2s += 1
    return res, notes
