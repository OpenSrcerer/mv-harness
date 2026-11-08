"""Quick numpy-only probe: onset envelope + ACF tempo candidates, local tempo curve, and coarse energy.
Mirrors the viz/js/audio.js approach (kick band 35-100 Hz, 100 Hz envelope, ACF with harmonic support)
so we can see octave ambiguity and tempo stability on the test songs. Not production code."""
import sys, time
import numpy as np
import soundfile as sf

def stft_mag(x, sr, n_fft=2048, hop=441):
    win = np.hanning(n_fft).astype(np.float32)
    n = 1 + (len(x) - n_fft) // hop
    idx = np.arange(n_fft)[None, :] + hop * np.arange(n)[:, None]
    frames = x[idx] * win
    return np.abs(np.fft.rfft(frames, axis=1)).astype(np.float32), sr / hop

def band_db(S, sr, n_fft, lo, hi):
    f = np.fft.rfftfreq(n_fft, 1 / sr)
    m = (f >= lo) & (f < hi)
    return 10 * np.log10(np.mean(S[:, m] ** 2, axis=1) + 1e-12)

def flux(S, sr, n_fft, lo, hi):
    f = np.fft.rfftfreq(n_fft, 1 / sr)
    m = (f >= lo) & (f < hi)
    L = np.log1p(100 * S[:, m])
    d = np.diff(L, axis=0, prepend=L[:1])
    return np.maximum(d, 0).mean(axis=1)

def acf_tempo(env, fps, lo=60, hi=200, topk=4):
    e = env - env.mean()
    n = len(e)
    spec = np.fft.rfft(e, 2 * n)
    r = np.fft.irfft(spec * np.conj(spec))[:n]
    r = r / (r[0] + 1e-12)
    cands = []
    for lag in range(int(fps * 60 / hi), int(fps * 60 / lo) + 1):
        s = r[lag]
        if 2 * lag < n: s += 0.5 * r[2 * lag]
        if 4 * lag < n: s += 0.25 * r[4 * lag]
        cands.append((s, 60 * fps / lag))
    cands.sort(reverse=True)
    out = []
    for s, b in cands:
        if all(abs(b - o[1]) / o[1] > 0.04 for o in out):
            out.append((round(float(s), 3), round(float(b), 2)))
        if len(out) == topk: break
    return out

for path in sys.argv[1:]:
    t0 = time.time()
    x, sr = sf.read(path, dtype="float32")
    x = x.mean(axis=1) if x.ndim > 1 else x
    S, fps = stft_mag(x, sr)
    kick = flux(S, sr, 2048, 35, 100)
    broad = flux(S, sr, 2048, 30, 16000)
    rms_db = 10 * np.log10(np.mean(S ** 2, axis=1) + 1e-12)
    print(f"== {path.split(chr(92))[-1]}  dur={len(x)/sr:.1f}s fps={fps:.0f}  (analysis {time.time()-t0:.1f}s)")
    print("  global ACF tempo candidates (kick flux):", acf_tempo(kick, fps))
    print("  global ACF tempo candidates (broadband):", acf_tempo(broad, fps))
    # local tempo curve: 8 s windows, 4 s hop
    w, h = int(8 * fps), int(4 * fps)
    curve = []
    for s in range(0, len(broad) - w, h):
        c = acf_tempo(broad[s:s + w], fps, topk=1)
        curve.append(c[0][1] if c else 0)
    print("  local tempo (8s win, 4s hop):", " ".join(f"{b:.0f}" for b in curve))
    # coarse energy per 4 s (dB, relative to max) + bass share
    bass = band_db(S, sr, 2048, 32, 150)
    blk = int(4 * fps)
    e = [np.mean(rms_db[i:i + blk]) for i in range(0, len(rms_db), blk)]
    b = [np.mean(bass[i:i + blk]) for i in range(0, len(bass), blk)]
    mx = max(e)
    print("  energy dB rel max per 4s:", " ".join(f"{v - mx:.0f}" for v in e))
    print("  bass dB rel max per 4s:  ", " ".join(f"{v - max(b):.0f}" for v in b))
