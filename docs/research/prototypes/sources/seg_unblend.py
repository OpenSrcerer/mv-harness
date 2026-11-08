import sys, time, numpy as np, onnxruntime as ort
path, prov = sys.argv[1], sys.argv[2]
so = ort.SessionOptions()
if prov == "dml":
    so.enable_mem_pattern = False
    so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    providers = [("DmlExecutionProvider", {"device_id": 0}), "CPUExecutionProvider"]
else:
    providers = ["CPUExecutionProvider"]
t0 = time.perf_counter(); s = ort.InferenceSession(path, so, providers=providers); t1 = time.perf_counter()
feeds = {"spec_real": np.random.randn(1,2,2048,336).astype(np.float32)*0.1, "spec_imag": np.random.randn(1,2,2048,336).astype(np.float32)*0.1, "audio": np.random.randn(1,2,343980).astype(np.float32)*0.1}
times=[]
for i in range(5):
    a=time.perf_counter(); y=s.run(None, feeds); times.append(time.perf_counter()-a)
print(f"{prov}: providers={s.get_providers()[:1]} load {t1-t0:.1f}s runs {[round(t,3) for t in times]} outs {[o.shape for o in y]}")
