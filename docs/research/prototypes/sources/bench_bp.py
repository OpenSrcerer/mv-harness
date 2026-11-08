import sys, time, warnings
warnings.filterwarnings("ignore")
t0 = time.perf_counter()
from basic_pitch.inference import predict, Model
from basic_pitch import ICASSP_2022_MODEL_PATH, FilenameSuffix, build_icassp_2022_model_path
t1 = time.perf_counter()
mp = build_icassp_2022_model_path(FilenameSuffix.onnx)
m = Model(mp)
t2 = time.perf_counter()
for stem in sys.argv[1:]:
    a = time.perf_counter()
    model_output, midi, notes = predict(stem, m)
    b = time.perf_counter()
    pitches = [n[2] for n in notes]
    print(f"{stem}: {b-a:.1f}s, {len(notes)} notes, pitch range {min(pitches) if pitches else None}-{max(pitches) if pitches else None}, note tuple len {len(notes[0]) if notes else 0}, out keys {list(model_output.keys())}")
print(f"import {t1-t0:.1f}s, model load {t2-t1:.1f}s, model {mp}")
