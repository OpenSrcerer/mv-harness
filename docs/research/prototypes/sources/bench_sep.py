import sys, time, os
import demucs_onnx as d
song, prov, outdir, cache = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
model = sys.argv[5] if len(sys.argv) > 5 else "htdemucs_6s"
t0 = time.perf_counter()
d.prewarm([model], providers=prov, precision="fp16weights", cache_dir=cache)
t1 = time.perf_counter()
stems = d.separate(song, outdir, model=model, providers=prov, precision="fp16weights", cache_dir=cache, progress=False)
t2 = time.perf_counter()
print(f"provider={prov} model={model} prewarm/download={t1-t0:.1f}s separate={t2-t1:.1f}s stems={ {k: v.shape for k,v in stems.items()} }")
