"""Prototype of the mv-harness output contract: decode with ffmpeg, compute a few 100 Hz curves
with numpy only, write raw float32 curves + a manifest, then sample them at video fps.
Purpose: check sizes, speed and Python/JS sampling parity. Not the real harness."""
import json, subprocess, sys, time, hashlib, os
import numpy as np

FF = r"C:\Users\OpenSrcerer\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe"
src, out = sys.argv[1], sys.argv[2]
os.makedirs(os.path.join(out, "curves"), exist_ok=True)
t0 = time.perf_counter()
SR = 44100
pcm = subprocess.run([FF, "-v", "error", "-i", src, "-map", "0:a:0", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                     capture_output=True, check=True).stdout
x = np.frombuffer(pcm, dtype="<f4")
t_dec = time.perf_counter() - t0
sha = hashlib.sha256(pcm).hexdigest()

RATE = 100                     # curve rate (Hz); hop 441 samples = exactly 10 ms
HOP, N = SR // RATE, 4096
nfr = int(np.ceil(len(x) / HOP))
pad = np.pad(x, (N // 2, N // 2 + HOP))
idx = np.arange(N)[None, :] + HOP * np.arange(nfr)[:, None]
win = np.hanning(N).astype(np.float32)
t1 = time.perf_counter()
spec = np.empty((nfr, N // 2 + 1), np.float32)
for i in range(0, nfr, 2048):                      # chunk to bound memory
    spec[i:i + 2048] = np.abs(np.fft.rfft(pad[idx[i:i + 2048]] * win, axis=1)) ** 2
freqs = np.fft.rfftfreq(N, 1 / SR)
def band_db(lo, hi):
    m = (freqs >= lo) & (freqs < hi)
    return 10 * np.log10(spec[:, m].mean(axis=1) + 1e-12)
bands = {"bass": (32, 150), "mid": (150, 2200), "high": (2200, 16000), "kick": (35, 100)}
cols, descr = [], []
for name, (lo, hi) in bands.items():
    db = band_db(lo, hi)
    p5, p99 = np.percentile(db, [5, 99])
    cols.append(np.clip((db - p5) / (p99 - p5), 0, 1)); descr.append({"name": f"{name}", "unit": "0..1", "norm": {"method": "p05-p99", "lo_db": round(float(p5), 2), "hi_db": round(float(p99), 2)}, "resample": "max" if name == "kick" else "mean", "band_hz": [lo, hi]})
    cols.append(db); descr.append({"name": f"{name}_db", "unit": "dB", "resample": "mean", "band_hz": [lo, hi]})
rms = 20 * np.log10(np.sqrt(np.mean((pad[idx[:, N // 2 - 2205:N // 2 + 2205]]) ** 2, axis=1)) + 1e-9)
cols.append(rms); descr.append({"name": "rms_db", "unit": "dBFS", "resample": "mean", "window_s": 0.1})
M = np.stack(cols, axis=1).astype("<f4")             # [frames x channels], row-major
t_feat = time.perf_counter() - t1
M.tofile(os.path.join(out, "curves", "core.f32"))
manifest = {
    "schema": "mvh/manifest@0.1-proto",
    "source": {"path": os.path.basename(src), "pcm_sha256": sha, "duration_s": round(len(x) / SR, 3), "sample_rate": SR},
    "timebase": {"unit": "s", "curve_rate_hz": RATE, "curve_t0_s": 0.0, "frame_time": "t = n / fps (frame start)", "frame_window": "[n/fps, (n+1)/fps)"},
    "curves": [{"id": "core", "path": "curves/core.f32", "dtype": "f32le", "shape": list(M.shape), "rate_hz": RATE, "t0_s": 0.0, "channels": descr}],
}
json.dump(manifest, open(os.path.join(out, "manifest.json"), "w"), indent=1)
print(f"decode {t_dec:.2f}s  features {t_feat:.2f}s  frames {M.shape}  bytes {M.nbytes}  manifest {os.path.getsize(os.path.join(out,'manifest.json'))}B")
