"""Task 3: faster-whisper large-v3 int8 CPU on lead_vocals (VAD, word ts, condition_on_previous_text=False) + hallucination filter + match score.
Usage: bw_whisper.py <slug> [stem]      Prints numbers only, never text."""
import sys, os, time, json, re, collections, difflib
sys.path.insert(0, r"C:\Users\OpenSrcerer\Desktop\playground\mv-harness\scripts")
sys.path.insert(0, os.path.dirname(__file__))
from heavy_lock import heavy, apply_thread_limits
apply_thread_limits(6)
import numpy as np
from bw_common import *
slug = sys.argv[1]; stem = sys.argv[2] if len(sys.argv) > 2 else "lead_vocals"
NONLYRIC = re.compile(r"^\s*[\(\[\*♪].*[\)\]\*♪]?\s*$|music|applause|subtitles|amara|thanks for watching", re.I)
def filter_segments(segs):
    kept, dropped = [], collections.Counter()
    for s in segs:
        w = [x["w"].strip().lower() for x in s["words"]]
        if not w: dropped["empty"] += 1; continue
        if NONLYRIC.search(s["text"]): dropped["non_lyric_tag"] += 1; continue
        grams = collections.Counter(tuple(w[i:i+3]) for i in range(len(w) - 2))
        if grams and grams.most_common(1)[0][1] >= 3 and len(w) >= 6: dropped["ngram_loop"] += 1; continue
        if len(w) >= 8 and len(set(w)) / len(w) < 0.3: dropped["low_unique_ratio"] += 1; continue
        if s["compression_ratio"] > 2.4 and s["avg_logprob"] < -1.0: dropped["compress_logprob"] += 1; continue
        if s["no_speech_prob"] > 0.8 and s["avg_logprob"] < -1.0: dropped["no_speech"] += 1; continue
        if sum(1 for x in s["words"] if x["end"] - x["start"] < 0.02) / len(w) > 0.5: dropped["zero_dur_words"] += 1; continue
        kept.append(s)
    return kept, dict(dropped)
def match(asr_words, ref_words):
    sm = difflib.SequenceMatcher(None, asr_words, ref_words, autojunk=False)
    m = sum(b.size for b in sm.get_matching_blocks())
    p = m / max(1, len(asr_words)); r = m / max(1, len(ref_words))
    return {"lcs_matched": m, "precision": round(p, 3), "recall": round(r, 3), "f1": round(2 * p * r / max(1e-9, p + r), 3)}
a = load_stem16k(slug, stem); dur = len(a) / 16000
out_dir = sdir(slug, "whisper_cpu")
with heavy("bench-words", gpu=False, threads=6) as slot:
    from faster_whisper import WhisperModel
    t0 = time.time()
    m = WhisperModel(os.path.join(os.environ["MVH_MODELS_DIR"], "faster-whisper", "large-v3"), device="cpu", compute_type="int8", cpu_threads=6)
    t_load = time.time() - t0
    t0 = time.time()
    segs_it, info = m.transcribe(a, word_timestamps=True, condition_on_previous_text=False, beam_size=5, vad_filter=True, language="en")
    segs = []
    for s in segs_it:
        segs.append({"start": s.start, "end": s.end, "text": s.text, "avg_logprob": s.avg_logprob, "no_speech_prob": s.no_speech_prob,
                     "compression_ratio": s.compression_ratio, "words": [{"w": w.word, "start": w.start, "end": w.end, "p": w.probability} for w in s.words]})
    t_run = time.time() - t0
kept, dropped = filter_segments(segs)
allw = [w for s in segs for w in s["words"]]; keptw = [w for s in kept for w in s["words"]]
ref_lines, meta = lyric_lines(slug)
ref = [w for l in ref_lines for w in norm_words(l["text"])]
asr = [x for w in keptw for x in norm_words(w["w"])]
asr_raw = [x for w in allw for x in norm_words(w["w"])]
res = {"slug": slug, "stem": stem, "duration_s": round(dur, 2), "load_s": round(t_load, 1), "transcribe_s": round(t_run, 1), "rtf": round(t_run / dur, 3),
       "language": info.language, "language_prob": round(info.language_probability, 3), "segments": len(segs), "segments_kept": len(kept),
       "words": len(allw), "words_kept": len(keptw), "dropped": dropped, "ref_words": len(ref),
       "mean_word_prob": round(float(np.mean([w["p"] for w in keptw])), 3) if keptw else None,
       "frac_words_p_lt_0.5": round(float(np.mean([w["p"] < 0.5 for w in keptw])), 3) if keptw else None,
       "lyrics_match_score": match(asr, ref), "lyrics_match_score_unfiltered": match(asr_raw, ref),
       "asr_first_t": round(keptw[0]["start"], 2) if keptw else None, "asr_last_t": round(keptw[-1]["end"], 2) if keptw else None}
json.dump({"segments": segs, "kept_idx": [i for i, s in enumerate(segs) if s in kept]}, open(os.path.join(out_dir, f"{slug}_whisper_{stem}.json"), "w", encoding="utf-8"))
json.dump(res, open(os.path.join(out_dir, f"{slug}_whisper_{stem}_summary.json"), "w"), indent=1)
print(json.dumps(res))
