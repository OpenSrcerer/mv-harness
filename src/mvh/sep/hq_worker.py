"""The separate_hq worker job (runs in the sep env: ``envs/sep/.venv-<variant>``; docs/spike/sep.md §4-§6).

Lifted from ``envs/sep/tools/separate_song.py``. Called by ``mvh.worker`` as
``mvh.stages.separate_hq.worker.run_job(job, out_dir)``. Inference only: it reads the float32 44.1 kHz stereo
mix WAV listed in ``job["inputs"]["mix"]`` and writes float32 WAVs into ``out_dir``:

  sw_{bass,drums,other,vocals,guitar,piano}.wav   BS-RoFormer-SW 6-stem on the mix
  mel_vocals.wav                                   Mel-RoFormer vocals on the mix
  kar_lead.wav, kar_backing.wav                    karaoke model on the Mel vocals (vocals -> lead, instrumental -> backing)
  ds_{kick,snare,toms,hihat,ride,crash}.wav        MDX23C DrumSep on the SW drums

Each model is a separate load / separate / free cycle under its own heavy slot (plus ``gpu.lock`` on rocm), so
other agents wait at most one model (``job["params"]["heavy_locks"]`` false disables the slots). audio-separator is
configured without any re-levelling: ``normalization_threshold = 100.0`` set as an ATTRIBUTE after construction
(the constructor rejects values above 1), ``amplification_threshold = 0.0``, float WAV output
(``use_soundfile=True`` + float32 input), explicit model files from ``job["models"]``.

DrumSep runs on the CPU by default (``params["drumsep_device"]``, CONTRACT D47): MDX23C is a convolution network,
and on ROCm MIOpen picks its convolution kernels from the free GPU workspace, so the sub-stems change in the last
bits (about 1e-8) whenever something else holds GPU memory, which breaks the NF1 determinism diff. The CPU path is
bit-reproducible (measured: two runs identical, 1.45 x real time at 6 threads). The RoFormer models stay on the GPU:
their run-to-run last-bit changes (atomic ``scatter_add_`` in the Mel mask sum, an auto-tuned SDPA kernel) are removed by
``mvh.sep.determinism`` (R4-2). ``"auto"`` keeps the old GPU behaviour for DrumSep.

Imports: stdlib + numpy at module level; torch and audio_separator inside ``run_job``.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any

__all__ = ["run_job", "STEPS", "SW_STEMS", "DRUM_STEMS"]

SW_STEMS = ("bass", "drums", "other", "vocals", "guitar", "piano")
DRUM_STEMS = {"kick": "kick", "snare": "snare", "toms": "toms", "hh": "hihat", "ride": "ride", "crash": "crash"}

#: (step key, models.lock id, input, {audio-separator stem name -> output basename})
STEPS = (
    ("sw_6stem", "sep.bs-roformer-sw-6stem", "mix", {s: f"sw_{s}" for s in SW_STEMS}),
    ("mel_vocals", "sep.mel-roformer-vocals-kimberley", "mix",
     {"vocals": "mel_vocals", "other": "mel_other", "instrumental": "mel_other"}),
    ("karaoke", "sep.mel-roformer-karaoke-aufr33-viperx", "mel_vocals", {"vocals": "kar_lead", "instrumental": "kar_backing"}),
    ("drumsep", "sep.mdx23c-drumsep", "sw_drums", {k: f"ds_{v}" for k, v in DRUM_STEMS.items()}),
)
#: the files each step must leave in out_dir
KEEP = {
    "sw_6stem": [f"sw_{s}" for s in SW_STEMS],
    "mel_vocals": ["mel_vocals"],
    "karaoke": ["kar_lead", "kar_backing"],
    "drumsep": [f"ds_{v}" for v in DRUM_STEMS.values()],
}


def _ckpt(files: dict[str, str]) -> Path:
    for rel, p in sorted(files.items()):
        if rel.endswith(".ckpt"):
            return Path(p)
    raise RuntimeError(f"no .ckpt among the model files {sorted(files)}")


def _make_separator(model_dir: Path, out_dir: Path, overlap: int, segment_size: int, threads: int,
                    norm_threshold: float = 100.0, amp_threshold: float = 0.0):
    import torch

    torch.set_num_threads(int(threads))
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass
    from audio_separator.separator import Separator

    mdxc = {"segment_size": int(segment_size), "override_model_segment_size": False, "batch_size": None,
            "overlap": int(overlap), "pitch_shift": 0}
    sep = Separator(
        log_level=30, model_file_dir=str(model_dir), output_dir=str(out_dir), output_format="WAV", use_soundfile=True,
        normalization_threshold=1.0, amplification_threshold=0.0, sample_rate=44100, mdxc_params=mdxc,
    )
    # TRAP (docs/spike/sep.md §4): the constructor rejects normalization_threshold > 1 but the value is only read
    # at load_model(): set it afterwards so spec_utils.normalize() never rescales (peak > 100 never happens).
    sep.normalization_threshold = float(norm_threshold)
    sep.amplification_threshold = float(amp_threshold)
    return sep


def run_job(job: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    import importlib.metadata as md

    if str(job.get("variant", "cpu")) == "rocm" and "ROCBLAS_USE_HIPBLASLT" not in os.environ:
        os.environ["ROCBLAS_USE_HIPBLASLT"] = "0"   # before torch loads rocBLAS: bit-reproducible GEMMs (mvh.sep.determinism)
    import torch

    from mvh.io.wav import read_wav

    params = dict(job.get("params", {}))
    variant = str(job.get("variant", "cpu"))
    threads = max(1, min(int(job.get("threads") or 6), 6))
    overlap = int(params.get("overlap", 4))
    segment_size = int(params.get("segment_size", 256))
    use_locks = bool(params.get("heavy_locks", True))
    norm_t = float(params.get("normalization_threshold", 100.0))
    amp_t = float(params.get("amplification_threshold", 0.0))
    drumsep_device = str(params.get("drumsep_device", "cpu"))
    if drumsep_device not in ("cpu", "auto"):
        raise RuntimeError(f"drumsep_device must be 'cpu' or 'auto', got {drumsep_device!r}")
    out_dir = Path(out_dir)
    work = Path(job.get("scratch") or out_dir.parent) / "_work"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    mix_path = Path(job["inputs"]["mix"])
    x, sr = read_wav(mix_path)
    if sr != 44100 or x.shape[0] != 2:
        raise RuntimeError(f"separate_hq worker expects 44.1 kHz stereo float WAV, got {x.shape[0]} ch at {sr} Hz")
    if variant == "rocm" and not torch.cuda.is_available():
        raise RuntimeError("variant rocm but torch.cuda.is_available() is False")
    models = job.get("models", {})
    skip = set(params.get("skip_steps") or [])     # e.g. "karaoke" for a mono song (the pan cue it relies on is absent)
    inputs = {"mix": mix_path}
    devices: dict[str, str] = {}
    lens: dict[str, int] = {}
    timings: dict[str, dict[str, float]] = {}
    for key, mid, inp, names in STEPS:
        if key in skip:
            continue
        if mid not in models:
            raise RuntimeError(f"model {mid} missing from job.json")
        ck = _ckpt(models[mid])
        step_dir = work / key
        step_dir.mkdir(parents=True, exist_ok=True)
        slot = None
        on_cpu = variant != "rocm" or (key == "drumsep" and drumsep_device == "cpu")
        if use_locks:
            from mvh.runner import locks

            slot = locks.acquire(f"mvh:separate_hq:{variant}:{key}", gpu=not on_cpu, poll=2.0)
        try:
            t0 = time.time()
            if not on_cpu:
                from mvh.sep.determinism import prefer_rocblas

                prefer_rocblas()
            sep = _make_separator(ck.parent, step_dir, overlap, segment_size, threads, norm_t, amp_t)
            if on_cpu:
                # read by load_model() (common_params): the architecture puts the model and the data on this device
                sep.torch_device = torch.device("cpu")
            sep.load_model(model_filename=ck.name)
            t1 = time.time()
            if on_cpu:
                sep.separate(str(inputs[inp]), custom_output_names=names)
            else:
                # atomic float scatter_add_ in the Mel-RoFormer mask sum and an auto-tuned SDPA kernel: run-to-run
                # last-bit changes on a GPU (NF1)
                from mvh.sep.determinism import deterministic_roformer

                with deterministic_roformer():
                    sep.separate(str(inputs[inp]), custom_output_names=names)
            if not on_cpu:
                torch.cuda.synchronize()
            t2 = time.time()
            devices[key] = str(getattr(sep, "torch_device", "?"))
            del sep
            if not on_cpu:
                torch.cuda.empty_cache()
        finally:
            if slot is not None:
                slot.release()
        timings[key] = {"load_s": round(t1 - t0, 2), "separate_s": round(t2 - t1, 2)}
        for base in KEEP[key]:
            src = step_dir / f"{base}.wav"
            if not src.is_file():
                raise RuntimeError(f"{key}: audio-separator wrote no {base}.wav (got {sorted(p.name for p in step_dir.iterdir())})")
            dst = out_dir / f"{base}.wav"
            os.replace(src, dst)
            a, _ = read_wav(dst)
            lens[base] = int(a.shape[1])
            inputs[base] = dst
        print(f"[separate_hq] {key}: load {t1 - t0:.1f}s separate {t2 - t1:.1f}s on {devices[key]}", flush=True)
    shutil.rmtree(work, ignore_errors=True)
    try:
        asv = md.version("audio-separator")
    except Exception:  # noqa: BLE001
        asv = "unknown"
    return {
        "status": "ok",
        "summary": {
            "variant": variant,
            "torch": torch.__version__,
            "hip": getattr(torch.version, "hip", None),
            "audio_separator": asv,
            "devices": devices,
            "output_lengths": lens,
            "input_samples": int(x.shape[1]),
            "timings": timings,
            "settings": {"normalization_threshold": norm_t, "amplification_threshold": amp_t, "overlap": overlap,
                         "segment_size": segment_size, "sample_rate": 44100, "output": "WAV float32 (use_soundfile)",
                         "threads": threads, "drumsep_device": drumsep_device,
                         "deterministic_roformer": True},
        },
        "provenance": {"tools": [{"name": "audio-separator", "version": asv}, {"name": "torch", "version": torch.__version__}]},
    }


