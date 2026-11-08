"""Smoke test of every tool named in PLAN 5 and 7 on 5 s clips (W0, env-main).

    powershell -NoProfile -File scripts\\run.ps1 python scripts\\smoke\\smoke_tools.py [--only name,name] [--no-lock]
Clips come from scripts\\smoke\\make_clips.ps1 (%LOCALAPPDATA%\\mvh\\smoke).  Results -> %LOCALAPPDATA%\\mvh\\smoke\\results.json.
Rules honoured: arrays (not paths) go to model libraries (own float32 WAVs only where a library insists); no lyric text is ever
printed (the song clips are only used for shapes / counts / statistics; TTS clips carry a known non-lyric sentence).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
THREADS = int(os.environ.get("MVH_THREADS", "3"))

import numpy as np  # noqa: E402  (thread env vars are set by mvh-env.ps1 before this import)

HOME = Path(os.environ["MVH_HOME"])
MODELS = Path(os.environ["MVH_MODELS_DIR"])
CLIPS = HOME / "smoke"
FFMPEG = os.environ["MVH_FFMPEG"]
FFPROBE = os.environ.get("MVH_FFPROBE", FFMPEG.replace("ffmpeg.exe", "ffprobe.exe"))
RESULTS: dict[str, dict] = {}
REG: dict[str, callable] = {}


def tool(name):
    def deco(fn):
        REG[name] = fn
        return fn
    return deco


def load_f32(path, sr=None, mono=False):
    """Decode with ffmpeg only (never libsndfile) -> float32 array (n,) or (n, 2)."""
    cmd = [FFMPEG, "-v", "error", "-i", str(path), "-map", "0:a:0", "-vn"]
    probe = json.loads(subprocess.run([FFPROBE, "-v", "error", "-select_streams", "a:0", "-show_entries",
                                       "stream=sample_rate,channels", "-of", "json", str(path)],
                                      capture_output=True, text=True, encoding="utf-8").stdout)["streams"][0]
    native_sr, ch = int(probe["sample_rate"]), int(probe["channels"])
    if mono:
        cmd += ["-ac", "1"]
        ch = 1
    if sr:
        cmd += ["-ar", str(sr)]
        native_sr = sr
    cmd += ["-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    a = np.frombuffer(raw, dtype=np.float32).copy()
    return (a.reshape(-1, ch) if ch > 1 else a), native_sr


def write_f32_wav(path, x, sr):
    import soundfile as sf
    sf.write(str(path), x, sr, subtype="FLOAT")


def mono16k(name):
    return load_f32(CLIPS / name, sr=16000, mono=True)[0]


def ort_opts(n=THREADS):
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.intra_op_num_threads = n
    so.inter_op_num_threads = 1
    return so


# ------------------------------------------------------------------------------------------------ external binaries
@tool("ffmpeg")
def t_ffmpeg():
    out = {}
    v = subprocess.run([FFMPEG, "-hide_banner", "-version"], capture_output=True, text=True, encoding="utf-8").stdout
    out["version"] = v.splitlines()[0][:60]
    for flag in ("--enable-whisper", "--enable-vulkan", "--enable-chromaprint", "--enable-libmp3lame", "--enable-libopus"):
        out[flag.replace("--enable-", "")] = flag in v
    filt = subprocess.run([FFMPEG, "-hide_banner", "-filters"], capture_output=True, text=True, encoding="utf-8").stdout
    out["filter_whisper"] = " whisper " in filt
    out["filter_ebur128"] = " ebur128 " in filt
    muxers = subprocess.run([FFMPEG, "-hide_banner", "-muxers"], capture_output=True, text=True, encoding="utf-8").stdout
    out["muxer_chromaprint"] = " chromaprint" in muxers
    # corrupt FLAC decodes through ffmpeg, -map 0:a:0 skips the cover stream
    vers = REPO.parent / "viz" / "Versatile.flac"
    r = subprocess.run([FFMPEG, "-v", "warning", "-i", str(vers), "-map", "0:a:0", "-vn", "-t", "30", "-f", "f32le", "-"],
                       capture_output=True)
    out["versatile_decode_bytes"] = len(r.stdout)
    out["versatile_decoder_warnings"] = len(r.stderr.decode("utf-8", "replace").strip().splitlines())
    assert out["versatile_decode_bytes"] > 1_000_000
    # chromaprint
    r = subprocess.run([FFMPEG, "-v", "error", "-i", str(CLIPS / "jeremy_5s.wav"), "-f", "chromaprint", "-fp_format", "raw", "-"],
                       capture_output=True)
    out["chromaprint_raw_bytes"] = len(r.stdout)
    assert out["chromaprint_raw_bytes"] > 0
    # ebur128 + true peak on the 5 s clip
    r = subprocess.run([FFMPEG, "-nostats", "-i", str(CLIPS / "jeremy_5s.wav"), "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    import re
    m = re.search(r"I:\s+(-?[\d.]+) LUFS", r.stderr[r.stderr.rfind("Summary"):])
    out["ebur128_integrated"] = float(m.group(1)) if m else None
    assert m
    # mp3 with encoder delay (for robustness tests)
    mp3 = CLIPS / "jeremy_5s.mp3"
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(CLIPS / "jeremy_5s.wav"), "-c:a", "libmp3lame", "-b:a", "192k", str(mp3)], check=True)
    out["mp3_ok"] = mp3.stat().st_size > 1000
    # whisper filter requires a model: only check that the filter is registered (env-sep owns Vulkan whisper benchmarks)
    return out


@tool("ffprobe")
def t_ffprobe():
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration:format_tags", "-of", "json", str(CLIPS / "jeremy_5s.wav")],
                       capture_output=True, text=True, encoding="utf-8")
    return {"duration": float(json.loads(r.stdout)["format"]["duration"])}


@tool("node")
def t_node():
    r = subprocess.run(["node", "--version"], capture_output=True, text=True)
    r2 = subprocess.run(["node", "-e", "import('node:fs').then(()=>console.log('esm ok'))"], capture_output=True, text=True)
    return {"version": r.stdout.strip(), "esm": r2.stdout.strip()}


@tool("rhubarb")
def t_rhubarb():
    """Rhubarb on a TTS clip (with dialog text) and on a sung vocal stem when the stems cache exists."""
    exe = os.environ["MVH_RHUBARB"]
    out = {"exe_exists": Path(exe).exists()}
    ver = subprocess.run([exe, "--version"], capture_output=True, text=True, encoding="utf-8")
    out["version"] = (ver.stdout or ver.stderr).strip()[:40]
    work = Path(tempfile.mkdtemp(prefix="rhubarb_"))
    x, sr = load_f32(CLIPS / "tts_david.wav", sr=16000, mono=True)
    import soundfile as sf
    wav = work / "tts16.wav"
    sf.write(str(wav), x, 16000, subtype="PCM_16")
    dlg = work / "dlg.txt"
    dlg.write_text((CLIPS / "tts_david.txt").read_text(encoding="utf-8-sig"), encoding="utf-8")
    for label, extra in (("tts_dialog", ["-d", str(dlg)]), ("tts_nodialog", [])):
        of = work / f"{label}.json"
        r = subprocess.run([exe, "-f", "json", "-o", str(of), *extra, str(wav)], capture_output=True, text=True, encoding="utf-8", cwd=work)
        assert r.returncode == 0, r.stderr[:300]
        j = json.loads(of.read_text(encoding="utf-8"))
        cues = j["mouthCues"]
        out[label] = {"cues": len(cues), "shapes": sorted({c["value"] for c in cues}), "end": cues[-1]["end"]}
    # sung vocal: use the demucs-separated vocals of the Jeremy clip if the demucs smoke test produced it
    sv = CLIPS / "jeremy_5s_vocals.wav"
    if sv.exists():
        v, vsr = load_f32(sv, sr=16000, mono=True)
        w2 = work / "vox16.wav"
        sf.write(str(w2), v, 16000, subtype="PCM_16")
        of = work / "sung.json"
        r = subprocess.run([exe, "-f", "json", "-o", str(of), str(w2)], capture_output=True, text=True, encoding="utf-8", cwd=work)
        assert r.returncode == 0, r.stderr[:300]
        j = json.loads(of.read_text(encoding="utf-8"))
        out["sung_vocals_nodialog"] = {"cues": len(j["mouthCues"]), "shapes": sorted({c["value"] for c in j["mouthCues"]})}
    else:
        out["sung_vocals_nodialog"] = "skipped (run demucs_onnx first)"
    return out


# ------------------------------------------------------------------------------------------------ core DSP
@tool("dsp_core")
def t_dsp():
    import librosa, pyloudnorm, scipy.signal, sklearn.cluster, soxr
    from PIL import Image
    out = {}
    x, sr = load_f32(CLIPS / "megafauna_5s.wav", mono=True)
    out["sr"] = sr
    meter = pyloudnorm.Meter(sr)
    out["pyloudnorm_integrated_5s_mega"] = round(float(meter.integrated_loudness(x[:, None] if x.ndim == 1 else x)), 2)
    y = librosa.resample(x, orig_sr=sr, target_sr=22050)
    S = librosa.feature.melspectrogram(y=y, sr=22050)
    out["mel_shape"] = list(S.shape)
    h, p = librosa.effects.hpss(y)
    C = librosa.feature.chroma_cqt(y=h, sr=22050, hop_length=512, bins_per_octave=36, n_octaves=6)
    out["chroma_cqt_shape"] = list(C.shape)
    oenv = librosa.onset.onset_strength(y=y, sr=22050)
    tempo = (getattr(librosa.feature, "tempo", None) or librosa.beat.tempo)(onset_envelope=oenv, sr=22050)
    out["librosa_tempo"] = round(float(np.atleast_1d(tempo)[0]), 1)
    pl = librosa.beat.plp(onset_envelope=oenv, sr=22050)
    out["plp_len"] = len(pl)
    z = soxr.resample(x, sr, 16000, quality="HQ")
    out["soxr_len"] = len(z)
    f, t_, Z = scipy.signal.stft(x, fs=sr, nperseg=2048)
    out["scipy_stft"] = list(Z.shape)
    img = np.random.default_rng(0).integers(0, 255, (64, 64, 3)).astype(np.uint8)
    km = sklearn.cluster.KMeans(n_clusters=5, n_init=3, random_state=0).fit(np.asarray(Image.fromarray(img)).reshape(-1, 3))
    out["kmeans_palette"] = len(km.cluster_centers_)
    import soundfile as sf
    tmp = Path(tempfile.mkdtemp()) / "t.wav"
    sf.write(str(tmp), x[:1000], sr, subtype="FLOAT")
    out["soundfile_roundtrip_exact"] = bool(np.array_equal(sf.read(str(tmp), dtype="float32")[0], x[:1000]))
    return out


@tool("midi_json_eval")
def t_midi():
    import jsonschema, mido, mir_eval, pretty_midi
    pm = pretty_midi.PrettyMIDI(initial_tempo=120)
    inst = pretty_midi.Instrument(program=33)
    inst.notes.append(pretty_midi.Note(velocity=90, pitch=40, start=0.0, end=0.5))
    pm.instruments.append(inst)
    d = Path(tempfile.mkdtemp())
    pm.write(str(d / "a.mid"))
    mf = mido.MidiFile(str(d / "a.mid"))
    jsonschema.validate({"a": 1}, {"type": "object", "properties": {"a": {"type": "integer"}}}, cls=jsonschema.Draft202012Validator)
    ref = np.arange(0, 10, 0.5)
    f = mir_eval.beat.f_measure(ref, ref + 0.01)
    import pytest, pytest_timeout  # noqa: F401
    return {"midi_tracks": len(mf.tracks), "mir_eval_f": f, "jsonschema_draft": "2020-12"}


@tool("ruff_pytest")
def t_ruff():
    exe = REPO / ".venv" / "Scripts"
    r = subprocess.run([str(exe / "ruff.exe"), "--version"], capture_output=True, text=True)
    r2 = subprocess.run([str(exe / "pytest.exe"), "--version"], capture_output=True, text=True)
    return {"ruff": r.stdout.strip(), "pytest": (r2.stdout or r2.stderr).strip()}


@tool("httpx_network")
def t_httpx():
    import httpx
    out = {}
    with httpx.Client(timeout=20, headers={"User-Agent": "mv-harness-smoke/0.1"}) as c:
        for name, url in (("lrclib", "https://lrclib.net/"), ("musicbrainz", "https://musicbrainz.org/ws/2/"), ("acoustid", "https://api.acoustid.org/")):
            try:
                out[name] = c.head(url, follow_redirects=True).status_code
            except Exception as e:  # noqa: BLE001
                out[name] = f"ERR {type(e).__name__}"
    return out


# ------------------------------------------------------------------------------------------------ rhythm / structure
@tool("beat_this")
def t_beat_this():
    from beat_this.inference import Audio2Frames, Audio2Beats
    out = {}
    x, sr = load_f32(CLIPS / "megafauna_5s.wav", mono=True)
    for name in ("final0", "small0"):
        ck = MODELS / "beat_this" / f"{name}.ckpt"
        t0 = time.time()
        a2f = Audio2Frames(checkpoint_path=str(ck), device="cpu")
        bl, dl = a2f(x, sr)
        out[name] = {"frames": list(np.asarray(bl).shape), "fps": 50, "secs": round(time.time() - t0, 2),
                     "beat_logit_max": round(float(np.max(np.asarray(bl))), 2)}
    a2b = Audio2Beats(checkpoint_path=str(MODELS / "beat_this" / "final0.ckpt"), device="cpu", dbn=False)
    b, d = a2b(x, sr)
    out["beats"] = len(b)
    out["downbeats"] = len(d)
    return out


@tool("allin1")
def t_allin1():
    """all-in-one-infer harmonix-all (8 folds) on 4 stems we wrote ourselves (float32 WAV), offline, folds from the HF-cache layout."""
    import torch
    import allin1_infer
    from allin1_infer import analyze
    from allin1_infer.stems_input import StemsInput
    torch.set_num_threads(THREADS)
    sd = CLIPS / "stems_jeremy"
    if not (sd / "vocals.wav").exists():
        t_demucs()
    work = Path(tempfile.mkdtemp(prefix="allin1_"))
    t0 = time.time()
    r = analyze(stems_input=StemsInput(bass=sd / "bass.wav", drums=sd / "drums.wav", other=sd / "other.wav", vocals=sd / "vocals.wav", identifier="smoke"),
                model="harmonix-all", device="cpu", include_activations=True, include_embeddings=True,
                demix_dir=work / "demix", spec_dir=work / "spec", multiprocess=False)
    r = r[0] if isinstance(r, list) else r
    return {"version": allin1_infer.__version__, "secs": round(time.time() - t0, 1), "bpm": r.bpm, "beats": len(r.beats), "downbeats": len(r.downbeats),
            "segments": len(r.segments), "activations": {k: list(np.asarray(v).shape) for k, v in (r.activations or {}).items()},
            "activation_fps": r.activation_fps, "embeddings": list(np.asarray(r.embeddings).shape), "hf_offline": os.environ.get("HF_HUB_OFFLINE")}


@tool("madmom_infer")
def t_madmom():
    import madmom_infer.models as mm
    from madmom_infer.features.downbeats import RNNDownBeatProcessor, DBNDownBeatTrackingProcessor
    paths = mm.downbeats_blstm()  # resolves via XDG_CACHE_HOME, sha256-verified, no download needed
    out = {"weights_found": len(paths), "cache_root": str(mm._cache_root())}
    x, sr = load_f32(CLIPS / "megafauna_5s.wav", sr=44100, mono=True)
    t0 = time.time()
    act = RNNDownBeatProcessor()(x if False else _wavpath(x, 44100))  # madmom API takes a path/signal; we hand it our own wav
    out["rnn_act_shape"] = list(np.asarray(act).shape)
    beats = DBNDownBeatTrackingProcessor(beats_per_bar=[3, 4], fps=100)(act)
    out["dbn_beats"] = int(len(beats))
    out["secs"] = round(time.time() - t0, 2)
    return out


def _wavpath(x, sr):
    p = Path(tempfile.mkdtemp()) / "m.wav"
    write_f32_wav(p, x, sr)
    return str(p)


@tool("demucs_onnx")
def t_demucs():
    import onnxruntime as ort
    from demucs_onnx import inference as di
    from demucs_onnx._hub import MODEL_REGISTRY
    out = {}
    x, sr = load_f32(CLIPS / "jeremy_5s.wav")
    assert sr == 44100 and x.ndim == 2
    mix = np.ascontiguousarray(x.T)
    for model, rel in (("htdemucs", "demucs-onnx/htdemucs-onnx/htdemucs_fp16weights.onnx"),
                       ("htdemucs_6s", "demucs-onnx/htdemucs-6s-onnx/htdemucs_6s_fp16weights.onnx")):
        sess = ort.InferenceSession(str(MODELS / rel), ort_opts(), providers=["CPUExecutionProvider"])
        t0 = time.time()
        st = di._chunked_separate_single(sess, MODEL_REGISTRY[model].sources, mix, verbose=False, progress=False)
        dt = time.time() - t0
        s = sum(st.values())
        resid = float(np.sqrt(np.mean((s - mix) ** 2)) / (np.sqrt(np.mean(mix ** 2)) + 1e-12))
        out[model] = {"stems": {k: list(v.shape) for k, v in st.items()}, "secs": round(dt, 2), "sum_vs_mix_relrms": round(resid, 4)}
        if model == "htdemucs":
            write_f32_wav(CLIPS / "jeremy_5s_vocals.wav", st["vocals"].T, 44100)
            (CLIPS / "stems_jeremy").mkdir(exist_ok=True)
            for k, v in st.items():
                write_f32_wav(CLIPS / "stems_jeremy" / f"{k}.wav", v.T, 44100)
    return out


# ------------------------------------------------------------------------------------------------ pitch / notes / chords / key
@tool("swift_f0")
def t_swiftf0():
    from swift_f0 import SwiftF0, segment_notes
    y = mono16k("jeremy_5s.wav")
    det = SwiftF0(threads=THREADS)
    r = det.detect(y, 16000, fmin=65.0, fmax=1400.0)
    notes = segment_notes(r)
    return {"frames": len(r.pitch_hz), "voiced_frac": round(float(np.mean(np.asarray(r.confidence) > 0.9)), 3), "notes": len(notes)}


@tool("rmvpe_onnx")
def t_rmvpe():
    import hashlib
    from rmvpe_onnx import RMVPE
    model = MODELS / "rmvpe" / "rmvpe.onnx"
    h = hashlib.sha256(model.read_bytes()).hexdigest()
    assert h == "5370e71ac80af8b4b7c793d27efd51fd8bf962de3a7ede0766dac0befa3660fd", h
    y = mono16k("jeremy_5s.wav")
    r = RMVPE(model_path=str(model), device="cpu")
    t, f, conf, act = r.predict(y, 16000)
    return {"frames": len(f), "voiced_frac": round(float(np.mean(np.asarray(f) > 0)), 3), "sha256_matches_library": True}


@tool("basic_pitch")
def t_basic_pitch():
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import Model, predict
    out = {}
    m = Model(ICASSP_2022_MODEL_PATH)
    out["backend"] = type(m.model).__name__
    x, sr = load_f32(CLIPS / "megafauna_5s.wav", sr=22050, mono=True)
    p = _wavpath(x, 22050)  # basic-pitch's own loader (librosa) reads our float32 wav
    mo, midi, notes = predict(p, m)
    out["note_events"] = len(notes)
    out["onset_shape"] = list(np.asarray(mo["onset"]).shape)
    return out


@tool("piano_transcription")
def t_piano():
    import torch
    from piano_transcription_inference import PianoTranscription
    torch.set_num_threads(THREADS)
    ck = MODELS / "piano_transcription" / "note_F1=0.9677_pedal_F1=0.9186.pth"
    pt = PianoTranscription(checkpoint_path=str(ck), device=torch.device("cpu"))
    y = mono16k("megafauna_5s.wav")
    d = Path(tempfile.mkdtemp())
    res = pt.transcribe(y, str(d / "p.mid"))
    return {"est_notes": len(res["est_note_events"]), "midi_written": (d / "p.mid").exists()}


@tool("lv_chordia")
def t_chordia():
    from lv_chordia.chord_recognition import chord_recognition
    x, sr = load_f32(CLIPS / "megafauna_5s.wav", sr=44100, mono=True)
    p = _wavpath(x, 44100)
    t0 = time.time()
    res = chord_recognition(p, "submission")
    return {"segments": len(res), "secs": round(time.time() - t0, 1), "first": {k: res[0][k] for k in ("start_time", "end_time", "chord")}}


@tool("skey_onnx")
def t_skey():
    import soxr
    cfg = json.loads((MODELS / "skey" / "config.json").read_text(encoding="utf-8"))
    import onnxruntime as ort
    s = ort.InferenceSession(str(MODELS / "skey" / "skey.onnx"), ort_opts(), providers=["CPUExecutionProvider"])
    x, sr = load_f32(CLIPS / "megafauna_5s.wav", mono=True)
    y = soxr.resample(x, sr, 22050).astype(np.float32)
    y = y / (np.max(np.abs(y)) + 1e-9)
    probs = s.run(None, {"audio": y[None, :]})[0]
    probs = np.asarray(probs).reshape(-1)
    keys = cfg.get("keys") or cfg.get("labels") or cfg.get("classes")
    top = int(np.argmax(probs))
    return {"n_out": int(probs.size), "sum": round(float(probs.sum()), 3), "top_key": (keys[top] if keys else top), "config_keys": list(cfg)}


# ------------------------------------------------------------------------------------------------ instruments / mood
@tool("ced_onnx")
def t_ced():
    import onnxruntime as ort
    cfg = json.loads((MODELS / "ced-base" / "config.json").read_text(encoding="utf-8"))
    labels = cfg["id2label"]
    s = ort.InferenceSession(str(MODELS / "ced-base" / "model.onnx"), ort_opts(), providers=["CPUExecutionProvider"])
    y = mono16k("jeremy_5s.wav")
    W = 4 * 16000
    frames = np.stack([y[i:i + W] for i in range(0, len(y) - W + 1, 16000)])
    lg = s.run(None, {"waveform": frames})[0]
    p = 1 / (1 + np.exp(-lg))
    top = np.argsort(-p.mean(0))[:3]
    return {"windows": len(frames), "n_classes": lg.shape[1], "top_labels_are_music_tags": [labels[str(i)] for i in top]}


@tool("clap_onnx")
def t_clap():
    import onnxruntime as ort
    from transformers import AutoTokenizer, ClapFeatureExtractor
    d = MODELS / "clap-larger-music-speech"
    fe = ClapFeatureExtractor.from_pretrained(str(d))
    tok = AutoTokenizer.from_pretrained(str(d))
    sa = ort.InferenceSession(str(d / "onnx" / "audio_model_quantized.onnx"), ort_opts(), providers=["CPUExecutionProvider"])
    st = ort.InferenceSession(str(d / "onnx" / "text_model_quantized.onnx"), ort_opts(), providers=["CPUExecutionProvider"])
    prompts = ["a man speaking", "a woman speaking", "electronic dance music with synthesizers", "distorted electric guitar rock", "silence"]
    enc = tok(prompts, padding=True, return_tensors="np")
    te = st.run(None, {"input_ids": enc["input_ids"].astype(np.int64)})[0]
    te_ = te / np.linalg.norm(te, axis=1, keepdims=True)
    out = {"text_embed": list(te.shape)}
    for clip, expect in (("tts_david.wav", "a man speaking"), ("jeremy_5s.wav", "distorted electric guitar rock")):
        x, sr = load_f32(CLIPS / clip, sr=48000, mono=True)
        feats = fe(x, sampling_rate=48000, return_tensors="np")
        ae = sa.run(None, {"input_features": feats["input_features"].astype(np.float32)})[0]
        ae_ = ae / np.linalg.norm(ae, axis=1, keepdims=True)
        sim = (ae_ @ te_.T)[0]
        top = prompts[int(np.argmax(sim))]
        out[clip] = {"top_prompt": top, "expected": expect, "ok": top == expect, "cos": round(float(sim.max()), 3)}
        out["audio_embed"] = list(ae.shape)
        out["feature_shape"] = list(feats["input_features"].shape)
        assert top == expect, (clip, top)
    return out


def _mel_port():
    """numpy mel front-end for the Essentia ONNX heads (from docs/research/prototypes/lyrics-meaning/mood_onnx.py)."""
    def hz_to_mel(f):
        f = np.asanyarray(f, float); m = f / (200 / 3); lin = 1000 / (200 / 3); logstep = np.log(6.4) / 27
        return np.where(f >= 1000, lin + np.log(np.maximum(f, 1e-10) / 1000) / logstep, m)

    def mel_to_hz(m):
        m = np.asanyarray(m, float); lin = 1000 / (200 / 3); logstep = np.log(6.4) / 27
        return np.where(m >= lin, 1000 * np.exp(logstep * (m - lin)), (200 / 3) * m)

    def mel_fb(sr=16000, n_fft=512, n_mels=96, fmin=0, fmax=8000):
        fft_f = np.linspace(0, sr / 2, n_fft // 2 + 1)
        mel_f = mel_to_hz(np.linspace(hz_to_mel(fmin), hz_to_mel(fmax), n_mels + 2))
        fdiff = np.diff(mel_f); ramps = mel_f[:, None] - fft_f[None, :]
        w = np.zeros((n_mels, len(fft_f)))
        for i in range(n_mels):
            lo = -ramps[i] / fdiff[i]; hi = ramps[i + 2] / fdiff[i + 1]
            w[i] = np.maximum(0, np.minimum(lo, hi))
        w *= (2.0 / (mel_f[2:n_mels + 2] - mel_f[:n_mels]))[:, None]
        return w.astype(np.float32)

    def logmel(y):
        n_fft, hop = 512, 256
        win = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n_fft) / n_fft)).astype(np.float32)
        nfr = 1 + (len(y) - n_fft) // hop
        idx = np.arange(n_fft)[None, :] + hop * np.arange(nfr)[:, None]
        S = np.abs(np.fft.rfft(y[idx] * win, axis=1)) ** 2
        return np.log10(1 + 10000 * (S @ mel_fb().T)).astype(np.float32)

    return logmel


@tool("essentia_mood_onnx")
def t_mood():
    import onnxruntime as ort
    E = MODELS / "essentia"
    S = lambda f: ort.InferenceSession(str(E / f"{f}.onnx"), ort_opts(), providers=["CPUExecutionProvider"])  # noqa: E731
    mus, emo, deam, eff, mt = (S("msd-musicnn-1"), S("emomusic-msd-musicnn-2"), S("deam-msd-musicnn-2"),
                               S("discogs-effnet-bsdynamic-1"), S("mtg_jamendo_moodtheme-discogs-effnet-1"))
    y = mono16k("megafauna_5s.wav")
    X = _mel_port()(y)
    patches = lambda X, size, hop: np.stack([X[i * hop:i * hop + size] for i in range(1 + max(0, len(X) - size) // hop)])  # noqa: E731
    P = patches(X, 187, 93)
    Em = mus.run(["embeddings"], {"melspectrogram": P})[0]
    va = emo.run(None, {"embeddings": Em})[0]
    va2 = deam.run(None, {"model/Placeholder:0": Em})[0]
    P2 = patches(X, 128, 62)
    E2 = eff.run(["embeddings"], {"melspectrogram": P2})[0]
    tags = mt.run(None, {"embeddings": E2})[0]
    return {"musicnn_patches": len(P), "emomusic_va": np.round(va.mean(0), 2).tolist(), "deam_va": np.round(va2.mean(0), 2).tolist(),
            "mood_tags_shape": list(tags.shape)}


# ------------------------------------------------------------------------------------------------ lyrics / voices
@tool("faster_whisper")
def t_fw():
    from faster_whisper import WhisperModel
    import ctranslate2
    d = MODELS / "faster-whisper" / "large-v3"
    t0 = time.time()
    m = WhisperModel(str(d), device="cpu", compute_type="int8", cpu_threads=THREADS)
    load = time.time() - t0
    y, _ = load_f32(CLIPS / "tts_david.wav", sr=16000, mono=True)
    t0 = time.time()
    segs, info = m.transcribe(y, language="en", word_timestamps=True, vad_filter=False, condition_on_previous_text=False, beam_size=5)
    segs = list(segs)
    words = [w for s in segs for w in (s.words or [])]
    text = " ".join(w.word.strip() for w in words).lower().strip(" .")
    ok = text.replace(",", "") == "the quick brown fox jumps over the lazy dog"
    # a 5 s sung clip: counts only (never print the transcription)
    ys = mono16k("jeremy_5s.wav")
    segs2, info2 = m.transcribe(ys, language="en", word_timestamps=True, vad_filter=True, condition_on_previous_text=False)
    n2 = sum(len(s.words or []) for s in segs2)
    return {"load_s": round(load, 1), "tts_exact_match": ok, "tts_words": len(words), "tts_secs": round(time.time() - t0, 1),
            "tts_word_probs_min": round(min(w.probability for w in words), 2), "sung_5s_words": n2,
            "ctranslate2": ctranslate2.__version__}


@tool("forced_align_mms")
def t_mms():
    import torch, torchaudio
    from torchaudio.pipelines import MMS_FA as bundle
    import uroman as ur
    out = {"align_op_available": bool(getattr(torchaudio._extension, "_IS_ALIGN_AVAILABLE", False))}
    d = MODELS / "mms_fa"
    torch.hub.set_dir(str(HOME / "torch" / "hub"))
    model = bundle.get_model(with_star=False, dl_kwargs={"model_dir": str(d)})
    model.eval()
    out["sample_rate"] = bundle.sample_rate
    y, _ = load_f32(CLIPS / "tts_david.wav", sr=16000, mono=True)
    wav = torch.from_numpy(y)[None, :]
    with torch.inference_mode():
        em, _ = model(wav)
    text = (CLIPS / "tts_david.txt").read_text(encoding="utf-8-sig").strip().lower().split()
    labels = bundle.get_labels(star=None)
    dct = bundle.get_dict(star=None)
    tokens = [dct[c] for w in text for c in w]
    if out["align_op_available"]:
        ali, sc = torchaudio.functional.forced_align(em, torch.tensor([tokens], dtype=torch.int32), blank=0)
        spans = torchaudio.functional.merge_tokens(ali[0], sc[0].exp())
        ratio = wav.size(1) / em.size(1) / 16000
        words, i = [], 0
        for w in text:
            sp = spans[i:i + len(w)]; i += len(w)
            words.append((sp[0].start * ratio, sp[-1].end * ratio))
        out["words"] = len(words)
        out["first_word_start_s"] = round(words[0][0], 3)
        out["last_word_end_s"] = round(words[-1][1], 3)
        out["clip_s"] = round(len(y) / 16000, 3)
    out["uroman_sample"] = ur.Uroman().romanize_string("Привет")
    out["emission"] = list(em.shape)
    return out


@tool("stable_ts")
def t_stable():
    import stable_whisper
    d = MODELS / "faster-whisper" / "large-v3"
    m = stable_whisper.load_faster_whisper(str(d), device="cpu", compute_type="int8", cpu_threads=THREADS)
    y, _ = load_f32(CLIPS / "tts_david.wav", sr=16000, mono=True)
    out = {}
    r = m.transcribe(y, language="en", word_timestamps=True, vad=False)
    out["transcribe_words"] = sum(len(s.words) for s in r.segments)
    try:
        r2 = m.align(y, (CLIPS / "tts_david.txt").read_text(encoding="utf-8-sig").strip(), language="en")
        out["align_words"] = sum(len(s.words) for s in r2.segments)
        out["align_first_start"] = round(r2.segments[0].words[0].start, 3)
    except Exception as e:  # noqa: BLE001
        out["align_error"] = f"{type(e).__name__}: {str(e)[:160]}"
    return out


@tool("text_tools")
def t_text():
    import num2words, rapidfuzz.fuzz as fz, uroman
    from g2p_en import G2p
    g = G2p()
    ph = g("hello world")
    return {"num2words": num2words.num2words(42), "rapidfuzz": fz.ratio("jeremy", "jeremy (redux)"), "g2p_phonemes": len(ph),
            "uroman": uroman.Uroman().romanize_string("東京")}


@tool("speaker_embeddings")
def t_speaker():
    import torch, torchaudio
    out = {}
    clips = {"david_a": "tts_david.wav", "david_b": "tts_david2.wav", "zira": "tts_zira.wav"}
    wavs = {k: load_f32(CLIPS / v, sr=16000, mono=True)[0] for k, v in clips.items()}

    def cos(a, b):
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    # --- SpeechBrain ECAPA (explicit local dir, tensors in)
    from speechbrain.inference.speaker import EncoderClassifier
    d = MODELS / "speaker" / "ecapa-voxceleb"
    t0 = time.time()
    from speechbrain.utils.fetching import LocalStrategy
    # Windows without symlink privilege: speechbrain's default SYMLINK strategy raises WinError 1314 -> force COPY
    clf = EncoderClassifier.from_hparams(source=str(d), savedir=str(HOME / "speechbrain" / "ecapa"), run_opts={"device": "cpu"},
                                         local_strategy=LocalStrategy.COPY, overrides={"pretrained_path": str(d)})
    emb = {k: clf.encode_batch(torch.from_numpy(w)[None, :]).squeeze().numpy() for k, w in wavs.items()}
    out["ecapa"] = {"dim": int(emb["zira"].size), "same_voice_cos": round(cos(emb["david_a"], emb["david_b"]), 3),
                    "diff_voice_cos": round(cos(emb["david_a"], emb["zira"]), 3), "secs": round(time.time() - t0, 1)}
    # --- WeSpeaker ONNX (kaldi fbank in torch, then onnxruntime)
    import onnxruntime as ort
    s = ort.InferenceSession(str(MODELS / "speaker" / "wespeaker-resnet34-lm" / "voxceleb_resnet34_LM.onnx"), ort_opts(), providers=["CPUExecutionProvider"])

    def wsp(w):
        f = torchaudio.compliance.kaldi.fbank(torch.from_numpy(w)[None, :] * 32768, num_mel_bins=80, frame_length=25, frame_shift=10,
                                              dither=0.0, sample_frequency=16000, window_type="hamming", use_energy=False)
        f = f - f.mean(0, keepdim=True)
        return s.run(None, {"feats": f[None].numpy().astype(np.float32)})[0][0]

    e2 = {k: wsp(w) for k, w in wavs.items()}
    out["wespeaker"] = {"dim": int(e2["zira"].size), "same_voice_cos": round(cos(e2["david_a"], e2["david_b"]), 3),
                        "diff_voice_cos": round(cos(e2["david_a"], e2["zira"]), 3)}
    # --- the rap battle clip: embed 1.5 s windows (no text), report the spread only
    nye = load_f32(CLIPS / "nye_25s.wav", sr=16000, mono=True)[0]
    wins = [nye[i:i + 24000] for i in range(0, len(nye) - 24000, 24000)]
    E = np.stack([wsp(w) for w in wins])
    E = E / np.linalg.norm(E, axis=1, keepdims=True)
    sim = E @ E.T
    out["nye_25s_windows"] = {"n": len(wins), "mean_pairwise_cos": round(float(sim[np.triu_indices(len(wins), 1)].mean()), 3),
                              "min_pairwise_cos": round(float(sim.min()), 3)}
    return out


# ------------------------------------------------------------------------------------------------ process-level checks
@tool("traps")
def t_traps():
    """Confirm the documented install traps still hold (so downstream code keeps avoiding them)."""
    out = {}
    import soundfile as sf
    try:
        sf.read(str(REPO.parent / "viz" / "Versatile.flac"), dtype="float32")
        out["soundfile_reads_corrupt_versatile"] = True
    except Exception as e:  # noqa: BLE001
        out["soundfile_reads_corrupt_versatile"] = False
        out["soundfile_error"] = f"{type(e).__name__}: {str(e)[:80]}"
    import torchaudio
    try:
        torchaudio.load(str(CLIPS / "jeremy_5s.wav"))
        out["torchaudio_load_works"] = True
    except Exception as e:  # noqa: BLE001
        out["torchaudio_load_works"] = False
        out["torchaudio_load_error"] = f"{type(e).__name__}: {str(e)[:100]}"
    import av
    out["pyav_version"] = av.__version__
    import importlib.metadata as md
    out["onnxruntime_dist"] = [d for d in ("onnxruntime", "onnxruntime-directml", "onnxruntime-gpu") if _has(d)]
    out["tensorflow_installed"] = _has("tensorflow")
    out["symlink_privilege"] = _can_symlink()
    return out


def _has(dist):
    import importlib.metadata as md
    try:
        md.version(dist)
        return True
    except md.PackageNotFoundError:
        return False


def _can_symlink():
    d = Path(tempfile.mkdtemp())
    (d / "a").write_text("x", encoding="utf-8")
    try:
        os.symlink(d / "a", d / "b")
        return True
    except OSError:
        return False


@tool("openmp_coexistence")
def t_openmp():
    """torch + ctranslate2 + onnxruntime + numba + librosa/scipy BLAS in ONE process, each doing real work, then list OpenMP runtimes."""
    import ctypes
    import numba, onnxruntime as ort, torch, ctranslate2, scipy.linalg
    out = {}
    torch.set_num_threads(THREADS)
    a = torch.randn(512, 512); out["torch_mm"] = float((a @ a).sum().isfinite())
    s = ort.InferenceSession(str(MODELS / "essentia" / "msd-musicnn-1.onnx"), ort_opts(), providers=["CPUExecutionProvider"])
    out["ort_run"] = list(s.run(None, {"melspectrogram": np.zeros((1, 187, 96), np.float32)})[0].shape)
    sv = ctranslate2.StorageView.from_array(np.random.rand(256, 256).astype(np.float32))
    out["ct2_cpu_threads_api"] = hasattr(ctranslate2, "set_random_seed")
    from faster_whisper import WhisperModel
    m = WhisperModel(str(MODELS / "faster-whisper" / "large-v3"), device="cpu", compute_type="int8", cpu_threads=THREADS)
    y, _ = load_f32(CLIPS / "tts_david.wav", sr=16000, mono=True)
    segs, _ = m.transcribe(y, language="en", beam_size=1)
    out["ct2_whisper_segments"] = len(list(segs))

    @numba.njit(parallel=True)
    def f(x):
        s = 0.0
        for i in numba.prange(x.shape[0]):
            s += x[i] * 2.0
        return s
    out["numba_parallel"] = float(f(np.arange(1_000_000, dtype=np.float64)))
    out["scipy_blas"] = float(np.linalg.norm(scipy.linalg.inv(np.random.rand(300, 300) + 300 * np.eye(300))))
    # loaded OpenMP / BLAS runtimes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.EnumProcessModules.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    psapi.GetModuleFileNameExW.argtypes = [wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    hs = (wintypes.HMODULE * 4096)(); need = wintypes.DWORD()
    assert psapi.EnumProcessModules(k32.GetCurrentProcess(), hs, ctypes.sizeof(hs), ctypes.byref(need))
    names = []
    buf = ctypes.create_unicode_buffer(1024)
    for h in hs[: need.value // ctypes.sizeof(wintypes.HMODULE)]:
        psapi.GetModuleFileNameExW(k32.GetCurrentProcess(), h, buf, 1024)
        names.append(Path(buf.value).name.lower())
    out["dlls_loaded_total"] = len(names)
    omp = sorted({n for n in names if any(k in n for k in ("iomp", "libomp", "vcomp", "gomp", "libgomp", "openblas", "mkl_"))})
    out["openmp_blas_dlls_loaded"] = omp
    iomp = [n for n in omp if "iomp" in n or "libomp" in n or "vcomp" in n]
    out["openmp_runtime_count"] = len(iomp)
    out["ort_providers"] = ort.get_available_providers()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--no-lock", action="store_true", help="skip the heavy slot (only for light tools)")
    a = ap.parse_args()
    names = a.only.split(",") if a.only else list(REG)
    from heavy_lock import heavy
    import contextlib
    cm = contextlib.nullcontext() if a.no_lock else heavy("env-main-smoke", threads=THREADS)
    resf = CLIPS / "results.json"
    if resf.exists():
        RESULTS.update(json.loads(resf.read_text(encoding="utf-8")))
    with cm:
        for n in names:
            t0 = time.time()
            try:
                d = REG[n]()
                RESULTS[n] = {"ok": True, "secs": round(time.time() - t0, 1), "detail": d}
                print(f"PASS {n} ({time.time()-t0:.1f}s) {json.dumps(d, default=str)[:900]}", flush=True)
            except BaseException as e:  # noqa: BLE001
                RESULTS[n] = {"ok": False, "secs": round(time.time() - t0, 1), "error": f"{type(e).__name__}: {str(e)[:500]}",
                              "tb": traceback.format_exc()[-1500:]}
                print(f"FAIL {n} ({time.time()-t0:.1f}s) {type(e).__name__}: {str(e)[:500]}", flush=True)
                print(traceback.format_exc()[-1200:], flush=True)
            resf.write_text(json.dumps(RESULTS, indent=1, default=str), encoding="utf-8")
    print("SUMMARY", {k: v["ok"] for k, v in RESULTS.items()})


if __name__ == "__main__":
    main()
