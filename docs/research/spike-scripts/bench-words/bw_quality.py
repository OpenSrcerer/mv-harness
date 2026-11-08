"""Task 4c: acoustic cross-check of word start times (no ground truth exists for these songs).
For each timing source (MMS CTC, stable-ts, faster-whisper) measure, against onsets of the vocal-stem energy flux:
  * median signed lag of word starts to the nearest onset within +/-250 ms,
  * hit rate (word start within 60 ms of an onset) vs a shifted-by-+0.5 s baseline (chance level) => lift.
Numbers only.  Usage: bw_quality.py <slug>"""
import sys, os, json, re
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from bw_common import *
import librosa
slug = sys.argv[1]
wav = load_stem16k(slug)
hop = 160  # 10 ms
S = librosa.feature.melspectrogram(y=wav, sr=16000, n_fft=512, hop_length=hop, n_mels=40, fmin=80, fmax=7600)
L = librosa.power_to_db(S + 1e-10)
flux = np.maximum(0, np.diff(L, axis=1)).mean(0)
flux = np.convolve(flux, np.ones(3) / 3, mode="same")
thr = np.percentile(flux, 75)
pk = [i for i in range(2, len(flux) - 2) if flux[i] >= thr and flux[i] == flux[i - 2:i + 3].max()]
onsets = (np.array(pk) + 1) * hop / 16000.0
def stats(starts):
    starts = np.asarray(starts); lag = []
    for s in starts:
        j = np.argmin(np.abs(onsets - s)); d = s - onsets[j]
        if abs(d) <= 0.25: lag.append(d)
    lag = np.array(lag)
    def hit(x): return float(np.mean([np.min(np.abs(onsets - s)) <= 0.06 for s in x]))
    base = float(np.mean([hit(starts + sh) for sh in (0.5, -0.5, 0.35, -0.35)]))
    h = hit(starts)
    return {"n": len(starts), "within250ms_frac": round(len(lag) / len(starts), 3), "median_lag_s": round(float(np.median(lag)), 3) if len(lag) else None,
            "hit60ms": round(h, 3), "chance_hit60ms": round(base, 3), "lift": round(h / max(base, 1e-6), 2)}
res = {"slug": slug, "n_onsets": len(onsets)}
mp = os.path.join(sdir(slug, "align_mms"), f"{slug}_lead_vocals_mms_words.json")
mw = json.load(open(mp, encoding="utf-8"))
res["mms"] = stats([w["start"] for w in mw if "start" in w])
res["mms_good_score>=0.5"] = stats([w["start"] for w in mw if "start" in w and w["score"] >= 0.5])
res["mms_poor_score<0.1"] = stats([w["start"] for w in mw if "start" in w and w["score"] < 0.1])
sp = os.path.join(sdir(slug, "align_stablets"), f"{slug}_lead_vocals_stablets_words.json")
if os.path.exists(sp): res["stablets"] = stats([w["start"] for w in json.load(open(sp, encoding="utf-8"))])
wp = os.path.join(sdir(slug, "whisper_cpu"), f"{slug}_whisper_lead_vocals.json")
W = json.load(open(wp, encoding="utf-8"))["segments"]
res["whisper"] = stats([w["start"] for s in W for w in s["words"]])
# LRCLIB line starts (raw, and shifted by the MMS median offset)
lines, _ = lyric_lines(slug)
d = json.load(open(os.path.join(sdir(slug, "align_mms"), f"{slug}_lead_vocals_line_deltas.json")))
med = float(np.median(d))
res["lrclib_line_starts_raw"] = stats([l["t"] for l in lines])
res["lrclib_line_starts_plus_median_offset"] = stats([l["t"] + med for l in lines])
res["mms_line_starts"] = stats([min(w["start"] for w in mw if w["line"] == li and "start" in w) for li in range(len(lines))])
json.dump(res, open(os.path.join(sdir(slug, "align_mms"), f"{slug}_onset_check.json"), "w"), indent=1)
print(json.dumps(res))
