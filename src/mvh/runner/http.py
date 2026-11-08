"""Cached, rate-limited HTTP for network stages (PLAN NF4; spec.HttpClient).

Every response a stage uses is stored under ``out/<slug>/.cache/_http/<stage>/<request-sha>.{json,body}``
and served
from there on the next run, so re-runs are offline. Offline (``--no-network``, ``MVH_OFFLINE=1``) serves the
cache
or raises StageError. The sha256 of every response used goes into the stage's effective cache key.
Requests are sequential per stage, at least ``min_interval_s`` apart per host, with an identifying
User-Agent, and
honour Retry-After on 429/503. Only 2xx and 404 responses are cached (definitive answers).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from mvh.io import atomic

from .cache import canon
from .spec import StageError

__all__ = ["Response", "CachedHttp", "USER_AGENT"]

USER_AGENT = "mv-harness/0.1 (personal music-video analysis; https://github.com/OpenSrcerer/mv-harness)"


@dataclass
class Response:
    status_code: int
    headers: dict[str, str]
    content: bytes
    url: str
    from_cache: bool = False

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.content.decode("utf-8"))

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


@dataclass
class CachedHttp:
    root: Path  # .cache/_http/<stage>
    offline: bool = False
    used: dict[str, str] = field(default_factory=dict)  # request sha -> response sha (into the cache key)
    _last: dict[str, float] = field(default_factory=dict)
    max_retries: int = 3

    def _key(self, method: str, url: str, params: Mapping[str, Any] | None, body: bytes | None) -> str:
        req = {
            "m": method.upper(),
            "u": url,
            "p": sorted((str(k), str(v)) for k, v in (params or {}).items()),
            "b": hashlib.sha256(body).hexdigest() if body else None,
        }
        return hashlib.sha256(canon(req).encode("utf-8")).hexdigest()

    def _load(self, k: str) -> Response | None:
        meta, body = self.root / f"{k}.json", self.root / f"{k}.body"
        if not (meta.is_file() and body.is_file()):
            return None
        with open(meta, encoding="utf-8") as fh:
            m = json.load(fh)
        return Response(int(m["status"]), dict(m.get("headers", {})), body.read_bytes(), m["url"], True)

    def _store(self, k: str, r: Response, method: str, params: Mapping[str, Any] | None) -> None:
        keep = {h: v for h, v in r.headers.items() if h.lower() in ("content-type", "etag", "last-modified")}
        atomic.write_bytes(self.root / f"{k}.body", r.content)
        atomic.write_text(
            self.root / f"{k}.json",
            json.dumps(
                {
                    "method": method.upper(),
                    "url": r.url,
                    "params": {str(a): str(b) for a, b in (params or {}).items()},
                    "status": r.status_code,
                    "headers": keep,
                },
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
        )

    def _record(self, k: str, r: Response) -> Response:
        self.used[k] = hashlib.sha256(r.content).hexdigest() + f":{r.status_code}"
        return r

    def _throttle(self, url: str, min_interval_s: float) -> None:
        host = urlsplit(url).netloc
        last = self._last.get(host)
        if last is not None and min_interval_s > 0:
            wait = min_interval_s - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last[host] = time.monotonic()

    def request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        data: bytes | None = None,
        json_body: Any = None,
        headers: Mapping[str, str] | None = None,
        min_interval_s: float = 0.0,
    ) -> Response:
        body = data
        hdrs = {"User-Agent": USER_AGENT, **(headers or {})}
        if json_body is not None:
            body = json.dumps(json_body, ensure_ascii=False, sort_keys=True).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
        k = self._key(method, url, params, body)
        hit = self._load(k)
        if hit is not None:
            return self._record(k, hit)
        if self.offline:
            raise StageError(
                f"offline and no cached response for a {method.upper()} to {urlsplit(url).netloc}"
            )
        import httpx  # main env only

        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self._throttle(url, min_interval_s)
            try:
                with httpx.Client(timeout=60.0, follow_redirects=True) as c:
                    rr = c.request(
                        method.upper(), url, params=dict(params or {}) or None, content=body, headers=hdrs
                    )
            except httpx.HTTPError as e:
                last_err = e
                time.sleep(2.0 * (attempt + 1))
                continue
            r = Response(rr.status_code, dict(rr.headers), rr.content, str(rr.url))
            if r.status_code in (429, 503) and attempt < self.max_retries:
                ra = rr.headers.get("Retry-After", "")
                time.sleep(min(float(ra) if ra.replace(".", "", 1).isdigit() else 5.0 * (attempt + 1), 120.0))
                continue
            if r.ok or r.status_code == 404:
                self._store(k, r, method, params)
            return self._record(k, r)
        raise StageError(f"HTTP request to {urlsplit(url).netloc} failed: {last_err}")

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        min_interval_s: float = 0.0,
    ) -> Response:
        return self.request("GET", url, params=params, headers=headers, min_interval_s=min_interval_s)

    def post(
        self,
        url: str,
        *,
        data: bytes | None = None,
        json: Any = None,
        headers: Mapping[str, str] | None = None,
        min_interval_s: float = 0.0,
    ) -> Response:
        return self.request(
            "POST", url, data=data, json_body=json, headers=headers, min_interval_s=min_interval_s
        )
