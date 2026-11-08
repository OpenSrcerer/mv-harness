"""Task 4b: stable-ts align (faster-whisper large-v3 int8 CPU) of the LRCLIB text, as the fallback to MMS_FA.  Numbers only.
Usage: bw_stablets.py <slug> [stem]"""
import sys, os, time, json, re
sys.path.insert(0, r"C:\Users\OpenSrcerer\Desktop\playground\mv-harness\scripts"); sys.path.insert(0, os.path.dirname(__file__))
from heavy_lock import heavy, apply_thread_limits
apply_thread_limits(6)
import numpy as np
from bw_common import *
slug = sys.argv[1]; stem = sys.argv[2] if len(sys.argv) > 2 else "lead_vocals"
lines, meta = lyric_lines(slug)
wav = load_stem16k(slug, stem); dur = len(wav) / 16000
text = "\n".join(l["text"] for l in lines)
out = sdir(slug, "align_stablets")
with heavy("bench-words", threads=6):
    import stable_whisper
    m = stable_whisper.load_faster_whisper(os.path.join(os.environ["MVH_MODELS_DIR"], "faster-whisper", "large-v3"), device="cpu", compute_type="int8", cpu_threads=6)
    t0 = time.time()
    r = m.align(wav, text, language="en", original_split=True, vad=False)
    t_run = time.time() - t0
segs = r.segments
words = [w for s in segs for w in s.words]
d = [(s.start - l["t"]) for s, l in zip(segs, lines)] if len(segs) == len(lines) else []
dur_w = np.array([w.end - w.start for w in words])
res = {"slug": slug, "stem": stem, "align_s": round(t_run, 1), "rtf": round(t_run / dur, 3), "segments": len(segs), "lines": len(lines), "words": len(words),
       "frac_word_dur_lt40ms": round(float((dur_w < 0.04).mean()), 3), "mean_word_dur_s": round(float(dur_w.mean()), 3),
       "frac_words_prob_ge_0.5": round(float(np.mean([getattr(w, "probability", 0) >= 0.5 for w in words])), 3),
       "mean_word_prob": round(float(np.mean([getattr(w, "probability", 0) for w in words])), 3)}
if d:
    d = np.array(d); med = float(np.median(d))
    res.update({"median_delta_line_start_s": round(med, 3), "median_abs_delta_raw_s": round(float(np.median(np.abs(d))), 3),
                "median_abs_delta_after_offset_s": round(float(np.median(np.abs(d - med))), 3), "p90_abs_delta_after_offset_s": round(float(np.percentile(np.abs(d - med), 90)), 3)})
# agreement with MMS word starts (same text, same whitespace tokenisation => match by order when counts agree)
mp = os.path.join(sdir(slug, "align_mms"), f"{slug}_{stem}_mms_words.json")
if os.path.exists(mp):
    mw = json.load(open(mp, encoding="utf-8"))
    if len(mw) == len(words):
        dd = np.array([w.start - x["start"] for w, x in zip(words, mw) if "start" in x])
        res["vs_mms_word_starts"] = {"n": len(dd), "median_delta_s": round(float(np.median(dd)), 3), "median_abs_delta_s": round(float(np.median(np.abs(dd))), 3),
                                     "p90_abs_delta_s": round(float(np.percentile(np.abs(dd), 90)), 3), "frac_within_250ms": round(float((np.abs(dd) < 0.25).mean()), 3)}
    else:
        res["vs_mms_word_starts"] = {"skipped": f"word count differs {len(words)} vs {len(mw)}"}
json.dump([{"w": w.word.strip(), "start": w.start, "end": w.end, "p": getattr(w, "probability", None)} for w in words], open(os.path.join(out, f"{slug}_{stem}_stablets_words.json"), "w"))
json.dump(res, open(os.path.join(out, f"{slug}_{stem}_stablets_summary.json"), "w"), indent=1)
print(json.dumps(res))
