"""Import every main-env package; print version + any error. Exit 1 on failure."""
import importlib, importlib.metadata as md, sys, time, json
MODS = [  # (import name, dist name)
 ("numpy","numpy"),("scipy","scipy"),("librosa","librosa"),("pyloudnorm","pyloudnorm"),("soundfile","soundfile"),("soxr","soxr"),
 ("sklearn","scikit-learn"),("PIL","pillow"),("torch","torch"),("torchaudio","torchaudio"),("onnxruntime","onnxruntime"),
 ("beat_this","beat-this"),("allin1_infer","all-in-one-infer"),("madmom_infer","madmom-infer"),("demucs_infer","demucs-infer"),
 ("demucs_onnx","demucs-onnx"),("basic_pitch","basic-pitch"),("swift_f0","swift-f0"),("rmvpe_onnx","rmvpe-onnx"),
 ("piano_transcription_inference","piano-transcription-inference"),("torchlibrosa","torchlibrosa"),("pretty_midi","pretty-midi"),("mido","mido"),
 ("transformers","transformers"),("tokenizers","tokenizers"),("lv_chordia","lv-chordia"),("faster_whisper","faster-whisper"),
 ("ctranslate2","ctranslate2"),("stable_whisper","stable-ts"),("uroman","uroman"),("num2words","num2words"),("rapidfuzz","rapidfuzz"),
 ("speechbrain","speechbrain"),("g2p_en","g2p-en"),("httpx","httpx"),("jsonschema","jsonschema"),("huggingface_hub","huggingface-hub"),
 ("pytest","pytest"),("pytest_timeout","pytest-timeout"),("mir_eval","mir_eval"),("anthropic","anthropic"),("resampy","resampy"),("numba","numba"),
]
bad = 0
for imp, dist in MODS:
    t = time.time()
    try:
        importlib.import_module(imp)
        try: v = md.version(dist)
        except Exception: v = "?"
        print(f"OK   {imp:32s} {dist:32s} {v:12s} {time.time()-t:5.1f}s")
    except BaseException as e:
        bad += 1; print(f"FAIL {imp:32s} {dist:32s} {type(e).__name__}: {str(e)[:200]}")
for forbidden in ("onnxruntime-directml","tensorflow","skey"):
    try: md.version(forbidden); print("FORBIDDEN installed:", forbidden); bad += 1
    except md.PackageNotFoundError: pass
sys.exit(1 if bad else 0)
