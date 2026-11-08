"""Prototype: offline spectral / dynamics / loudness / stereo / key+chord features at 100 Hz.

Purpose: measure speed + output sizes on the real test songs and sanity-check the viz port.
Not the harness; scratch research code.
"""
import json
import os
import sys
import time

import numpy as np
import soundfile as sf
from scipy import ndimage

T = {}


def tic(name):
    T[name] = time.perf_counter()


def toc(name):
    T[name] = time.perf_counter() - T[name]


path = sys.argv[1]
outdir = sys.argv[2]
os.makedirs(outdir, exist_ok=True)

FPS = 100
F_MIN, F_MAX, NB = 32.0, 16000.0, 128
MIN_DB, MAX_DB = -88.0, -18.0
TILT = 2.6

tic("load")
x, sr = sf.read(path, dtype="float32", always_2d=True)
toc("load")
L = x[:, 0]
R = x[:, 1] if x.shape[1] > 1 else x[:, 0]
mono = 0.5 * (L + R)
n = len(mono)
dur = n / sr
nfr = int(np.floor(dur * FPS)) + 1
centres = np.round(np.arange(nfr) * sr / FPS).astype(np.int64)
N = 2048 if sr <= 50000 else 4096
print(f"sr={sr} ch={x.shape[1]} dur={dur:.1f}s frames={nfr} N={N}")

# ---------------- STFT (centred, Blackman, 1/N like Web Audio AnalyserNode) -------------
tic("stft")
win = np.blackman(N).astype(np.float32)
pad = np.pad(mono, (N // 2, N // 2))
padS = np.pad(0.5 * (L - R), (N // 2, N // 2))
nbins = N // 2 + 1
P = np.empty((nfr, nbins), np.float32)      # power of mid (mono)
PS = np.empty((nfr, nbins), np.float32)     # power of side
ar = np.arange(N)
CH = 2048
for s in range(0, nfr, CH):
    c = centres[s:s + CH]
    idx = c[:, None] + ar[None, :]
    idx = np.minimum(idx, len(pad) - 1)
    X = np.fft.rfft(pad[idx] * win, axis=1) / N
    P[s:s + CH] = (X.real ** 2 + X.imag ** 2)
    X = np.fft.rfft(padS[idx] * win, axis=1) / N
    PS[s:s + CH] = (X.real ** 2 + X.imag ** 2)
toc("stft")

freqs = np.arange(nbins) * sr / N
binW = sr / N

# ---------------- 128 log bands, viz mapping (mean of per-bin dB; interp for narrow) ----------
tic("bands")
ratio = F_MAX / F_MIN
k = np.arange(NB)
f0 = F_MIN * ratio ** (k / NB)
f1 = F_MIN * ratio ** ((k + 1) / NB)
fc = np.sqrt(f0 * f1)
tilt = TILT * np.log2(fc / F_MIN)
W = np.zeros((NB, nbins), np.float32)
for b in range(NB):
    lo, hi = f0[b] / binW, f1[b] / binW
    if hi - lo < 1.0:
        c = fc[b] / binW
        i = int(np.floor(c)); fr = c - i
        W[b, i] += 1 - fr; W[b, i + 1] += fr
    else:
        i0, i1 = int(np.floor(lo)), min(nbins, int(np.ceil(hi)))
        W[b, i0:i1] = 1.0 / (i1 - i0)
DB = 10 * np.log10(P + 1e-20)               # == 20log10(|X|/N), AnalyserNode scale
DB = np.maximum(DB, -200)
band_db = DB @ W.T                          # (nfr, 128) mean of dB, like viz
band_raw = np.clip((band_db + tilt - MIN_DB) / (MAX_DB - MIN_DB), 0, None)
# per-song gain instead of AGC: 99.5th pct of per-frame max band -> 0.95
pk = np.percentile(band_raw.max(axis=1), 99.5)
g = 0.95 / max(pk, 0.2)
v = band_raw * g
band_norm = np.minimum(v / (1 + 0.18 * v), 1.0).astype(np.float32)


def bidx(f):
    return int(np.clip(round(np.log(f / F_MIN) / np.log(ratio) * NB), 0, NB - 1))


RNG = {"bass": (32, 150), "mid": (150, 2200), "high": (2200, 16000)}
viz3 = {name: band_norm[:, bidx(a):bidx(b) + 1].mean(axis=1) for name, (a, b) in RNG.items()}

# physical band energies (dB of mean power) - studio bands
STUDIO = {"sub": (20, 60), "bass": (60, 150), "lowmid": (150, 500), "mid": (500, 2000),
          "highmid": (2000, 4000), "presence": (4000, 6000), "air": (6000, 16000),
          "viz_bass": (32, 150), "viz_mid": (150, 2200), "viz_high": (2200, 16000), "kick": (35, 100)}
band_pow_db = {}
for name, (a, b) in STUDIO.items():
    m = (freqs >= a) & (freqs < b)
    band_pow_db[name] = 10 * np.log10(P[:, m].sum(axis=1) + 1e-20)
toc("bands")

# ---------------- kick envelope: straight port of viz _hitEnvelope (causal) -------------
tic("kick")
i0 = max(1, int(np.ceil(35 / binW))); i1 = max(i0, int(np.floor(100 / binW)))
kickDb = 10 * np.log10(P[:, i0:i1 + 1].mean(axis=1) + 1e-20)
eKick = np.maximum(0, (kickDb + 2 - MIN_DB) / (MAX_DB - MIN_DB))


def hit_envelope(e, dt=1.0 / FPS, gateDb=None, hitThreshold=0.35, hitRelease=0.18,
                 hitFloor=0.05, refFloor=0.075, rearmDb=4.0, ref_override=None):
    dbRange = MAX_DB - MIN_DB
    fast = slow = e[0]; ref = 0.2; cur = 0.0
    armed = True; hitLevel = 0.0; minSince = 0.0; attackV = 0.0; attackLevel = 0.0
    aF = 1 - np.exp(-dt / 0.008); aS = 1 - np.exp(-dt / 0.09); refDecay = np.exp(-dt / 20)
    aRel = 1 - np.exp(-dt / hitRelease)
    out = np.zeros(len(e), np.float32); raw = np.zeros(len(e), np.float32)
    rise_out = np.zeros(len(e), np.float32)
    prev = 0.0
    thr = min(max(hitThreshold, 0), 0.95)
    for i in range(len(e)):
        ei = e[i]
        fast += (ei - fast) * aF
        slow += (ei - slow) * aS
        rise = max(0.0, fast - slow)
        rise_out[i] = rise
        gate = 1.0
        if gateDb is not None:
            levelDb = fast * dbRange + MIN_DB - 2
            t = min(max((levelDb - (gateDb - 3)) / 6, 0), 1)
            gate = t * t * (3 - 2 * t)
        attackEnded = False
        if rise > cur:
            cur = rise
        elif cur > 0 and rise < cur * 0.5:
            if cur > hitFloor:
                ref += (cur - ref) * (0.3 if cur < ref else 0.12)
            cur = 0.0
            attackEnded = True
        ref = max(refFloor, ref * refDecay)
        r_use = ref if ref_override is None else max(refFloor, ref_override[i])
        xx = rise / r_use
        vv = min(max((xx - thr) / (1.15 - thr), 0), 1)
        vv = vv * vv * (3 - 2 * vv) * gate
        minSince = min(minSince, fast)
        if (not armed) and (hitLevel - minSince > rearmDb / dbRange or xx > 2.2):
            armed = True
        if not armed:
            vv = 0.0
        if vv > attackV:
            attackV = vv
        if fast > attackLevel:
            attackLevel = fast
        if attackEnded:
            if attackV > 0.3 and armed:
                armed = False; hitLevel = attackLevel; minSince = fast
            attackV = 0.0; attackLevel = fast
        raw[i] = vv
        prev = vv if vv > prev else prev + (vv - prev) * aRel
        out[i] = prev
    return out, raw, rise_out


kick_env, kick_raw, kick_rise = hit_envelope(eKick, gateDb=-46)
eMid = viz3["mid"]; eHigh = viz3["high"]
mid_env, mid_raw, _ = hit_envelope(eMid)
high_env, high_raw, _ = hit_envelope(eHigh)


def events_from_raw(raw, min_gap=0.08, thr=0.3):
    """Discrete hits: local maxima of the raw (no-release) envelope above thr."""
    pk = (raw > thr) & (raw >= np.roll(raw, 1)) & (raw > np.roll(raw, -1))
    ii = np.flatnonzero(pk)
    out = []
    last = -1e9
    for i in ii:
        if (i - last) / FPS >= min_gap:
            out.append((i / FPS, float(raw[i]))); last = i
    return out


kick_events = events_from_raw(kick_raw)

# offline variant: reference = centred rolling median of attack peaks (+-8 s), no warm-up
rise_pk = (kick_rise > 0.05) & (kick_rise >= np.roll(kick_rise, 1)) & (kick_rise > np.roll(kick_rise, -1))
ref_series = np.full(nfr, np.nan, np.float32); ref_series[rise_pk] = kick_rise[rise_pk]
tt = np.flatnonzero(rise_pk)
if len(tt) > 3:
    vals = kick_rise[tt]
    half = 8 * FPS
    lo = np.searchsorted(tt, np.arange(nfr) - half); hi = np.searchsorted(tt, np.arange(nfr) + half)
    med = np.array([np.median(vals[a:b]) if b > a else np.nan for a, b in zip(lo, hi)], np.float32)
    med = np.where(np.isnan(med), np.nanmedian(vals), med)
    # viz's ref tracks a "typical" attack ~ slightly below the median of attack peaks
    _, kick_raw_off, _ = hit_envelope(eKick, gateDb=-46, ref_override=med)
    kick_events_off = events_from_raw(kick_raw_off)
else:
    kick_events_off = []
toc("kick")

# ---------------- per-band spectral flux onsets with centred adaptive threshold -----------
tic("flux")
dnorm = np.diff(band_norm, axis=0, prepend=band_norm[:1])
dnorm = np.maximum(dnorm, 0)
FLUXR = {"low": (32, 260), "mid": (300, 2200), "high": (2500, 14000)}
flux = {nm: dnorm[:, bidx(a):bidx(b) + 1].mean(axis=1) for nm, (a, b) in FLUXR.items()}
onsets = {}
for nm, f in flux.items():
    # centred moving mean over +-0.24 s (viz uses trailing 48 frames ~0.33s at 144 Hz)
    mean = ndimage.uniform_filter1d(f, size=49, mode="nearest")
    thr = mean * (1.55 if nm == "low" else 1.7) + 0.012
    pk = (f > thr) & (f >= ndimage.maximum_filter1d(f, size=7, mode="nearest"))
    ii = np.flatnonzero(pk)
    gap = {"low": 0.16, "mid": 0.12, "high": 0.08}[nm]
    ev = []; last = -1e9
    for i in ii:
        if (i - last) / FPS >= gap:
            ev.append((i / FPS, float(min(1, 0.55 + (f[i] - thr[i]) / (thr[i] + 1e-4) * 0.3)))); last = i
    onsets[nm] = ev
toc("flux")

# ---------------- RMS / peak / spectral shape / stereo --------------------------------
tic("timbre_stereo")
cs = lambda a: np.concatenate([[0.0], np.cumsum(a.astype(np.float64))])
half = N // 2
lo_i = np.clip(centres - half, 0, n); hi_i = np.clip(centres + half, 0, n)
cnt = np.maximum(hi_i - lo_i, 1)
cL2, cR2, cLR = cs(L * L), cs(R * R), cs(L * R)
sL2 = (cL2[hi_i] - cL2[lo_i]); sR2 = (cR2[hi_i] - cR2[lo_i]); sLR = (cLR[hi_i] - cLR[lo_i])
ms = (sL2 + sR2) / 2 / cnt
rms_db = 10 * np.log10(ms + 1e-20)
corr = sLR / np.sqrt(sL2 * sR2 + 1e-20)
side = (sL2 + sR2 - 2 * sLR) / 4; mid_ = (sL2 + sR2 + 2 * sLR) / 4
width = side / (side + mid_ + 1e-20)        # 0 mono .. 0.5 decorrelated .. 1 out of phase
balance_db = 10 * np.log10((sL2 + 1e-20) / (sR2 + 1e-20))
# per-band width from the side STFT
bw = {}
for nm, (a, b) in RNG.items():
    m = (freqs >= a) & (freqs < b)
    sp = PS[:, m].sum(axis=1); mp = P[:, m].sum(axis=1)
    bw[nm] = sp / (sp + mp + 1e-20)
# spectral shape on 32 Hz .. 16 kHz
m = (freqs >= 32) & (freqs <= 16000)
Pm = P[:, m]; fm = freqs[m]
tot = Pm.sum(axis=1) + 1e-20
centroid = (Pm @ fm) / tot
csum = np.cumsum(Pm, axis=1)
rolloff = fm[np.minimum((csum < 0.85 * tot[:, None]).sum(axis=1), len(fm) - 1)]
flatness = np.exp(np.mean(np.log(Pm + 1e-20), axis=1)) / (Pm.mean(axis=1) + 1e-20)
bandwidth = np.sqrt(((fm[None, :] - centroid[:, None]) ** 2 * Pm).sum(axis=1) / tot)
toc("timbre_stereo")

# ---------------- EBU R128 loudness ------------------------------------------------------
tic("loudness")
import pyloudnorm as pyln
meter = pyln.Meter(sr)
kw = []
for ch in (L, R):
    y = ch.astype(np.float64)
    for f in meter._filters.values():
        y = f.apply_filter(y)
    kw.append(y)
z = cs(kw[0] ** 2 + kw[1] ** 2)


def lufs_win(wsec):
    hw = int(round(wsec * sr / 2))
    a = np.clip(centres - hw, 0, n); b = np.clip(centres + hw, 0, n)
    return -0.691 + 10 * np.log10((z[b] - z[a]) / (2 * hw) + 1e-20)


lufs_m = lufs_win(0.4)      # centred (spec meter is trailing: spec_t = t + 0.2 s)
lufs_s = lufs_win(3.0)      # centred (spec_t = t + 1.5 s)
toc("loudness")
tic("pyln_I_LRA")
I = meter.integrated_loudness(x.astype(np.float64))
LRA = meter.loudness_range(x.astype(np.float64))
toc("pyln_I_LRA")
true_peak_sample = float(20 * np.log10(np.abs(x).max() + 1e-20))

# ---------------- key + chords (librosa chroma + templates + Viterbi) ---------------------
tic("librosa_import")
import librosa
toc("librosa_import")
tic("key_chords")
y22 = librosa.resample(mono, orig_sr=sr, target_sr=22050, res_type="soxr_hq")
yh = librosa.effects.harmonic(y22, margin=2.0)
HOP = 512
chroma = librosa.feature.chroma_cqt(y=yh, sr=22050, hop_length=HOP, bins_per_octave=36, n_octaves=6, fmin=librosa.note_to_hz("C1"))
ct = librosa.times_like(chroma, sr=22050, hop_length=HOP)
# key: Krumhansl-Kessler + Temperley-ish profile correlation
KK_MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KK_MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
prof = np.stack([np.roll(KK_MAJ, i) for i in range(12)] + [np.roll(KK_MIN, i) for i in range(12)])
prof = (prof - prof.mean(1, keepdims=True)) / prof.std(1, keepdims=True)


def key_scores(c):
    c = (c - c.mean()) / (c.std() + 1e-9)
    return prof @ c / 12


gs = key_scores(chroma.mean(axis=1))
order = np.argsort(gs)[::-1]
key_global = [(NAMES[i % 12] + (" major" if i < 12 else " minor"), float(gs[i])) for i in order[:3]]
# windowed key (8 s windows, 2 s hop) + Viterbi smoothing with sticky transitions
wlen = int(8 * 22050 / HOP); whop = int(2 * 22050 / HOP)
wk = []
for s0 in range(0, max(1, chroma.shape[1] - wlen + 1), whop):
    wk.append(key_scores(chroma[:, s0:s0 + wlen].mean(axis=1)))
wk = np.array(wk).T  # 24 x W
probk = np.exp(wk * 8); probk /= probk.sum(0, keepdims=True)
trans = librosa.sequence.transition_loop(24, 0.95)
kpath = librosa.sequence.viterbi(probk, trans)
key_changes = []
for i, kk in enumerate(kpath):
    if i == 0 or kk != kpath[i - 1]:
        key_changes.append((i * 2.0, NAMES[kk % 12] + (" major" if kk < 12 else " minor")))
# chords: 24 maj/min triad templates + N, Viterbi with self-transition
tmpl = []
labels = []
for r in range(12):
    t = np.zeros(12); t[[r, (r + 4) % 12, (r + 7) % 12]] = 1; tmpl.append(t); labels.append(NAMES[r])
for r in range(12):
    t = np.zeros(12); t[[r, (r + 3) % 12, (r + 7) % 12]] = 1; tmpl.append(t); labels.append(NAMES[r] + "m")
tmpl = np.array(tmpl); tmpl /= np.linalg.norm(tmpl, axis=1, keepdims=True)
cn = chroma / (np.linalg.norm(chroma, axis=0, keepdims=True) + 1e-9)
sim = tmpl @ cn                       # 24 x T
energy = librosa.feature.rms(y=y22, hop_length=HOP)[0][: sim.shape[1]]
nsc = np.where(energy < 0.01, 1.0, 0.25)[None, :]
S = np.vstack([sim, nsc])
pr = np.exp(S * 12); pr /= pr.sum(0, keepdims=True)
tr = librosa.sequence.transition_loop(25, 0.97)
cpath = librosa.sequence.viterbi(pr, tr)
labels.append("N")
chords = []
for i, c in enumerate(cpath):
    if i == 0 or c != cpath[i - 1]:
        chords.append([float(ct[i]), labels[c]])
toc("key_chords")

# ---------------- write outputs in several formats, measure size -----------------------
tic("write")
cols = {
    "viz_bass": viz3["bass"], "viz_mid": viz3["mid"], "viz_high": viz3["high"],
    **{f"db_{k_}": v_ for k_, v_ in band_pow_db.items()},
    "kick": kick_env, "kick_raw": kick_raw, "mid_hit": mid_env, "high_hit": high_env,
    "flux_low": flux["low"], "flux_mid": flux["mid"], "flux_high": flux["high"],
    "rms_db": rms_db, "lufs_m": lufs_m, "lufs_s": lufs_s,
    "centroid_hz": centroid, "rolloff_hz": rolloff, "flatness": flatness, "bandwidth_hz": bandwidth,
    "width": width, "corr": corr, "balance_db": balance_db,
    "width_bass": bw["bass"], "width_mid": bw["mid"], "width_high": bw["high"],
}
names = list(cols)
M = np.stack([np.asarray(cols[c], np.float32) for c in names], axis=1)
M.astype("<f4").tofile(os.path.join(outdir, "curves.f32"))
band_norm.astype("<f4").tofile(os.path.join(outdir, "spectrum128.f32"))
(np.round(band_norm * 255)).astype(np.uint8).tofile(os.path.join(outdir, "spectrum128.u8"))
band_norm.astype("<f2").tofile(os.path.join(outdir, "spectrum128.f16"))
np.savez_compressed(os.path.join(outdir, "curves.npz"), curves=M, spectrum=band_norm.astype(np.float16))
np.savetxt(os.path.join(outdir, "curves.csv"), M, delimiter=",", fmt="%.5g", header=",".join(names), comments="")
with open(os.path.join(outdir, "curves.json"), "w") as fh:
    json.dump({"fps": FPS, "columns": {c: [round(float(v_), 4) for v_ in M[:, j]] for j, c in enumerate(names)}}, fh)
try:
    import pyarrow as pa, pyarrow.parquet as pq
    pq.write_table(pa.table({c: M[:, j] for j, c in enumerate(names)}), os.path.join(outdir, "curves.parquet"), compression="zstd")
    pq.write_table(pa.table({f"b{j:03d}": band_norm[:, j].astype(np.float16) for j in range(NB)}), os.path.join(outdir, "spectrum128.parquet"), compression="zstd")
except Exception as e:
    print("parquet failed", e)
toc("write")

sizes = {f: os.path.getsize(os.path.join(outdir, f)) for f in os.listdir(outdir)}
summary = {
    "file": os.path.basename(path), "sr": sr, "dur": dur, "frames": nfr, "n_curves": len(names),
    "timings_s": {k_: round(v_, 3) for k_, v_ in T.items()},
    "integrated_lufs": round(I, 2), "lra_lu": round(LRA, 2), "sample_peak_dbfs": round(true_peak_sample, 2),
    "lufs_s_max": round(float(lufs_s.max()), 2), "lufs_m_max": round(float(lufs_m.max()), 2),
    "song_gain": round(g, 3),
    "kick_events_port": len(kick_events), "kick_events_offline_ref": len(kick_events_off),
    "onsets": {k_: len(v_) for k_, v_ in onsets.items()},
    "key_global_top3": key_global, "key_changes": key_changes[:8], "n_key_changes": len(key_changes),
    "n_chord_changes": len(chords), "chords_first": chords[:12],
    "corr_median": round(float(np.median(corr)), 3), "width_median": round(float(np.median(width)), 3),
    "centroid_median": round(float(np.median(centroid)), 1),
    "sizes_bytes": sizes,
    "first_kicks": [round(t_, 2) for t_, _ in kick_events[:16]],
}
print(json.dumps(summary, indent=1))
