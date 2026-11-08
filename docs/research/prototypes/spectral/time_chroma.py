import sys, time
import numpy as np, soundfile as sf
t = time.perf_counter()
import librosa
print("import", round(time.perf_counter() - t, 2))
x, sr = sf.read(sys.argv[1], dtype="float32", always_2d=True)
mono = x.mean(axis=1)
for rep in range(2):
    t = time.perf_counter(); y = librosa.resample(mono, orig_sr=sr, target_sr=22050, res_type="soxr_hq"); a = time.perf_counter() - t
    t = time.perf_counter(); yh = librosa.effects.harmonic(y, margin=2.0); b = time.perf_counter() - t
    t = time.perf_counter(); c = librosa.feature.chroma_cqt(y=yh, sr=22050, hop_length=512, bins_per_octave=36, n_octaves=6, fmin=librosa.note_to_hz("C1")); d = time.perf_counter() - t
    t = time.perf_counter(); c2 = librosa.feature.chroma_cqt(y=y, sr=22050, hop_length=512, bins_per_octave=36, n_octaves=6, fmin=librosa.note_to_hz("C1")); e = time.perf_counter() - t
    t = time.perf_counter(); cs = librosa.feature.chroma_stft(y=y, sr=22050, hop_length=512, n_fft=8192); f = time.perf_counter() - t
    print(f"rep{rep}: resample {a:.2f}s  hpss-harmonic {b:.2f}s  chroma_cqt(harm) {d:.2f}s  chroma_cqt(raw) {e:.2f}s  chroma_stft {f:.2f}s")
