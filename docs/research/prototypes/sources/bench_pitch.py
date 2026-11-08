import sys, time, numpy as np, soundfile as sf, soxr
from swift_f0 import SwiftF0, segment_notes
stem = sys.argv[1]
x, sr = sf.read(stem, dtype="float32"); x = x.mean(axis=1)
t0 = time.perf_counter(); y = soxr.resample(x, sr, 16000); t1 = time.perf_counter()
det = SwiftF0()
r = det.detect(y, 16000, fmin=65.0, fmax=1400.0); t2 = time.perf_counter()
notes = segment_notes(r); t3 = time.perf_counter()
hz = np.asarray(r.pitch_hz); conf = np.asarray(r.confidence); ldb = np.asarray(r.loudness_db)
v = (conf > 0.9) & (hz > 0) & (ldb > np.percentile(ldb, 30))
midi = 69 + 12*np.log2(hz[v]/440.0)
names = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
nm = lambda m: f"{names[int(round(m))%12]}{int(round(m))//12-1}"
p = np.percentile(midi, [1, 5, 10, 50, 90, 95, 99]) if v.sum() else []
print(f"resample {t1-t0:.2f}s, swift-f0 {t2-t1:.2f}s for {len(x)/sr:.0f}s audio, segment_notes {t3-t2:.2f}s; frames {len(hz)}, voiced {v.mean()*100:.0f}% ; notes {len(notes)}")
print("percentiles 1/5/10/50/90/95/99:", [nm(m) for m in p], "min/max", nm(midi.min()), nm(midi.max()))
