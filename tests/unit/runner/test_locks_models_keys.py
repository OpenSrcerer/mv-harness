"""runner.locks (heavy_lock.py compatible), runner.models (registry, fetch, verify), runner.cache keys."""

from __future__ import annotations

import hashlib
import http.server
import importlib.util
import json
import socketserver
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mvh.runner import cache, locks, models


# ============================================================================================ locks
@pytest.fixture
def lock_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MVH_HOME", str(tmp_path / "mvh home"))
    return tmp_path / "mvh home" / "locks"


def _load_heavy_lock_script(repo_root: Path):
    spec = importlib.util.spec_from_file_location(
        "heavy_lock_script", repo_root / "scripts" / "heavy_lock.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_slot_files_and_json(lock_home):
    with locks.heavy("pytest-a", gpu=True, timeout=1, poll=0.05) as slot:
        names = sorted(p.name for p in lock_home.iterdir())
        assert names == ["gpu.lock", "heavy-0.lock"] and slot.gpu
        info = json.loads((lock_home / "heavy-0.lock").read_text(encoding="utf-8"))
        assert set(info) == {"owner", "pid", "started"} and info["owner"] == "pytest-a"
        datetime.fromisoformat(info["started"])
    assert list(lock_home.iterdir()) == []


def test_two_slots_then_timeout(lock_home):
    a = locks.acquire("a", timeout=1, poll=0.05)
    b = locks.acquire("b", timeout=1, poll=0.05)
    try:
        assert {p.name for p in a.paths + b.paths} == {"heavy-0.lock", "heavy-1.lock"}
        with pytest.raises(TimeoutError):
            locks.acquire("c", timeout=0.2, poll=0.05)
    finally:
        a.release()
        b.release()


def test_stale_locks_are_taken_over(lock_home):
    lock_home.mkdir(parents=True)
    (lock_home / "heavy-0.lock").write_text(
        json.dumps({"owner": "dead", "pid": 999999, "started": datetime.now(timezone.utc).isoformat()}),
        encoding="utf-8",
    )
    old = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()
    import os

    (lock_home / "heavy-1.lock").write_text(
        json.dumps({"owner": "old", "pid": os.getpid(), "started": old}), encoding="utf-8"
    )
    st = locks.status()
    assert st["heavy-0.lock"]["stale"] and st["heavy-1.lock"]["stale"] and st["gpu.lock"] is None
    with locks.heavy("new", timeout=1, poll=0.05) as slot:
        assert json.loads(slot.paths[0].read_text(encoding="utf-8"))["owner"] == "new"


def test_compatible_with_scripts_heavy_lock(lock_home, repo_root, monkeypatch):
    import os

    for v in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMBA_NUM_THREADS",
        "MVH_THREADS",
    ):
        monkeypatch.setenv(
            v, os.environ.get(v, "3")
        )  # the script exports 6 threads on acquire; restore after
    hl = _load_heavy_lock_script(repo_root)
    assert Path(hl.LOCK_DIR) == lock_home
    s1 = hl.acquire("script", timeout=1, poll=0.05)  # the script takes one slot ...
    try:
        with locks.heavy("runtime", timeout=1, poll=0.05) as slot:  # ... the runtime gets the other
            assert slot.paths[0].name != Path(s1.paths[0]).name
            with pytest.raises(TimeoutError):
                hl.acquire("script-2", timeout=0.2, poll=0.05)
    finally:
        s1.release()
    # and the script reads our lock files
    with locks.heavy("runtime", timeout=1, poll=0.05):
        assert "owner=runtime" in hl.describe()


def test_testing_heavy_helper(lock_home):
    from mvh import testing

    with testing.heavy("pytest") as slot:
        assert slot.threads == 6 and (lock_home / slot.paths[0].name).exists()


# ============================================================================================ models
class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@pytest.fixture
def file_server(tmp_path):
    root = tmp_path / "srv"
    root.mkdir()

    def handler(*a, **kw):
        return _Quiet(*a, directory=str(root), **kw)

    srv = socketserver.TCPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield root, f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()


def _mk_lock(tmp_path, base_url, files):
    entries = []
    for i, (rel, data) in enumerate(files):
        entries.append(
            {
                "id": f"m{i}",
                "envs": ["main"],
                "licence": "test",
                "used_by": ["x"],
                "files": [
                    {
                        "path": rel,
                        "url": f"{base_url}/f{i}",
                        "revision": "r1",
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "size": len(data),
                    }
                ],
            }
        )
    lock = tmp_path / "models.lock.json"
    lock.write_text(json.dumps({"schema": 1, "models": entries}), encoding="utf-8")
    return lock


def test_fetch_verify_list(tmp_path, monkeypatch, file_server):
    root, url = file_server
    data = [b"model zero", b"model one bytes"]
    for i, d in enumerate(data):
        (root / f"f{i}").write_bytes(d)
    lock = _mk_lock(tmp_path, url, [("a/zero.bin", data[0]), ("nltk/one.zip", data[1])])
    monkeypatch.setenv("MVH_MODELS_LOCK", str(lock))
    monkeypatch.setenv("MVH_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MVH_MODELS_DIR", str(tmp_path / "home" / "models"))
    monkeypatch.delenv("MVH_OFFLINE", raising=False)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    assert models.local_path("nltk/one.zip") == tmp_path / "home" / "nltk" / "one.zip"
    assert [r.status for r in models.verify()] == ["missing", "missing"]
    rows = models.fetch(log=lambda s: None)
    assert sorted(r.status for r in rows) == ["fetched", "fetched"]
    assert (tmp_path / "home" / "models" / "a" / "zero.bin").read_bytes() == data[0]
    assert [r.status for r in models.fetch(log=lambda s: None)] == ["ok", "ok"]
    assert [r.status for r in models.verify()] == ["ok", "ok"]
    assert all(m["present"] for m in models.list_models())
    h = models.handle("m0")
    assert h.files["a/zero.bin"].is_file() and h.licence == "test" and h.revision == "r1"
    # corruption is detected (size, then content) and fetch never re-pins
    (tmp_path / "home" / "models" / "a" / "zero.bin").write_bytes(b"model ZERO")
    assert models.verify(["m0"], use_cache=False)[0].status == "mismatch"
    (root / "f0").write_bytes(b"something else")
    with pytest.raises(models.ModelError, match="SHA MISMATCH"):
        models.fetch(["m0"], log=lambda s: None)
    # offline: a missing file fails fast
    (tmp_path / "home" / "models" / "a" / "zero.bin").unlink()
    monkeypatch.setenv("MVH_OFFLINE", "1")
    with pytest.raises(models.ModelError, match="offline"):
        models.fetch(["m0"], log=lambda s: None)
    with pytest.raises(models.ModelError, match="missing"):
        models.handle("m0")


def test_real_lock_has_28_entries():
    ids = [e["id"] for e in models.entries()]
    assert len(ids) == 28 and len(set(ids)) == 28
    assert {"sep", "ffmpeg", "main"} <= set().union(*(models.env_class(e["envs"]) for e in models.entries()))
    assert models.local_path("venv:Lib/site-packages/x").parts[-4:] == (".venv", "Lib", "site-packages", "x")


def test_ctx_model_lookup_gives_local_paths():
    present = [m for m in models.list_models() if m["present"] and not m["bundled"]]
    if not present:
        pytest.skip("no models fetched on this machine")
    h = models.handle(present[0]["id"])
    assert all(p.is_absolute() and p.is_file() for p in h.files.values())


# ============================================================================================ keys
def test_key_is_canonical_and_diffable():
    a = {"stage": "x", "params": {"b": 1, "a": 2}, "upstream": {"ingest": "k1"}}
    b = {"upstream": {"ingest": "k1"}, "params": {"a": 2, "b": 1}, "stage": "x"}
    assert cache.key_of(a) == cache.key_of(b) and len(cache.key_of(a)) == 64
    c = {**a, "params": {"a": 3, "b": 1}}
    assert cache.diff_inputs(a, c) == ["params changed: a"]
    assert cache.diff_inputs(None, a) == ["never run"]


def test_env_lock_hash_is_full_sha256(repo_root):
    h = cache.env_lock_hash("main")
    assert h["uv.lock"] == hashlib.sha256((repo_root / "uv.lock").read_bytes()).hexdigest()
    assert len(h["models.lock.json"]) == 64
    s = cache.env_lock_hash("sep")
    assert set(s) == {"models.lock.json", "envs/sep/uv.rocm.lock", "envs/sep/uv.cpu.lock"}


def test_scripts_fetch_models_is_a_thin_wrapper(repo_root):
    r = subprocess.run(
        [sys.executable, "-X", "utf8", str(repo_root / "scripts" / "fetch_models.py"), "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert r.returncode == 0 and "mvh models" in r.stdout
