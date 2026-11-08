"""Task 4: MMS_FA forced alignment (torchaudio forced_align op) of LRCLIB lines to the vocal stem.
30 s emission windows with 2 s context; line-group windows from LRCLIB starts (+/-2 s); global offset detection; per-line constraint re-align.
Numbers only on stdout.  Usage: bw_align.py <slug> [stem]"""
import sys, os, time, json, re
sys.path.insert(0, r"C:\Users\OpenSrcerer\Desktop\playground\mv-harness\scripts"); sys.path.insert(0, os.path.dirname(__file__))
from heavy_lock import heavy, apply_thread_limits
apply_thread_limits(6)
import numpy as np, torch
from bw_common import *
SLUG = sys.argv[1] if len(sys.argv) > 1 else "jeremy"; STEM = sys.argv[2] if len(sys.argv) > 2 else "lead_vocals"
FR = 0.02  # 20 ms per frame
OUT = sdir(SLUG, "align_mms")


def emissions(wav, model, ctx_s=2.0, win_s=30.0):
    """Full-song log-probs [T, C]; 30 s windows with 2 s of context each side, centre parts stitched (frame-aligned: 320 samples/frame)."""
    n = len(wav); hop = int(win_s * 16000); ctx = int(ctx_s * 16000); parts = []
    for s in range(0, n, hop):
        a0 = max(0, s - ctx); a1 = min(n, s + hop + ctx)
        x = torch.from_numpy(wav[a0:a1]).float(); x = (x - x.mean()) / (x.std() + 1e-7)
        with torch.inference_mode():
            em, _ = model(x[None]); lp = torch.log_softmax(em, -1)[0].numpy()
        f_lo = (s - a0) // 320; f_hi = f_lo + min(hop, n - s) // 320
        parts.append(lp[f_lo:f_hi])
    return np.concatenate(parts)


def mms_prep(lines, dct, uro, n2w):
    """lines -> words [{line, w, tok}] using uroman + num2words, MMS dictionary chars only."""
    words, dropped = [], 0
    for li, l in enumerate(lines):
        t = re.sub(r"\d+", lambda m: n2w(int(m.group())), l["text"])
        t = uro.romanize_string(t).lower().replace("\u2019", "'")
        for w in re.sub(r"[^a-z'\s]", " ", t).split():
            tok = [dct[c] for c in w if c in dct]
            if tok:
                words.append({"line": li, "w": w, "tok": tok})
            else:
                dropped += 1
    return words, dropped


def align_chunk(logp, f0, f1, toks):
    import torchaudio.functional as F
    f0 = max(0, f0); f1 = min(len(logp), f1)
    seg = torch.from_numpy(logp[f0:f1]).float()[None]
    flat = [t for w in toks for t in w]
    if len(flat) > f1 - f0:
        raise ValueError("fewer frames than tokens")
    ali, sc = F.forced_align(seg, torch.tensor([flat], dtype=torch.int32), blank=0)
    spans = F.merge_tokens(ali[0], sc[0].exp())
    if len(spans) != len(flat):
        raise ValueError("span/token mismatch %d/%d" % (len(spans), len(flat)))
    out, k = [], 0
    for w in toks:
        sp = spans[k:k + len(w)]; k += len(w)
        out.append({"start": (f0 + sp[0].start) * FR, "end": (f0 + sp[-1].end) * FR, "score": float(np.mean([s.score for s in sp])), "tok_scores": [float(s.score) for s in sp]})
    return out


def groups(lines, ends, max_span=30.0, max_gap=12.0):
    g, cur = [], []
    for i, l in enumerate(lines):
        if cur and (ends[i] - lines[cur[0]]["t"] + 4 > max_span or l["t"] - ends[cur[-1]] > max_gap):
            g.append(cur); cur = []
        cur.append(i)
    if cur:
        g.append(cur)
    return g


def run_alignment(logp, lines, words, offset, ctx=2.0, tail_len=8.0, slack_line=2.5):
    ends = [lines[i + 1]["t"] if i + 1 < len(lines) else lines[i]["t"] + tail_len for i in range(len(lines))]
    by_line = {}
    for wi, w in enumerate(words):
        by_line.setdefault(w["line"], []).append(wi)
    res = [None] * len(words); notes = {"group_fail": 0, "groups": 0, "tokens_per_frame_max": 0.0, "line_realigned": 0, "line_realign_accepted": 0}
    T = len(logp)
    for g in groups(lines, ends):
        notes["groups"] += 1
        wis = [wi for li in g for wi in by_line.get(li, [])]
        if not wis:
            continue
        t0 = lines[g[0]]["t"] + offset - ctx; t1 = ends[g[-1]] + offset + ctx
        f0, f1 = max(0, int(t0 / FR)), min(T, int(t1 / FR))
        toks = [words[wi]["tok"] for wi in wis]
        notes["tokens_per_frame_max"] = round(max(notes["tokens_per_frame_max"], sum(map(len, toks)) / max(1, f1 - f0)), 3)
        try:
            al = align_chunk(logp, f0, f1, toks)
            for wi, a in zip(wis, al):
                res[wi] = a
        except Exception as e:
            notes["group_fail"] += 1; notes.setdefault("errors", []).append(str(e)[:80])
    # per-line window constraint: re-align lines whose start deviates from LRCLIB (+offset) by > slack, in a tight window
    for li, wis in by_line.items():
        dev = 99 if res[wis[0]] is None else abs(res[wis[0]]["start"] - (lines[li]["t"] + offset))
        if dev > slack_line:
            notes["line_realigned"] += 1
            t0 = lines[li]["t"] + offset - slack_line; t1 = ends[li] + offset + slack_line
            try:
                al = align_chunk(logp, int(t0 / FR), int(t1 / FR), [words[wi]["tok"] for wi in wis])
                old = np.mean([res[wi]["score"] for wi in wis]) if res[wis[0]] is not None else -1
                if np.mean([a["score"] for a in al]) > old:
                    notes["line_realign_accepted"] += 1
                    for wi, a in zip(wis, al):
                        res[wi] = a
            except Exception:
                pass
    return res, notes


def metrics(res, lines, words):
    ok = [r for r in res if r is not None]
    sc = np.array([r["score"] for r in ok]) if ok else np.array([0.0])
    allsc = np.array([s for r in ok for s in r["tok_scores"]]) if ok else np.array([0.0])
    n = len(words)
    by_line = {}
    for wi, w in enumerate(words):
        by_line.setdefault(w["line"], []).append(wi)
    d_start = np.array([res[wis[0]]["start"] - lines[li]["t"] for li, wis in by_line.items() if res[wis[0]] is not None])
    med = float(np.median(d_start))
    m = {"words": n, "aligned": len(ok), "mean_token_score": round(float(allsc.mean()), 3), "mean_word_score": round(float(sc.mean()), 3),
         "cov_word>=0.5": round(float((sc >= 0.5).sum() / n), 3), "cov_word>=0.3": round(float((sc >= 0.3).sum() / n), 3), "cov_word>=0.1": round(float((sc >= 0.1).sum() / n), 3),
         "frac_dur_lt40ms": round(float(np.mean([(r["end"] - r["start"]) < 0.04 for r in ok])), 3),
         "median_ctc_minus_lrclib_line_start_s": round(med, 3), "median_abs_delta_raw_s": round(float(np.median(np.abs(d_start))), 3),
         "median_abs_delta_after_offset_s": round(float(np.median(np.abs(d_start - med))), 3),
         "p90_abs_delta_after_offset_s": round(float(np.percentile(np.abs(d_start - med), 90)), 3),
         "lines": len(by_line), "lines_with_dev_gt1s": int((np.abs(d_start - med) > 1.0).sum())}
    return m, d_start


def vs_whisper(res, words, whisper_json):
    """Independent cross-check: CTC word times vs faster-whisper word times for LCS-matched words."""
    import difflib
    W = json.load(open(whisper_json, encoding="utf-8"))["segments"]
    ww = [(x, w["start"]) for s in W for w in s["words"] for x in norm_words(w["w"])]
    mw = [(re.sub(r"'", "", w["w"]), i) for i, w in enumerate(words)]
    sm = difflib.SequenceMatcher(None, [a for a, _ in ww], [a for a, _ in mw], autojunk=False)
    d = []
    for b in sm.get_matching_blocks():
        for k in range(b.size):
            r = res[mw[b.b + k][1]]
            if r is not None:
                d.append(r["start"] - ww[b.a + k][1])
    d = np.array(d)
    if not len(d):
        return {}
    return {"matched_words": len(d), "median_delta_s": round(float(np.median(d)), 3), "median_abs_delta_s": round(float(np.median(np.abs(d))), 3),
            "p90_abs_delta_s": round(float(np.percentile(np.abs(d), 90)), 3), "frac_within_100ms": round(float((np.abs(d) < 0.1).mean()), 3), "frac_within_250ms": round(float((np.abs(d) < 0.25).mean()), 3)}


if __name__ == "__main__":
    import torchaudio, uroman, num2words
    lines, meta = lyric_lines(SLUG)
    wav = load_stem16k(SLUG, STEM); dur = len(wav) / 16000
    uro = uroman.Uroman()
    with heavy("bench-words", threads=6):
        torch.set_num_threads(6)
        bundle = torchaudio.pipelines.MMS_FA
        t0 = time.time()
        model = bundle.get_model(with_star=False, dl_kwargs={"model_dir": os.path.join(os.environ["MVH_MODELS_DIR"], "mms_fa")}).eval(); t_load = time.time() - t0
        dct = bundle.get_dict(star=None)
        emp = os.path.join(OUT, f"{SLUG}_{STEM}_logp.npy")
        t0 = time.time()
        if os.path.exists(emp):
            logp = np.load(emp).astype(np.float32)
        else:
            logp = emissions(wav, model); np.save(emp, logp.astype(np.float16))
        t_em = time.time() - t0
        words, dropped = mms_prep(lines, dct, uro, lambda n: num2words.num2words(n))
        t0 = time.time()
        res0, notes0 = run_alignment(logp, lines, words, 0.0)
        m0, d0 = metrics(res0, lines, words)
        off = float(np.median(d0))
        use_off = off if abs(off) > 0.15 else 0.0
        res1, notes1 = run_alignment(logp, lines, words, use_off) if use_off else (res0, notes0)
        m1, d1 = metrics(res1, lines, words)
        t_al = time.time() - t0
    wj = os.path.join(sdir(SLUG, "whisper_cpu"), f"{SLUG}_whisper_{STEM}.json")
    xw = vs_whisper(res1, words, wj) if os.path.exists(wj) else {}
    summary = {"slug": SLUG, "stem": STEM, "duration_s": round(dur, 2), "model_load_s": round(t_load, 1), "emission_s": round(t_em, 1), "emission_rtf": round(t_em / dur, 3),
               "viterbi_s": round(t_al, 2), "frames": len(logp), "words_dropped_no_tokens": dropped, "global_offset_s_detected": round(off, 3), "offset_applied_s": use_off,
               "pass0": {**m0, "notes": notes0}, "final": {**m1, "notes": notes1}, "vs_whisper_word_starts": xw}
    json.dump(summary, open(os.path.join(OUT, f"{SLUG}_{STEM}_mms_summary.json"), "w"), indent=1, default=float)
    json.dump([{"line": w["line"], "w": w["w"], **({k: r[k] for k in ("start", "end", "score")} if r else {})} for w, r in zip(words, res1)], open(os.path.join(OUT, f"{SLUG}_{STEM}_mms_words.json"), "w"))
    json.dump([float(x) for x in d1], open(os.path.join(OUT, f"{SLUG}_{STEM}_line_deltas.json"), "w"))
    print(json.dumps(summary, default=float))
