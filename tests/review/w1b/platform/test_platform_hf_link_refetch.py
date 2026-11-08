"""R-PLATFORM (W1b) finding: after ``mvh models fetch`` repairs a corrupt model, the HF-cache copy that the
library actually loads stays corrupt, and ``mvh models verify`` / ``mvh doctor`` report everything OK.

For ``HF_CACHE_IDS`` (allin1 folds, demucs-onnx) ``fetch`` hard-links each model file into
``HF_HOME/hub/models--org--name/snapshots/<rev>/`` because the libraries resolve them through
``hf_hub_download``. A hard link shares the file's data, so in-place corruption of the model (bit rot, a
partial write, a tool that edits in place) corrupts both names. ``fetch`` then re-downloads, verifies and
``os.replace``s the models/ path (a NEW file) but ``_hf_link`` skips any existing snapshot path, so
the snapshot keeps the old corrupt data. ``verify`` only hashes the models/ path, so nothing reports it.

Expected: after a successful ``fetch``, the HF snapshot file has the lock's SHA-256 (re-link when the inode or
hash differs), and ``verify`` (doctor) checks the snapshot links too.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import socketserver
import threading

import pytest

from mvh.runner import models


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@pytest.fixture
def server(tmp_path):
    root = tmp_path / "srv"
    root.mkdir()
    srv = socketserver.TCPServer(("127.0.0.1", 0), lambda *a, **kw: _Quiet(*a, directory=str(root), **kw))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield root, f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()


def test_refetch_repairs_the_hf_snapshot_copy(tmp_path, monkeypatch, server):
    root, base = server
    data = bytes(range(256)) * 64
    rel_url = "huggingface.co/org/demo/resolve/0123abcd/model.onnx"
    (root / rel_url).parent.mkdir(parents=True)
    (root / rel_url).write_bytes(data)
    mid = "demucs_onnx_htdemucs"  # an id in models.HF_CACHE_IDS
    lock = tmp_path / "models.lock.json"
    lock.write_text(
        json.dumps(
            {
                "schema": 1,
                "models": [
                    {
                        "id": mid,
                        "envs": ["main"],
                        "licence": "test",
                        "used_by": ["x"],
                        "files": [
                            {
                                "path": "demo/model.onnx",
                                "url": f"{base}/{rel_url}",
                                "revision": "0123abcd",
                                "sha256": hashlib.sha256(data).hexdigest(),
                                "size": len(data),
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    home = tmp_path / "mvh home"
    monkeypatch.setenv("MVH_MODELS_LOCK", str(lock))
    monkeypatch.setenv("MVH_HOME", str(home))
    monkeypatch.setenv("MVH_MODELS_DIR", str(home / "models"))
    monkeypatch.setenv("HF_HOME", str(home / "hf"))
    monkeypatch.delenv("MVH_OFFLINE", raising=False)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)

    models.fetch([mid], log=lambda s: None)
    snap = home / "hf" / "hub" / "models--org--demo" / "snapshots" / "0123abcd" / "model.onnx"
    local = models.local_path("demo/model.onnx")
    assert snap.read_bytes() == data and local.read_bytes() == data

    with open(local, "r+b") as fh:  # in-place corruption (same size) hits both hard links
        fh.seek(100)
        fh.write(b"\xff\xff\xff\xff")
    assert models.verify([mid], use_cache=False)[0].status == "mismatch"

    rows = models.fetch([mid], log=lambda s: None)  # the documented repair
    assert [r.status for r in rows] == ["fetched"]
    assert models.verify([mid], use_cache=False)[0].status == "ok"
    snap_sha = hashlib.sha256(snap.read_bytes()).hexdigest()
    assert snap_sha == hashlib.sha256(data).hexdigest(), (
        "the HF-cache snapshot the library loads is still the corrupt file after mvh models fetch, "
        "and mvh models verify reported ok"
    )
