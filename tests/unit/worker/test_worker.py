"""The sep worker protocol: job.json -> mvh.worker -> result.json, in-process and in the real sep-cpu venv."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from mvh import worker
from mvh.contract import schemas
from mvh.io.wav import read_wav, write_wav
from mvh.runner import sepworker
from mvh.runner.spec import Audio, StageError

SRC = Path(__file__).resolve().parents[3] / "src"


def _job(tmp_path, **params):
    x = np.linspace(-0.5, 0.5, 4410, dtype=np.float32)[None].repeat(2, 0)
    write_wav(tmp_path / "in.wav", x, 44100)
    out = tmp_path / "out"
    job = {
        "schema": "mvh/worker_job",
        "stage": "_echo",
        "stage_version": "1.0.0",
        "variant": "cpu",
        "device": "cpu",
        "threads": 2,
        "params": {"gain": 2.0, **params},
        "inputs": {"mix": str(tmp_path / "in.wav")},
        "models": {},
        "out_dir": str(out),
        "scratch": str(tmp_path),
    }
    (tmp_path / "job.json").write_text(json.dumps(job), encoding="utf-8")
    return job, x


def test_worker_in_process(tmp_path):
    job, x = _job(tmp_path)
    assert worker.main(["_echo", str(tmp_path / "job.json")]) == 0
    res = json.loads((tmp_path / "out/result.json").read_text(encoding="utf-8"))
    assert schemas.validate(res, "mvh/envelope/stage_result") == []
    assert res["status"] == "ok" and [o["path"] for o in res["outputs"]] == ["mix.wav"]
    y, sr = read_wav(tmp_path / "out/mix.wav")
    assert sr == 44100 and np.allclose(y, 2 * x)


def test_worker_failure_writes_result(tmp_path):
    _job(tmp_path, fail=True)
    assert worker.main(["_echo", str(tmp_path / "job.json")]) == 2
    res = json.loads((tmp_path / "out/result.json").read_text(encoding="utf-8"))
    assert res["status"] == "failed" and "asked to fail" in res["warnings"][0]
    assert worker.main(["only-one-arg"]) == 3


def test_worker_core_imports_stay_light():
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "import mvh.worker, mvh.io.wav, mvh.runner.threads, mvh.contract; "
        "heavy = sorted({m.split('.')[0] for m in sys.modules} & {'jsonschema', 'httpx', 'torch', 'scipy', "
        "'onnxruntime', 'librosa', 'referencing'}); print(heavy)"
    )
    r = subprocess.run([sys.executable, "-c", code, str(SRC)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and r.stdout.strip() == "[]", r.stdout + r.stderr


def _need_sep(variant: str = "cpu") -> Path:
    py = sepworker.sep_python(variant)
    if py is None:
        pytest.skip(f"sep-{variant} venv not built")
    return py


def test_run_worker_in_sep_cpu_venv(tmp_path):
    _need_sep("cpu")
    x = (0.1 * np.ones((2, 2205))).astype(np.float32)
    res = sepworker.run_worker(
        "_echo",
        stage_version="1.0.0",
        params={"gain": 3.0},
        inputs={"mix": Audio(x, 22050)},
        scratch=tmp_path / "scr atch ü",
        threads=2,
        variants=("cpu",),
        hold_slot=False,
    )
    assert res.variant == "cpu" and res.fallbacks == [] and set(res.outputs) == {"mix.wav"}
    a = res.read("mix.wav")
    assert a.sr == 22050 and np.allclose(a.samples, 0.3)
    s = res.result["summary"]
    assert s["omp"] == "2" and s["ffmpeg_first_on_path"] and s["python"].startswith("3.12")


def test_run_worker_falls_back_to_cpu(tmp_path, monkeypatch):
    real = sepworker.sep_python
    _need_sep("cpu")
    monkeypatch.setattr(sepworker, "sep_python", lambda v, root=None: None if v == "rocm" else real(v, root))
    res = sepworker.run_worker(
        "_echo",
        stage_version="1.0.0",
        params={},
        inputs={"mix": (np.zeros((1, 100)), 8000)},
        scratch=tmp_path,
        threads=1,
        hold_slot=False,
    )
    assert res.variant == "cpu" and res.fallbacks == ["sep:cpu"] and res.attempts[0]["variant"] == "rocm"


def test_run_worker_reports_failure(tmp_path):
    _need_sep("cpu")
    with pytest.raises(StageError, match="every variant"):
        sepworker.run_worker(
            "_echo",
            stage_version="1.0.0",
            params={"fail": True},
            inputs={"mix": (np.zeros((1, 100)), 8000)},
            scratch=tmp_path,
            threads=1,
            variants=("cpu",),
            hold_slot=False,
        )


def test_variant_order(monkeypatch):
    monkeypatch.delenv("MVH_SEP_VARIANTS", raising=False)
    monkeypatch.setenv("MVH_HOME", str(Path(__file__).parent / "no-such-home"))
    assert sepworker.variant_order() == ["rocm", "cpu"]
    assert sepworker.variant_order(["cpu", "htdemucs"]) == ["cpu"]
    monkeypatch.setenv("MVH_SEP_VARIANTS", "cpu")
    assert sepworker.variant_order(["rocm"]) == ["cpu"]


@pytest.mark.skipif(
    sepworker.sep_python("rocm") is None or __import__("os").environ.get("MVH_TEST_GPU") != "1",
    reason="opt-in (MVH_TEST_GPU=1): needs the sep-rocm venv, a heavy slot and gpu.lock",
)
def test_rocm_worker_torch_probe(tmp_path):
    """Real ROCm variant (GPU): holds a heavy slot + gpu.lock like a real separation would."""
    res = sepworker.run_worker(
        "_echo",
        stage_version="1.0.0",
        params={"probe_torch": True},
        inputs={"mix": (np.zeros((1, 100)), 8000)},
        scratch=tmp_path,
        threads=2,
        variants=("rocm",),
        hold_slot=True,
        timeout=600,
    )
    s = res.result["summary"]
    assert s["torch"].endswith("rocm7.13.0") or "rocm" in s["torch"]
    assert s["torch_threads"] == 2
