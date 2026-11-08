"""Task 7 input: candidate MEASURED alignment-gate statistics per song, from the stored MMS / whisper / LRCLIB outputs. Numbers only."""
import sys, os, json, difflib, re
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from bw_common import *
out = {}
for slug in ("jeremy", "newton-vs-nye"):
    lines, _ = lyric_lines(slug)
    mw = json.load(open(os.path.join(sdir(slug, "align_mms"), f"{slug}_lead_vocals_mms_words.json"), encoding="utf-8"))
    deltas = json.load(open(os.path.join(sdir(slug, "align_mms"), f"{slug}_lead_vocals_line_deltas.json")))
    off = float(np.median(deltas))
    by = {}
    for w in mw:
        by.setdefault(w["line"], []).append(w)
    ls, dev, wc = [], [], []
    for li, ws in sorted(by.items()):
        ws = [w for w in ws if "start" in w]
        if not ws:
            continue
        ls.append(np.mean([w["score"] for w in ws])); dev.append(abs(ws[0]["start"] - lines[li]["t"] - off))
    ls, dev = np.array(ls), np.array(dev)
    bad = dev > 1.0
    # AUC of (1 - mean line score) as predictor of 'line start > 1 s from LRCLIB+offset'
    auc = None
    if bad.any() and (~bad).any():
        pos, neg = (1 - ls[bad]), (1 - ls[~bad])
        auc = float(np.mean([(p > q) + 0.5 * (p == q) for p in pos for q in neg]))
    # words matched to whisper: agreement after removing the median bias
    W = json.load(open(os.path.join(sdir(slug, "whisper_cpu"), f"{slug}_whisper_lead_vocals.json"), encoding="utf-8"))["segments"]
    ww = [(x, w["start"]) for s in W for w in s["words"] for x in norm_words(w["w"])]
    mm = [(re.sub(r"'", "", w["w"]), i) for i, w in enumerate(mw)]
    sm = difflib.SequenceMatcher(None, [a for a, _ in ww], [a for a, _ in mm], autojunk=False)
    d = [mw[mm[b.b + k][1]]["start"] - ww[b.a + k][1] for b in sm.get_matching_blocks() for k in range(b.size) if "start" in mw[mm[b.b + k][1]]]
    d = np.array(d); dc = d - np.median(d)
    sc_all = np.array([w["score"] for w in mw if "start" in w])
    out[slug] = {"n_lines": len(ls), "lrclib_offset_s": round(off, 3),
                 "frac_lines_start_within_0.5s_of_lrclib+offset": round(float((dev <= 0.5).mean()), 3),
                 "frac_lines_start_within_1.0s": round(float((dev <= 1.0).mean()), 3), "frac_lines_start_within_2.0s": round(float((dev <= 2.0).mean()), 3),
                 "line_mean_score_p10_p50_p90": [round(float(np.percentile(ls, q)), 3) for q in (10, 50, 90)],
                 "auc_low_line_score_flags_bad_line(>1s)": None if auc is None else round(auc, 3), "n_bad_lines": int(bad.sum()),
                 "whisper_matched_words": int(len(d)), "whisper_bias_s": round(float(np.median(d)), 3),
                 "whisper_agree_within_250ms_raw": round(float((np.abs(d) < 0.25).mean()), 3), "whisper_agree_within_250ms_bias_removed": round(float((np.abs(dc) < 0.25).mean()), 3),
                 "words_score>=0.5": round(float((sc_all >= 0.5).mean()), 3), "words_score>=0.3": round(float((sc_all >= 0.3).mean()), 3), "words_score>=0.1": round(float((sc_all >= 0.1).mean()), 3),
                 "words_score<0.01": round(float((sc_all < 0.01).mean()), 3)}
json.dump(out, open(os.path.join(sdir("jeremy", "align_mms"), "gate_stats.json"), "w"), indent=1)
print(json.dumps(out))
