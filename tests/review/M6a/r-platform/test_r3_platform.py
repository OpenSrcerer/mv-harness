# ruff: noqa: E501  (long lines)
"""R-PLATFORM review of M6a, ROUND 3 (r-platform-m6a-r3): findings left after the round-2 fixes.

Each test is the evidence of one finding in docs/build/reports/r-platform-m6a-r3.md and FAILS until the viewer is fixed.
"""

from __future__ import annotations

import json

import pytest
from rp_support import drive, find_browser, find_node


@pytest.mark.usefixtures("browser_ok")
def test_a_failed_undo_keeps_the_state_it_was_restoring(served, tmp_path):
    """F-R3-UNDO-FAIL: when an Undo's POST fails (503 is what mvh view answers when overrides.json is read-only or
    locked by another program on Windows), save(..., isUndo=true) pushes the CURRENT document back onto the history
    instead of the entry undo() popped. The state Undo was restoring is lost: the next Undo "restores" the state that is
    already on disk (nothing changes, but the toast says 'Saved: undo') and the Undo after that skips a step.
    Edits 10, 20, 30 ms; Undo fails; then Undo, Undo must give 20 ms and 10 ms on disk."""
    assert find_node() and find_browser()
    res = drive(served.url, "undo-fail", tmp_path / "prof")
    assert res["state"] == "ready", res
    steps = res["steps"]
    assert all(s["clicked"] for s in steps), f"a button was not found / was disabled: {json.dumps(steps)}"
    assert [s["disk"] for s in steps[:3]] == [0.01, 0.02, 0.03], f"the +10 ms edits did not save as expected: {json.dumps(steps)}"
    failed = steps[3]
    assert failed["failedPosts"] == 1 and failed["disk"] == 0.03 and failed["shown"] == 0.03, f"the failing Undo was not simulated as intended: {failed}"
    after = [s["disk"] for s in steps[4:]]
    assert after == [0.02, 0.01], f"after a failed Undo, Undo, Undo gave {after} on disk (expected [0.02, 0.01]): the entry the failed Undo popped was replaced by the current state"
