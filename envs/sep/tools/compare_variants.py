"""Compare two sep/ output folders (e.g. rocm vs cpu_ref): per-stem relative difference in dB. python compare_variants.py <dirA> <dirB> <out.json>"""
import json, sys
from pathlib import Path
import numpy as np, soundfile as sf
A, B, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
res = {}
for f in sorted(A.rglob("*.wav")):
    rel = f.relative_to(A)
    if rel.parts[0] in ("_work", "cpu_ref") or rel.name == "mix_f32.wav":
        continue
    g = B / rel
    if not g.exists():
        continue
    a, _ = sf.read(f, dtype="float64"); b, _ = sf.read(g, dtype="float64")
    n = min(len(a), len(b))
    ea = float(np.sum(a[:n] ** 2)); d = float(np.sum((a[:n] - b[:n]) ** 2))
    res[rel.as_posix()] = {"rel_diff_db": round(10 * np.log10(max(d, 1e-30) / max(ea, 1e-30)), 2), "rms_dbfs_a": round(10 * np.log10(max(ea / a[:n].size, 1e-30)), 2),
                           "max_abs_diff": round(float(np.abs(a[:n] - b[:n]).max()), 5)}
out.write_text(json.dumps(res, indent=1), encoding="utf-8")
for k, v in res.items():
    print(k, v)
