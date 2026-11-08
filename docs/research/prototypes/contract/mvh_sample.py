"""Reference sampler for the prototype contract (numpy only, Blender/ComfyUI friendly).
Curve sample i sits at t_i = t0 + i / rate. A video frame n at fps F covers [n/F, (n+1)/F).
  linear: value interpolated at the frame start n/F
  mean:   mean of samples with t_i in the window; if none, linear value at the window centre
  max:    max of (samples in the window, linear value at the window start)  -> transients survive downsampling
"""
import json, math, os, sys
import numpy as np

def load(out_dir):
    man = json.load(open(os.path.join(out_dir, "manifest.json")))
    curves = {}
    for c in man["curves"]:
        arr = np.fromfile(os.path.join(out_dir, c["path"]), dtype="<f4").reshape(c["shape"])
        for j, ch in enumerate(c["channels"]):
            curves[ch["name"]] = (arr[:, j], c["rate_hz"], c["t0_s"], ch.get("resample", "linear"))
    return man, curves

def _lin(v, rate, t0, t):
    x = (t - t0) * rate
    if x <= 0: return float(v[0])
    if x >= len(v) - 1: return float(v[-1])
    i = int(math.floor(x)); f = x - i
    return float(v[i] * (1 - f) + v[i + 1] * f)

def frame_value(curve, n, fps):
    v, rate, t0, mode = curve
    a, b = n / fps, (n + 1) / fps
    if mode == "linear":
        return _lin(v, rate, t0, a)
    i0 = max(0, math.ceil((a - t0) * rate - 1e-9)); i1 = min(len(v), math.ceil((b - t0) * rate - 1e-9))
    if mode == "mean":
        return float(v[i0:i1].astype(np.float64).mean()) if i1 > i0 else _lin(v, rate, t0, (a + b) / 2)
    if mode == "max":
        m = _lin(v, rate, t0, a)
        return max(m, float(v[i0:i1].max())) if i1 > i0 else m
    raise ValueError(mode)

if __name__ == "__main__":
    out, fps = sys.argv[1], float(sys.argv[2])
    man, curves = load(out)
    nframes = int(math.ceil(man["source"]["duration_s"] * fps))
    res = {name: [round(frame_value(c, n, fps), 6) for n in range(nframes)] for name, c in curves.items() if name in ("bass", "kick", "rms_db")}
    json.dump(res, open(os.path.join(out, f"py_{int(fps)}.json"), "w"))
    print(nframes, {k: v[1000:1003] for k, v in res.items()})
