"""Separate one song with audio-separator (no normalisation, float WAV) and write sep/index.json.

Run with envs/sep/.venv-rocm or .venv-cpu python:
  python -X utf8 separate_song.py --variant rocm --slug jeremy --src <flac> --out <tests/.cache/real/jeremy/sep>

Steps (each holds a heavy slot; rocm also the gpu lock):
  decode (ffmpeg -> float32 WAV 44.1k stereo) -> BS-RoFormer-SW (6 stems) -> Mel-RoFormer vocals
  -> karaoke (lead/backing, run on the Mel vocals) -> DrumSep (on the SW drums) -> post checks.
Resumable: a step whose outputs exist in <out>/_work is skipped (timings are kept in _work/timings.json).
"""
import argparse, json, os, subprocess, sys, time
from pathlib import Path

THREADS = "6"
for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[k] = THREADS
os.environ.setdefault("PYTHONUTF8", "1")

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mvh_locks import Slot

LOCALAPPDATA = Path(os.environ["LOCALAPPDATA"])
MODEL_DIR = LOCALAPPDATA / "mvh" / "models" / "separator"
FFMPEG = os.environ.get("MVH_FFMPEG") or r"C:\Users\OpenSrcerer\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe"
os.environ["PATH"] = str(Path(FFMPEG).parent) + os.pathsep + os.environ["PATH"]  # audio-separator shells out to bare `ffmpeg`
FRAG = Path(__file__).resolve().parents[1] / "models.fragment.json"

SW = "BS-Roformer-SW.ckpt"
MEL = "vocals_mel_band_roformer.ckpt"
KARAOKE = "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt"
DRUMSEP = "MDX23C-DrumSep-aufr33-jarredou.ckpt"
SW_STEMS = ["bass", "drums", "other", "vocals", "guitar", "piano"]
DRUM_STEMS = ["kick", "snare", "toms", "hh", "ride", "crash"]


def db(x, ref=1.0):
    return float(10 * np.log10(max(x, 1e-30) / max(ref, 1e-30)))


def rms_dbfs(a):
    return float(10 * np.log10(max(float(np.mean(np.square(a, dtype=np.float64))), 1e-30)))


def decode(src, dst, log):
    cmd = [FFMPEG, "-hide_banner", "-nostdin", "-y", "-v", "warning", "-i", str(src), "-map", "0:a:0", "-ac", "2", "-ar", "44100", "-c:a", "pcm_f32le", str(dst)]
    t = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise RuntimeError(r.stderr[-800:])
    warns = [l for l in r.stderr.splitlines() if l.strip()]
    log["decode"] = {"seconds": round(time.time() - t, 2), "ffmpeg_warning_lines": len(warns), "ffmpeg_warning_sample": warns[:3]}


def load_wav(p):
    a, sr = sf.read(str(p), dtype="float32", always_2d=True)
    return a, sr


def write_wav(p, a, sr=44100):
    p.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(p), a.astype(np.float32), sr, subtype="FLOAT")


def make_separator(variant, outdir, overlap):
    import torch
    torch.set_num_threads(int(THREADS))
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass
    from audio_separator.separator import Separator
    mdxc = {"segment_size": 256, "override_model_segment_size": False, "batch_size": None, "overlap": overlap, "pitch_shift": 0}
    sep = Separator(
        log_level=20, model_file_dir=str(MODEL_DIR), output_dir=str(outdir), output_format="WAV", use_soundfile=True,
        normalization_threshold=1.0, amplification_threshold=0.0, sample_rate=44100, mdxc_params=mdxc,
    )
    # TRAP: the constructor rejects normalization_threshold > 1, but the value is only consumed at load_model(),
    # so set the attribute afterwards. peak > 100 never happens => spec_utils.normalize() becomes a no-op;
    # amplification_threshold=0 => min_peak branch (0 < maxv < 0) never fires.
    sep.normalization_threshold = 100.0
    sep.amplification_threshold = 0.0
    return sep


def run_model(variant, owner, model, inp, outdir, names, overlap, timings, key):
    """Run one model under a heavy slot. names: audio-separator stem -> output basename."""
    if all((outdir / f"{n}.wav").exists() for n in names.values()) and key in timings:
        print(f"[skip] {key}", flush=True)
        return
    outdir.mkdir(parents=True, exist_ok=True)
    with Slot(f"env-sep:{owner}:{key}", gpu=(variant == "rocm")) as slot:
        print(f"[run] {key} slot={slot.name} waited={slot.waited:.0f}s others={slot.others}", flush=True)
        import torch
        sep = make_separator(variant, outdir, overlap)
        t0 = time.time()
        sep.load_model(model_filename=model)
        t1 = time.time()
        outs = sep.separate(str(inp), custom_output_names=names)
        if variant == "rocm":
            torch.cuda.synchronize()
        t2 = time.time()
        dev = str(getattr(sep, "torch_device", "?"))
        del sep
        if variant == "rocm":
            torch.cuda.empty_cache()
    missing = [n for n in names.values() if not (outdir / f"{n}.wav").exists()]
    if missing:
        raise RuntimeError(f"{key}: missing outputs {missing}; got {outs}")
    timings[key] = {"model": model, "load_s": round(t1 - t0, 1), "separate_s": round(t2 - t1, 1), "slot": slot.name,
                    "lock_wait_s": round(slot.waited, 1), "other_lock_owners": slot.others, "device": dev, "overlap": overlap or "yaml-default"}
    print(f"[done] {key} load={t1-t0:.1f}s sep={t2-t1:.1f}s dev={dev}", flush=True)


def fit_gains(mix, parts):
    """Least-squares weights w with mix ~ sum(w_i * part_i), per channel pooled. Returns weights (linear)."""
    n = min(len(mix), *(len(p) for p in parts))
    A = np.stack([p[:n].reshape(-1).astype(np.float64) for p in parts], axis=1)
    y = mix[:n].reshape(-1).astype(np.float64)
    w, *_ = np.linalg.lstsq(A, y, rcond=None)
    return w


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=["rocm", "cpu"], required=True)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--overlap", type=int, default=0, help="0 = model yaml default (SW: 2)")
    ap.add_argument("--max-seconds", type=float, default=0, help="trim input to N s (smoke tests)")
    ap.add_argument("--owner", default="env-sep")
    a = ap.parse_args()

    out = Path(a.out)
    work = out / "_work"
    work.mkdir(parents=True, exist_ok=True)
    overlap = a.overlap or None
    tpath = work / "timings.json"
    timings = json.loads(tpath.read_text(encoding="utf-8")) if tpath.exists() else {}
    log = {"decode": None}
    T0 = time.time()

    mixp = out / "mix_f32.wav"
    if not mixp.exists():
        decode(a.src, mixp, log)
        if a.max_seconds:
            m, sr0 = load_wav(mixp)
            write_wav(mixp, m[: int(a.max_seconds * sr0)], sr0)
        (work / "decode.json").write_text(json.dumps(log["decode"]), encoding="utf-8")
    elif (work / "decode.json").exists():
        log["decode"] = json.loads((work / "decode.json").read_text(encoding="utf-8"))
    mix, sr = load_wav(mixp)
    dur = len(mix) / sr
    print(f"mix {mix.shape} sr={sr} dur={dur:.2f}s peak={np.abs(mix).max():.4f}", flush=True)

    run_model(a.variant, a.slug, SW, mixp, work / "sw", {s: f"sw_{s}" for s in SW_STEMS}, overlap, timings, "sw_6stem")
    tpath.write_text(json.dumps(timings, indent=1), encoding="utf-8")
    # Mel-RoFormer vocals model: stems are [vocals, other]; only keep vocals.
    mel_dir = work / "mel"
    if not (mel_dir / "mel_vocals.wav").exists():
        run_model_single(a.variant, a.slug, MEL, mixp, mel_dir, "vocals", "mel_vocals", overlap, timings, "mel_vocals")
        tpath.write_text(json.dumps(timings, indent=1), encoding="utf-8")
    kar_dir = work / "karaoke"
    if not (kar_dir / "lead.wav").exists():
        run_model(a.variant, a.slug, KARAOKE, mel_dir / "mel_vocals.wav", kar_dir, {"vocals": "lead", "instrumental": "backing"}, overlap, timings, "karaoke")
        tpath.write_text(json.dumps(timings, indent=1), encoding="utf-8")
    run_model(a.variant, a.slug, DRUMSEP, work / "sw" / "sw_drums.wav", work / "drumsep", {s: f"ds_{s}" for s in DRUM_STEMS}, overlap, timings, "drumsep")
    tpath.write_text(json.dumps(timings, indent=1), encoding="utf-8")

    # ---- post: align, write final stems, checks ----
    N = len(mix)
    lens = {}

    def get(p, name):
        x, _ = load_wav(p)
        lens[name] = len(x)
        if len(x) < N:
            x = np.pad(x, ((0, N - len(x)), (0, 0)))
        return x[:N]

    sw = {s: get(work / "sw" / f"sw_{s}.wav", f"sw_{s}") for s in SW_STEMS}
    vocals = get(mel_dir / "mel_vocals.wav", "vocals")
    lead = get(kar_dir / "lead.wav", "lead_vocals")
    backing = get(kar_dir / "backing.wav", "backing_vocals")
    drums_sub = {s: get(work / "drumsep" / f"ds_{s}.wav", f"drum_{s}") for s in DRUM_STEMS}
    instrumental = mix - vocals

    final = {"bass": sw["bass"], "drums": sw["drums"], "other": sw["other"], "guitar": sw["guitar"], "piano": sw["piano"],
             "vocals_sw": sw["vocals"], "vocals": vocals, "lead_vocals": lead, "backing_vocals": backing, "instrumental": instrumental}
    for s in DRUM_STEMS:
        final[f"drums/{'hihat' if s == 'hh' else s}"] = drums_sub[s]
    for name, x in final.items():
        write_wav(out / f"{name}.wav", x)

    mix_e = float(np.sum(np.square(mix, dtype=np.float64)))
    sum6 = sum(sw[s].astype(np.float64) for s in SW_STEMS)
    res6 = mix.astype(np.float64) - sum6
    w6 = fit_gains(mix, [sw[s] for s in SW_STEMS])
    sig_floor = rms_dbfs(mix) - 20.0  # stems quieter than this (vs mix) make the LS gain ill-conditioned
    gains = {}
    for s, w in zip(SW_STEMS, w6):
        r = rms_dbfs(sw[s])
        gains[s] = {"ls_gain_linear": round(float(w), 5), "ls_gain_db": round(20 * float(np.log10(abs(w) + 1e-12)), 3),
                    "rms_dbfs": round(r, 2), "peak": round(float(np.abs(sw[s]).max()), 4), "significant": bool(r > sig_floor)}
    d_sum = sum(drums_sub[s].astype(np.float64) for s in DRUM_STEMS)
    wd = fit_gains(sw["drums"], [drums_sub[s] for s in DRUM_STEMS])
    lb = lead.astype(np.float64) + backing
    # SW vocals vs Mel vocals similarity (dB of difference)
    chk = {
        "stems_sum_vs_mix": {
            "definition": "10*log10(|mix - sum(6 SW stems)|^2 / |mix|^2); PLAN gate <= -30 dB",
            "residual_db": round(db(float(np.sum(res6 ** 2)), mix_e), 2),
            "pass_minus30": bool(db(float(np.sum(res6 ** 2)), mix_e) <= -30.0),
            "per_stem_ls_gain": gains,
            "gain_gate": "least-squares weight w_i in mix ~ sum(w_i*stem_i); each stem within 20 dB of the mix RMS must have |20log10 w_i| <= 0.1 dB (silent stems are ill-conditioned and excluded)",
            "gain_pass": bool(all(abs(g["ls_gain_db"]) <= 0.1 for g in gains.values() if g["significant"])),
        },
        "instrumental_def": "mix - mel_vocals (float, un-normalised)",
        "instrumental_plus_vocals_vs_mix_db": round(db(float(np.sum((instrumental.astype(np.float64) + vocals - mix) ** 2)), mix_e), 2),
        "lead_plus_backing_vs_vocals_db": round(db(float(np.sum((lb - vocals) ** 2)), float(np.sum(vocals.astype(np.float64) ** 2))), 2),
        "drum_substems_vs_drums_db": round(db(float(np.sum((sw["drums"] - d_sum) ** 2)), float(np.sum(sw["drums"].astype(np.float64) ** 2))), 2),
        "drum_substem_ls_gain_db": {s: round(20 * float(np.log10(abs(w) + 1e-12)), 2) for s, w in zip(DRUM_STEMS, wd)},
        "mel_vs_sw_vocals_diff_db": round(db(float(np.sum((vocals.astype(np.float64) - sw["vocals"]) ** 2)), float(np.sum(vocals.astype(np.float64) ** 2))), 2),
        "stem_gain_vs_mix_rms_db": {k: round(rms_dbfs(v) - rms_dbfs(mix), 2) for k, v in final.items()},
        "peaks": {k: round(float(np.abs(v).max()), 4) for k, v in final.items()},
    }

    import importlib.metadata as md
    pins = {}
    if FRAG.exists():
        for e in json.loads(FRAG.read_text(encoding="utf-8"))["models"]:
            if e["id"].startswith("sep."):
                pins[e["id"]] = {f["path"]: f["sha256"][:16] for f in e["files"] if f["path"].endswith(".ckpt")}
    try:
        import torch
        tv, hip = torch.__version__, getattr(torch.version, "hip", None)
    except Exception:
        tv, hip = "?", None
    idx = {
        "schema": "mvh.sep.index/0",
        "slug": a.slug, "source": Path(a.src).name if False else None,
        "variant": a.variant,
        "device": timings.get("sw_6stem", {}).get("device"),
        "torch": tv, "hip": hip, "audio_separator": md.version("audio-separator"),
        "settings": {"normalization_threshold": 100.0, "amplification_threshold": 0.0, "output": "WAV FLOAT (use_soundfile=True, float32 input)",
                     "sample_rate": 44100, "overlap": overlap or "model yaml default", "threads_cap": int(THREADS)},
        "input": {"duration_s": round(dur, 3), "samples": N, "sample_rate": sr, "mix_peak": round(float(np.abs(mix).max()), 4),
                  "mix_rms_dbfs": round(rms_dbfs(mix), 2), **({"decode": log["decode"]} if log["decode"] else {})},
        "output_lengths_before_align": lens,
        "files": sorted(f"{k}.wav" for k in final),
        "models": {"sw": SW, "vocals": MEL, "karaoke": KARAOKE, "drumsep": DRUMSEP, "sha256_prefix": pins},
        "timings": timings,
        "timings_total_separate_s": round(sum(v["separate_s"] for v in timings.values()), 1),
        "checks": chk,
        "wall_s_this_invocation": round(time.time() - T0, 1),
    }
    idx["source"] = Path(a.src).name
    (out / "index.json").write_text(json.dumps(idx, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("INDEX written; stems-sum residual", chk["stems_sum_vs_mix"]["residual_db"], "dB; gain_pass", chk["stems_sum_vs_mix"]["gain_pass"], flush=True)


def run_model_single(variant, owner, model, inp, outdir, stem, basename, overlap, timings, key):
    """Models whose output has one wanted stem: audio-separator writes both; we rename the wanted one, delete the other."""
    outdir.mkdir(parents=True, exist_ok=True)
    with Slot(f"env-sep:{owner}:{key}", gpu=(variant == "rocm")) as slot:
        print(f"[run] {key} slot={slot.name} waited={slot.waited:.0f}s others={slot.others}", flush=True)
        import torch
        sep = make_separator(variant, outdir, overlap)
        t0 = time.time()
        sep.load_model(model_filename=model)
        t1 = time.time()
        sep.separate(str(inp), custom_output_names={stem: basename, "other": basename + "_other", "instrumental": basename + "_other"})
        if variant == "rocm":
            torch.cuda.synchronize()
        t2 = time.time()
        dev = str(getattr(sep, "torch_device", "?"))
        del sep
        if variant == "rocm":
            torch.cuda.empty_cache()
    if not (outdir / f"{basename}.wav").exists():
        raise RuntimeError(f"{key}: no {basename}.wav in {list(outdir.iterdir())}")
    timings[key] = {"model": model, "load_s": round(t1 - t0, 1), "separate_s": round(t2 - t1, 1), "slot": slot.name,
                    "lock_wait_s": round(slot.waited, 1), "other_lock_owners": slot.others, "device": dev, "overlap": overlap or "yaml-default"}
    print(f"[done] {key} load={t1-t0:.1f}s sep={t2-t1:.1f}s dev={dev}", flush=True)


if __name__ == "__main__":
    main()
