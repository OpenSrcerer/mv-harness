"""bench-music: run every music-analysis tool of PLAN 5 on one song and keep the RAW outputs.

    run (always under a heavy slot, 6 threads):
      scripts\\run.ps1 python scripts\\heavy_lock.py run --owner bench-music --threads 6 -- <python> <this file> <slug> [--only a,b] [--force a,b]

Output: tests/.cache/real/<slug>/<step>/...   Each step writes _done.json {secs, cpu, load, versions} or _error.json and is skipped when
_done.json exists (resumable).  Never prints lyric text (this script never touches text).  Offline (HF_HUB_OFFLINE=1 expected).
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
REPO = Path(__file__).resolve().parents[4]
THREADS = int(os.environ.get("MVH_THREADS", "6"))
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[_v] = str(THREADS)

import numpy as np  # noqa: E402

HOME = Path(os.environ["MVH_HOME"])
MODELS = Path(os.environ["MVH_MODELS_DIR"])
FFMPEG = os.environ["MVH_FFMPEG"]
FFPROBE = os.environ.get("MVH_FFPROBE", FFMPEG.replace("ffmpeg.exe", "ffprobe.exe"))
LOCKS = HOME / "locks"
CACHE = REPO / "tests" / ".cache" / "real"
PROTO = REPO / "docs" / "research" / "prototypes" / "spectral"
PLAY = REPO.parent
SONGS = {
    "megafauna": PLAY / "viz" / "MEGAFAUNA.flac",
    "versatile": PLAY / "viz" / "Versatile.flac",
    "jeremy": REPO / "songs" / "Jeremy (Redux Version).flac",
    "newton-vs-nye": REPO / "songs" / "Sir Isaac Newton vs Bill Nye.flac",
}
STEMS4 = ("drums", "bass", "other", "vocals")
STEMS6 = STEMS4 + ("guitar", "piano")
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


# ------------------------------------------------------------------ helpers
class _FT(ctypes.Structure):
    _fields_ = [("lo", ctypes.c_uint32), ("hi", ctypes.c_uint32)]


def _systimes():
    i, k, u = _FT(), _FT(), _FT()
    ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(i), ctypes.byref(k), ctypes.byref(u))
    v = lambda f: (f.hi << 32) | f.lo  # noqa: E731
    idle, kern, user = v(i), v(k), v(u)
    return idle, kern + user  # kernel time includes idle


def lock_owners():
    out = []
    for p in sorted(LOCKS.glob("*.lock")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append(f"{p.stem}:{d.get('owner')}")
        except Exception:  # noqa: BLE001
            out.append(f"{p.stem}:?")
    return out


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def jdump(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def jload(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256(path, n=None):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def pkg_ver(name):
    try:
        from importlib.metadata import version
        return version(name)
    except Exception:  # noqa: BLE001
        return None


class Ctx:
    def __init__(self, slug):
        self.slug = slug
        self.root = CACHE / slug
        self.src = SONGS[slug]
        self._mix = None

    def d(self, step):
        p = self.root / step
        p.mkdir(parents=True, exist_ok=True)
        return p

    # canonical mix (float32 stereo at native sr), from our own WAV
    def mix(self):
        if self._mix is None:
            import soundfile as sf
            x, sr = sf.read(str(self.d("decode") / "mix.wav"), dtype="float32", always_2d=True)
            self._mix = (x, sr)
        return self._mix

    def mono(self, sr_out=None):
        import soxr
        x, sr = self.mix()
        m = x.mean(1).astype(np.float32)
        if sr_out and sr_out != sr:
            m = soxr.resample(m, sr, sr_out).astype(np.float32)
        return m

    def stem(self, model, name):
        import soundfile as sf
        x, sr = sf.read(str(self.root / "demucs" / model / f"{name}.wav"), dtype="float32", always_2d=True)
        return x, sr

    def stem_mono(self, model, name, sr_out):
        import soxr
        x, sr = self.stem(model, name)
        m = x.mean(1).astype(np.float32)
        return soxr.resample(m, sr, sr_out).astype(np.float32) if sr != sr_out else m


def ort_opts(n=None):
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.intra_op_num_threads = n or THREADS
    so.inter_op_num_threads = 1
    return so


STEPS = {}


def step(name, deps=()):
    def deco(fn):
        STEPS[name] = (fn, tuple(deps))
        return fn
    return deco


# ------------------------------------------------------------------ 1 decode
@step("decode")
def s_decode(c: Ctx):
    import soundfile as sf
    d = c.d("decode")
    pr = json.loads(subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration,format_name:format_tags=title,artist,album,date,genre:stream=index,codec_name,sample_rate,channels,bits_per_raw_sample,duration,codec_type",
                                    "-of", "json", str(c.src)], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout)
    a = [s for s in pr["streams"] if s.get("codec_type") == "audio"][0]
    sr, ch = int(a["sample_rate"]), int(a["channels"])
    r = subprocess.run([FFMPEG, "-v", "warning", "-i", str(c.src), "-map", "0:a:0", "-vn", "-f", "f32le", "-"], capture_output=True)
    x = np.frombuffer(r.stdout, np.float32).reshape(-1, ch).copy()
    warn = [w for w in r.stderr.decode("utf-8", "replace").splitlines() if w.strip()]
    sf.write(str(d / "mix.wav"), x, sr, subtype="FLOAT")
    mono = x.mean(1)
    rms = float(np.sqrt(np.mean(mono ** 2)))
    info = {"source_file": c.src.name, "ffprobe": pr, "decoder_warning_count": len(warn), "decoder_warnings_first5": warn[:5],
            "sr": sr, "channels": ch, "samples": int(len(x)), "duration_s": len(x) / sr, "peak": float(np.abs(x).max()),
            "peak_dbfs": float(20 * np.log10(np.abs(x).max() + 1e-12)), "rms_dbfs": float(20 * np.log10(rms + 1e-12)),
            "mix_wav_sha256": sha256(d / "mix.wav"), "ffmpeg": subprocess.run([FFMPEG, "-version"], capture_output=True, text=True).stdout.splitlines()[0],
            "format": "mix.wav = IEEE float32 WAV, native sr, 2ch (own writer); decode via ffmpeg -map 0:a:0 -f f32le"}
    jdump(d / "decode.json", info)
    return {"sr": sr, "dur": info["duration_s"], "warnings": len(warn)}


# ------------------------------------------------------------------ 2 demucs
@step("demucs", ("decode",))
def s_demucs(c: Ctx):
    import onnxruntime as ort
    import soundfile as sf
    import soxr
    from demucs_onnx import inference as di
    from demucs_onnx._hub import MODEL_REGISTRY
    x, sr = c.mix()
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    if sr != 44100:
        x = soxr.resample(x, sr, 44100).astype(np.float32)
    mix = np.ascontiguousarray(x.T)
    out = {"input_sr": sr, "model_sr": 44100, "models": {}}
    for model, rel in (("htdemucs", "demucs-onnx/htdemucs-onnx/htdemucs_fp16weights.onnx"), ("htdemucs_6s", "demucs-onnx/htdemucs-6s-onnx/htdemucs_6s_fp16weights.onnx")):
        sd = c.d("demucs") / model
        sd.mkdir(exist_ok=True)
        sess = ort.InferenceSession(str(MODELS / rel), ort_opts(), providers=["CPUExecutionProvider"])
        t0 = time.time()
        st = di._chunked_separate_single(sess, MODEL_REGISTRY[model].sources, mix, verbose=False, progress=False)
        dt = time.time() - t0
        ssum = sum(st.values())
        resid = float(np.sqrt(np.mean((ssum - mix) ** 2)) / (np.sqrt(np.mean(mix ** 2)) + 1e-12))
        rms = {}
        for k, v in st.items():
            sf.write(str(sd / f"{k}.wav"), v.T.astype(np.float32), 44100, subtype="FLOAT")
            rms[k] = float(20 * np.log10(np.sqrt(np.mean(v ** 2)) + 1e-12))
        out["models"][model] = {"stems": list(st), "secs": round(dt, 1), "sum_vs_mix_relrms": round(resid, 4), "stem_rms_dbfs": rms,
                                "rel_to_mix_realtime_factor": round(dt / (mix.shape[1] / 44100), 3), "onnx": rel}
        del sess, st
    jdump(c.d("demucs") / "demucs.json", out)
    return out


# ------------------------------------------------------------------ 3 beat_this
@step("beat_this", ("decode",))
def s_beat_this(c: Ctx):
    from beat_this.inference import Audio2Frames
    from beat_this.model.postprocessor import Postprocessor
    from beat_this.utils import infer_beat_numbers
    d = c.d("beat_this")
    x, sr = c.mix()
    mono = x.mean(1)
    ck = MODELS / "beat_this" / "final0.ckpt"
    a2f = Audio2Frames(checkpoint_path=str(ck), device="cpu")
    t0 = time.time()
    bl, dl = a2f(mono, sr)
    t_inf = time.time() - t0
    bl, dl = bl.detach().cpu().numpy().astype(np.float32), dl.detach().cpu().numpy().astype(np.float32)
    np.save(d / "logits_beat.npy", bl)
    np.save(d / "logits_downbeat.npy", dl)
    import torch
    beats, downbeats = Postprocessor(type="minimal")(torch.from_numpy(bl), torch.from_numpy(dl))
    beats, downbeats = np.asarray(beats, float), np.asarray(downbeats, float)
    try:
        nums = infer_beat_numbers(beats, downbeats).astype(int).tolist()
    except Exception as e:  # noqa: BLE001
        nums = None
        log(f"beat numbers failed: {e}")
    ibi = np.diff(beats)
    res = {"model": "beat_this final0", "checkpoint_sha256": sha256(ck), "logit_fps": 50, "n_frames": int(len(bl)), "inference_s": round(t_inf, 2),
           "postprocessor": "minimal (no DBN)", "beats": beats.tolist(), "downbeats": downbeats.tolist(), "beat_numbers": nums,
           "median_bpm": float(60 / np.median(ibi)) if len(ibi) else None,
           "format": "logits_*.npy float32 [T] at 50 fps (frame i centred at i/50 s, raw logits, sigmoid = prob); beat_this.json times in s"}
    jdump(d / "beat_this.json", res)
    return {"beats": len(beats), "downbeats": len(downbeats), "bpm": res["median_bpm"], "inference_s": round(t_inf, 2)}


# ------------------------------------------------------------------ 4 allin1
@step("allin1", ("demucs",))
def s_allin1(c: Ctx):
    import torch
    import allin1_infer
    from allin1_infer import analyze
    from allin1_infer.stems_input import StemsInput
    torch.set_num_threads(THREADS)
    d = c.d("allin1")
    sd = c.root / "demucs" / "htdemucs"
    work = Path(tempfile.mkdtemp(prefix="allin1_", dir=str(d)))
    try:
        r = analyze(stems_input=StemsInput(bass=sd / "bass.wav", drums=sd / "drums.wav", other=sd / "other.wav", vocals=sd / "vocals.wav", identifier=c.slug),
                    model="harmonix-all", device="cpu", include_activations=True, include_embeddings=True,
                    demix_dir=work / "demix", spec_dir=work / "spec", multiprocess=False)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    r = r[0] if isinstance(r, list) else r
    acts = {k: np.asarray(v, np.float32) for k, v in (r.activations or {}).items()}
    np.savez_compressed(d / "activations.npz", **acts)
    emb = np.asarray(r.embeddings, np.float32)
    np.save(d / "embeddings.npy", emb)
    from allin1_infer import config as acfg
    labels = getattr(acfg, "LABELS", None)
    jdump(d / "allin1.json", {"model": "harmonix-all (8 folds)", "version": allin1_infer.__version__, "bpm": r.bpm, "beats": [float(b) for b in r.beats],
                              "downbeats": [float(b) for b in r.downbeats], "beat_positions": [int(b) for b in r.beat_positions],
                              "segments": [{"start": float(s.start), "end": float(s.end), "label": s.label} for s in r.segments],
                              "activation_fps": r.activation_fps, "activation_keys": {k: list(v.shape) for k, v in acts.items()},
                              "embeddings_shape": list(emb.shape), "label_order": [str(l) for l in labels] if labels else None,
                              "format": "activations.npz: beat[T], downbeat[T], segment[T], label[10,T] (probabilities, 100 fps); embeddings.npy float32 [stem4,T,24,8]; allin1.json times in s"})
    return {"bpm": r.bpm, "beats": len(r.beats), "segments": len(r.segments)}


# ------------------------------------------------------------------ 5 librosa
@step("librosa", ("decode",))
def s_librosa(c: Ctx):
    import librosa
    d = c.d("librosa")
    SR, HOP = 22050, 512
    y = c.mono(SR)
    oenv = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
    tg = librosa.feature.tempogram(onset_envelope=oenv, sr=SR, hop_length=HOP, win_length=384)
    bpm_axis = librosa.tempo_frequencies(384, hop_length=HOP, sr=SR)
    tempo_g = float(np.atleast_1d(librosa.feature.tempo(onset_envelope=oenv, sr=SR, hop_length=HOP, aggregate=np.mean))[0])
    tempo_dyn = np.asarray(librosa.feature.tempo(onset_envelope=oenv, sr=SR, hop_length=HOP, aggregate=None), np.float32)
    tempo_med = float(np.median(tempo_dyn))
    # candidate list: peaks of the time-averaged tempogram (autocorrelation) over 40..240 bpm
    mean_tg = tg.mean(1)
    sel = (bpm_axis >= 40) & (bpm_axis <= 240)
    idx = np.where(sel)[0]
    cand = []
    for i in idx:
        if 0 < i < len(mean_tg) - 1 and mean_tg[i] >= mean_tg[i - 1] and mean_tg[i] > mean_tg[i + 1]:
            cand.append((float(mean_tg[i]), float(bpm_axis[i])))
    cand.sort(reverse=True)
    pl = librosa.beat.plp(onset_envelope=oenv, sr=SR, hop_length=HOP)
    plp_pk = librosa.util.peak_pick(pl, pre_max=3, post_max=3, pre_avg=3, post_avg=3, delta=0.0, wait=5)
    tempo_bt, bt = librosa.beat.beat_track(onset_envelope=oenv, sr=SR, hop_length=HOP, units="time")
    ons = librosa.onset.onset_detect(onset_envelope=oenv, sr=SR, hop_length=HOP, units="time")
    np.save(d / "onset_envelope.npy", oenv.astype(np.float32))
    np.save(d / "plp.npy", pl.astype(np.float32))
    np.save(d / "tempo_dynamic.npy", tempo_dyn)
    np.savez_compressed(d / "tempogram.npz", tempogram=tg.astype(np.float16), bpm_axis=bpm_axis.astype(np.float32))
    res = {"sr": SR, "hop": HOP, "frame_rate": SR / HOP, "tempo_global_mean_agg": tempo_g, "tempo_dynamic_median": tempo_med,
           "tempo_dynamic_p10_p90": [float(np.percentile(tempo_dyn, 10)), float(np.percentile(tempo_dyn, 90))],
           "tempogram_candidates_bpm_salience": [[round(b, 2), round(s, 4)] for s, b in cand[:10]],
           "beat_track_tempo": float(np.atleast_1d(tempo_bt)[0]), "beat_track_beats": [float(b) for b in bt],
           "plp_peak_times": (plp_pk * HOP / SR).tolist(), "onset_times": [float(o) for o in ons],
           "librosa": librosa.__version__,
           "format": "onset_envelope.npy/plp.npy float32 [T] at 22050/512 Hz; tempo_dynamic.npy bpm per frame; tempogram.npz float16 [384,T] + bpm_axis"}
    jdump(d / "librosa.json", res)
    return {"tempo_mean": tempo_g, "tempo_median_dyn": tempo_med, "top_cands": res["tempogram_candidates_bpm_salience"][:4]}


# ------------------------------------------------------------------ 6 spectral proto
@step("spectral_proto", ("decode",))
def s_spectral(c: Ctx):
    d = c.d("spectral_proto")
    mixp = c.root / "decode" / "mix.wav"
    t0 = time.time()
    r = subprocess.run([sys.executable, "-X", "utf8", str(PROTO / "proto.py"), str(mixp), str(d)], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(d))
    (d / "proto.stdout.txt").write_text(r.stdout, encoding="utf-8")
    (d / "proto.stderr.txt").write_text(r.stderr[-4000:], encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError("proto.py rc=%s: %s" % (r.returncode, r.stderr[-600:]))
    i0 = r.stdout.find("{\n")
    summ = json.loads(r.stdout[i0:])
    jdump(d / "summary.json", summ)
    I = summ["integrated_lufs"]
    t1 = time.time()
    r2 = subprocess.run([sys.executable, "-X", "utf8", str(PROTO / "seg.py"), str(d / "curves.f32"), str(I)], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(d))
    (d / "dynamics_segments.txt").write_text(r2.stdout, encoding="utf-8")
    segs = []
    import re
    for ln in r2.stdout.splitlines():
        m = re.match(r"\s*([\d.]+)-\s*([\d.]+)\s+rel=\s*([+-][\d.]+) LU\s+bass=\s*([-\d.]+) dB\s+kick/s=\s*([\d.]+)\s+slope=([+-][\d.]+)\s+(\w+)\s*(.*)", ln)
        if m:
            segs.append({"t0": float(m[1]), "t1": float(m[2]), "rel_lu": float(m[3]), "bass_db": float(m[4]), "kick_hz": float(m[5]), "slope": float(m[6]),
                         "level": m[7], "tags": [t for t in m[8].split(",") if t]})
    jdump(d / "dynamics_segments.json", {"integrated_lufs": I, "segments": segs, "raw_header": r2.stdout.splitlines()[0] if r2.stdout else "",
                                         "format": "curves.f32 = float32 LE row-major [frames,34] at 100 Hz, columns per seg.py COLS; spectrum128.u8 [frames,128]; see proto.py"})
    (d / "curve_columns.json").write_text(json.dumps(["viz_bass", "viz_mid", "viz_high", "db_sub", "db_bass", "db_lowmid", "db_mid", "db_highmid", "db_presence", "db_air", "db_viz_bass", "db_viz_mid", "db_viz_high", "db_kick", "kick", "kick_raw", "mid_hit", "high_hit", "flux_low", "flux_mid", "flux_high", "rms_db", "lufs_m", "lufs_s", "centroid_hz", "rolloff_hz", "flatness", "bandwidth_hz", "width", "corr", "balance_db", "width_bass", "width_mid", "width_high"]), encoding="utf-8")
    return {"proto_s": round(t1 - t0, 1), "seg_s": round(time.time() - t1, 1), "lufs": I, "lra": summ["lra_lu"], "dyn_segments": len(segs)}


# ------------------------------------------------------------------ 7 chords
@step("chords", ("decode",))
def s_chords(c: Ctx):
    from lv_chordia.chord_recognition import chord_recognition
    d = c.d("chords")
    cwd = os.getcwd()
    os.chdir(d)
    try:
        t0 = time.time()
        res = chord_recognition(str(c.root / "decode" / "mix.wav"), "submission")
        dt = time.time() - t0
    finally:
        os.chdir(cwd)
    jdump(d / "chords.json", {"model": "lv-chordia 1.1.0 ismir2019 chordnet (5-model ensemble, bundled), dict=submission", "segments": res, "secs": round(dt, 1),
                              "format": "segments [{start_time,end_time,chord}] seconds, chord = Harte-like 'C:maj', 'N' = no chord"})
    from collections import Counter
    cnt = Counter()
    for s in res:
        cnt[s["chord"]] += s["end_time"] - s["start_time"]
    return {"segments": len(res), "secs": round(dt, 1), "top": [(k, round(v, 1)) for k, v in cnt.most_common(5)]}


# ------------------------------------------------------------------ 8 key
KS_MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KS_MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
TP_MAJ = np.array([5.0, 2.0, 3.5, 2.0, 4.5, 4.0, 2.0, 4.5, 2.0, 3.5, 1.5, 4.0])
TP_MIN = np.array([5.0, 2.0, 3.5, 4.5, 2.0, 4.0, 2.0, 4.5, 3.5, 2.0, 1.5, 4.0])


def profile_key(chroma12, maj, mn):
    """-> list of (score, 'C major') best first (Pearson correlation against rotated profiles)."""
    c = np.asarray(chroma12, float)
    out = []
    for pc in range(12):
        for mode, prof in (("major", maj), ("minor", mn)):
            r = np.corrcoef(c, np.roll(prof, pc))[0, 1]
            out.append((float(r), f"{NAMES[pc]} {mode}"))
    out.sort(reverse=True)
    return out


@step("key", ("decode",))
def s_key(c: Ctx):
    import librosa
    import onnxruntime as ort
    d = c.d("key")
    cfg = jload(MODELS / "skey" / "config.json")
    sess = ort.InferenceSession(str(MODELS / "skey" / "skey.onnx"), ort_opts(), providers=["CPUExecutionProvider"])
    y = c.mono(22050)

    def skey(seg):
        seg = seg / (np.max(np.abs(seg)) + 1e-9)
        return np.asarray(sess.run(None, {"audio": seg[None, :].astype(np.float32)})[0]).reshape(-1)

    res = {"skey_keymap": cfg["keyMap"], "skey_revision_note": "musetric/skey-onnx (see models.lock.json skey_onnx)"}
    t0 = time.time()
    try:
        g = skey(y)
        res["skey_global_probs"] = g.tolist()
        res["skey_global_top3"] = [[cfg["keyMap"][i], round(float(g[i]), 4)] for i in np.argsort(-g)[:3]]
    except Exception as e:  # noqa: BLE001
        res["skey_global_error"] = f"{type(e).__name__}: {str(e)[:200]}"
    W, H = 30 * 22050, 15 * 22050
    wins = []
    for s in range(0, max(1, len(y) - W // 2), H):
        seg = y[s:s + W]
        if len(seg) < 10 * 22050:
            break
        p = skey(seg)
        wins.append({"t0": s / 22050, "t1": (s + len(seg)) / 22050, "top": cfg["keyMap"][int(np.argmax(p))], "p": round(float(p.max()), 4), "probs": [round(float(v), 4) for v in p]})
    res["skey_windows_30s_hop15s"] = wins
    res["skey_secs"] = round(time.time() - t0, 1)
    # profile fallback: harmonic CQT chroma + KS / Temperley
    t1 = time.time()
    h = librosa.effects.harmonic(y)
    ch = librosa.feature.chroma_cqt(y=h, sr=22050, hop_length=2048, bins_per_octave=36, n_octaves=6)
    res["profile_chroma_hop_s"] = 2048 / 22050
    gsum = ch.sum(1)
    res["chroma_global"] = (gsum / gsum.sum()).tolist()
    res["profile_global_ks_top3"] = [[k, round(s, 4)] for s, k in profile_key(gsum, KS_MAJ, KS_MIN)[:3]]
    res["profile_global_temperley_top3"] = [[k, round(s, 4)] for s, k in profile_key(gsum, TP_MAJ, TP_MIN)[:3]]
    fw, fh = int(30 / res["profile_chroma_hop_s"]), int(15 / res["profile_chroma_hop_s"])
    pw = []
    for s in range(0, max(1, ch.shape[1] - fw // 2), fh):
        seg = ch[:, s:s + fw]
        if seg.shape[1] < fw // 3:
            break
        best = profile_key(seg.sum(1), KS_MAJ, KS_MIN)[0]
        pw.append({"t0": s * res["profile_chroma_hop_s"], "top": best[1], "r": round(best[0], 4)})
    res["profile_windows_ks_30s_hop15s"] = pw
    res["profile_secs"] = round(time.time() - t1, 1)
    res["format"] = "key.json; skey probs[24] in keyMap order; chroma_global [12] C..B; windows list"
    jdump(d / "key.json", res)
    return {"skey_top3": res.get("skey_global_top3"), "ks_top3": res["profile_global_ks_top3"], "tp_top1": res["profile_global_temperley_top3"][0]}


# ------------------------------------------------------------------ 9 notes (basic-pitch)
@step("notes", ("demucs",))
def s_notes(c: Ctx):
    import soundfile as sf
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import Model, predict
    d = c.d("notes")
    m = Model(ICASSP_2022_MODEL_PATH)
    out = {}
    for model, name in (("htdemucs", "bass"), ("htdemucs", "other"), ("htdemucs_6s", "guitar")):
        y = c.stem_mono(model, name, 22050)
        tmp = d / f"_tmp_{name}.wav"
        sf.write(str(tmp), y, 22050, subtype="FLOAT")
        t0 = time.time()
        mo, midi, notes = predict(str(tmp), m)
        dt = time.time() - t0
        tmp.unlink(missing_ok=True)
        midi.write(str(d / f"{model}_{name}.mid"))
        arr = [[round(float(n[0]), 4), round(float(n[1]), 4), int(n[2]), round(float(n[3]), 4)] for n in notes]
        jdump(d / f"{model}_{name}.json", {"model": "basic-pitch 0.4.0 ICASSP_2022 (onnx)", "source_stem": f"{model}/{name}", "notes_fields": ["start_s", "end_s", "midi", "amplitude"],
                                          "notes": arr, "secs": round(dt, 1)})
        p = [a[2] for a in arr]
        out[f"{model}/{name}"] = {"notes": len(arr), "secs": round(dt, 1), "midi_p5_p95": [int(np.percentile(p, 5)), int(np.percentile(p, 95))] if p else None}
    jdump(d / "notes.json", out)
    return out


# ------------------------------------------------------------------ 10 pitch (SwiftF0 + RMVPE on htdemucs vocals)
@step("pitch", ("demucs",))
def s_pitch(c: Ctx):
    from rmvpe_onnx import RMVPE
    from swift_f0 import SwiftF0, segment_notes
    d = c.d("pitch")
    y = c.stem_mono("htdemucs", "vocals", 16000)
    det = SwiftF0(threads=THREADS)
    t0 = time.time()
    r = det.detect(y, 16000, fmin=65.0, fmax=1400.0)
    t_sw = time.time() - t0
    np.savez_compressed(d / "swiftf0.npz", t=r.timestamps.astype(np.float32), hz=r.pitch_hz.astype(np.float32), conf=r.confidence.astype(np.float32), loudness_db=r.loudness_db.astype(np.float32))
    notes = segment_notes(r)
    jdump(d / "swiftf0_notes.json", {"fields": ["start_s", "end_s", "midi"], "notes": [[round(float(n.start), 3), round(float(n.end), 3), int(getattr(n, "pitch_midi", getattr(n, "midi", 0)))] for n in notes] if notes else []})
    t0 = time.time()
    rm = RMVPE(model_path=str(MODELS / "rmvpe" / "rmvpe.onnx"), device="cpu")
    t, f, conf, act = rm.predict(y, 16000)
    t_rm = time.time() - t0
    np.savez_compressed(d / "rmvpe.npz", t=np.asarray(t, np.float32), hz=np.asarray(f, np.float32), conf=np.asarray(conf, np.float32))
    hz = r.pitch_hz
    v = (r.confidence > 0.9) & (hz > 0) & (r.loudness_db > np.percentile(r.loudness_db, 30))
    midi = 69 + 12 * np.log2(hz[v] / 440.0)
    pc = lambda m: f"{NAMES[int(round(m)) % 12]}{int(round(m)) // 12 - 1}"  # noqa: E731
    stats = {"swiftf0_secs": round(t_sw, 1), "rmvpe_secs": round(t_rm, 1), "swiftf0_frames": len(hz), "rmvpe_frames": len(f),
             "swiftf0_voiced_gated_frac": round(float(v.mean()), 3), "swiftf0_voiced_s": round(float(v.sum() * 0.016), 1)}
    if v.sum() > 50:
        ps = np.percentile(midi, [2, 10, 50, 90, 98])
        stats["swiftf0_midi_p2_p10_p50_p90_p98"] = [round(float(x), 2) for x in ps]
        stats["swiftf0_range_names_p2_p98"] = [pc(ps[0]), pc(ps[-1])]
    fz = np.asarray(f)
    vr = (fz > 0) & (np.asarray(conf) >= 0.3)  # RMVPE emits a pitch for every frame; gate on its confidence
    if vr.sum() > 50:
        mr = 69 + 12 * np.log2(fz[vr] / 440.0)
        stats["rmvpe_voiced_frac"] = round(float(vr.mean()), 3)
        stats["rmvpe_midi_p2_p10_p50_p90_p98"] = [round(float(x), 2) for x in np.percentile(mr, [2, 10, 50, 90, 98])]
    # octave agreement between the two on frames where both voiced
    ts_sw = r.timestamps
    fr = np.interp(ts_sw, np.asarray(t), fz)
    both = v & (fr > 0)
    if both.sum() > 50:
        dm = 12 * np.log2(hz[both] / fr[both])
        stats["agree_both_voiced_frames"] = int(both.sum())
        stats["agree_within_1_semitone"] = round(float(np.mean(np.abs(dm) < 1)), 3)
        stats["agree_octave_off"] = round(float(np.mean(np.abs(np.abs(dm) - 12) < 1)), 3)
    stats["format"] = "swiftf0.npz t/hz/conf/loudness_db float32 (16 ms hop); rmvpe.npz t/hz/conf (10 ms hop, hz 0 = unvoiced); *_notes.json"
    jdump(d / "pitch.json", stats)
    return stats


# ------------------------------------------------------------------ 11 instruments (CED + CLAP)
CLAP_PROMPTS = [
    "a person singing", "a man rapping", "a man speaking", "a woman singing", "a choir singing", "distorted electric guitar", "clean electric guitar",
    "acoustic guitar", "bass guitar", "synth bass", "sub bass drop", "lead synthesizer", "synth pad", "arpeggiated synthesizer", "electronic drum machine",
    "acoustic drum kit", "kick drum", "snare drum", "hi-hats", "piano", "string orchestra", "cello", "brass", "organ", "sound effects and risers",
    "vocal chops", "silence", "crowd noise", "electronic dance music", "grunge rock",
]


def windows(n, sr, win_s, hop_s):
    W, H = int(win_s * sr), int(hop_s * sr)
    starts = list(range(0, max(1, n - W + 1), H))
    if n > W and starts[-1] + W < n:
        starts.append(n - W)
    return starts, W


@step("instruments", ("demucs",))
def s_instruments(c: Ctx):
    import onnxruntime as ort
    from transformers import AutoTokenizer, ClapFeatureExtractor
    d = c.d("instruments")
    cfg = jload(MODELS / "ced-base" / "config.json")
    labels = [cfg["id2label"][str(i)] for i in range(len(cfg["id2label"]))]
    ced = ort.InferenceSession(str(MODELS / "ced-base" / "model.onnx"), ort_opts(), providers=["CPUExecutionProvider"])
    srcs = {"mix": lambda: c.mono(16000)}
    for n in STEMS4:
        srcs[f"htdemucs_{n}"] = (lambda n=n: c.stem_mono("htdemucs", n, 16000))
    for n in ("guitar", "piano"):
        srcs[f"htdemucs_6s_{n}"] = (lambda n=n: c.stem_mono("htdemucs_6s", n, 16000))
    timing = {}
    summ = {"labels_file": "ced_labels.json"}
    jdump(d / "ced_labels.json", labels)
    t_all = time.time()
    for name, fn in srcs.items():
        y = fn()
        starts, W = windows(len(y), 16000, 4.0, 1.0)
        t0 = time.time()
        P = []
        for i in range(0, len(starts), 16):
            fr = np.stack([y[s:s + W] if len(y[s:s + W]) == W else np.pad(y[s:s + W], (0, W - len(y[s:s + W]))) for s in starts[i:i + 16]])
            lg = ced.run(None, {"waveform": fr})[0]
            P.append(lg)  # the ONNX already outputs probabilities (0..1), NOT logits
        P = np.concatenate(P).astype(np.float16)
        timing[f"ced_{name}"] = round(time.time() - t0, 1)
        np.savez_compressed(d / f"ced_{name}.npz", probs=P, t_start=np.asarray(starts, np.float32) / 16000, win_s=np.float32(4.0))
        m = P.astype(np.float32).mean(0)
        top = np.argsort(-m)[:12]
        summ[f"ced_{name}_top12_mean"] = [[labels[i], round(float(m[i]), 3)] for i in top]
    # CLAP
    cd = MODELS / "clap-larger-music-speech"
    fe = ClapFeatureExtractor.from_pretrained(str(cd))
    tok = AutoTokenizer.from_pretrained(str(cd))
    sa = ort.InferenceSession(str(cd / "onnx" / "audio_model_quantized.onnx"), ort_opts(), providers=["CPUExecutionProvider"])
    st = ort.InferenceSession(str(cd / "onnx" / "text_model_quantized.onnx"), ort_opts(), providers=["CPUExecutionProvider"])
    enc = tok(CLAP_PROMPTS, padding=True, return_tensors="np")
    te = st.run(None, {"input_ids": enc["input_ids"].astype(np.int64)})[0]
    te = te / np.linalg.norm(te, axis=1, keepdims=True)
    np.save(d / "clap_text_embeds.npy", te.astype(np.float32))
    jdump(d / "clap_prompts.json", CLAP_PROMPTS)
    csrc = {"mix": lambda: c.mono(48000)}
    for n in STEMS4:
        csrc[f"htdemucs_{n}"] = (lambda n=n: c.stem_mono("htdemucs", n, 48000))
    for name, fn in csrc.items():
        y = fn()
        starts, W = windows(len(y), 48000, 10.0, 5.0)
        t0 = time.time()
        E = []
        for s in starts:
            seg = y[s:s + W]
            feats = fe(seg, sampling_rate=48000, return_tensors="np")
            ae = sa.run(None, {"input_features": feats["input_features"].astype(np.float32)})[0]
            E.append(ae[0] / np.linalg.norm(ae[0]))
        E = np.stack(E).astype(np.float32)
        timing[f"clap_{name}"] = round(time.time() - t0, 1)
        sims = E @ te.T
        np.savez_compressed(d / f"clap_{name}.npz", audio_embeds=E.astype(np.float16), sims=sims.astype(np.float16), t_start=np.asarray(starts, np.float32) / 48000, win_s=np.float32(10.0))
        m = sims.mean(0)
        summ[f"clap_{name}_top8_mean_cos"] = [[CLAP_PROMPTS[i], round(float(m[i]), 3)] for i in np.argsort(-m)[:8]]
    summ["timings_s"] = timing
    summ["total_s"] = round(time.time() - t_all, 1)
    summ["format"] = "ced_<src>.npz probs float16 [W,527] (model output is already probability), t_start s, 4 s windows hop 1 s (last window end-aligned); clap_<src>.npz audio_embeds [W,512], sims [W,P] cosine vs clap_text_embeds.npy, 10 s windows hop 5 s"
    jdump(d / "instruments.json", summ)
    return {"total_s": summ["total_s"], "mix_top": summ["ced_mix_top12_mean"][:5]}


# ------------------------------------------------------------------ 12 mood (Essentia ONNX)
def _mel_port():
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
        fb = mel_fb().T
        out = np.empty((nfr, 96), np.float32)
        for s in range(0, nfr, 4096):
            e = min(nfr, s + 4096)
            idx = np.arange(n_fft)[None, :] + hop * np.arange(s, e)[:, None]
            S = np.abs(np.fft.rfft(y[idx] * win, axis=1)) ** 2
            out[s:e] = np.log10(1 + 10000 * (S @ fb)).astype(np.float32)
        return out
    return logmel


@step("mood", ("decode",))
def s_mood(c: Ctx):
    import onnxruntime as ort
    d = c.d("mood")
    E = MODELS / "essentia"
    S = lambda f: ort.InferenceSession(str(E / f"{f}.onnx"), ort_opts(), providers=["CPUExecutionProvider"])  # noqa: E731
    mus, emo, deam, eff, mt = (S("msd-musicnn-1"), S("emomusic-msd-musicnn-2"), S("deam-msd-musicnn-2"), S("discogs-effnet-bsdynamic-1"), S("mtg_jamendo_moodtheme-discogs-effnet-1"))
    classes = jload(E / "mtg_jamendo_moodtheme-discogs-effnet-1.json")["classes"]
    y = c.mono(16000)
    t0 = time.time()
    X = _mel_port()(y)
    patches = lambda X, size, hop: np.stack([X[i * hop:i * hop + size] for i in range(1 + max(0, len(X) - size) // hop)])  # noqa: E731
    P = patches(X, 187, 93)
    Em = np.concatenate([mus.run(["embeddings"], {"melspectrogram": P[i:i + 32]})[0] for i in range(0, len(P), 32)])
    va = emo.run(None, {"embeddings": Em})[0]
    va2 = deam.run(None, {"model/Placeholder:0": Em})[0]
    P2 = patches(X, 128, 62)
    E2 = np.concatenate([eff.run(["embeddings"], {"melspectrogram": P2[i:i + 32]})[0] for i in range(0, len(P2), 32)])
    tags = mt.run(None, {"embeddings": E2})[0]
    dt = time.time() - t0
    np.savez_compressed(d / "mood.npz", emomusic_va=va.astype(np.float32), deam_va=va2.astype(np.float32), moodtheme_probs=tags.astype(np.float16),
                        musicnn_patch_hop_s=np.float32(93 * 256 / 16000), musicnn_patch_s=np.float32(187 * 256 / 16000),
                        effnet_patch_hop_s=np.float32(62 * 256 / 16000), effnet_patch_s=np.float32(128 * 256 / 16000))
    m = tags.mean(0)
    jdump(d / "mood.json", {"classes": classes, "secs": round(dt, 1), "emomusic_va_mean": va.mean(0).tolist(), "deam_va_mean": va2.mean(0).tolist(),
                            "top_moodtheme_mean": [[classes[i], round(float(m[i]), 3)] for i in np.argsort(-m)[:8]],
                            "valence_arousal_order": "as emitted by the head (emomusic/DEAM: [valence, arousal] in 1..9); see Essentia model json",
                            "format": "mood.npz: emomusic_va[N,2], deam_va[N,2] (one row per musicnn patch of 3 s hop 1.5 s), moodtheme_probs float16 [M,56] (effnet patch 2 s hop ~1 s)"})
    return {"secs": round(dt, 1), "emomusic_va": np.round(va.mean(0), 2).tolist(), "deam_va": np.round(va2.mean(0), 2).tolist()}


# ------------------------------------------------------------------ 13 madmom DBN
@step("madmom_dbn", ("decode",))
def s_madmom(c: Ctx):
    import soundfile as sf
    from madmom_infer.features.downbeats import DBNDownBeatTrackingProcessor, RNNDownBeatProcessor
    d = c.d("madmom_dbn")
    tmp = d / "_tmp_mono44k.wav"
    sf.write(str(tmp), c.mono(44100), 44100, subtype="FLOAT")
    t0 = time.time()
    act = np.asarray(RNNDownBeatProcessor()(str(tmp)), np.float32)
    t_rnn = time.time() - t0
    np.save(d / "rnn_activations.npy", act)
    res = {"model": "madmom-infer 0.2.0 RNNDownBeatProcessor (8 BLSTM) + DBNDownBeatTrackingProcessor", "fps": 100, "rnn_secs": round(t_rnn, 1)}
    for tag, bpb in (("bpb34", [3, 4]), ("bpb4", [4])):
        t0 = time.time()
        b = np.asarray(DBNDownBeatTrackingProcessor(beats_per_bar=bpb, fps=100)(act))
        res[tag] = {"secs": round(time.time() - t0, 1), "beats": [[round(float(t), 4), int(p)] for t, p in b], "n": int(len(b)),
                    "downbeats": [round(float(t), 4) for t, p in b if int(p) == 1]}
    tmp.unlink(missing_ok=True)
    res["format"] = "rnn_activations.npy float32 [T,2] (beat, downbeat) at 100 fps; beats [[t_s, beat_in_bar]]"
    jdump(d / "madmom_dbn.json", res)
    return {"rnn_s": res["rnn_secs"], "n_beats": res["bpb34"]["n"], "n_downbeats": len(res["bpb34"]["downbeats"])}


# ------------------------------------------------------------------ 14 piano
@step("piano", ("demucs", "instruments"))
def s_piano(c: Ctx):
    import torch
    import soundfile as sf
    torch.set_num_threads(THREADS)
    d = c.d("piano")
    ped, sr = c.stem("htdemucs_6s", "piano")
    mix, msr = c.mix()
    # presence: stem_activity rule (> -45 dBFS and within 18 dB of mix) over 100 ms frames, plus CED 'Piano' prob on mix and on the piano stem
    def frame_db(x, sr_):
        m = x.mean(1)
        n = int(0.1 * sr_)
        k = len(m) // n
        return 10 * np.log10(np.mean(m[:k * n].reshape(k, n) ** 2, 1) + 1e-12)
    ps, ms = frame_db(ped, sr), frame_db(mix, msr)
    k = min(len(ps), len(ms))
    act = (ps[:k] > -45) & (ps[:k] > ms[:k] - 18)
    cfg = jload(MODELS / "ced-base" / "config.json")
    labels = [cfg["id2label"][str(i)] for i in range(len(cfg["id2label"]))]
    pi = labels.index("Piano")
    pm = float(np.load(c.root / "instruments" / "ced_mix.npz")["probs"][:, pi].astype(np.float32).mean())
    pp95 = float(np.percentile(np.load(c.root / "instruments" / "ced_mix.npz")["probs"][:, pi].astype(np.float32), 95))
    ps_mean = float(np.load(c.root / "instruments" / "ced_htdemucs_6s_piano.npz")["probs"][:, pi].astype(np.float32).mean())
    pres = {"stem_active_frac": round(float(act.mean()), 3), "stem_rms_dbfs": round(float(ps.mean()), 1), "ced_mix_piano_mean": round(pm, 3), "ced_mix_piano_p95": round(pp95, 3),
            "ced_pianostem_piano_mean": round(ps_mean, 3), "rule": "run when stem_active_frac >= 0.10 or ced_mix_piano_mean >= 0.05 or ced_mix_piano_p95 >= 0.25"}
    run = act.mean() >= 0.10 or pm >= 0.05 or pp95 >= 0.25
    pres["run"] = bool(run)
    jdump(d / "presence.json", pres)
    for stale in ("piano.json", "piano.mid"):
        (d / stale).unlink(missing_ok=True)
    if not run:
        return {"skipped": "no piano", **pres}
    from piano_transcription_inference import PianoTranscription
    import soxr
    y = soxr.resample(ped.mean(1), sr, 16000).astype(np.float32)
    pt = PianoTranscription(checkpoint_path=str(MODELS / "piano_transcription" / "note_F1=0.9677_pedal_F1=0.9186.pth"), device=torch.device("cpu"))
    t0 = time.time()
    res = pt.transcribe(y, str(d / "piano.mid"))
    dt = time.time() - t0
    ev = res["est_note_events"]
    jdump(d / "piano.json", {"model": "ByteDance piano_transcription_inference 0.0.6 note_F1=0.9677", "secs": round(dt, 1), "presence": pres,
                             "notes_fields": ["onset_s", "offset_s", "midi", "velocity"], "notes": [[round(float(e["onset_time"]), 4), round(float(e["offset_time"]), 4), int(e["midi_note"]), int(e["velocity"])] for e in ev],
                             "n_pedal_events": len(res.get("est_pedal_events", []))})
    return {"notes": len(ev), "secs": round(dt, 1), **pres}


ORDER = ["decode", "demucs", "beat_this", "allin1", "librosa", "spectral_proto", "chords", "key", "notes", "pitch", "instruments", "mood", "madmom_dbn", "piano"]


def run_step(c: Ctx, name, force):
    d = c.d(name)
    done, err = d / "_done.json", d / "_error.json"
    if done.exists() and not force:
        log(f"{c.slug}/{name}: already done, skip")
        return
    fn, deps = STEPS[name]
    for dep in deps:
        if not (c.root / dep / "_done.json").exists():
            log(f"{c.slug}/{name}: dependency {dep} missing, skipped")
            return
    err.unlink(missing_ok=True)
    i0, t0_ = _systimes()
    owners0 = lock_owners()
    pt0, wt0 = time.process_time(), time.time()
    log(f"{c.slug}/{name}: start (locks: {owners0})")
    try:
        out = fn(c)
        ok = True
    except Exception as e:  # noqa: BLE001
        ok, out = False, None
        err.write_text(json.dumps({"error": f"{type(e).__name__}: {str(e)[:800]}", "trace": traceback.format_exc()[-3000:]}), encoding="utf-8")
        log(f"{c.slug}/{name}: FAILED {type(e).__name__}: {str(e)[:200]}")
    wall = time.time() - wt0
    i1, t1_ = _systimes()
    sysbusy = 1 - (i1 - i0) / max(1, (t1_ - t0_))
    if ok:
        try:
            jdump(done, {"step": name, "slug": c.slug, "wall_s": round(wall, 2), "proc_cpu_s": round(time.process_time() - pt0, 1),
                         "system_cpu_busy_frac_during": round(sysbusy, 3), "concurrent_locks_start": owners0, "concurrent_locks_end": lock_owners(),
                         "threads": THREADS, "when": time.strftime("%Y-%m-%dT%H:%M:%S"), "result": out})
        except TypeError:
            jdump(done, {"step": name, "slug": c.slug, "wall_s": round(wall, 2), "result": str(out)[:2000]})
        log(f"{c.slug}/{name}: done {wall:.1f}s sys_cpu={sysbusy:.2f} -> {str(out)[:300]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug", choices=list(SONGS))
    ap.add_argument("--only", default="")
    ap.add_argument("--force", default="")
    a = ap.parse_args()
    import torch
    torch.set_num_threads(THREADS)
    c = Ctx(a.slug)
    only = [s for s in a.only.split(",") if s] or ORDER
    force = set(s for s in a.force.split(",") if s)
    log(f"== {a.slug} threads={THREADS} offline={os.environ.get('HF_HUB_OFFLINE')} locks={lock_owners()}")
    for name in ORDER:
        if name in only:
            run_step(c, name, name in force)
    log(f"== {a.slug} finished")


if __name__ == "__main__":
    main()
