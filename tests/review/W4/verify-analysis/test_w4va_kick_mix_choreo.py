"""W4A-KICKCURVE: under the UD2 mix fallback (meta/drums.json kick_source = mix), choreo must follow the agent kick.

Round 1 (w4verify-analysis-r1): choreo read the drum-stem kick rows of drum_hits and ignored kick_source, so under the
fallback grooves and 'drum' hit points followed the drum-stem kick UD2 rejected (MEGAFAUNA: 35 % of groove kick steps on
an agent kick, 5 of 6 'drum' hit points with no agent kick).

Round 2 (w4verify-analysis-r2), after choreo 1.3.x (W4-AN-10): the kick rows come from events/hits.kick. A 'drum' hit
point is "a kick OR a snare hit with vel >= 0.5" (choreo), and only the stem KICK was rejected; so the check is that
every 'drum' hit point has an agent kick within 30 ms or a drum-stem snare with vel >= 0.5 within the 30 ms hit window
(round 1 asked for an agent kick at every one, which is stricter than the definition). Measured on the fixer's r2 folders
(drums with kick_source = mix, then choreo): groove kick steps on agent kicks MEGAFAUNA 0.98 / Versatile 1.00 /
Jeremy 1.00; every 'drum' hit point without an agent kick has a stem snare 0.65-1.0.

Runs the real drums and choreo stages (no models, about 30-60 s per song); skips when the song folder or its cache is absent.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from w4va_devchain import chain, has_cache, items
from w4va_support import BASE


@pytest.mark.slow
@pytest.mark.parametrize("slug", ["megafauna", "versatile", "jeremy"])
def test_w4va_choreo_follows_the_agent_kick_under_mix_fallback(tmp_path, slug):
    song = BASE / slug
    if not has_cache(song):
        pytest.skip(f"no song folder with a stage cache at {song}")
    outs = chain(song, [("drums", {"kick_source": "mix"}), ("choreo", {})], tmp_path, slug=slug)

    with open(outs["drums"] / "meta" / "drums.json", encoding="utf-8") as fh:
        assert json.load(fh)["kick_source"] == "mix"
    with open(outs["choreo"] / "meta" / "grooves.json", encoding="utf-8") as fh:
        assert json.load(fh).get("kick_rows") == "hits.kick"
    agent = np.array(sorted(h["t"] for h in items(song, "hits.kick")))
    dh = items(outs["drums"], "drum_hits")
    stem_kick = np.array(sorted(h["t"] for h in dh if h["drum"] == "kick"))
    snare = np.array(sorted(h["t"] for h in dh if h["drum"] == "snare" and h["vel"] >= 0.5))
    gr = items(outs["choreo"], "grooves")
    hp = items(outs["choreo"], "hit_points")
    steps = np.array([g["t"] + g["d"] * k / 16 for g in gr for k, v in enumerate(g["pattern"]["kick"]) if v >= 0.3])
    assert len(agent) >= 50 and len(steps) >= 50

    def near(arr, t, tol):
        return bool(len(arr)) and float(np.min(np.abs(arr - t))) <= tol

    step_ok = float(np.mean([near(agent, t, 0.06) for t in steps]))
    stem_only = float(np.mean([near(stem_kick, t, 0.06) and not near(agent, t, 0.06) for t in steps]))
    drum_hp = [h["t"] for h in hp if "drum" in h.get("kinds", [])]
    bad = [round(t, 2) for t in drum_hp if not near(agent, t, 0.03) and not near(snare, t, 0.03)]
    assert step_ok >= 0.9 and stem_only <= 0.05 and not bad, (
        f"{slug} kick_source=mix: {len(agent)} agent kicks; {step_ok:.2f} of the {len(steps)} groove kick steps on an agent "
        f"kick (60 ms), {stem_only:.2f} only on a rejected stem kick; 'drum' hit points with neither an agent kick nor a "
        f"stem snare >= 0.5 within 30 ms: {bad} (of {len(drum_hp)})")
