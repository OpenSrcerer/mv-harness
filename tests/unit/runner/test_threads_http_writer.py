"""Thread patches in a fresh process, the cached HTTP client, and the Writer/Upstream rules."""

from __future__ import annotations

import http.server
import json
import socketserver
import subprocess
import sys
import threading
from pathlib import Path

import numpy as np
import pytest

from mvh.contract import catalog
from mvh.runner.ctx import CacheUpstream, StageWriter, match_output
from mvh.runner.http import CachedHttp
from mvh.runner.spec import (
    ExternalInput,
    Output,
    StageError,
    StageSpec,
    UndeclaredDependency,
    UndeclaredOutput,
    catalog_outputs,
)
from mvh.runner.threads import thread_env

SRC = str(Path(__file__).resolve().parents[3] / "src")


# ============================================================================================ threads
def test_thread_hooks_in_a_fresh_process():
    code = (
        "import sys; sys.path.insert(0, sys.argv[1])\n"
        "from mvh.runner import threads; threads.install(2)\n"
        "import onnxruntime as ort, torch, json\n"
        "so = ort.SessionOptions()\n"
        "out = {'ort_intra': so.intra_op_num_threads, 'ort_inter': so.inter_op_num_threads,\n"
        "       'torch': torch.get_num_threads(), 'interop': torch.get_num_interop_threads(),\n"
        "       'applied': threads.applied}\n"
        "import ctranslate2\n"
        "out['ct2'] = getattr(ctranslate2.models.Whisper, '_mvh_patched', False)\n"
        "print(json.dumps(out))\n"
    )
    r = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", code, SRC],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        env={**__import__("os").environ, **thread_env(2)},
    )
    assert r.returncode == 0, r.stderr[-2000:]
    d = json.loads(r.stdout.strip().splitlines()[-1])
    assert d["ort_intra"] == 2 and d["ort_inter"] == 1 and d["torch"] == 2 and d["interop"] == 1 and d["ct2"]


def test_thread_env():
    e = thread_env(4)
    assert (
        e["OMP_NUM_THREADS"]
        == e["OPENBLAS_NUM_THREADS"]
        == e["MKL_NUM_THREADS"]
        == e["NUMBA_NUM_THREADS"]
        == "4"
    )


# ============================================================================================ http
class _H(http.server.BaseHTTPRequestHandler):
    hits = {"n": 0, "busy": 0}

    def log_message(self, *a):
        pass

    def do_GET(self):  # noqa: N802
        _H.hits["n"] += 1
        if self.path.startswith("/busy") and _H.hits["busy"] == 0:
            _H.hits["busy"] += 1
            self.send_response(429)
            self.send_header("Retry-After", "0")
            self.end_headers()
            return
        body = json.dumps({"path": self.path, "ua": self.headers.get("User-Agent")}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def server():
    srv = socketserver.TCPServer(("127.0.0.1", 0), _H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()


def test_cached_http(tmp_path, server):
    _H.hits.update(n=0, busy=0)
    c = CachedHttp(tmp_path / "http")
    r = c.get(server + "/api/get", params={"track": "Tëst"})
    assert r.ok and r.json()["ua"].startswith("mv-harness/") and not r.from_cache
    r2 = CachedHttp(tmp_path / "http", offline=True).get(server + "/api/get", params={"track": "Tëst"})
    assert r2.from_cache and r2.json() == r.json() and _H.hits["n"] == 1
    with pytest.raises(StageError, match="offline"):
        CachedHttp(tmp_path / "http", offline=True).get(server + "/other")
    r3 = c.get(server + "/busy")  # 429 + Retry-After: retried
    assert r3.ok and _H.hits["busy"] == 1
    assert len(c.used) == 2 and all(":" in v for v in c.used.values())


# ============================================================================================ writer
def _job(tmp_path, stage, timebase=None):
    return {
        "stage": stage,
        "stage_version": "1.0.0",
        "contract_version": catalog.CONTRACT_VERSION,
        "key": "a" * 64,
        "pre_key": "a" * 64,
        "params": {"x": 1},
        "device": "cpu",
        "upstream": {},
        "overrides": {"rhythm.bpm": 120.0},
        "timebase": timebase,
        "song_dir": str(tmp_path),
        "http_dir": str(tmp_path / "http"),
    }


def test_writer_rules(tmp_path):
    spec = StageSpec("loudness", ("ingest",), "main", "1.0.0", outputs=catalog_outputs("loudness"))
    w = StageWriter(
        spec,
        tmp_path / "out",
        _job(tmp_path, "loudness", {"n_samples": 48000, "sample_rate": 48000, "channels": 2}),
    )
    with pytest.raises(UndeclaredOutput):
        w.json("meta/tempo.json", {})
    with pytest.raises(UndeclaredOutput):
        w.text("overrides.json", "{}")
    with pytest.raises(StageError, match="does not match"):
        w.json("meta/loudness.json", {"integrated_lufs": "loud"})
    good = {
        "integrated_lufs": -9.0,
        "lra_lu": 5.0,
        "lra_low_lufs": -14.0,
        "lra_high_lufs": -9.0,
        "true_peak_dbtp": 0.5,
        "sample_peak_db": 0.0,
        "plr_db": 9.5,
    }
    w.json("meta/loudness.json", good)
    # curves: undeclared channel, wrong length, NaN
    with pytest.raises(UndeclaredOutput):
        w.curves("core", {"bands.bass": np.zeros(100)})
    with pytest.raises(StageError, match="expected 100"):
        w.curves("core", {"loud.rms_db": np.zeros(99)})
    with pytest.raises(StageError, match="NaN"):
        w.curves("core", {"loud.rms_db": np.full(100, np.nan)})
    w.curves(
        "core",
        {"loud.rms_db": np.full(100, -20.0), "loud.rms": np.zeros(100)},
        meta={"loud.rms": {"norm": {"lo": -30.0, "hi": -10.0}}},
    )
    assert (tmp_path / "out/_mvh/curves/core/loud.rms_db.f32").stat().st_size == 400
    assert w.curves_meta["core"]["loud.rms"]["meta"] == {"lo": -30.0, "hi": -10.0}


def test_writer_events_tables_audio_and_restamp(tmp_path):
    spec = StageSpec(
        "rhythm", ("ingest", "allin1", "spectral"), "main", "1.0.0", outputs=catalog_outputs("rhythm")
    )
    out = tmp_path / "out"
    w = StageWriter(spec, out, _job(tmp_path, "rhythm"))
    p = w.events(
        "tempo_segments",
        [
            {"t": 0.5, "d": 1.0, "bpm": 120.0, "stable": True},
            {"t": 0.0, "d": 0.5, "bpm": 120.0, "stable": True},
        ],
    )
    env = json.loads(p.read_text(encoding="utf-8"))
    assert [i["t"] for i in env["items"]] == [0.0, 0.5] and env["provenance"]["overrides_applied"] == [
        {"key": "rhythm.bpm", "value": 120.0}
    ]
    with pytest.raises(StageError):
        w.events("tempo_segments", [{"t": 0.0, "bpm": 120.0, "stable": True}])  # segment without d
    with pytest.raises(UndeclaredOutput):
        w.events("beatz", [])
    w.restamp({**env["provenance"], "fallbacks": ["x:y"], "notes": ["restamped"]})
    env2 = json.loads(p.read_text(encoding="utf-8"))
    assert env2["provenance"]["fallbacks"] == ["x:y"] and env2["items"] == env["items"]

    # tables (choreo owns them) and the lines.tsv text rule (meaning)
    cs = StageSpec("meaning", ("lyrics",), "main", "1.0.0", outputs=catalog_outputs("meaning"))
    wm = StageWriter(cs, tmp_path / "m", _job(tmp_path, "meaning"))
    wm.table(
        "lyrics/lines.tsv",
        [
            {
                "id": "L001",
                "t": 1.0,
                "d": 2.0,
                "section_id": None,
                "singer": "C1",
                "repeat_group": None,
                "grade": "B",
                "text": "synthetic\tline\nhere",
            }
        ],
        ["id", "t", "d", "section_id", "singer", "repeat_group", "grade", "text"],
    )
    lines = (tmp_path / "m/lyrics/lines.tsv").read_text(encoding="utf-8").split("\n")
    assert lines[1] == "L001\t1.0\t2.0\t\tC1\t\tB\tsynthetic line here"

    # audio: FLAC plus a float WAV twin when |x| > 1 (D23); stems pattern
    hs = StageSpec("separate_hq", ("ingest",), "sep", "1.0.0", outputs=catalog_outputs("separate_hq"))
    wh = StageWriter(hs, tmp_path / "h", _job(tmp_path, "separate_hq"))
    x = np.zeros((2, 4800), np.float32)
    x[0, 10] = 1.5
    wh.audio("stems/bass.flac", x, 48000)
    assert (tmp_path / "h/stems/bass.flac").is_file() and (tmp_path / "h/stems/bass.wav").is_file()
    wh.audio("stems/drums/kick.flac", x * 0.5, 48000)
    assert not (tmp_path / "h/stems/drums/kick.wav").exists()
    with pytest.raises(UndeclaredOutput):
        wh.audio("stems/kazoo.flac", x, 48000)
    assert match_output(hs, "stems/vocals.wav") is not None


def test_upstream_reads(tmp_path):
    from mvh.contract.events import dumps_events, make_envelope

    root = tmp_path / "up"
    (root / "events").mkdir(parents=True)
    env = make_envelope("onsets.bass", [{"t": 0.25, "strength": 0.5}], {})
    (root / "events/onsets.bass.json").write_text(dumps_events(env), encoding="utf-8")
    (root / "_mvh/curves/core").mkdir(parents=True)
    np.zeros(5, "<f4").tofile(root / "_mvh/curves/core/flux.bass.f32")
    rec = {
        "outputs": {"events/onsets.bass.json": {"kind": "events", "events": "onsets.bass"}},
        "curves": {"core": {"flux.bass": {"n": 5, "meta": {"lo": 0.0, "hi": 2.0}}}},
    }
    up = CacheUpstream("spectral", root, rec)
    assert up.events("onsets.bass").items[0]["t"] == 0.25
    c = up.curve("flux.bass")
    assert c.values.shape == (5,) and c.rate_hz == 100 and c.meta["norm"]["hi"] == 2.0
    with pytest.raises(StageError):
        up.json("meta/none.json")


def test_ctx_dependency_and_external_rules(tmp_path):
    from mvh.runner.ctx import StageCtx

    spec = StageSpec(
        "voices",
        ("lyrics",),
        "main",
        "1.0.0",
        outputs=(Output("meta/voices.json", "json"),),
        external_inputs=(ExternalInput("intent", "meaning/intent.md"),),
    )
    job = {
        **_job(tmp_path, "voices"),
        "slug": "s",
        "profile": "max",
        "threads": 1,
        "scratch": str(tmp_path / "s"),
        "offline": True,
    }
    ctx = StageCtx(spec, job, StageWriter(spec, tmp_path / "o", job), __import__("logging").getLogger("t"))
    with pytest.raises(UndeclaredDependency):
        ctx.upstream("rhythm")
    with pytest.raises(UndeclaredDependency):
        ctx.model("beat_this")
    assert ctx.external("intent") is None
    (tmp_path / "meaning").mkdir()
    (tmp_path / "meaning/intent.md").write_text("characters: 2\n", encoding="utf-8")
    assert ctx.external("intent") == tmp_path / "meaning/intent.md"
    with pytest.raises(StageError):
        ctx.http()
