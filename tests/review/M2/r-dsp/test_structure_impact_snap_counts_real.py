"""R-DSP M2 round 4, finding F7-r4 (major, real song, opt-in -m real): the S05 fix (structure ``impact_snap_strength``)
moves Jeremy's verse#1 start one bar back onto the band-entry impact (19.47 s, bar 9), but the phrases still start at the
section start and put the remainder at the END. The 9-bar verse#1 is phrased 8 + 1 bars (P 19.47 s, then a 1-bar phrase
at 37.86 s), so the choreo eight-counts of the whole first verse shift by one bar (4 counts) against the song's phrase
grid:

* without the snap (and in every other section of the song: 40.13, 58.4, 76.4, 94.7 ... s are all 8 or 4 bars from
  21.80 s) the eight-counts start at 21.80 / 26.37 / 30.96 / 35.56 s, the vocal entry is count 1;
* with the snap they start at 19.47 / 24.10 / 28.68 / 33.26 s, the vocal entry falls on count 5, and a 4-beat partial
  eight-count (37.86 s) dangles right before the first chorus.

The band-entry bar is a one-bar pickup into the verse: the section may start there (that is S05), but the eight-count /
phrase grid must stay where the music phrases (a 1-bar partial at the section START, then 8-bar phrases), so a dancer's
"1" does not move when a section boundary is snapped to an impact. The snap fires on Jeremy only (none of the other
three real songs or the synthetic song changes with ``impact_snap_strength`` 0), so this is the one case it was built for.

Upstream: the integrator's real runner caches (out/_wip/integrator/jeremy/.cache, W3 real upstream). No inference."""
import json
import shutil

import pytest
from tests.synth.m2 import ctx as M2
from tests.synth.m2.testing import REPO, events

SLUG = "jeremy"
INTEG = REPO / "out" / "_wip" / "integrator" / SLUG
pytestmark = pytest.mark.real


def _cache_dir(stage):
    c = INTEG / ".cache" / stage
    with open(c / "latest.json", encoding="utf-8") as fh:
        return c / json.load(fh)["key"]


class _RealCtx(M2.FixtureCtx):
    """Upstream from the integrator's runner cache, our own re-run stages through overlays."""

    def _upstream(self, stage):
        from mvh.runner.ctx import CacheUpstream

        if stage not in self._ups:
            ov = self.overlays.get(stage)
            if ov is not None and (ov / M2.RECORD).is_file():
                with open(ov / M2.RECORD, encoding="utf-8") as fh:
                    self._ups[stage] = CacheUpstream(stage, ov, json.load(fh))
            else:
                self._ups[stage] = CacheUpstream(stage, _cache_dir(stage))
        return self._ups[stage]


def _run(root, snap):
    import importlib

    out = {}
    for st in ("structure", "choreo"):
        params = {"impact_snap_strength": snap} if st == "structure" else None
        ctx = _RealCtx(st, INTEG, root / st, overlays=dict(out), slug=SLUG, threads=6, params=params)
        res = importlib.import_module(f"mvh.stages.{st}").run(ctx)
        ctx.save_record(res)
        shutil.rmtree(ctx.scratch, ignore_errors=True)
        out[st] = root / st
    return events(root / "structure", "sections"), [c for c in events(root / "choreo", "counts") if not c["lead_in"]]


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    if not (INTEG / ".cache" / "structure" / "latest.json").is_file():
        pytest.skip("no integrator run for jeremy (out/_wip/integrator/jeremy)")
    root = tmp_path_factory.mktemp("jeremy_snap")
    return {"snap": _run(root / "snap", 0.6), "nosnap": _run(root / "nosnap", 0.0)}


def _section_at(secs, t):
    return next(s for s in secs if s["t"] - 0.05 <= t < s["t"] + s["d"] - 0.05)


def test_precondition_the_snap_moves_verse1_onto_the_band_entry(runs):
    snap = [round(s["t"], 2) for s in runs["snap"][0]]
    nosnap = [round(s["t"], 2) for s in runs["nosnap"][0]]
    assert any(abs(t - 19.47) < 0.1 for t in snap), snap[:4]
    assert any(abs(t - 21.80) < 0.1 for t in nosnap), nosnap[:4]


def test_snapping_a_section_start_keeps_the_eight_count_grid(runs):
    """Eight-count starts inside the original section (21.80 s up to the next section) must not move with the snap."""
    secs_n, counts_n = runs["nosnap"]
    _, counts_s = runs["snap"]
    s = _section_at(secs_n, 21.85)
    t0, t1 = s["t"], s["t"] + s["d"]
    want = [round(c["t"], 2) for c in counts_n if t0 - 0.05 <= c["t"] < t1 - 0.05]
    got = [round(c["t"], 2) for c in counts_s if t0 - 0.05 <= c["t"] < t1 - 0.05]
    assert got == want, f"eight-count starts in {t0:.2f}-{t1:.2f} s: snap {got} vs no snap {want}"


def test_no_dangling_partial_eight_count_before_the_first_chorus(runs):
    secs, counts = runs["snap"]
    s = _section_at(secs, 21.85)
    end = s["t"] + s["d"]
    last = [c for c in counts if c["section_id"] == s["id"] and abs(c["t"] + c["d"] - end) < 0.05]
    assert last and not last[0]["partial"], (
        f"the section {s['id']} ({s['t']:.2f} s, {s['n_bars']} bars) ends with a partial eight-count "
        f"{last[0]['id'] if last else None} of {last[0]['len'] if last else None} beats at {last[0]['t'] if last else 0:.2f} s")
