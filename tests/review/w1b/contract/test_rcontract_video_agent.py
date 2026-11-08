"""R-CONTRACT (W1b) failing tests: the video-agent lens (PLAN §11).

Each test is the evidence for one blocker/major finding in docs/review/w1b-r-contract.md. They read the
synthetic fixture (tests/contract/synth, read-only) or a walking-skeleton run of it in pytest tmp_path,
exactly as a Remotion / three.js / Blender agent would: through manifest.json, lyrics/lines.tsv,
events/*.json and the copied lib/ loaders. No lyric text is printed: assertions report ids, times, counts.
JS twin: rcontract_video_agent.test.mjs (node --test).
"""

from __future__ import annotations

import csv
import importlib.util
import json
import re
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
SYNTH = REPO / "tests" / "contract" / "synth"
SONG_FLAC = SYNTH / "_truth" / "synth-song.flac"
ASSETS = REPO / "src" / "mvh" / "assets"
CONTRACT_MD = REPO / "docs" / "CONTRACT.md"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mvh_load():
    """The Python loader exactly as it is copied into every song folder (lib/mvh_load.py)."""
    return _load_module(ASSETS / "mvh_load.py", "rcontract_mvh_load")


@pytest.fixture(scope="module")
def song(mvh_load):
    return mvh_load.load(SYNTH)


@pytest.fixture(scope="module")
def skeleton_dir(tmp_path_factory) -> Path:
    """`mvh analyze` (walking skeleton: real ingest + every stub) of the synthetic song into tmp_path."""
    from mvh.runner import run as rr

    song_dir = tmp_path_factory.mktemp("rcontract") / "synth"
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("MVH_HEAVY_LOCKS", "0")
        mp.delenv("MVH_FIXTURE_DIR", raising=False)
        settings = rr.Settings(
            song=SONG_FLAC,
            song_dir=song_dir,
            slug="synth",
            progress=lambda m: None,
            heavy_locks=False,
            offline=True,
        )
        res = rr.analyze(settings)
    assert res["failed"] == [] and res["pending"] == [], res
    return song_dir


# ===================================================================== F1 cues: next() hides co-timed cues
def test_f1_cue_next_iteration_reaches_every_tier1_cue(song):
    """CONTRACT §9 gives `events('cues').next(t, {minTier})` as THE cue lookup. Stepping through the cue
    list with it (t = cue.t each time, the only way to advance) must reach every tier-1 cue. Today next()
    is 'first item strictly after t', so a cue sharing its time with an earlier-returned cue is never
    returned: the build start (25.0 s) and the drop (34.5 s, moment rank 1) sit under section cues."""
    cues = song.events("cues")
    want = [c["id"] for c in cues.items if c["tier"] == 1]
    got, t = [], -1.0
    while (c := cues.next(t, min_tier=1)) is not None:
        got.append(c["id"])
        t = float(c["t"])
    missing = sorted(set(want) - set(got))
    kinds = {c["id"]: (c["t"], c["kind"]) for c in cues.items if c["id"] in missing}
    assert not missing, f"tier-1 cues unreachable by next()-iteration: {kinds}"


def test_f1_moment_rank1_cue_reachable_by_next(song):
    """The rank-1 moment (the drop) must be found when an agent asks for the next major cue before it."""
    cues = song.events("cues")
    m1 = min(song.events("moments").items, key=lambda m: m["rank"])
    cue = cues.by_id(m1["cue_id"])
    seen = []
    nxt = cues.next(float(cue["t"]) - 0.5, min_tier=1)
    while nxt is not None and abs(float(nxt["t"]) - float(cue["t"])) < 1e-9:
        seen.append(nxt["id"])
        nxt = cues.next(float(nxt["t"]), min_tier=1)
    first_kind = cues.by_id(seen[0])["kind"] if seen else None
    assert cue["id"] in seen, (
        f"next(t, minTier=1) before the rank-1 moment returns {seen} ({first_kind}), "
        f"never {cue['id']} ({cue['kind']})"
    )


# ===================================================================== F2 lines.tsv drops duet singers
def test_f2_lines_tsv_singer_lists_every_character_singing_the_line():
    """lines.tsv is THE context-safe file a video agent reads for words and singers (PLAN §10). On duet
    lines events/singing.json has two characters (lead C1 + backing C2) but the `singer` column holds only
    the lead, so an agent planning character shots from lines.tsv never sees C2 in either chorus."""
    sing = json.loads((SYNTH / "events" / "singing.json").read_text(encoding="utf-8"))["items"]
    by_line: dict[str, set[str]] = {}
    for s in sing:
        by_line.setdefault(s["line_id"], set()).add(s["character_id"])
    with open(SYNTH / "lyrics" / "lines.tsv", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    bad = {}
    for r in rows:
        tsv = {x for x in re.split(r"[+,; |/]+", r["singer"] or "") if x}
        if tsv != by_line.get(r["id"], set()):
            bad[r["id"]] = (sorted(tsv), sorted(by_line.get(r["id"], set())))
    assert not bad, f"lines.tsv singer != singing.json characters (line: (tsv, singing)): {bad}"


# ===================================================================== F3 one file, two producers
def test_f3_notes_stage_does_not_claim_the_vocals_stage_outputs():
    """D6: events/notes.vocals.json and notes/vocals.mid are produced by `vocals`. The notes stage's
    declared patterns `events/notes.{src}.json` and `notes/{src}.mid` also match them (PITCHED_SOURCES
    includes 'vocals'), so both stages may write and publish the same path."""
    from mvh.runner.ctx import match_output
    from mvh.runner.spec import load_stage_specs

    specs = load_stage_specs()
    claims = {}
    for rel in ("events/notes.vocals.json", "notes/vocals.mid"):
        claims[rel] = sorted(n for n, s in specs.items() if match_output(s, rel) is not None)
    assert all(v == ["vocals"] for v in claims.values()), f"declared producers per path: {claims}"


def test_f3_manifest_lists_each_published_file_once(skeleton_dir):
    """manifest.files is the agent's file index. In the walking-skeleton output the same path appears twice
    with different producing stages; a later notes publish that no longer writes it would unlink the
    vocals stage's file (runner publish removes paths a stage published before and no longer produces)."""
    man = json.loads((skeleton_dir / "manifest.json").read_text(encoding="utf-8"))
    cnt = Counter(f["path"] for f in man["files"])
    dup = {
        p: sorted(f["stage"] for f in man["files"] if f["path"] == p) for p, k in cnt.items() if k > 1
    }
    assert not dup, f"paths listed more than once in manifest.files (path: stages): {dup}"


# ===================================================================== F4 vizState default 60 fps
def test_f4_vizstate_documented_call_never_drops_onsets_at_30fps(song, mvh_load):
    """CONTRACT §9 documents `song.vizState(t)` / `viz_state(t)` with t only. The loaders silently pool at
    60 fps, so a 30 fps renderer (Remotion's default) calling it as documented at each frame time sees
    `onset` false for about a quarter of the bass onsets. Acceptable fixes: require the frame rule (raise
    without it) or make the documented call frame-rate safe."""
    fr = {"fps": 30}
    try:
        song.viz_state(1.0)
    except (TypeError, ValueError) as e:  # a mandatory frame rule is a valid fix
        assert "fr" in str(e) or "frame" in str(e) or "fps" in str(e)
        return
    n_frames = song.frame_count(fr)
    items = song.events("onsets.bass").items
    want = {mvh_load.frame_of(float(it["t"]), fr) for it in items}
    seen = {n for n in range(n_frames) if song.viz_state(mvh_load.time_of(n, fr))["onset"]}
    lost = sorted(want - seen)
    assert not lost, (
        f"{len(lost)} of {len(want)} bass-onset frames at 30 fps never report onset=True "
        f"(first: {lost[:5]})"
    )


def test_f4_contract_documents_the_vizstate_frame_rule():
    """The CONTRACT §9 helper table must show vizState's frame-rule argument and its default, like every
    other frame helper; today the row reads `song.vizState(t)` with Args `t`."""
    lines = CONTRACT_MD.read_text(encoding="utf-8").splitlines()
    row = next(ln for ln in lines if ln.startswith("| `song.vizState("))
    assert "fr" in row.split("|")[1] or "fps" in row, f"CONTRACT §9 vizState row has no frame rule: {row}"


# ===================================================================== F5 overlapping segments
def test_f5_all_overlapping_segments_are_queryable(song):
    """CONTRACT §9: 'Notes, visemes and sections need no helpers of their own: use
    events('notes.bass').at(t), events('visemes').at(t)'. at(t) returns ONE item (latest start), so in a
    duet the lead character's viseme is hidden by the backing voice's, and only one note of a chord is
    returned. A video agent needs every segment containing t (`all_at(t)` / `allAt(t)`)."""
    vis = song.events("visemes")
    assert hasattr(vis, "all_at"), "Events has no all_at(t): duet visemes and chords are unreachable"
    t = 17.3  # chorus duet: V1 (C1, lead) and V2 (C2, backing) sing L005 together
    voices = sorted({it["voice_id"] for it in vis.all_at(t)})
    assert voices == ["V1", "V2"], voices
    chord = song.events("notes.other").all_at(1.0)
    assert len(chord) == 3, [it["midi"] for it in chord]


def test_f5_documented_viseme_recipe_returns_lead_voice_in_duet(song):
    """Without an all-at query, the one item events('visemes').at(t) returns must at least be the lead
    singer's (singerAt orders lead first). Today it is the backing voice V2 on every duet frame."""
    if hasattr(song.events("visemes"), "all_at"):
        pytest.skip("all_at exists: duets are covered by test_f5_all_overlapping_segments_are_queryable")
    t = 17.3
    lead = song.singer_at(t)[0]["voice_id"]
    got = song.events("visemes").at(t)["item"]["voice_id"]
    assert got == lead, f"events('visemes').at({t}) gives voice {got}; the lead singer is {lead}"
