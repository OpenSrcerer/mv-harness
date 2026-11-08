"""R-PLATFORM (W1b) finding: ``mvh status`` does not predict what ``mvh analyze`` will re-run when MVH_THREADS
changed.

NF2 puts the fixed thread count in every stage key, and ``mvh analyze`` takes it from ``--threads`` /
``MVH_THREADS``. ``mvh status`` instead replays the thread count recorded by the LAST run
(``.cache/_run.json``), so after ``MVH_THREADS`` changes (another shell, the gate's ``-Threads``, a heavy-slot
helper that exports 6) status reports every stage ``done / cached`` while the next ``mvh analyze`` silently
re-runs all of them (with real models: hours of separation). D36 says status must report ``stale`` with the
changed inputs named (``threads changed``).
"""

from __future__ import annotations

import json

import pytest

from mvh import cli


@pytest.fixture
def fx(monkeypatch, skeleton, no_heavy_locks):
    monkeypatch.setenv("MVH_FIXTURE_DIR", str(skeleton))
    return skeleton


def test_status_agrees_with_analyze_after_mvh_threads_changes(tmp_path, tone48, fx, monkeypatch, capsys):
    song_dir = tmp_path / "song dir"
    monkeypatch.setenv("MVH_THREADS", "3")
    assert cli.main(["analyze", str(tone48), "--out", str(song_dir)]) == 0
    capsys.readouterr()

    monkeypatch.setenv("MVH_THREADS", "4")  # e.g. a different shell
    assert cli.main(["status", str(song_dir), "--json"]) == 0
    rows = {r["stage"]: r for r in json.loads(capsys.readouterr().out)}

    assert cli.main(["analyze", str(song_dir)]) == 0  # re-run the folder, as D35 documents
    capsys.readouterr()
    run = json.loads((song_dir / "run.json").read_text(encoding="utf-8"))
    rerun = sorted(n for n, s in run["stages"].items() if s.get("cache") in ("miss", "forced"))
    claimed_done = sorted(n for n in rerun if rows[n]["status"] == "done")
    assert claimed_done == [], (
        f"mvh status said 'done' for {len(claimed_done)} stages that the next mvh analyze re-ran "
        f"(e.g. {claimed_done[:4]}); status reason for ingest: {rows['ingest']['reason']!r}"
    )
