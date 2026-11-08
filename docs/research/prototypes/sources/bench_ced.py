import sys, time, json, numpy as np, soundfile as sf, soxr, onnxruntime as ort
model, cfg, audio, prov = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
win_s, hop_s = float(sys.argv[5]), float(sys.argv[6])
labels = json.load(open(cfg))["id2label"]
x, sr = sf.read(audio, dtype="float32"); x = x.mean(axis=1) if x.ndim > 1 else x
y = soxr.resample(x, sr, 16000).astype(np.float32)
W, H = int(win_s*16000), int(hop_s*16000)
starts = list(range(0, max(1, len(y)-W+1), H))
frames = np.stack([y[s:s+W] for s in starts])
providers = [("DmlExecutionProvider", {}), "CPUExecutionProvider"] if prov == "dml" else ["CPUExecutionProvider"]
so = ort.SessionOptions()
if prov == "dml": so.enable_mem_pattern = False
s = ort.InferenceSession(model, so, providers=providers)
t0 = time.perf_counter()
out = []
B = 32
for i in range(0, len(frames), B):
    out.append(s.run(None, {"waveform": frames[i:i+B]})[0])
t1 = time.perf_counter()
p = np.concatenate(out); print("output range", float(p.min()), float(p.max()))
print(f"{prov}: {len(frames)} windows of {win_s}s hop {hop_s}s in {t1-t0:.1f}s")
mean = p.mean(0); top = np.argsort(-mean)[:15]
print("top mean:", [(labels[str(i)], round(float(mean[i]),2)) for i in top])
