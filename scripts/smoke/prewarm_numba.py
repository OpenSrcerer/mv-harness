"""Pre-warm the numba on-disk cache (NUMBA_CACHE_DIR) by running the numba-jitted paths of librosa on a synthetic clip."""
import time, os
import numpy as np
t = time.time()
import librosa
sr = 22050
rng = np.random.default_rng(0)
x = (0.1 * rng.standard_normal(sr * 6)).astype(np.float32)
x += 0.5 * np.sin(2 * np.pi * 440 * np.arange(sr * 6) / sr).astype(np.float32)
x[::sr // 2] += 1.0
S = librosa.feature.melspectrogram(y=x, sr=sr)
oenv = librosa.onset.onset_strength(y=x, sr=sr)
tempo, beats = librosa.beat.beat_track(onset_envelope=oenv, sr=sr)
librosa.feature.mfcc(y=x, sr=sr)
librosa.feature.chroma_stft(y=x, sr=sr)
librosa.feature.chroma_cqt(y=x, sr=sr)
librosa.feature.tempogram(onset_envelope=oenv, sr=sr)
librosa.beat.plp(onset_envelope=oenv, sr=sr)
librosa.effects.hpss(x)
librosa.segment.recurrence_matrix(S[:, :100])
librosa.sequence.viterbi(np.random.default_rng(1).random((4, 50)), np.eye(4) * 0.9 + 0.025)
librosa.feature.rms(y=x)
librosa.resample(x, orig_sr=sr, target_sr=16000)
try:
    import resampy; resampy.resample(x, sr, 16000)
except Exception as e: print('resampy', e)
print(f"numba prewarm done in {time.time()-t:.1f}s; cache dir {os.environ.get('NUMBA_CACHE_DIR')}")
