import sys, time, numpy as np, onnxruntime as ort
path, prov, lvl = sys.argv[1], sys.argv[2], sys.argv[3]
so = ort.SessionOptions()
so.graph_optimization_level = {"all": ort.GraphOptimizationLevel.ORT_ENABLE_ALL, "ext": ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED, "basic": ort.GraphOptimizationLevel.ORT_ENABLE_BASIC, "none": ort.GraphOptimizationLevel.ORT_DISABLE_ALL}[lvl]
if prov == "dml":
    so.enable_mem_pattern = False
    so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    providers = [("DmlExecutionProvider", {"device_id": 0}), "CPUExecutionProvider"]
else:
    providers = ["CPUExecutionProvider"]
t0 = time.perf_counter()
s = ort.InferenceSession(path, so, providers=providers)
t1 = time.perf_counter()
x = (np.random.randn(1, 2, 343980) * 0.1).astype(np.float32)
times = []
for i in range(4):
    a = time.perf_counter(); y = s.run(["stems"], {"mix": x})[0]; times.append(time.perf_counter() - a)
print(f"{prov}/{lvl}: load {t1-t0:.1f}s, per-7.8s-segment runs: {[round(t,3) for t in times]} out {y.shape}")
