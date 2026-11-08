"""Task 4d: synthetic test of repeated-section expansion.  Jeremy's LRCLIB lines contain repeats (11 duplicate lines).
We pretend the supplied text is the compact version (first occurrence of every line only), map the faster-whisper segments to compact lines
(rapidfuzz), expand the sequence, take ASR segment starts as line starts, and align with MMS_FA (cached emissions, CPU Viterbi only).
Compared with the full LRCLIB timing.  Numbers only."""
import sys, os, json, re
sys.argv = ["x", "jeremy"]
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from rapidfuzz import fuzz
import bw_align as A
from bw_common import *
slug = "jeremy"
lines, _ = lyric_lines(slug)
key = lambda t: " ".join(norm_words(t))
seen = {}; compact = []
for l in lines:
    k = key(l["text"])
    if k not in seen:
        seen[k] = len(compact); compact.append(l)
truth_ids = [seen[key(l["text"])] for l in lines]
W = json.load(open(os.path.join(sdir(slug, "whisper_cpu"), f"{slug}_whisper_lead_vocals.json"), encoding="utf-8"))["segments"]
segs = [(s["start"], s["end"], " ".join(norm_words(s["text"]))) for s in W if s["words"]]
ctext = [key(l["text"]) for l in compact]
seq = []
for st, en, tx in segs:
    sc = [fuzz.token_set_ratio(tx, c) if len(tx) > 3 else 0 for c in ctext]
    # token_set_ratio rewards subsets; blend with plain ratio to avoid matching a short fragment to everything
    sc = [0.5 * a + 0.5 * fuzz.ratio(tx, c) for a, c in zip(sc, ctext)]
    j = int(np.argmax(sc)); seq.append((st, en, j, sc[j]))
# group consecutive ASR segments mapping to the same compact line (a line split by the ASR in two) -> one instance
inst = []
for st, en, j, sc in seq:
    if sc < 45:
        continue
    if inst and inst[-1]["id"] == j and st - inst[-1]["end"] < 1.5:
        inst[-1]["end"] = en; continue
    inst.append({"id": j, "start": st, "end": en, "score": sc})
import difflib
sm = difflib.SequenceMatcher(None, [i["id"] for i in inst], truth_ids, autojunk=False)
matched = sum(b.size for b in sm.get_matching_blocks())
res = {"lines_full": len(lines), "lines_compact": len(compact), "asr_segments": len(segs), "expanded_instances": len(inst),
       "sequence_recall_vs_full": round(matched / len(truth_ids), 3), "sequence_precision": round(matched / max(1, len(inst)), 3)}
# per-line time agreement: an instance is right if some truth line with the same id starts within 2 s of the instance (after global offset ~0)
ok = 0
for i in inst:
    if any(truth_ids[k] == i["id"] and abs(lines[k]["t"] - i["start"]) <= 2.0 for k in range(len(lines))):
        ok += 1
res["instances_timing_consistent_with_lrclib_2s"] = round(ok / max(1, len(inst)), 3)
# align the expanded text with ASR starts as line starts
exp_lines = [{"t": i["start"], "text": compact[i["id"]]["text"]} for i in inst]
import torchaudio, uroman, num2words
bundle = torchaudio.pipelines.MMS_FA; dct = bundle.get_dict(star=None); uro = uroman.Uroman()
logp = np.load(os.path.join(sdir(slug, "align_mms"), f"{slug}_lead_vocals_logp.npy")).astype(np.float32)
words, _ = A.mms_prep(exp_lines, dct, uro, lambda n: num2words.num2words(n))
r, notes = A.run_alignment(logp, exp_lines, words, 0.0)
m, d = A.metrics(r, exp_lines, words)
# compare each expanded-instance first word with the nearest LRCLIB-aligned (full) MMS word start of the same line id
full = json.load(open(os.path.join(sdir(slug, "align_mms"), f"{slug}_lead_vocals_mms_words.json"), encoding="utf-8"))
fl = {}
for w in full:
    if "start" in w:
        fl.setdefault(w["line"], w["start"]); fl[w["line"]] = min(fl[w["line"]], w["start"])
dd = []
by = {}
for wi, w in enumerate(words):
    by.setdefault(w["line"], []).append(wi)
for k, wis in by.items():
    if r[wis[0]] is None:
        continue
    cand = [fl[q] for q in range(len(lines)) if truth_ids[q] == inst[k]["id"] and q in fl]
    if cand:
        dd.append(min(abs(r[wis[0]]["start"] - c) for c in cand))
dd = np.array(dd)
res["expanded_alignment"] = {"mean_token_score": m["mean_token_score"], "cov_word>=0.3": m["cov_word>=0.3"], "words": m["words"],
                             "median_abs_line_start_vs_full_alignment_s": round(float(np.median(dd)), 3), "frac_within_250ms": round(float((dd <= 0.25).mean()), 3), "n": int(len(dd))}
json.dump(res, open(os.path.join(sdir(slug, "align_mms"), "jeremy_expansion_test.json"), "w"), indent=1)
print(json.dumps(res))
