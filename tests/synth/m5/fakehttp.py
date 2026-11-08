# ruff: noqa: E501
"""Synthetic recorded HTTP for the M5 tests (tests/fixtures/http/*.json; never real lyrics).

* ``FakeHttp``: an in-memory stand-in for ``mvh.runner.http.CachedHttp`` (``get``/``post`` -> Response) that
  serves canned responses by (path suffix, params subset) rules and records every request it saw;
* ``seed_cache(http_dir, fixture)``: writes canned responses into a CachedHttp cache directory under the exact
  request keys the stage will compute, so the real stage code runs offline against recorded HTTP.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from mvh.runner.http import CachedHttp, Response

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tests" / "fixtures" / "http"

__all__ = ["FakeHttp", "seed_cache", "load_fixture", "FIXTURES"]


def load_fixture(name: str) -> list[dict[str, Any]]:
    with open(FIXTURES / name, encoding="utf-8") as fh:
        return json.load(fh)["responses"]


@dataclass
class FakeHttp:
    """rules: [{"method": "GET", "url_endswith": "/api/search", "params": {...subset...}, "status": 200,
    "body": <json>}]; the first matching rule answers; unmatched requests get 404."""

    rules: list[dict[str, Any]]
    seen: list[dict[str, Any]] = field(default_factory=list)

    def _answer(self, method: str, url: str, params: Mapping[str, Any] | None) -> Response:
        p = {str(k): str(v) for k, v in (params or {}).items()}
        self.seen.append({"method": method, "url": url, "params": p})
        for r in self.rules:
            if r.get("method", "GET") != method or not url.endswith(r["url_endswith"]):
                continue
            want = {str(k): str(v) for k, v in (r.get("params") or {}).items()}
            has = {str(k): str(v) for k, v in (r.get("contains") or {}).items()}
            lacks = {str(k): str(v) for k, v in (r.get("lacks") or {}).items()}
            if (all(p.get(k) == v for k, v in want.items()) and (not r.get("exact") or set(p) == set(want))
                    and all(v in p.get(k, "") for k, v in has.items()) and not any(v in p.get(k, "") for k, v in lacks.items())):
                body = json.dumps(r.get("body"), ensure_ascii=False).encode("utf-8")
                return Response(int(r.get("status", 200)), {"content-type": "application/json"}, body, url)
        return Response(404, {}, b'{"statusCode":404}', url)

    def get(self, url: str, *, params=None, headers=None, min_interval_s: float = 0.0) -> Response:
        return self._answer("GET", url, params)

    def post(self, url: str, *, data=None, json=None, headers=None, min_interval_s: float = 0.0) -> Response:
        return self._answer("POST", url, None)


def seed_cache(http_dir: Path, requests: list[dict[str, Any]]) -> int:
    """requests: [{"method", "url", "params", "status", "body"}] with the exact params the stage sends."""
    c = CachedHttp(Path(http_dir))
    Path(http_dir).mkdir(parents=True, exist_ok=True)
    for r in requests:
        k = c._key(r.get("method", "GET"), r["url"], r.get("params"), None)
        body = json.dumps(r.get("body"), ensure_ascii=False).encode("utf-8")
        c._store(k, Response(int(r.get("status", 200)), {"content-type": "application/json"}, body, r["url"]),
                 r.get("method", "GET"), r.get("params"))
    return len(requests)
