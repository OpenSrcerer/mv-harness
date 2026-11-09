"""W4 verify-words r2, VWR2-4 (major, foreign cause): the skill's generated CONTRACT copy is stale.

docs/CONTRACT.md was edited for W4VP-1 (platform fixer, 19:46) and skill/mv-harness/references/CONTRACT.md was not
regenerated, so the M6b unit test tests/unit/brief/test_skill.py::test_contract_copy_is_current fails and the M6b gate
unit step fails. Fix: python skill/mv-harness/scripts/sync_contract.py (stdlib, no other change).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_vwr2_4_skill_contract_copy_is_current():
    r = subprocess.run([sys.executable, str(ROOT / "skill" / "mv-harness" / "scripts" / "sync_contract.py"), "--check"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, ("skill/mv-harness/references/CONTRACT.md is stale against docs/CONTRACT.md: "
                               "run python skill/mv-harness/scripts/sync_contract.py")
