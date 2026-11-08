"""Probe: what does whisper find in the lyric-less tail of jeremy (no VAD vs VAD, different VAD params)? Numbers only."""
import sys, os, json, time
sys.path.insert(0, r"C:\Users\OpenSrcerer\Desktop\playground\mv-harness\scripts"); sys.path.insert(0, os.path.dirname(__file__))
from heavy_lock import heavy, apply_thread_limits
apply_thread_limits(6)
import numpy as np
from bw_common import *
a = load_stem16k("jeremy"); a = a[int(205 * 16000):]
with heavy("bench-words", threads=6):
    from faster_whisper import WhisperModel
    m = WhisperModel(os.path.join(os.environ["MVH_MODELS_DIR"], "faster-whisper", "large-v3"), device="cpu", compute_type="int8", cpu_threads=6)
    for name, kw in [("no_vad", dict(vad_filter=False)), ("vad_loose", dict(vad_filter=True, vad_parameters=dict(threshold=0.2, min_silence_duration_ms=300, speech_pad_ms=300)))]:
        t0 = time.time(); segs, info = m.transcribe(a, word_timestamps=True, condition_on_previous_text=False, beam_size=5, language="en", **kw)
        segs = list(segs)
        print(name, round(time.time() - t0, 1), "s; segs", len(segs), "words", sum(len(s.words) for s in segs),
              [(round(s.start + 205, 1), round(s.end + 205, 1), len(s.words), round(s.avg_logprob, 2), round(s.no_speech_prob, 2), round(s.compression_ratio, 1)) for s in segs][:14])
