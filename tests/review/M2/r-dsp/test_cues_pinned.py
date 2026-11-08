# ruff: noqa: E501
"""R-DSP M2 finding F1 (major): a user-pinned cue (override ``cues.pinned``) is snapped onto the beat grid and then
merged (D37) with the tier-4 beat reference at the same time. ``pinned`` is the lowest-priority kind in
CUE_KIND_PRIORITY, so the merged cue gets ``kind: beat``; the cues stage then nulls strength and lead_in for every
``kind == beat`` cue and builds moments only from ``kind`` - the pinned moment comes out as a tier-1 "beat" with
null strength and never reaches moments.json. The user's correction is silently lost (PLAN goal 4, §9 "pinning
moments")."""
from tests.synth.m2.ctx import run_stage
from tests.synth.m2.testing import events, synth_ready

PINS = [{"t": 20.51, "note": "hero pose"}, {"t": 44.0}]


def _run(tmp_path):
    fx = synth_ready()
    run_stage("cues", fx, tmp_path / "cues", overrides={"cues.pinned": PINS})
    return events(tmp_path / "cues", "cues"), events(tmp_path / "cues", "moments")


def test_pinned_cue_keeps_its_identity_strength_and_tier(tmp_path):
    cues, _ = _run(tmp_path)
    for pin in PINS:
        c = min(cues, key=lambda q: abs(q["t"] - pin["t"]))
        assert abs(c["t"] - pin["t"]) <= 0.05, (pin, c["t"])
        kinds = c.get("kinds") or [c["kind"]]
        assert "pinned" in kinds, c
        # a tier-1 cue must not be a 'beat' (tier-4 reference kind) with a null strength
        assert c["tier"] == 1, c
        assert c["kind"] != "beat", c
        assert c["strength"] is not None and c["strength"] >= 0.99, c


def test_pinned_cue_appears_in_moments(tmp_path):
    cues, moments = _run(tmp_path)
    pinned_ids = {c["id"] for c in cues if "pinned" in (c.get("kinds") or [c["kind"]])}
    assert pinned_ids, "no cue carries the pinned kind"
    got = {m["cue_id"] for m in moments}
    assert pinned_ids <= got, (sorted(pinned_ids), sorted(got))
