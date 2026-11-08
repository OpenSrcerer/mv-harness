"""Task 6b: mouth_open envelope prototype, comparing gate definitions (raw CTC word spans / sustain-extended words / line spans), + per-voice tracks on newton.
Numbers only.  Usage: bw_mouth.py <slug>"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from bw_common import *
slug = sys.argv[1]
y = load_stem16k(slug); hop = 160; n = len(y) // hop
env_raw = np.sqrt((y[:n * hop].reshape(n, hop) ** 2).mean(1))
fs = 100.0; aa = 1 - np.exp(-1 / (0.010 * fs)); ar = 1 - np.exp(-1 / (0.060 * fs))
env = np.zeros(n); s = 0.0
for i, v in enumerate(env_raw):
    k = aa if v > s else ar
    s += k * (v - s); env[i] = s
mw = json.load(open(os.path.join(sdir(slug, "align_mms"), f"{slug}_lead_vocals_mms_words.json"), encoding="utf-8"))
byl = {}
for w in mw:
    if "start" in w:
        byl.setdefault(w["line"], []).append(w)
p95 = np.percentile(env[env > 0], 95)
floor = 0.1 * p95  # about -20 dB under p95


def gate_words(lines_subset=None, pad=0.08):
    g = np.zeros(n)
    for li in (lines_subset if lines_subset is not None else byl):
        for w in byl.get(li, []):
            g[max(0, int((w["start"] - pad) * 100)):int((w["end"] + pad) * 100) + 1] = 1
    return g


def gate_sustain(lines_subset=None, pad=0.08, max_hold=1.5):
    """word end extended to the next word start in the line; the last word of a line holds while env > floor for at most max_hold s"""
    g = np.zeros(n)
    for li in (lines_subset if lines_subset is not None else byl):
        ws = byl.get(li, [])
        for k, w in enumerate(ws):
            a = max(0, int((w["start"] - pad) * 100))
            if k + 1 < len(ws):
                b = int(ws[k + 1]["start"] * 100)
            else:
                b = int((w["end"] + pad) * 100)
                lim = min(n - 1, b + int(max_hold * 100))
                while b < lim and env[b] > floor:
                    b += 1
            g[a:b + 1] = 1
    return g


def gate_line(lines_subset=None, pad=0.08, max_hold=1.5):
    g = np.zeros(n)
    for li in (lines_subset if lines_subset is not None else byl):
        ws = byl.get(li, [])
        if not ws:
            continue
        a = max(0, int((ws[0]["start"] - pad) * 100)); b = int((ws[-1]["end"] + pad) * 100)
        lim = min(n - 1, b + int(max_hold * 100))
        while b < lim and env[b] > floor:
            b += 1
        g[a:b + 1] = 1
    return g


def stats(g):
    gs = np.convolve(g, np.ones(5) / 5, mode="same")
    tot = float((env ** 2).sum())
    return {"frac_time_open": round(float(g.mean()), 3), "energy_outside_gate": round(float((env[gs == 0] ** 2).sum() / tot), 4)}


res = {"slug": slug, "gates": {"word_spans": stats(gate_words()), "word_sustain": stats(gate_sustain()), "line_span_hold": stats(gate_line())}}
gs = np.convolve(gate_sustain(), np.ones(5) / 5, mode="same")
mo = env * gs; pp = np.percentile(mo[mo > 0], 95); mo = np.clip(mo / pp, 0, 1)
res["mouth_open_sustain"] = {"frames": n, "frac_nonzero": round(float((mo > 0.02).mean()), 3), "p50_when_open": round(float(np.median(mo[mo > 0.02])), 3)}
od = sdir(slug, "mouth_open"); np.save(os.path.join(od, f"{slug}_mouth_open_sustain_100hz.npy"), mo.astype(np.float32))
if slug == "newton-vs-nye":
    from sklearn.cluster import AgglomerativeClustering
    E = np.load(os.path.join(sdir(slug, "voices"), "emb_ecapa_lead_vocals.npy")); items = json.load(open(os.path.join(sdir(slug, "voices"), "items.json")))["ids"]
    En = E / np.linalg.norm(E, axis=1, keepdims=True)
    lab = AgglomerativeClustering(n_clusters=4, metric="cosine", linkage="average").fit_predict(En)
    line_voice = {i: int(l) for i, l in zip(items, lab) if i < 1000}
    # lines skipped as too short inherit the previous line's voice (neighbour rule)
    last = None
    for li in sorted(byl):
        if li in line_voice:
            last = line_voice[li]
        elif last is not None:
            line_voice[li] = last
    tracks = {}
    for v in sorted(set(line_voice.values())):
        subset = [li for li, vv in line_voice.items() if vv == v]
        g = gate_sustain(subset); tracks[v] = g
    allg = np.stack(list(tracks.values()))
    overlap = float((allg.sum(0) > 1).sum() / max(1, (allg.sum(0) > 0).sum()))
    res["per_voice"] = {"voices": {f"V{k}": {"lines": int(sum(1 for vv in line_voice.values() if vv == k)), "frac_time_open": round(float(g.mean()), 3)} for k, g in tracks.items()},
                        "frac_of_open_frames_where_two_voices_overlap": round(overlap, 4)}
json.dump(res, open(os.path.join(od, f"{slug}_mouth_summary.json"), "w"), indent=1)
print(json.dumps(res))
