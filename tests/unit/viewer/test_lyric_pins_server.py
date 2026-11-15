"""D82 in the viewer server: lyric line pins are saved through POST /api/overrides, and the server's own list of
override fields covers every key of the contract (it rejected a new key once)."""
from __future__ import annotations

import json

from test_server import folder, post, req, srv  # noqa: F401  (fixtures)

from mvh.contract import catalog
from mvh.stages.viewer.server import KNOWN_FIELDS, affected_by_keys, changed_keys, check_overrides

PINS = [{"index": 15, "t": 59.5, "key": "0123456789", "line": "L016"}, {"index": 18, "t": 74.4}]


def test_every_contract_override_key_is_a_known_field():
    for key in catalog.OVERRIDE_KEYS:
        sec, field = key.split(".", 1)
        assert field in KNOWN_FIELDS[sec], key
    assert {f"{s}.{f}" for s, fs in KNOWN_FIELDS.items() for f in fs} == set(catalog.OVERRIDE_KEYS)


def test_pins_validate_and_name_the_lyrics_stage():
    assert check_overrides({"lyrics": {"pins": PINS}}) == []
    assert check_overrides({"lyrics": {"pins": [{"index": -1, "t": 1.0}]}})          # index >= 0
    assert check_overrides({"lyrics": {"pins": [{"index": 3}]}})                     # t is required
    assert check_overrides({"lyrics": {"pins": {"L016": {"t": 1.0}}}})               # a list, not a map
    keys = changed_keys({}, {"lyrics": {"pins": PINS}})
    assert keys == ["lyrics.pins"]
    assert "lyrics" in [a["stage"] for a in affected_by_keys(keys)]


def test_pins_are_saved_through_the_overrides_endpoint(srv, folder):  # noqa: F811
    st, res = post(srv, "/api/overrides", {"overrides": {"lyrics": {"pins": PINS}}, "etag": None})
    assert st == 200 and res["changed"] == ["lyrics.pins"] and "lyrics" in [a["stage"] for a in res["affected"]]
    saved = json.loads((folder / "overrides.json").read_text(encoding="utf-8"))
    assert saved["lyrics"]["pins"] == PINS
    got = json.loads(req(srv, "GET", "/api/overrides")[2])
    assert got["overrides"]["lyrics"]["pins"][1] == {"index": 18, "t": 74.4}
