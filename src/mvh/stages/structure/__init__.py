"""structure stage (contract v1, owner M2): canonical sections, repeat groups, phrases and THE EDM roles.

* **Boundaries** are chosen among bar starts (downbeats) by dynamic programming over a per-bar boundary score:
  allin1 boundary activation and its segment boundaries, Foote novelty (4- and 8-bar kernels) on a combined
  self-similarity matrix (MFCC timbre, chroma, allin1 embeddings), the novelty of the drum / onset pattern (kick,
  percussive onsets, hat flux in 16 slots per bar) and of the allin1 embeddings alone, and energy change (RMS, bass,
  kick and onset density, brightness). The dynamics stage's segments, impacts and novelty are only weak CONFIRMATORY
  evidence: they add to a bar that already has evidence of its own and never create a boundary alone. Novelty at the
  song's first/last bars is damped (one-sided kernel). The DP prefers section lengths that are multiples of 4/8 bars;
  sections are >= ``min_section_bars``; silent runs of >= 2 bars become their own ``silence`` section. A long section
  is then split on the 4-bar grid where the 4-bar-window novelty clearly exceeds the in-section level
  (``split_min_novelty``): the verse -> chorus step that keeps the chords.
* **Repeat groups** cluster sections by bar-aligned similarity (chroma, melodic fingerprint, timbre, embeddings) with
  agglomerative average linkage; neighbouring sections need a higher similarity than distant ones because a boundary
  was placed between them (``repeat_adjacent_penalty``); a group shares one label.
* **Labels**: allin1's Harmonix probabilities when they are informative (vocal songs); otherwise (electronic /
  instrumental, SPIKE "allin1 labels are uninformative") structural labels from energy and the EDM roles:
  intro, drop, build, breakdown, inst, outro, silence. ``label_probs`` always carries allin1's probabilities.
* **Phrases** use the dominant 4/8/16-bar length that best fits the section lengths, from each section start; a
  section that is not a whole number of phrases puts its remainder first (a pickup phrase) when the song's other
  section starts sit on that grid, else last.
* **EDM roles** (defined ONLY here): drop = a section where bass/kick drive jumps (>= 6 dB bass or +0.5 kick
  per beat) into the loudest part of the song; build = the rising stretch before a drop (up to a stop/silence);
  breakdown = a >= 4-bar low-drive section after a high-energy part. Evidence strings cite the measurements and
  the dynamics items (impacts, stops, silences).

Overrides (anchored by time, D27): ``structure.boundaries`` add/remove/move a boundary at the nearest downbeat;
``structure.labels`` relabel the section containing t.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from mvh.contract.ids import make_id, repeat_group_label
from mvh.runner.spec import StageError, StageResult, StageSpec, catalog_outputs

from . import features as fx

STAGE = StageSpec(
    "structure",
    ('allin1', 'rhythm', 'harmony', 'dynamics'),
    "main",
    "1.4.1",
    override_keys=('structure.boundaries', 'structure.labels'),
    outputs=catalog_outputs("structure"),
    params={'analysis_lufs': -10.0, 'drop_top_min_rise': -0.25, 'verse_min_before_chorus': 0.25, 'min_section_bars': 2, 'phrase_bars': [4, 8, 16], 'repeat_threshold': 0.62, 'section_cost_q': 75,
            'drop_bass_jump_db': 6.0, 'drop_kick_jump': 0.5, 'drop_context_bars': 2, 'merge_repeat_max_bars': 8, 'merge_keep_strong': 1.4,
            'silence_db': -55.0, 'w_pattern': 0.7, 'w_embedding': 0.5, 'dyn_gate': 0.7, 'split_min_novelty': 0.5, 'repeat_len_exp': 0.15, 'repeat_adjacent_penalty': 0.85,
            'bar_jitter_frames': 2, 'short_section_margin': 0.25, 'impact_snap_strength': 0.6,
            'phrase_pickup_margin': 0.3, 'drive_kick_cap': 1.0},
    module="M2",
    description='Canonical sections (allin1 labels, downbeat-snapped, >= 2 bars), repetition groups, phrases, EDM roles.',
)

VOCAB = ["intro", "verse", "pre-chorus", "chorus", "bridge", "inst", "solo", "break", "outro"]
HARMONIX_TO_VOCAB = {"start": "intro", "end": "outro", "intro": "intro", "outro": "outro", "break": "break",
                     "bridge": "bridge", "inst": "inst", "solo": "solo", "verse": "verse", "chorus": "chorus"}


def _opt(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001 - optional upstream evidence
        return default


def _nearest_bar(t: float, starts: np.ndarray) -> int:
    return int(np.argmin(np.abs(starts - t)))


def _reg(L: int) -> float:
    r = 0.5 if L % 8 == 0 else 0.2 if L % 4 == 0 else -0.25 if L == 2 else -0.3 if L == 1 else 0.0 if L % 2 == 0 else -0.15
    if L > 24:
        r -= 0.02 * (L - 24)
    return r


def segment_dp(score: np.ndarray, n_bars: int, min_len: int, cost: float, forced: set[int], forbidden: set[int],
               short_pen: float = 0.0, silent: np.ndarray | None = None) -> list[int]:
    """Section start bars (indices into the section bars, always including 0) maximising
    sum(score[start] - cost + reg(length)). A section shorter than 4 bars that does not end at a forced boundary or
    at the song's end pays ``short_pen`` more: a phrase-breaking cut needs a clear margin over the section cost, so
    it does not appear or vanish with one frame of downbeat jitter (F4-r3).

    ``silent`` (per bar): a single silent bar that ends a section (the stop before a drop) is not counted in the
    phrase-length prior: 4 bars + a stop bar is a 4-bar phrase, not a 5-bar one (W4A-GAIN / W4A-STABLE: the synthetic
    bridge flipped between 25.0 and 27.0 s on a 0.05 score difference because 4 + 5 and 5 + 4 bars scored the same)."""
    sil = np.zeros(n_bars, bool) if silent is None else np.asarray(silent, bool)[:n_bars]

    def eff_len(i: int, j: int) -> int:
        L = j - i
        if L >= 2 and sil[j - 1] and not sil[j - 2]:
            return L - 1
        return L

    NEG = -1e18
    if n_bars <= min_len:
        return [0]
    f = np.full(n_bars + 1, NEG)
    arg = np.full(n_bars + 1, -1, int)
    f[0] = 0.0
    forced_sorted = sorted(forced)
    for j in range(1, n_bars + 1):
        for i in range(max(0, j - 64), j - min_len + 1):
            if f[i] <= NEG / 2:
                continue
            if i > 0 and i in forbidden:
                continue
            # a forced boundary strictly inside (i, j) is not allowed to be skipped
            if any(i < q < j for q in forced_sorted):
                continue
            g = f[i] + (score[i] if i > 0 else 0.0) - cost + _reg(eff_len(i, j))
            if j - i < 4 and j != n_bars and j not in forced:
                g -= short_pen
            if g > f[j]:
                f[j], arg[j] = g, i
        if f[j] <= NEG / 2 and (j == n_bars or j in forced):
            # a short tail or a forced short piece (never a short first section: sections are >= min_len bars)
            i = j - 1
            while i > 0 and f[i] <= NEG / 2:
                i -= 1
            f[j], arg[j] = f[i] - cost, i
    out = []
    j = n_bars
    while j > 0:
        i = int(arg[j])
        out.append(i)
        j = i
    return sorted(set(out))


def phrase_layout(sec_ranges: list[tuple[int, int]], phrase_L: int, lead: set[int] | frozenset[int] = frozenset(),
                  evidence: np.ndarray | None = None, margin: float = 0.3) -> list[tuple[int, int, int]]:
    """Phrases as (first bar, end bar, section index), restarting at every section start.

    A section that is not a whole number of phrases puts its remainder FIRST (a leading pickup phrase) only on local
    evidence (F8-r5: never on a count of sections elsewhere in the song):
    - its start was snapped one bar back to a major impact (``lead`` holds those section indices), or
    - the boundary evidence at ``a + remainder`` beats both the evidence at the section start ``a`` (the start sits on a
      fill or lead-in bar) and at ``b - remainder`` (where a trailing remainder would start) by ``margin``.
    Otherwise the remainder closes the section.
    """
    out: list[tuple[int, int, int]] = []
    for i, (a, b) in enumerate(sec_ranges):
        k = a
        r = (b - a) % phrase_L
        if r and b - a > phrase_L:
            pickup = i in lead
            if not pickup and evidence is not None and 0 <= a + r < len(evidence) and 0 <= b - r < len(evidence):
                e_lead = float(evidence[a + r])
                pickup = e_lead >= float(evidence[a]) + margin and e_lead >= float(evidence[b - r]) + margin
            if pickup:
                out.append((a, a + r, i))
                k = a + r
        while k < b:
            e = min(b, k + phrase_L)
            out.append((k, e, i))
            k = e
    return out


def run(ctx) -> StageResult:  # noqa: C901
    p = ctx.params
    warnings: list[str] = []
    fallbacks: list[str] = []
    notes: list[str] = []
    bars_all = list(ctx.events("bars").items)
    mix = ctx.audio("mix", mono=True)
    x = np.asarray(mix.samples, np.float32).reshape(-1)
    from mvh.stages.loudness.level import mix_gain

    a_gain, _, _ = mix_gain(ctx, p.get("analysis_lufs", -10.0))
    if a_gain != 1.0:  # W4V-GAIN (W4-AN-9): the bar features read the mix at one fixed analysis level
        x = (x * np.float32(a_gain)).astype(np.float32)
    sr = int(mix.sr)
    duration = x.size / sr
    n = -(-x.size * 100 // sr)
    sbars = [b for b in bars_all if b["bar"] >= 1]
    if not sbars:
        raise StageError("rhythm produced no bars")
    N = len(sbars)
    starts = np.array([b["t"] for b in sbars], float)
    spans = fx.bar_frames(sbars, n)
    bpb = np.array([b.get("n_beats") or b["beats_in_bar"] for b in sbars], float)

    # ------------------------------------------------------------------ features
    af = fx.audio_features(x, sr, n)
    chroma = None
    try:
        ch = [ctx.curve(f"chroma.{k}").values for k in range(12)]
        chroma = np.stack([np.asarray(c, float)[:n] for c in ch], axis=1)
        if chroma.shape[0] < n:
            chroma = np.vstack([chroma, np.zeros((n - chroma.shape[0], 12))])
        notes.append("chroma from the harmony stage")
    except Exception:  # noqa: BLE001
        chroma = fx.own_chroma(af["y44"], n)
        fallbacks.append("chroma:own_cqt")
        notes.append("chroma: own CQT chroma (harmony chroma12 unavailable)")
    from mvh.stages.allin1.read import load_allin1

    a1 = _opt(lambda: load_allin1(ctx.upstream("allin1")))
    if a1 is None:
        fallbacks.append("allin1:unavailable")
    mfcc_b = fx.pool(af["mfcc"], spans)
    chroma_b = fx.pool(chroma, spans)
    rms_b = fx.pool(af["rms_db"], spans)
    bass_b = fx.pool(af["bass_db"], spans)
    cent_b = fx.pool(af["centroid"], spans)
    kick_rate = fx.peak_rate(af["kick"], spans, bpb)
    onset_rate = fx.peak_rate(af["onset"], spans, bpb, rel=0.3)
    silent = rms_b < float(p.get("silence_db", -55.0))
    emb_b = None
    lab_b = None
    a1_bnd = np.zeros(N)
    a1_seg = np.zeros(N)
    label_names: list[str] = []
    if a1 is not None:
        if a1.emb is not None and a1.emb_rate_hz:
            r = a1.emb_rate_hz
            espans = [(int(round(b["t"] * r)), max(int(round(b["t"] * r)) + 1, int(round((b["t"] + b["d"]) * r)))) for b in sbars]
            espans = [(min(a, len(a1.emb) - 1), min(max(e, a + 1), len(a1.emb))) for a, e in espans]
            emb_b = fx.pool(a1.emb, espans)
        lp = a1.label_probs()
        if lp is not None:
            label_names = a1.label_names
            lspans = [(min(int(round(b["t"] * a1.rate_hz)), len(lp) - 1), min(len(lp), max(int(round(b["t"] * a1.rate_hz)) + 1, int(round((b["t"] + b["d"]) * a1.rate_hz))))) for b in sbars]
            lab_b = fx.pool(lp, lspans)
        bc = a1.col("boundary")
        if bc is not None:
            for k, t in enumerate(starts):
                a, e = int(round((t - 0.2) * a1.rate_hz)), int(round((t + 0.2) * a1.rate_hz)) + 1
                seg = bc[max(0, a):max(0, min(len(bc), e))]
                a1_bnd[k] = float(seg.max()) if len(seg) else 0.0
        for s in a1.doc.get("segments") or []:
            k = _nearest_bar(float(s["start"]), starts)
            half = 0.5 * float(sbars[k]["d"])
            if abs(starts[k] - float(s["start"])) <= half:
                a1_seg[k] = 1.0

    # dynamics evidence (optional upstream)
    dyn_b = np.zeros(N)
    imp_b = np.zeros(N)
    impacts = _opt(lambda: list(ctx.events("impacts").items), []) or []
    silences = _opt(lambda: list(ctx.events("silences").items), []) or []
    stops = []
    dyn_items = _opt(lambda: list(ctx.events("dynamics").items), None)
    if dyn_items is None:
        fallbacks.append("dynamics:unavailable")
        notes.append("dynamics evidence unavailable: own energy features only")
    else:
        # a dynamics part that starts on a decay tail (the last hit ringing out) is not a section start: the tail is the
        # end of the part before it (W4A-STABLE: the synthetic outro moved one bar late onto its decay tail)
        tails_t = [float(y["t"]) for y in (_opt(lambda: list(ctx.events("decay_tails").items), []) or [])]
        for it in dyn_items[1:]:
            k = _nearest_bar(float(it["t"]), starts)
            if any(abs(float(it["t"]) - y) <= 0.25 * sbars[k]["d"] for y in tails_t):
                continue
            if abs(starts[k] - it["t"]) <= 0.5 * sbars[k]["d"]:
                dyn_b[k] = 1.0
    for it in impacts:
        k = _nearest_bar(float(it["t"]), starts)
        if abs(starts[k] - it["t"]) <= 0.25 * sbars[k]["d"]:
            imp_b[k] = max(imp_b[k], float(it.get("strength", 0.5)))
    nov_dyn = _opt(lambda: fx.pool(ctx.curve("dyn.novelty").values[:n], spans, "max"))
    # the dynamics stage's silences mark bars as silent too (union with the own RMS gate)
    for z in silences:
        z0, z1 = float(z["t"]), float(z["t"]) + float(z["d"])
        for k, b in enumerate(sbars):
            ov = min(z1, b["t"] + b["d"]) - max(z0, b["t"])
            if ov >= 0.7 * b["d"]:
                silent[k] = True

    # ------------------------------------------------------------------ self-similarity, novelty, energy change
    def novelty_terms(sp: list[tuple[int, int]], emb_rows: np.ndarray | None) -> dict[str, Any]:
        """Self-similarity novelty, energy change and drum-pattern / embedding novelty for one set of bar spans."""
        mf = fx.pool(af["mfcc"], sp)
        chb = fx.pool(chroma, sp)
        grp = [fx.zscore(mf), fx.zscore(chb)]
        if emb_rows is not None:
            grp.append(fx.zscore(emb_rows))
        s_list = [fx.cosine_ssm(g) for g in grp]
        s_all = np.mean(s_list, axis=0)
        nv = 0.5 * fx.norm01(fx.foote(s_all, 4)) + 0.5 * fx.norm01(fx.foote(s_all, 8))
        en = fx.zscore(np.column_stack([fx.pool(af["rms_db"], sp), fx.pool(af["bass_db"], sp), 4 * fx.peak_rate(af["kick"], sp, bpb),
                                        2 * fx.peak_rate(af["onset"], sp, bpb, rel=0.3), np.log(np.maximum(fx.pool(af["centroid"], sp), 50))]))
        ch_ = np.zeros(N)
        for k in range(1, N):
            ch_[k] = float(np.linalg.norm(en[k:min(N, k + 2)].mean(axis=0) - en[max(0, k - 2):k].mean(axis=0)))
        pt = fx.bar_pattern([af["kick"], af["onset"], af["hat"]], sp)
        s_pat = fx.cosine_ssm(pt - pt.mean(axis=0, keepdims=True))
        return {"S_list": s_list, "S_pat": s_pat, "S_hom": np.mean(s_list + [s_pat], axis=0), "nov": nv, "chg": fx.norm01(ch_),
                "nov_pat": 0.5 * fx.norm01(fx.foote(s_pat, 2)) + 0.5 * fx.norm01(fx.foote(s_pat, 4)),
                "nov_emb": (0.5 * fx.norm01(fx.foote(s_list[2], 2)) + 0.5 * fx.norm01(fx.foote(s_list[2], 4))) if emb_rows is not None else np.zeros(N)}

    # The bar grid is an ESTIMATE (downbeats within +-20 ms of the truth are correct by the rhythm thresholds), so the
    # novelty evidence is averaged over bar grids shifted by -jitter..+jitter frames: a boundary decision must not flip
    # on one frame of downbeat jitter (F4-r3). The unshifted grid gives the features used for repeat groups and energy.
    base = novelty_terms(spans, emb_b)
    jit = int(p.get("bar_jitter_frames", 2))
    terms = {k: [base[k]] for k in ("nov", "chg", "nov_pat", "nov_emb", "S_hom")}
    for dj in [d for d in range(-jit, jit + 1) if d != 0]:
        sp = [(min(max(a + dj, 0), n - 1), min(max(e + dj, min(max(a + dj, 0), n - 1) + 1), n)) for a, e in spans]
        er = None
        if emb_b is not None and a1 is not None and a1.emb_rate_hz:
            r = a1.emb_rate_hz
            es = [(int(round((b["t"] + dj / fx.FPS) * r)), int(round((b["t"] + b["d"] + dj / fx.FPS) * r))) for b in sbars]
            es = [(min(max(a_, 0), len(a1.emb) - 1), min(max(e_, max(a_, 0) + 1), len(a1.emb))) for a_, e_ in es]
            er = fx.pool(a1.emb, es)
        alt = novelty_terms(sp, er)
        for k in terms:
            terms[k].append(alt[k])
    nov, chg, nov_pat, nov_emb = (np.mean(terms[k], axis=0) for k in ("nov", "chg", "nov_pat", "nov_emb"))
    S_hom = np.mean(terms["S_hom"], axis=0)
    sil_edge = np.zeros(N)
    for k in range(1, N):
        if silent[k - 1] and not silent[k]:
            sil_edge[k] = 1.0          # the music restarts: a section starts here
        elif silent[k] and not silent[k - 1]:
            sil_edge[k] = 0.3          # the silence ends the previous section (kept inside it when < 2 bars)
    # the song's first/last bars see a one-sided kernel (a decay tail or a one-bar lead-in always "changes"): damp the
    # signal-derived novelty terms there (explicit evidence such as allin1 boundaries or silences is not damped)
    edge = np.clip(np.minimum(np.arange(N) / 2.0, (N - np.arange(N)) / 4.0), 0.35, 1.0)
    own = (1.0 * fx.norm01(a1_bnd) + 0.8 * a1_seg + edge * (0.9 * nov + 0.7 * chg + float(p.get("w_pattern", 0.7)) * nov_pat
                                                            + float(p.get("w_embedding", 0.5)) * nov_emb) + 0.8 * sil_edge)
    # the dynamics stage's segments / impacts / novelty are weak CONFIRMATORY evidence: they add to a bar that already has
    # evidence of its own, they never create a boundary alone (its segments can come from other cues than the arrangement)
    dyn_ev = 0.3 * dyn_b + 0.3 * imp_b + (0.2 * fx.norm01(nov_dyn) if nov_dyn is not None else 0.0)
    gate = np.clip(own / float(p.get("dyn_gate", 0.7)), 0.0, 1.0)
    score = own + gate * dyn_ev
    score[0] = 0.0
    comps = {"a1_bnd": a1_bnd, "a1_seg": a1_seg, "nov": nov, "chg": chg, "dyn_b": dyn_b, "imp_b": imp_b, "sil_edge": sil_edge,
             "nov_pat": nov_pat, "nov_emb": nov_emb, "own": own, "edge": edge}
    # a short silence ends the section it falls in; sections do not start on a silent bar (long ones are forced below)
    score[silent] *= 0.2

    # ------------------------------------------------------------------ DP, impact snap, then the user's edits
    # W3C-6 (integrator-r2): the user's boundary edits are applied LOCALLY to the un-overridden segmentation (the same
    # result the user saw and edited), never by re-optimising the whole song, so an edit cannot move boundaries the
    # user did not touch.
    forced: set[int] = set()
    # silent runs >= 2 bars are sections of their own
    k = 0
    while k < N:
        if silent[k]:
            j = k
            while j < N and silent[j]:
                j += 1
            if j - k >= 2:
                if k > 0:
                    forced.add(k)
                if j < N:
                    forced.add(j)
            k = j
        else:
            k += 1
    forced.discard(0)
    min_len = int(p.get("min_section_bars", 2))
    cost = float(max(0.8, np.percentile(score[1:], float(p.get("section_cost_q", 75))))) if N > 2 else 1.0
    bounds = segment_dp(score, N, min_len, cost, forced, set(), float(p.get("short_section_margin", 0.25)) * cost, silent)
    # a major impact on the downbeat one bar BEFORE a section start is where the arrangement changes (the band enters,
    # then the voice a bar later): the section starts at the impact when that bar clears the section cost on its own
    # (S05). The DP cannot keep both (a 1-bar section), and allin1's functional boundary follows the voice.
    snap = float(p.get("impact_snap_strength", 0.6))
    snapped: set[int] = set()     # section start bars moved back by the snap (their phrase remainder leads, F8-r5)
    if snap > 0:
        moved = []
        bset = set(bounds)
        for k in sorted(bset):
            if k <= 0 or k in forced or (k - 1) in bset or silent[k - 1]:
                continue
            prev_b = max(q for q in bset if q < k)
            if imp_b[k - 1] >= snap and imp_b[k - 1] > imp_b[k] and score[k - 1] >= cost and (k - 1) - prev_b >= min_len:
                bset.discard(k)
                bset.add(k - 1)
                snapped.add(k - 1)
                moved.append(f"{starts[k]:.2f}->{starts[k - 1]:.2f} s")
        if moved:
            bounds = sorted(bset)
            notes.append("section start moved one bar back to a major impact: " + ", ".join(moved))
    sec_ranges = [(bounds[i], bounds[i + 1] if i + 1 < len(bounds) else N) for i in range(len(bounds))]

    # ------------------------------------------------------------------ repeat groups
    rep_feats = [fx.cosine_ssm(fx.zscore(chroma_b)), fx.cosine_ssm(fx.zscore(mfcc_b))]
    w_rep = [0.5, 0.25]
    if emb_b is not None:
        rep_feats.append(fx.cosine_ssm(fx.zscore(emb_b)))
        w_rep.append(0.25)
    if lab_b is not None:
        # allin1 functional-label probabilities: sections the model calls the same part look alike
        lp_song = lab_b.mean(axis=0)
        vc_idx = [k for k, nm in enumerate(label_names) if nm in ("verse", "chorus")]
        if vc_idx and float(lp_song[vc_idx].sum()) >= 0.3:
            rep_feats.append(2.0 * fx.cosine_ssm(np.sqrt(np.maximum(lab_b, 0))) - 1.0)
            w_rep.append(0.25)
    R = sum(w * s for w, s in zip(w_rep, rep_feats)) / sum(w_rep)
    # melodic fingerprint (static harmony removed): the same tune in a different arrangement is a repeat
    Rm = fx.cosine_ssm(fx.melody_residual(chroma, spans))

    def sec_sim(a: tuple[int, int], b: tuple[int, int], R=R) -> float:
        la, lb = a[1] - a[0], b[1] - b[0]
        m = min(la, lb)
        if m <= 0:
            return 0.0
        best = -1.0
        for off in (0, 1, -1):
            vals = [R[a[0] + i, b[0] + i + off] for i in range(m) if 0 <= b[0] + i + off < b[1] and a[0] + i < a[1]]
            if vals:
                best = max(best, float(np.mean(vals)))
        return best * (m / max(la, lb)) ** float(p.get("repeat_len_exp", 0.15))

    def grouping(ranges: list[tuple[int, int]]):
        nsec = len(ranges)
        sims = np.eye(nsec)
        for i in range(nsec):
            for j in range(i + 1, nsec):
                s_ij = max(sec_sim(ranges[i], ranges[j]), sec_sim(ranges[i], ranges[j], Rm))
                if j == i + 1:
                    s_ij *= float(p.get("repeat_adjacent_penalty", 0.85))   # a boundary was placed between them: they are different parts
                sims[i, j] = sims[j, i] = s_ij
        is_sil = [bool(silent[a:b].mean() > 0.7) for a, b in ranges]
        offd = [sims[i, j] for i in range(nsec) for j in range(i + 1, nsec) if not is_sil[i] and not is_sil[j]]
        tau = min(float(p.get("repeat_threshold", 0.62)), max(0.5, float(np.percentile(offd, 85)) if offd else 1.0))
        group_of = [-1] * nsec
        # agglomerative, average linkage: the most alike pair of clusters merges first (so a section joins the part it
        # repeats best, not the first one it clears the threshold with), until no pair reaches ``tau``
        clusters: list[list[int]] = [[i] for i in range(nsec) if not is_sil[i]]
        while len(clusters) > 1:
            best, bi, bj = tau, -1, -1
            for x in range(len(clusters)):
                for y in range(x + 1, len(clusters)):
                    s_ = float(np.mean([sims[a_, b_] for a_ in clusters[x] for b_ in clusters[y]]))
                    if s_ >= best:
                        best, bi, bj = s_, x, y
            if bi < 0:
                break
            clusters[bi] = sorted(clusters[bi] + clusters[bj])
            del clusters[bj]
        reps: list[list[int]] = sorted(clusters, key=min)
        for g, mem in enumerate(reps):
            for m in mem:
                group_of[m] = g
        for i in range(nsec):
            if is_sil[i]:
                reps.append([i])
                group_of[i] = len(reps) - 1
        return nsec, sims, is_sil, group_of, reps

    nsec, sims, is_sil, group_of, reps = grouping(sec_ranges)
    # adjacent short sections that are the same material (same repeat group) form one phrase-length section
    # (e.g. 4 + 4 bars of the same loop, or 2 + 2 bars of an intro): danceable sections, fewer cuts that change nothing
    merge_max = int(p.get("merge_repeat_max_bars", 8))
    # a boundary with strong evidence (a clear arrangement change) is kept even when both sides look alike
    strong_cut = float(p.get("merge_keep_strong", 1.4)) * cost
    if merge_max > 0:
        merged: list[tuple[int, int]] = []
        last_g = None
        for i, (a, b) in enumerate(sec_ranges):
            if (merged and not is_sil[i] and last_g is not None and group_of[i] == last_g and a not in forced
                    and b - merged[-1][0] <= merge_max and score[a] < strong_cut):
                merged[-1] = (merged[-1][0], b)
            else:
                merged.append((a, b))
                last_g = None if is_sil[i] else group_of[i]
        if len(merged) < len(sec_ranges):
            notes.append(f"merged {len(sec_ranges) - len(merged)} adjacent same-group section(s) into phrase-length sections")
            sec_ranges = merged
            nsec, sims, is_sil, group_of, reps = grouping(sec_ranges)
    # phrase-grid refinement: a long section (>= 8 bars) is split at a 4-bar-grid point when the 4-bar-window novelty of
    # the combined self-similarity (timbre, harmony, embeddings, drum pattern) is clearly above the song's typical
    # in-section level. Evidence for a verse -> chorus step that keeps the same chords can be too weak to peak
    # among the single-bar scores, yet a clean 4+4 / 8+8 change on the grid is what choreography counts in.
    split_min = float(p.get("split_min_novelty", 0.5))
    if split_min > 0:
        nov_grid = fx.norm01(fx.foote(S_hom, 4))
        comps["nov_grid"] = nov_grid
        refined: list[tuple[int, int]] = []

        def split_range(a: int, b: int) -> list[tuple[int, int]]:
            # a single silent bar closing the section (the stop before a drop) is not part of its phrase grid (W4A-GAIN)
            be = b - 1 if b - a >= 2 and silent[b - 1] and not silent[b - 2] else b
            cand = list(range(a + 4, be - 3, 4))
            if be - a < 8 or not cand or silent[a:be].any():
                return [(a, b)]
            m = max(cand, key=lambda q: nov_grid[q])
            if nov_grid[m] < split_min:
                return [(a, b)]
            return split_range(a, m) + split_range(m, b)

        for i, (a, b) in enumerate(sec_ranges):
            refined += [(a, b)] if is_sil[i] else split_range(a, b)
        if len(refined) > len(sec_ranges):
            notes.append(f"phrase-grid refinement split {len(refined) - len(sec_ranges)} long section(s) at 4-bar novelty >= {split_min}")
            sec_ranges = refined
            nsec, sims, is_sil, group_of, reps = grouping(sec_ranges)
    # the user's boundary edits, applied to the automatic result (W3C-6: local edits; nothing else moves)
    applied: list[dict[str, Any]] = []
    edits = list(ctx.overrides.get("structure.boundaries") or [])
    if edits:
        bset = {a_ for a_, _ in sec_ranges}
        for ed in edits:
            act = ed.get("action")
            k = _nearest_bar(float(ed["t"]), starts)
            if act == "add":
                if k > 0:
                    bset.add(k)
            elif act == "remove":
                if k > 0:
                    bset.discard(k)
                snapped.discard(k)
            elif act == "move":
                if k > 0:
                    bset.discard(k)
                snapped.discard(k)
                if ed.get("to_t") is not None:
                    k2 = _nearest_bar(float(ed["to_t"]), starts)
                    if k2 > 0:
                        bset.add(k2)
        bset.add(0)
        bl = sorted(bset)
        sec_ranges = [(bl[i], bl[i + 1] if i + 1 < len(bl) else N) for i in range(len(bl))]
        nsec, sims, is_sil, group_of, reps = grouping(sec_ranges)
        # one entry per key holding the whole edit list (as the runner's default provenance does; F-R5-APPLIED-BOUNDARY)
        applied.append({"key": "structure.boundaries", "value": edits})
    # group letters in order of first appearance
    order = sorted(range(len(reps)), key=lambda g: min(reps[g]))
    letter = {g: repeat_group_label(k + 1) for k, g in enumerate(order)}

    # ------------------------------------------------------------------ section energy / drive, EDM roles
    # the kick term is the kick COVERAGE (kick peaks per beat capped at 1): a snare roll or a fill leaking into the kick band
    # doubles the peak rate of a build, which must not out-drive the four-on-the-floor drop (W4A-STABLE: at 0.9x tempo the
    # synthetic build read 2 'kicks' per beat and both EDM roles were lost)
    kick_cov = np.minimum(kick_rate, float(p.get("drive_kick_cap", 1.0)))
    drive_bar = fx.zscore(bass_b)[:, 0] + fx.zscore(4 * kick_cov)[:, 0] + 0.5 * fx.zscore(rms_b)[:, 0]
    nonsil = ~silent

    def sec_mean(arr, a, b):
        sel = np.arange(a, b)
        sel = sel[nonsil[a:b]] if nonsil[a:b].any() else sel
        return float(np.mean(arr[sel]))

    drive = [sec_mean(drive_bar, a, b) for a, b in sec_ranges]
    bass_s = [sec_mean(bass_b, a, b) for a, b in sec_ranges]
    kick_s = [sec_mean(kick_rate, a, b) for a, b in sec_ranges]
    kick_cov_s = [sec_mean(kick_cov, a, b) for a, b in sec_ranges]
    roles: list[dict[str, Any]] = []
    role_of: dict[int, str] = {}
    stop_items = _opt(lambda: list(ctx.events("stops").items), []) or []
    stops = sorted(stop_items, key=lambda z: z["t"])
    live = [d for d, s in zip(drive, is_sil) if not s] or [0.0]
    drive_hi = float(np.percentile(live, 70))
    drive_peak = float(max(live))
    def drop_level(a: int) -> float:
        """The drop's plateau level: mean bar drive over its first 8 non-silent bars, whatever the segmentation (a drop
        that opens with a 4-bar section must not set a higher bar for its continuation than one opening with 8)."""
        idx = [k for k in range(a, min(N, a + 8)) if nonsil[k]] or [a]
        return float(np.mean(drive_bar[idx]))

    def place_drop(i: int, ev: list[str], conf: float) -> None:
        a = sec_ranges[i][0]
        level = drop_level(a)
        groups_in = {group_of[i]}
        j = i
        # the drop runs on while the energy stays on the plateau: a following section within 0.6 z of the opening level,
        # or one that repeats material already in this drop (same repeat group) and stays within 1.2 z (F6-r3)
        while j + 1 < nsec and not is_sil[j + 1] and j + 1 not in role_of:
            dj = drive[j + 1]
            if dj >= level - 0.6 or (group_of[j + 1] in groups_in and dj >= level - 1.2):
                j += 1
                groups_in.add(group_of[j])
            else:
                break
        t_end = starts[sec_ranges[j][1]] if sec_ranges[j][1] < N else duration
        roles.append({"role": "drop", "a": a, "b": sec_ranges[j][1], "t": float(starts[a]), "t_end": float(t_end), "sec": i, "conf": conf,
                      "evidence": ev, "level": level, "groups": groups_in})
        for q in range(i, j + 1):
            role_of[q] = "drop"
        place_build(i)

    def place_build(i: int) -> None:
        """The build: the section before the drop (skipping silence), when it rises or ends in a stop."""
        q = i - 1
        while q >= 0 and is_sil[q]:
            q -= 1
        if q < 0 or q in role_of:
            return
        ba, bb = sec_ranges[q]
        end = bb
        while end > ba and silent[end - 1]:
            end -= 1
        if end - ba < 2:
            return
        idx = np.arange(ba, end)
        xs = (idx - idx.mean()) / max(1.0, idx.std())
        sl_on = float(np.polyfit(xs, onset_rate[idx], 1)[0]) if len(idx) > 2 else 0.0
        sl_ce = float(np.polyfit(xs, np.log(np.maximum(cent_b[idx], 50)), 1)[0]) if len(idx) > 2 else 0.0
        sl_rms = float(np.polyfit(xs, rms_b[idx], 1)[0]) if len(idx) > 2 else 0.0
        rising = sl_on > 0.05 or sl_ce > 0.05 or sl_rms > 0.5
        lower = drive[q] < drive[i] - 0.25
        ends_stop = end < bb or any(abs(s["t"] - starts[min(end, N - 1)]) < 0.6 * sbars[min(end, N - 1)]["d"] for s in stops)
        if not ((rising and (lower or ends_stop)) or (lower and ends_stop)):
            return
        evb = []
        if sl_on > 0.05:
            evb.append("rising onset density")
        if sl_ce > 0.05:
            evb.append("riser (brightness rising)")
        if sl_rms > 0.5:
            evb.append("rising level")
        if ends_stop:
            evb.append("ends in a stop/silence")
        for s in stops:
            if starts[ba] <= s["t"] <= (starts[end] if end < N else duration) + 0.1:
                evb.append(f"stop {s['id']}")
        bconf = float(np.clip(0.35 + 0.15 * len(evb), 0, 0.95))
        t_end_b = starts[end] if end < N else duration
        roles.append({"role": "build", "a": ba, "b": end, "t": float(starts[ba]), "t_end": float(t_end_b), "sec": q,
                      "conf": bconf, "evidence": evb})
        role_of[q] = "build"

    def drop_cue(i: int) -> tuple[bool, list[str], float] | None:
        """The entry of a drop at section i: a bass / kick jump against the bars right before it, a silence or stop
        just before it, or a strong impact with a large rise. Returns (cue, evidence, confidence)."""
        a, b = sec_ranges[i]
        # context before: the last up-to-4 non-silent bars before the section
        prev = [k for k in range(a - 1, -1, -1) if nonsil[k]][:4]
        if not prev:
            return None
        # the bass / kick jump is measured against the bars right before the section (an instrument entering earlier
        # in the previous section is not part of this jump)
        near = prev[:max(1, int(p.get("drop_context_bars", 2)))]
        pb = float(np.mean(bass_b[near]))
        pk = float(np.mean(kick_rate[near]))
        nb = float(np.mean(bass_b[a:min(b, a + 4)]))
        nk = float(np.mean(kick_rate[a:min(b, a + 4)]))
        jump_b, jump_k = nb - pb, nk - pk
        gap_sil = any(silent[k] for k in range(max(0, a - 2), a)) or any(
            starts[max(0, a - 1)] - 0.05 <= s["t"] <= starts[a] + 0.05 for s in stops)
        imp_s = max([float(it.get("strength", 0.5)) for it in impacts if abs(it["t"] - starts[a]) <= 0.25 * sbars[a]["d"]], default=0.0)
        rise = float(np.mean(drive_bar[a:min(b, a + 4)])) - float(np.mean(drive_bar[prev]))
        kick_enters = pk <= 0.35 and nk >= max(0.75, pk + float(p.get("drop_kick_jump", 0.5)))
        big_jump = (jump_b >= float(p.get("drop_bass_jump_db", 6.0)) or kick_enters) and rise >= 0.8
        # margin (W4A-STABLE): the song's top-drive section entered after a stop / silence with a strong impact is a drop
        # even when the build before it already rose most of the way (its last bars as loud as the drop)
        # (round 2: rise > drop_top_min_rise, -0.25 z: at 0.95x tempo the synthetic drop's rise was +0.01 / -0.01 z
        # depending on one kick-band peak)
        top = drive[i] >= drive_peak - 0.25 and gap_sil and imp_s >= 0.6 and rise > float(p.get("drop_top_min_rise", -0.25))
        cue = big_jump or (gap_sil and rise >= 0.3) or (imp_s >= 0.6 and rise >= 1.2 and jump_b >= 3.0) or top
        # m-d (W4): an onset rate of the mix kick band, not the agent-facing kick count
        ev = [f"bass {jump_b:+.1f} dB", f"kick-band onsets {pk:.2f}->{nk:.2f}/beat", f"drive {rise:+.2f} z"]
        for it in impacts:
            if abs(it["t"] - starts[a]) <= 0.25 * sbars[a]["d"]:
                ev.append(f"impact {it['id']}")
        if gap_sil:
            ev.append("silence/stop before")
        conf = float(np.clip(0.4 + 0.04 * max(jump_b, 0) + 0.25 * max(jump_k, 0) + 0.1 * max(rise, 0) + (0.15 if gap_sil else 0)
                             + 0.1 * imp_s, 0, 0.97))
        return cue, ev, conf

    for i in range(1, nsec):
        if is_sil[i] or i in role_of:
            continue
        at_peak = drive[i] >= drive_hi and drive[i] >= drive_peak - 1.0
        dc = drop_cue(i) if at_peak else None
        if dc is not None and dc[0]:
            place_drop(i, dc[1], dc[2])
    # roles stay consistent within a repeat group: the drop's material entering again with its own drop cue at the
    # drop's energy (within 0.6 z of its plateau) is a drop too, even when that section sits just below the song's
    # 70th-percentile drive (the 'at peak' test is a percentile and must not split one material into drop and inst)
    for i in range(1, nsec):
        if is_sil[i] or i in role_of:
            continue
        src = next((r for r in roles if r["role"] == "drop" and group_of[i] in r["groups"] and drive[i] >= r["level"] - 0.6), None)
        dc = drop_cue(i) if src is not None else None
        if dc is not None and dc[0]:
            place_drop(i, dc[1] + [f"repeats the drop at {src['t']:.1f} s (group {letter[group_of[i]]})"], dc[2])
    # breakdowns: low-drive sections (>= 4 bars) after a drop / high-energy section
    first_high = next((i for i in range(nsec) if not is_sil[i] and drive[i] >= drive_hi), None)
    for i in range(1, nsec):
        if i in role_of or is_sil[i] or first_high is None or i <= first_high:
            continue
        a, b = sec_ranges[i]
        if b - a < 4:
            continue
        prev_hi = max(drive[k] for k in range(first_high, i) if not is_sil[k])
        prev_bass = max(bass_s[k] for k in range(first_high, i) if not is_sil[k])
        comes_back = any(drive[k] >= prev_hi - 0.6 for k in range(i + 1, nsec) if not is_sil[k])
        # the kick thins out in a breakdown: a section that keeps a kick on every beat is a verse without bass, not a
        # breakdown (W4A-STABLE margin: Newton's bass-less rap verse sat at the 1.2 z threshold)
        prev_kick = max(kick_cov_s[k] for k in range(first_high, i) if not is_sil[k])
        kick_thins = kick_cov_s[i] <= prev_kick - 0.2 or kick_cov_s[i] < 0.5
        if drive[i] <= prev_hi - 1.2 and bass_s[i] <= prev_bass - 6.0 and i < nsec - 1 and comes_back and kick_thins:
            conf = float(np.clip(0.4 + 0.04 * (prev_bass - bass_s[i]), 0, 0.9))
            roles.append({"role": "breakdown", "a": a, "b": b, "t": float(starts[a]), "t_end": float(starts[b] if b < N else duration), "sec": i,
                          "conf": conf, "evidence": [f"bass {bass_s[i] - prev_bass:+.1f} dB vs the preceding peak", f"kick-band onsets {kick_s[i]:.2f}/beat"]})
            role_of[i] = "breakdown"

    # ------------------------------------------------------------------ labels
    lab_names_v = [HARMONIX_TO_VOCAB.get(nm, nm) for nm in label_names]
    sec_probs: list[dict[str, float]] = []
    for a, b in sec_ranges:
        pr: dict[str, float] = {}
        if lab_b is not None:
            m = lab_b[a:b].mean(axis=0)
            for nm, v in zip(lab_names_v, m):
                pr[nm] = pr.get(nm, 0.0) + float(v)
            tot = sum(pr.values()) or 1.0
            pr = {k: round(v / tot, 3) for k, v in pr.items() if v / tot >= 0.01}
        sec_probs.append(pr)
    informative = False
    if lab_b is not None:
        song = {}
        for d_ in sec_probs:
            for k_, v in d_.items():
                song[k_] = song.get(k_, 0.0) + v
        tot = sum(song.values()) or 1.0
        vc = (song.get("verse", 0) + song.get("chorus", 0)) / tot
        informative = vc >= 0.3
    labels = [""] * nsec
    confs = [0.5] * nsec
    if informative:
        for g, mem in enumerate(reps):
            agg: dict[str, float] = {}
            for m in mem:
                for k_, v in sec_probs[m].items():
                    agg[k_] = agg.get(k_, 0.0) + v
            for m in mem:
                own = sec_probs[m]
                lab = max(agg, key=agg.get) if (len(mem) > 1 and agg) else (max(own, key=own.get) if own else "inst")
                labels[m] = lab
                confs[m] = float(own.get(lab, 0.3)) if own else 0.3
        # form rules on top of the model's frame labels (allin1 labels a vocal-less opening or a contrasting middle part
        # by its nearest Harmonix class): the song's opening section is an intro when nothing repeats it and it is
        # quieter than the song's typical level; a part that is not repeated, sits between two choruses and that the
        # model cannot place (no Harmonix class above 0.55: neither verse nor chorus) is a bridge
        live_i = [i for i in range(nsec) if not is_sil[i]]
        med_drive = float(np.median([drive[i] for i in live_i])) if live_i else 0.0
        singleton = [len(reps[group_of[i]]) == 1 for i in range(nsec)]
        if live_i:
            i0 = live_i[0]
            if singleton[i0] and labels[i0] not in ("intro", "silence") and drive[i0] < med_drive and len(live_i) > 2:
                notes.append(f"labels: opening section relabelled intro (not repeated, below the median drive; allin1 said {labels[i0]})")
                labels[i0] = "intro"
                confs[i0] = float(sec_probs[i0].get("intro", 0.5)) if sec_probs[i0] else 0.5
        for i in range(1, nsec - 1):
            # W4A-GAIN: allin1 can run one 'chorus' segment over chorus + bridge; a part that is not repeated and sits
            # between two members of ONE chorus repeat group (the repeat analysis found it unlike them) is the bridge too
            sandwiched = (labels[i] == "chorus" and group_of[i - 1] == group_of[i + 1] != group_of[i]
                          and not is_sil[i - 1] and not is_sil[i + 1])
            if (singleton[i] and not is_sil[i] and labels[i - 1] == "chorus" and labels[i + 1] == "chorus"
                    and ((labels[i] not in ("chorus", "bridge", "intro", "outro") and max(sec_probs[i].values(), default=0.0) < 0.55)
                         or sandwiched)):
                notes.append(f"labels: section at {starts[sec_ranges[i][0]]:.1f} s relabelled bridge (not repeated, between choruses; allin1 said {labels[i]})")
                labels[i] = "bridge"
                confs[i] = float(sec_probs[i].get("bridge", 0.4)) if sec_probs[i] else 0.4
        # W4 round 2: allin1 can call the part right before the first chorus 'chorus' as well (synth at 32 kHz: verse 0.36,
        # chorus 0.60). A section that is not repeated, is a different repeat group from the chorus right after it, sits
        # just before the FIRST occurrence of that repeated chorus group and still has verse >= verse_min_before_chorus
        # is the verse leading into it (two different choruses back to back is not a form)
        vmin = float(p.get("verse_min_before_chorus", 0.25))
        for i in range(nsec - 1):
            j = i + 1
            if (labels[i] == "chorus" and labels[j] == "chorus" and singleton[i] and not is_sil[i] and not is_sil[j]
                    and group_of[j] != group_of[i] and len(reps[group_of[j]]) >= 2 and min(reps[group_of[j]]) == j
                    and not any(labels[k] == "chorus" for k in range(i)) and sec_probs[i].get("verse", 0.0) >= vmin):
                notes.append(f"labels: section at {starts[sec_ranges[i][0]]:.1f} s relabelled verse (not repeated, right before the "
                             f"first chorus of a repeated chorus group; allin1 verse {sec_probs[i].get('verse', 0.0):.2f})")
                labels[i] = "verse"
                confs[i] = float(sec_probs[i].get("verse", 0.3))
        notes.append("labels: allin1 Harmonix probabilities (informative), shared within repeat groups")
    else:
        e_sec = drive
        for i in range(nsec):
            if i in role_of:
                labels[i] = role_of[i]
                confs[i] = 0.6
        for i in range(nsec):
            if labels[i]:
                continue
            if i == 0:
                labels[i] = "intro"
            elif i == nsec - 1 and e_sec[i] < max(e_sec):
                labels[i] = "outro"
            else:
                labels[i] = "inst" if e_sec[i] >= np.median(e_sec) - 0.3 else "break"
        # repeat groups share the label of their first member (roles kept)
        for g, mem in enumerate(reps):
            base = next((labels[m] for m in mem if m not in role_of), None)
            for m in mem:
                if m not in role_of and base and labels[m] not in ("intro", "outro"):
                    labels[m] = base
        notes.append("labels: structural (allin1 labels uninformative): energy, repetition and EDM roles")
    for i in range(nsec):
        if is_sil[i]:
            labels[i] = "silence"
            confs[i] = 0.9
    for lo in ctx.overrides.get("structure.labels") or []:
        t = float(lo["t"])
        for i, (a, b) in enumerate(sec_ranges):
            t0 = starts[a]
            t1 = starts[b] if b < N else duration
            if t0 - 1e-6 <= t < t1:
                labels[i] = str(lo["label"])
                confs[i] = 1.0
    if ctx.overrides.get("structure.labels"):
        applied.append({"key": "structure.labels", "value": list(ctx.overrides.get("structure.labels"))})

    # ------------------------------------------------------------------ sections
    sections = []
    occ: dict[str, int] = {}
    sid = []
    for i, (a, b) in enumerate(sec_ranges):
        t0 = float(starts[a])
        t1 = float(starts[b]) if b < N else float(duration)
        lab = labels[i] or "inst"
        occ[lab] = occ.get(lab, 0) + 1
        s_id = make_id("section", i + 1)
        sid.append(s_id)
        bc = 1.0 if i == 0 else float(np.clip(score[a] / max(1e-9, np.percentile(score[1:], 95) if N > 2 else 1.0), 0, 1))
        if a in forced:
            bc = 1.0
        sections.append({"id": s_id, "t": round(t0, 6), "d": round(t1 - t0, 6), "label": lab, "occurrence": occ[lab],
                         "occurrence_label": f"{lab}#{occ[lab]}", "repeat_group": letter[group_of[i]],
                         "start_bar": int(sbars[a]["bar"]), "n_bars": int(b - a), "label_probs": sec_probs[i] or {lab: 1.0},
                         "conf": round(float(np.clip(confs[i], 0, 1)), 3), "boundary_conf": round(bc, 3),
                         "energy": round(float(drive[i]), 3)})

    # ------------------------------------------------------------------ phrases
    lens = [b - a for a, b in sec_ranges]
    cands = [int(v) for v in p.get("phrase_bars", [4, 8, 16])]
    pscore = {}
    for L in cands:
        fit = sum(ln for ln in lens if ln % L == 0) / max(1, sum(lens))
        inner = []
        for a, b in sec_ranges:
            inner += [nov[k] for k in range(a + L, b, L)]
        pscore[L] = fit + 0.3 * (float(np.mean(inner)) if inner else 0.0)
    # the longest phrase length that still tiles most of the song (multiples of 8 are multiples of 4 too)
    fits = {L: sum(ln for ln in lens if ln % L == 0) / max(1, sum(lens)) for L in cands}
    ok = [L for L in sorted(cands, reverse=True) if fits[L] >= 0.65]
    phrase_L = ok[0] if ok else max(pscore, key=lambda L_: (round(pscore[L_], 6), -L_))
    phrases: list[dict[str, Any]] = []
    lead_moved = []
    snapped_secs = {i for i, (a, _b) in enumerate(sec_ranges) if a in snapped}
    for k, e, i in phrase_layout(sec_ranges, phrase_L, snapped_secs, score,
                                 float(p.get("phrase_pickup_margin", 0.3)) * cost):
        t0 = float(starts[k])
        t1 = float(starts[e]) if e < N else float(duration)
        phrases.append({"id": make_id("phrase", len(phrases) + 1), "t": round(t0, 6), "d": round(t1 - t0, 6),
                        "start_bar": int(sbars[k]["bar"]), "n_bars": int(e - k), "section_id": sid[i]})
        a, b = sec_ranges[i]
        if k == a and e - k < phrase_L and e < b:
            lead_moved.append(f"{t0:.2f} s ({e - k} bar{'s' if e - k > 1 else ''})")
    if lead_moved:
        notes.append("phrase remainder placed at the section start (song phrase grid): " + ", ".join(lead_moved))

    # ------------------------------------------------------------------ EDM role items
    edm = []
    for r in sorted(roles, key=lambda r: r["t"]):
        edm.append({"id": make_id("edm_role", len(edm) + 1), "t": round(r["t"], 6), "d": round(r["t_end"] - r["t"], 6), "role": r["role"],
                    "start_bar": int(sbars[r["a"]]["bar"]), "n_bars": int(max(1, r["b"] - r["a"])), "section_id": sid[r["sec"]],
                    "conf": round(r["conf"], 3), "evidence": r["evidence"]})
    for s in sections:
        # the EDM role whose span holds the section's start (m6: every section of a multi-section drop is 'drop')
        s["edm_role"] = next((e["role"] for e in edm if e["section_id"] == s["id"]), None) or next(
            (e["role"] for e in edm if e["t"] - 1e-6 <= s["t"] < e["t"] + e["d"] - 1e-6), None)

    # ------------------------------------------------------------------ write
    w = ctx.writer
    w.events("sections", sections, fields={"energy": {"unit": "z", "type": "number"}, "edm_role": {"unit": None, "type": "enum|null"}})
    w.events("phrases", phrases)
    w.events("edm_roles", edm)
    rg = {}
    for g, mem in enumerate(reps):
        ids = [sid[m] for m in mem]
        sim = float(np.mean([sims[a_, b_] for ai, a_ in enumerate(mem) for b_ in mem[ai + 1:]])) if len(mem) > 1 else 0.0
        rg[letter[g]] = {"label": labels[mem[0]] or "inst", "section_ids": ids, "similarity": round(float(np.clip(sim, 0, 1)), 3)}
    rg = dict(sorted(rg.items(), key=lambda kv: (len(kv[0]), kv[0])))
    w.json("meta/structure.json", {
        "repeat_groups": rg, "phrase_bars": int(phrase_L), "n_sections": len(sections),
        "labeling": "allin1" if informative else "structural",
        "phrase_scores": {str(k): round(v, 3) for k, v in pscore.items()},
        "edm": {"n_drops": sum(1 for e in edm if e["role"] == "drop"), "n_builds": sum(1 for e in edm if e["role"] == "build"),
                "n_breakdowns": sum(1 for e in edm if e["role"] == "breakdown")},
        "boundary_evidence": {"allin1_activation": a1 is not None and a1.col("boundary") is not None, "allin1_segments": bool(a1_seg.any()),
                              "dynamics": dyn_items is not None, "chroma": "harmony" if "chroma:own_cqt" not in fallbacks else "own_cqt",
                              "embeddings": emb_b is not None, "section_cost": round(cost, 3)},
        "overrides_applied": applied,
        "bar_boundary_score": [round(float(v), 2) for v in score],
        "boundary_components": {k: [round(float(v), 2) for v in arr] for k, arr in comps.items()},
        "section_similarity": [[round(float(v), 2) for v in row] for row in sims],
    })
    summary = {"n_sections": len(sections), "labels": [s["occurrence_label"] for s in sections][:16], "phrase_bars": int(phrase_L),
               "n_phrases": len(phrases), "edm_roles": [f"{e['role']}@{e['t']:.1f}" for e in edm][:8],
               "labeling": "allin1" if informative else "structural", "repeat_groups": len(rg)}
    prov: dict[str, Any] = {"notes": notes}
    if applied:
        prov["overrides_applied"] = applied
    status = "degraded" if "allin1:unavailable" in fallbacks else "ok"
    return StageResult(status=status, summary=summary, warnings=warnings, fallbacks=sorted(set(fallbacks)),
                       confidence=round(float(np.mean([s["conf"] for s in sections])), 3), provenance=prov)
