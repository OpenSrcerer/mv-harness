"""Task 6: Rhubarb Lip Sync on a 20 s sung excerpt (with -d aligned text via a temp file outside the repo, deleted afterwards) + mouth_open envelope prototype.
Numbers only on stdout.  Usage: bw_lipsync.py <slug> [excerpt_start_s]"""
import sys, os, json, time, subprocess, tempfile, shutil
sys.path.insert(0, r"C:\Users\OpenSrcerer\Desktop\playground\mv-harness\scripts"); sys.path.insert(0, os.path.dirname(__file__))
from heavy_lock import heavy, apply_thread_limits
apply_thread_limits(6)
import numpy as np, soundfile as sf
from bw_common import *
slug = sys.argv[1]; EX_LEN = 20.0
RB = os.environ.get("MVH_RHUBARB") or json.load(open(os.path.join(os.environ["LOCALAPPDATA"], "mvh", "config.json"), encoding="utf-8-sig"))["rhubarb"]
OPEN = {"A": 0.05, "B": 0.3, "C": 0.6, "D": 1.0, "E": 0.5, "F": 0.3, "G": 0.2, "H": 0.6, "X": 0.0}
lines, _ = lyric_lines(slug)
mw = json.load(open(os.path.join(sdir(slug, "align_mms"), f"{slug}_lead_vocals_mms_words.json"), encoding="utf-8"))
byl = {}
for w in mw:
    if "start" in w:
        byl.setdefault(w["line"], []).append(w)
lspan = {li: (min(x["start"] for x in ws), max(x["end"] for x in ws)) for li, ws in byl.items()}
# excerpt: the 20 s window with the most aligned-word seconds, snapped to line boundaries
best = None
cand_starts = [lspan[li][0] - 0.3 for li in lspan]
for t0 in cand_starts:
    inside = [li for li in lspan if lspan[li][0] >= t0 and lspan[li][1] <= t0 + EX_LEN]
    sec = sum(lspan[li][1] - lspan[li][0] for li in inside)
    if len(sys.argv) > 2:
        pass
    if best is None or sec > best[0]:
        best = (sec, t0, inside)
t0 = (lspan[int(sys.argv[2][1:])][0] - 0.3 if sys.argv[2].startswith("L") else float(sys.argv[2])) if len(sys.argv) > 2 else best[1]
inside = [li for li in lspan if lspan[li][0] >= t0 and lspan[li][1] <= t0 + EX_LEN]
st = sdir(slug, "rhubarb")
x, sr = sf.read(stem_path(slug), dtype="float32")
x = x.mean(1) if x.ndim > 1 else x
import soxr
y = soxr.resample(x, sr, 16000, quality="HQ")
seg = y[int(t0 * 16000):int((t0 + EX_LEN) * 16000)]
wav_path = os.path.join(st, f"{slug}_excerpt.wav"); sf.write(wav_path, seg, 16000, subtype="PCM_16")
tmpd = tempfile.mkdtemp(prefix="bw_rb_")  # outside the repo
dlg = os.path.join(tmpd, "dialog.txt")
with open(dlg, "w", encoding="utf-8") as f:
    f.write("\n".join(lines[li]["text"] for li in sorted(inside)))
out = {"slug": slug, "excerpt_start_s": round(t0, 2), "excerpt_len_s": EX_LEN, "lines_in_excerpt": sorted(inside), "words_in_excerpt": sum(len(byl[li]) for li in inside)}
runs = {}
try:
    with heavy("bench-words", threads=6):
        for name, extra in (("with_dialog", ["-d", dlg]), ("no_dialog", [])):
            jp = os.path.join(st, f"{slug}_rhubarb_{name}.json")
            t1 = time.time()
            r = subprocess.run([RB, "-f", "json", "-o", jp, *extra, wav_path], capture_output=True, text=True)
            runs[name] = {"rc": r.returncode, "secs": round(time.time() - t1, 2), "stderr_tail": r.stderr[-200:] if r.returncode else ""}
finally:
    shutil.rmtree(tmpd, ignore_errors=True)
out["temp_dialog_deleted"] = not os.path.exists(tmpd)
# analysis ------------------------------------------------------------
hop = 160  # 100 Hz
n = int(EX_LEN * 100)
rms = np.array([np.sqrt(np.mean(seg[i * hop:(i + 1) * hop] ** 2) + 1e-12) for i in range(n)])
db = 20 * np.log10(rms + 1e-9)
t = (np.arange(n) + 0.5) / 100.0
word_gate = np.zeros(n, bool)
for li in byl:
    for w in byl[li]:
        if not (t0 - 1 <= w["start"] < t0 + EX_LEN):
            continue
        a, b = int((w["start"] - t0) * 100), int((w["end"] - t0) * 100)
        word_gate[max(0, a):max(0, b) + 1] = True


def grid(cues):
    o = np.zeros(n); sh = np.array(["X"] * n)
    for c in cues:
        a, b = int(round(c["start"] * 100)), int(round(c["end"] * 100))
        o[a:b] = OPEN[c["value"]]; sh[a:b] = c["value"]
    return o, sh


for name in runs:
    if runs[name]["rc"] != 0:
        continue
    cues = json.load(open(os.path.join(st, f"{slug}_rhubarb_{name}.json"), encoding="utf-8"))["mouthCues"]
    o, sh = grid(cues)
    vals, cnt = np.unique(sh, return_counts=True)
    dur_cues = np.array([c["end"] - c["start"] for c in cues])
    # does the viseme track open where the voice is on?  correlation with the vocal level (dB, gated floor) and open-while-voiced rate
    voiced = db > (np.percentile(db, 95) - 25)
    d = {"cues": len(cues), "shape_counts": {str(v): int(c) for v, c in zip(vals, cnt)}, "median_cue_s": round(float(np.median(dur_cues)), 3), "cues_per_s": round(len(cues) / EX_LEN, 2),
         "corr_open_vs_rms_db": round(float(np.corrcoef(o, np.clip(db, db.max() - 50, None))[0, 1]), 3),
         "frac_X_during_word_spans": round(float(np.mean(sh[word_gate] == "X")), 3), "frac_nonX_outside_word_spans": round(float(np.mean(sh[~word_gate] != "X")), 3) if (~word_gate).any() else None,
         "frac_voiced_frames_nonX": round(float(np.mean(sh[voiced] != "X")), 3), "frac_unvoiced_frames_X": round(float(np.mean(sh[~voiced] == "X")), 3)}
    # onset agreement: viseme-open onsets vs word starts (within 100 ms)
    opens = np.array([c["start"] for c, p in zip(cues[1:], cues[:-1]) if p["value"] == "X" and c["value"] != "X"])
    wstarts = np.array([w["start"] - t0 for li in inside for w in byl[li]])
    if len(opens):
        d["open_onsets"] = int(len(opens)); d["open_onset_within_150ms_of_word_start"] = round(float(np.mean([np.min(np.abs(wstarts - o_)) <= 0.15 for o_ in opens])), 3)
    runs[name].update(d)
out["rhubarb"] = runs
if all(r["rc"] == 0 for r in runs.values()):
    a = json.load(open(os.path.join(st, f"{slug}_rhubarb_with_dialog.json"), encoding="utf-8"))["mouthCues"]
    b = json.load(open(os.path.join(st, f"{slug}_rhubarb_no_dialog.json"), encoding="utf-8"))["mouthCues"]
    ga, _ = grid(a); gb, _ = grid(b)
    out["with_vs_without_dialog_open_corr"] = round(float(np.corrcoef(ga, gb)[0, 1]), 3)
# mouth_open envelope prototype (full song): attack 10 ms / release 60 ms one-pole on |x| (100 Hz), gated by word spans (dilated 80 ms), per-song p95 gain
full_n = len(y) // hop
env_raw = np.array([np.sqrt(np.mean(y[i * hop:(i + 1) * hop] ** 2)) for i in range(full_n)])
fs = 100.0; a_att = 1 - np.exp(-1 / (0.010 * fs)); a_rel = 1 - np.exp(-1 / (0.060 * fs))
env = np.zeros(full_n); s = 0.0
for i, v in enumerate(env_raw):
    k = a_att if v > s else a_rel
    s += k * (v - s); env[i] = s
gate = np.zeros(full_n)
for li in byl:
    for w in byl[li]:
        a, b = int((w["start"] - 0.08) * 100), int((w["end"] + 0.08) * 100)
        gate[max(0, a):b + 1] = 1.0
gate_s = np.convolve(gate, np.ones(5) / 5, mode="same")
mo = env * gate_s; p95 = np.percentile(mo[mo > 0], 95) if (mo > 0).any() else 1.0
mo = np.clip(mo / p95, 0, 1)
vis_energy_out = float((env[gate_s == 0] ** 2).sum() / max(1e-12, (env ** 2).sum()))
np.save(os.path.join(st, f"{slug}_mouth_open_100hz.npy"), mo.astype(np.float32))
od = sdir(slug, "mouth_open"); np.save(os.path.join(od, f"{slug}_mouth_open_100hz.npy"), mo.astype(np.float32))
out["mouth_open"] = {"frames": int(full_n), "frac_gate_open": round(float(gate_s.mean()), 3), "frac_frames_nonzero": round(float((mo > 0.02).mean()), 3),
                     "ungated_energy_removed_by_gate": round(vis_energy_out, 4), "mean_when_gate_open": round(float(mo[gate_s > 0].mean()), 3)}
if len(runs) and runs.get("with_dialog", {}).get("rc") == 0:
    oi = int(t0 * 100); sl = mo[oi:oi + n]
    o_, _ = grid(json.load(open(os.path.join(st, f"{slug}_rhubarb_with_dialog.json"), encoding="utf-8"))["mouthCues"])
    out["mouth_open"]["corr_with_rhubarb_openness_in_excerpt"] = round(float(np.corrcoef(sl[:n], o_[:len(sl)])[0, 1]), 3)
json.dump(out, open(os.path.join(st, f"{slug}_lipsync_summary.json"), "w"), indent=1)
print(json.dumps(out))
