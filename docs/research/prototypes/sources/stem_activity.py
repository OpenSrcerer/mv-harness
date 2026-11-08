import sys, time, numpy as np, soundfile as sf, os
d = sys.argv[1]
t0 = time.perf_counter()
stems = {}
for f in sorted(os.listdir(d)):
    if f.endswith(".wav"):
        x, sr = sf.read(os.path.join(d, f), dtype="float32"); stems[f[:-4]] = x.mean(axis=1)
mix = sum(stems.values())
hop = sr // 50  # 20 ms
def rms_db(x):
    n = len(x) // hop; f = x[: n*hop].reshape(n, hop)
    return 10*np.log10(np.mean(f*f, axis=1) + 1e-12)
mdb = rms_db(mix)
print(f"mix: median {np.median(mdb):.1f} dBFS, p95 {np.percentile(mdb,95):.1f}")
for k, x in stems.items():
    db = rms_db(x); rel = db - mdb
    active = (db > -50) & (rel > -15)
    print(f"{k:7s} median {np.median(db):6.1f} dBFS  p95 {np.percentile(db,95):6.1f}  share-of-mix(median rel) {np.median(rel):6.1f} dB  active(>-50dBFS & >-15dB rel) {active.mean()*100:5.1f}%")
print(f"computed in {time.perf_counter()-t0:.1f}s")
