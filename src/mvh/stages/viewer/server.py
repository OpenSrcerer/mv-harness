# ruff: noqa: E501  (long lines)
"""``mvh view``: a tiny local server for the viewer's EDIT MODE (PLAN §9, CONTRACT D35).

* binds 127.0.0.1 (port 0 = any free port), checks the Host header (DNS-rebinding guard) and, for every POST, a
  per-run token (``X-MVH-Token``, injected into the page it serves) and the Origin;
* serves the song folder read-only (Range requests for audio); hidden / cache / intermediate folders are never served;
* ``POST /api/overrides`` validates the document against the ``mvh/envelope/overrides`` schema and writes
  ``overrides.json`` atomically; ``POST /api/intent`` updates the viewer-managed block of ``meaning/intent.md``
  (everything else in that file is preserved);
* both answer with the stages that will re-run (the override keys each stage declares, plus its dependants);
* ``POST /api/rerun`` optionally runs ``mvh analyze <folder>`` in a child process;
* exits after ``idle_timeout`` seconds without requests (the open page pings every 15 s).

No lyric text is ever logged.
"""
from __future__ import annotations

import hashlib
import json
import math
import mimetypes
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import unquote, urlsplit

from mvh.io import atomic

from . import intent_block as ib

EDIT_MARK = "<!--MVH-EDIT-->"
MAX_BODY = 1_000_000
KNOWN_SECTIONS = ("schema", "schema_version", "rhythm", "structure", "lyrics", "voices", "cues")
KNOWN_FIELDS = {
    "rhythm": {"beat_offset_s", "bpm", "downbeat_phase"},
    "structure": {"boundaries", "labels"},
    "lyrics": {"lines", "words"},
    "voices": {"lines"},
    "cues": {"pinned"},
}
_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
          ".flac": "audio/flac", ".opus": "audio/ogg", ".wav": "audio/wav", ".mid": "audio/midi", ".csv": "text/csv; charset=utf-8",
          ".tsv": "text/tab-separated-values; charset=utf-8", ".md": "text/markdown; charset=utf-8", ".f32": "application/octet-stream",
          ".u8": "application/octet-stream", ".jpg": "image/jpeg", ".png": "image/png", ".lrc": "text/plain; charset=utf-8",
          ".vtt": "text/vtt; charset=utf-8", ".srt": "text/plain; charset=utf-8", ".ass": "text/plain; charset=utf-8", ".glsl": "text/plain; charset=utf-8"}


def _no_constant(name: str) -> Any:
    raise ValueError(f"non-standard JSON constant {name}")


def loads_strict(text: str) -> Any:
    """json.loads that refuses NaN / Infinity / -Infinity."""
    return json.loads(text, parse_constant=_no_constant)


def all_finite(obj: Any) -> bool:
    if isinstance(obj, float):
        return math.isfinite(obj)
    if isinstance(obj, dict):
        return all(all_finite(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return all(all_finite(v) for v in obj)
    return True


def etag_of(path: Path) -> str:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]
    except OSError:
        return "none"


# ------------------------------------------------------------------------------------------------ affected stages
def _specs() -> dict[str, Any] | None:
    try:
        from mvh.runner.spec import load_stage_specs

        return load_stage_specs()
    except Exception:  # noqa: BLE001  (a stage being edited by another agent must not break the viewer server)
        return None


_FALLBACK_KEYS = {"rhythm": ("rhythm.",), "structure": ("structure.",), "lyrics": ("lyrics.",), "voices": ("voices.",), "cues": ("cues.",)}


def _closure(specs: Mapping[str, Any], seeds: list[str]) -> list[str]:
    from mvh.runner.spec import topo_order

    users: dict[str, list[str]] = {n: [] for n in specs}
    for s in specs.values():
        for d in s.deps:
            if d in users:
                users[d].append(s.name)
    seen: set[str] = set(seeds)
    todo = list(seeds)
    while todo:
        n = todo.pop()
        for u in users.get(n, []):
            if u not in seen and specs[u].trigger == "analyze":
                seen.add(u)
                todo.append(u)
    return [n for n in topo_order(specs) if n in seen]


def changed_keys(old: Mapping[str, Any], new: Mapping[str, Any]) -> list[str]:
    keys = []
    for sec, fields in KNOWN_FIELDS.items():
        for f in sorted(fields):
            a = (old.get(sec) or {}).get(f) if isinstance(old.get(sec), dict) else None
            b = (new.get(sec) or {}).get(f) if isinstance(new.get(sec), dict) else None
            if json.dumps(a, sort_keys=True) != json.dumps(b, sort_keys=True):
                keys.append(f"{sec}.{f}")
    return keys


def affected_by_keys(keys: list[str], specs: Mapping[str, Any] | None = None) -> list[dict[str, str]]:
    """Stages that re-run when these override keys change: the declaring stages and every dependant."""
    if not keys:
        return []
    specs = specs if specs is not None else _specs()
    if not specs:
        direct = sorted({s for k in keys for s, pre in _FALLBACK_KEYS.items() if k.startswith(pre[0])})
        return [{"stage": s, "reason": "overrides changed: " + ", ".join(keys)} for s in [*direct, "viewer"]]
    direct = [n for n, s in specs.items() if any(k in s.override_keys for k in keys)]
    out = []
    for n in _closure(specs, direct):
        why = "overrides changed: " + ", ".join(k for k in keys if k in specs[n].override_keys) if n in direct else "an upstream stage re-runs"
        out.append({"stage": n, "reason": why})
    if not direct:  # nobody declares the key yet (stub stages): still say what the contract says
        return [{"stage": "viewer", "reason": "no stage declares " + ", ".join(keys) + " yet"}]
    return out


def affected_by_intent(specs: Mapping[str, Any] | None = None) -> list[dict[str, str]]:
    specs = specs if specs is not None else _specs()
    if not specs:
        return [{"stage": s, "reason": "meaning/intent.md changed"} for s in ("voices", "meaning", "brief", "viewer")]
    direct = [n for n, s in specs.items() if any(e.path == "meaning/intent.md" for e in s.external_inputs)]
    if not direct:
        direct = [n for n in ("voices", "meaning") if n in specs]
    return [{"stage": n, "reason": "meaning/intent.md changed" if n in direct else "an upstream stage re-runs"} for n in _closure(specs, direct)]


# ------------------------------------------------------------------------------------------------ validation
def check_overrides(doc: Any) -> list[str]:
    if not isinstance(doc, dict):
        return ["overrides must be a JSON object"]
    if not all_finite(doc):
        return ["numbers must be finite (no NaN / Infinity)"]
    errs: list[str] = []
    for k, v in doc.items():
        if k not in KNOWN_SECTIONS:
            errs.append(f"unknown section {k[:30]!r} (known: {', '.join(KNOWN_SECTIONS[2:])})")
        elif k in KNOWN_FIELDS and isinstance(v, dict):
            for f in v:
                if f not in KNOWN_FIELDS[k]:
                    errs.append(f"unknown field {k}.{f[:30]}")
    try:
        from mvh.runner import overrides as ovr

        errs += ovr.validate(doc)
    except Exception as e:  # noqa: BLE001
        errs.append(f"schema validation failed: {type(e).__name__}")
    return errs


# ------------------------------------------------------------------------------------------------ server
def _decode_user_text(raw: bytes) -> tuple[str, bool]:
    """Decode a user-owned text file: (text, was_utf8). Falls back to BOM-detected UTF-16, then cp1252, then latin-1."""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace"), False
    try:
        return raw.decode("utf-8-sig"), True
    except UnicodeDecodeError:
        pass
    for enc in ("cp1252", "latin-1"):
        try:
            return raw.decode(enc), False
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), False


class _QuietServer(ThreadingHTTPServer):
    """A browser aborting a media request is normal: no traceback on stderr."""

    def handle_error(self, request: Any, client_address: Any) -> None:  # noqa: D401
        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            return
        super().handle_error(request, client_address)


class ViewServer:
    def __init__(self, folder: Path, *, port: int = 0, idle_timeout: float = 900.0, allow_rerun: bool = True,
                 edit: bool = True, token: str | None = None):
        self.folder = Path(folder).resolve()
        if not self.folder.is_dir():
            raise FileNotFoundError(f"no such song folder: {folder}")
        self.edit = edit
        self.allow_rerun = allow_rerun and edit
        self.token = token or secrets.token_urlsafe(24)
        self.idle_timeout = float(idle_timeout)
        self.last_activity = time.monotonic()
        self.stop = threading.Event()
        self.rerun: dict[str, Any] = {"running": False, "code": None, "tail": []}
        self._lock = threading.Lock()
        self._status_cache: tuple[float, dict[str, Any]] | None = None
        handler = _make_handler(self)
        self.httpd = _QuietServer(("127.0.0.1", int(port)), handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/"
        self._thread: threading.Thread | None = None
        self.log: list[str] = []

    # ---- lifecycle
    def start(self) -> "ViewServer":
        self._thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True, name="mvh-view")
        self._thread.start()
        return self

    def wait(self) -> str:
        """Block until the idle timeout or shutdown(); returns the reason."""
        while not self.stop.wait(0.5):
            if self.idle_timeout > 0 and time.monotonic() - self.last_activity > self.idle_timeout:
                self.shutdown()
                return "idle"
        return "stopped"

    def shutdown(self) -> None:
        self.stop.set()
        try:
            self.httpd.shutdown()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.httpd.server_close()
        except Exception:  # noqa: BLE001
            pass

    # ---- files
    def resolve(self, url_path: str) -> Path | None:
        rel = unquote(urlsplit(url_path).path).lstrip("/")
        if not rel:
            rel = "viewer.html"
        parts = [p for p in rel.replace("\\", "/").split("/") if p]
        if any(p in (".", "..") or p.startswith((".", "_")) or ":" in p for p in parts):
            return None
        p = (self.folder / Path(*parts)).resolve()
        try:
            p.relative_to(self.folder)
        except ValueError:
            return None
        return p if p.is_file() else None

    def page(self) -> bytes | None:
        p = self.folder / "viewer.html"
        if not p.is_file():
            return None
        html = p.read_text(encoding="utf-8")
        script = ""
        if self.edit:
            cfg = {"token": self.token, "folder": str(self.folder), "rerun": self.allow_rerun}
            script = "<script>window.MVH_EDIT=" + json.dumps(cfg).replace("</", "<\\/") + ";</script>"
        if EDIT_MARK in html:
            html = html.replace(EDIT_MARK, script, 1)
        elif script:
            html = html.replace("</head>", script + "</head>", 1)
        return html.encode("utf-8")

    # ---- documents
    def overrides_path(self) -> Path:
        return self.folder / "overrides.json"

    def read_overrides(self) -> tuple[dict[str, Any], str]:
        d, tag, _err = self.read_overrides_checked()
        return d, tag

    def read_overrides_checked(self) -> tuple[dict[str, Any], str, str | None]:
        """(document, etag, error). An unparseable file yields ({}, etag, message): it is never treated as empty."""
        p = self.overrides_path()
        if not p.is_file():
            return {}, "none", None
        raw = p.read_bytes()
        tag = hashlib.sha256(raw).hexdigest()[:16]
        try:
            d = loads_strict(raw.decode("utf-8-sig"))
        except (ValueError, UnicodeDecodeError, RecursionError) as e:
            return {}, tag, f"overrides.json is not valid JSON ({str(e)[:80]}); fix or delete it by hand, the viewer will not overwrite it"
        if not isinstance(d, dict):
            return {}, tag, "overrides.json is not a JSON object; fix or delete it by hand, the viewer will not overwrite it"
        return d, tag, None

    def write_overrides(self, doc: dict[str, Any], etag: str | None) -> tuple[int, dict[str, Any]]:
        with self._lock:
            old, cur, bad = self.read_overrides_checked()
            if bad:
                return 409, {"error": bad, "etag": cur}
            if etag not in (None, "", cur):
                return 409, {"error": "overrides.json changed on disk since this page loaded; reloaded", "etag": cur}
            errs = check_overrides(doc)
            if errs:
                return 400, {"errors": errs[:8]}
            try:
                data = (json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=False, allow_nan=False) + "\n").encode("utf-8")
            except ValueError:
                return 400, {"errors": ["numbers must be finite (no NaN / Infinity)"]}
            try:
                atomic.write_bytes(self.overrides_path(), data)
            except OSError as e:
                return 503, {"error": f"could not write overrides.json ({type(e).__name__}); is it open in another program?"}
            keys = changed_keys(old, doc)
            return 200, {"ok": True, "etag": hashlib.sha256(data).hexdigest()[:16], "changed": keys, "affected": affected_by_keys(keys)}

    def intent_path(self) -> Path:
        return self.folder / "meaning" / "intent.md"

    def read_intent(self) -> dict[str, Any]:
        p = self.intent_path()
        text, utf8 = _decode_user_text(p.read_bytes()) if p.is_file() else ("", True)
        st = ib.parse(text)
        st["exists"] = p.is_file()
        if not utf8:
            st["warning"] = "intent.md is not UTF-8; shown as decoded. Re-save it as UTF-8 to edit it from the viewer."
        return st

    def write_intent(self, patch: Any) -> tuple[int, dict[str, Any]]:
        if not isinstance(patch, dict):
            return 400, {"errors": ["intent patch must be an object"]}
        with self._lock:
            p = self.intent_path()
            text, utf8 = _decode_user_text(p.read_bytes()) if p.is_file() else ("", True)
            if not utf8:
                return 409, {"error": "intent.md is not UTF-8; re-save it as UTF-8 (nothing was changed)"}
            try:
                state = ib.merge(ib.parse(text), patch)
            except ib.IntentError as e:
                return 400, {"errors": [str(e)]}
            new = ib.apply(text, state)
            if new != text:
                atomic.write_bytes(p, new.encode("utf-8"))
            st = ib.parse(new)
            st["exists"] = p.is_file()
            return 200, {"ok": True, "intent": st, "affected": affected_by_intent() if new != text else []}

    # ---- status / rerun
    def status(self) -> dict[str, Any]:
        now = time.monotonic()
        if self._status_cache and now - self._status_cache[0] < 3:
            return self._status_cache[1]
        try:
            from mvh.runner import run as rr

            states = rr.status(self.folder)
            rows = [{"stage": n, "status": s.status, "reason": s.reason} for n, s in states.items()]
            res = {"stages": rows, "stale": [r for r in rows if r["status"] in ("stale", "pending", "failed")]}
        except Exception as e:  # noqa: BLE001
            res = {"stages": [], "stale": [], "error": f"{type(e).__name__}: {str(e)[:200]}"}
        self._status_cache = (now, res)
        return res

    def start_rerun(self) -> tuple[int, dict[str, Any]]:
        if not self.allow_rerun:
            return 403, {"error": "re-run is disabled (mvh view --no-rerun)"}
        with self._lock:
            if self.rerun.get("running"):
                return 409, {"error": "a re-run is already running"}
            from mvh.io import proc
            from mvh.io.paths import repo_root

            env = dict(os.environ)
            src = str(Path(__file__).resolve().parents[3])
            env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
            env["PYTHONUTF8"] = "1"
            try:
                p = proc.popen([sys.executable, "-X", "utf8", "-m", "mvh.cli", "analyze", str(self.folder)], env=env, cwd=str(repo_root()),
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            except Exception as e:  # noqa: BLE001
                return 500, {"error": f"could not start: {type(e).__name__}"}
            self.rerun = {"running": True, "code": None, "tail": []}
            self._status_cache = None

            def pump() -> None:
                assert p.stdout is not None
                for line in p.stdout:
                    tail = self.rerun["tail"]
                    tail.append(line.rstrip()[:300])
                    del tail[:-60]
                code = p.wait()
                self.rerun = {"running": False, "code": code, "tail": self.rerun["tail"]}

            threading.Thread(target=pump, daemon=True, name="mvh-rerun").start()
        return 200, {"ok": True}


def _make_handler(srv: ViewServer):
    class H(BaseHTTPRequestHandler):
        server_version = "mvh-view/1"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:  # never log lyric text; paths only, kept in memory
            srv.log.append((fmt % args)[:200])
            del srv.log[:-200]

        # ---- helpers
        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").lower()
            return host in (f"127.0.0.1:{srv.port}", f"localhost:{srv.port}")

        def _send(self, code: int, body: bytes, ctype: str, extra: Mapping[str, str] | None = None, head: bool = False) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if not head:
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        def _json(self, code: int, obj: Any, head: bool = False) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", head=head)

        # ---- GET / HEAD
        def do_HEAD(self) -> None:  # noqa: N802
            self._get(head=True)

        def do_GET(self) -> None:  # noqa: N802
            self._get(head=False)

        def _get(self, head: bool) -> None:
            srv.last_activity = time.monotonic()
            if not self._host_ok():
                return self._json(403, {"error": "bad Host header"}, head)
            path = urlsplit(self.path).path
            if path == "/api/ping":
                return self._json(200, {"ok": True}, head)
            if path.startswith("/api/"):
                if path == "/api/overrides":
                    return self._overrides_get(head)
                if path == "/api/intent":
                    return self._json(200, srv.read_intent(), head)
                if path == "/api/status":
                    return self._json(200, srv.status(), head)
                if path == "/api/rerun":
                    return self._json(200, srv.rerun, head)
                return self._json(404, {"error": "unknown endpoint"}, head)
            if path in ("/", "/viewer.html", "/index.html"):
                page = srv.page()
                if page is None:
                    return self._send(404, b"viewer.html is missing: run mvh analyze first", "text/plain; charset=utf-8", head=head)
                return self._send(200, page, "text/html; charset=utf-8", head=head)
            f = srv.resolve(path)
            if f is None:
                return self._send(404, b"not found", "text/plain; charset=utf-8", head=head)
            self._file(f, head)

        def _overrides_get(self, head: bool) -> None:
            doc, tag, err = srv.read_overrides_checked()
            res: dict[str, Any] = {"overrides": doc, "etag": tag}
            if err:
                res["error"] = err
            self._json(200, res, head)

        def _file(self, f: Path, head: bool) -> None:
            size = f.stat().st_size
            ctype = _TYPES.get(f.suffix.lower()) or mimetypes.guess_type(str(f))[0] or "application/octet-stream"
            rng = self.headers.get("Range")
            start, end, code = 0, size - 1, 200
            if rng:
                m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng.strip())
                if m and (m.group(1) or m.group(2)):
                    if m.group(1):
                        start = int(m.group(1))
                        end = int(m.group(2)) if m.group(2) else size - 1
                    else:
                        start = max(0, size - int(m.group(2)))
                    end = min(end, size - 1)
                    if start > end or start >= size:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    code = 206
            n = end - start + 1
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(n))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            if code == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if head:
                return
            try:
                with open(f, "rb") as fh:
                    fh.seek(start)
                    left = n
                    while left > 0:
                        chunk = fh.read(min(262144, left))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        # ---- POST
        def do_POST(self) -> None:  # noqa: N802
            srv.last_activity = time.monotonic()
            if not self._host_ok():
                return self._json(403, {"error": "bad Host header"})
            if not srv.edit:
                return self._json(403, {"error": "read-only server"})
            origin = self.headers.get("Origin")
            if origin and origin not in (f"http://127.0.0.1:{srv.port}", f"http://localhost:{srv.port}"):
                return self._json(403, {"error": "bad Origin"})
            if not secrets.compare_digest(self.headers.get("X-MVH-Token") or "", srv.token):
                return self._json(403, {"error": "missing or wrong token"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = -1
            if n < 0 or n > MAX_BODY:
                return self._json(413, {"error": "body too large"})
            raw = self.rfile.read(n) if n else b""
            try:
                body = loads_strict(raw.decode("utf-8")) if raw else {}
            except (ValueError, UnicodeDecodeError, RecursionError):
                return self._json(400, {"errors": ["body is not valid JSON"]})
            path = urlsplit(self.path).path
            if path == "/api/overrides":
                if not isinstance(body, dict) or not isinstance(body.get("overrides"), dict):
                    return self._json(400, {"errors": ["expected {overrides: {...}, etag}"]})
                code, res = srv.write_overrides(body["overrides"], body.get("etag"))
                return self._json(code, res)
            if path == "/api/intent":
                try:
                    code, res = srv.write_intent(body)
                except OSError as e:
                    code, res = 503, {"error": f"could not write intent.md ({type(e).__name__})"}
                return self._json(code, res)
            if path == "/api/rerun":
                code, res = srv.start_rerun()
                return self._json(code, res)
            return self._json(404, {"error": "unknown endpoint"})

    return H


def make_server(folder: Path | str, **kw: Any) -> ViewServer:
    return ViewServer(Path(folder), **kw)
