"""Prototype loud/quiet + build/drop/breakdown segmentation from the 100 Hz curves."""
import sys, time
import numpy as np
from scipy import ndimage, signal

COLS = ["viz_bass", "viz_mid", "viz_high", "db_sub", "db_bass", "db_lowmid", "db_mid", "db_highmid", "db_presence",
        "db_air", "db_viz_bass", "db_viz_mid", "db_viz_high", "db_kick", "kick", "kick_raw", "mid_hit", "high_hit",
        "flux_low", "flux_mid", "flux_high", "rms_db", "lufs_m", "lufs_s", "centroid_hz", "rolloff_hz", "flatness",
        "bandwidth_hz", "width", "corr", "balance_db", "width_bass", "width_mid", "width_high"]
t0 = time.perf_counter()
M = np.fromfile(sys.argv[1], dtype="<f4").reshape(-1, len(COLS))
I = float(sys.argv[2])
C = {c: M[:, i] for i, c in enumerate(COLS)}
FPS = 100
n = len(M)

# --- silence (100 Hz): rms below -60 dBFS for >= 0.4 s
sil = C["rms_db"] < -60
lab, k = ndimage.label(sil)
silences = []
for s in ndimage.find_objects(lab):
    a, b = s[0].start, s[0].stop
    if (b - a) / FPS >= 0.4:
        silences.append((round(a / FPS, 2), round(b / FPS, 2)))

# --- 10 Hz feature matrix for novelty
D = 10
def ds(v):
    return v[: n // D * D].reshape(-1, D).mean(1)
kick_rate = ndimage.uniform_filter1d((C["kick_raw"] > 0.3).astype(float), 200)  # hits per 2 s window fraction
feats = np.stack([
    ds(C["lufs_m"]), ds(C["db_viz_bass"]), ds(C["db_viz_mid"]), ds(C["db_viz_high"]),
    ds(kick_rate) * 50, ds(np.log2(C["centroid_hz"] + 1)) * 3, ds(C["width"]) * 10,
], 1)
feats = ndimage.median_filter(feats, size=(9, 1))
Z = (feats - feats.mean(0)) / (feats.std(0) + 1e-9)
# Foote novelty with checkerboard kernel (+-8 s)
Lk = 80
S = -np.sqrt(((Z[:, None, :] - Z[None, :, :]) ** 2).sum(-1))
g = signal.windows.gaussian(2 * Lk, Lk / 2)
G = np.outer(g, g) * np.outer(np.r_[-np.ones(Lk), np.ones(Lk)], np.r_[-np.ones(Lk), np.ones(Lk)])
Sp = np.pad(S, Lk, mode="edge")
nov = np.array([(Sp[i:i + 2 * Lk, i:i + 2 * Lk] * G).sum() for i in range(len(S))])
nov = -nov  # contrast between blocks
nov = (nov - nov.min()) / (np.ptp(nov) + 1e-9)
pk, _ = signal.find_peaks(nov, distance=60, prominence=0.08)
bounds = np.r_[0, pk, len(Z)]

# --- per-segment stats + labels
rel_s = ds(C["lufs_s"]) - I
bass = ds(C["db_viz_bass"])
kr = ds(kick_rate) * 2 * 100 / 2  # approx hits per second
segs = []
for a, b in zip(bounds[:-1], bounds[1:]):
    segs.append(dict(t0=a / 10, t1=b / 10, rel_lu=float(np.median(rel_s[a:b])), bass_db=float(np.median(bass[a:b])),
                     kick_hz=float(kr[a:b].mean()), slope_lu_per_s=float(np.polyfit(np.arange(b - a) / 10, rel_s[a:b], 1)[0]) if b - a > 5 else 0.0,
                     cent_slope=float(np.polyfit(np.arange(b - a) / 10, Z[a:b, 5], 1)[0]) if b - a > 5 else 0.0))
med_bass = np.median([s["bass_db"] for s in segs])
for i, s in enumerate(segs):
    lvl = "quiet" if s["rel_lu"] < -8 else "soft" if s["rel_lu"] < -4 else "loud" if s["rel_lu"] > -1.5 else "medium"
    tags = []
    prev = segs[i - 1] if i else None
    nxt = segs[i + 1] if i + 1 < len(segs) else None
    if (s["slope_lu_per_s"] > 0.15 or s["cent_slope"] > 0.03) and nxt and nxt["rel_lu"] > s["rel_lu"] + 2:
        tags.append("build-up")
    if prev and s["bass_db"] - prev["bass_db"] > 6 and s["rel_lu"] > -3:
        tags.append("drop")
    if prev and s["bass_db"] < med_bass - 8 and prev["bass_db"] > s["bass_db"] + 6:
        tags.append("breakdown")
    s["level"] = lvl; s["tags"] = tags
print(f"elapsed {time.perf_counter() - t0:.2f}s  silences={silences}")
for s in segs:
    print(f"{s['t0']:6.1f}-{s['t1']:6.1f}  rel={s['rel_lu']:+5.1f} LU  bass={s['bass_db']:6.1f} dB  kick/s={s['kick_hz']:4.2f}  "
          f"slope={s['slope_lu_per_s']:+.2f}  {s['level']:6s} {','.join(s['tags'])}")
