"""W3 seam S01 / D47: on the rocm variant the DrumSep step runs on the CPU (bit-reproducible) and takes no gpu.lock;
the RoFormer steps stay on the GPU. A fake audio-separator records the device each model was loaded on."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np


class _Fake:
    instances: list = []

    def __init__(self, **kw):
        self.kw = kw
        self.torch_device = "cuda"
        _Fake.instances.append(self)

    def load_model(self, model_filename):
        self.loaded = model_filename
        self.device_at_load = str(self.torch_device)

    def separate(self, path, custom_output_names=None):
        from mvh.io.wav import read_wav, write_wav

        x, sr = read_wav(path)
        for base in dict.fromkeys(custom_output_names.values()):
            write_wav(Path(self.kw["output_dir"]) / f"{base}.wav", x * 0.5, sr)


def _run(monkeypatch, tmp_path, params):
    import torch

    from mvh.io.wav import write_wav
    from mvh.runner import locks
    from mvh.sep import hq_worker

    pkg, sub = types.ModuleType("audio_separator"), types.ModuleType("audio_separator.separator")
    sub.Separator = _Fake
    pkg.separator = sub
    monkeypatch.setitem(sys.modules, "audio_separator", pkg)
    monkeypatch.setitem(sys.modules, "audio_separator.separator", sub)
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "synchronize", lambda: None)
    monkeypatch.setattr(torch.cuda, "empty_cache", lambda: None)
    gpu_asks = []

    class _Slot:
        def release(self):
            pass

    monkeypatch.setattr(locks, "acquire", lambda owner, gpu=False, **k: gpu_asks.append((owner.rsplit(":", 1)[-1], gpu)) or _Slot())
    _Fake.instances.clear()
    write_wav(tmp_path / "mix.wav", (np.random.default_rng(0).standard_normal((2, 4410)) * 0.1).astype(np.float32), 44100)
    models = {}
    for _k, mid, _i, _n in hq_worker.STEPS:
        ck = tmp_path / f"{mid}.ckpt"
        ck.write_bytes(b"x")
        models[mid] = {f"separator/{mid}.ckpt": str(ck)}
    out = tmp_path / "out"
    out.mkdir()
    job = {"inputs": {"mix": str(tmp_path / "mix.wav")}, "models": models, "variant": "rocm", "threads": 2,
           "params": {"heavy_locks": True, **params}, "scratch": str(tmp_path / "scr")}
    res = hq_worker.run_job(job, out)
    dev = {i.loaded.split(".ckpt")[0]: i.device_at_load for i in _Fake.instances}
    return res, dev, dict(gpu_asks)


def test_drumsep_runs_on_cpu_by_default(monkeypatch, tmp_path):
    res, dev, gpu = _run(monkeypatch, tmp_path, {})
    assert dev["sep.mdx23c-drumsep"] == "cpu"
    assert dev["sep.bs-roformer-sw-6stem"] == "cuda"
    assert gpu["drumsep"] is False and gpu["sw_6stem"] is True
    assert res["summary"]["settings"]["drumsep_device"] == "cpu"


def test_drumsep_auto_keeps_the_gpu(monkeypatch, tmp_path):
    _res, dev, gpu = _run(monkeypatch, tmp_path, {"drumsep_device": "auto"})
    assert dev["sep.mdx23c-drumsep"] == "cuda" and gpu["drumsep"] is True


def test_stage_default_is_cpu():
    from mvh.stages.separate_hq import STAGE

    assert STAGE.params["drumsep_device"] == "cpu"
