"""skill/mv-harness: the generated CONTRACT copy is current, SKILL.md stays small, and every helper, events name and
curve channel the skill and recipes mention exists (so a video agent never calls something that is not there)."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from mvh.contract import catalog, registry

ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / "skill" / "mv-harness"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_contract_copy_is_current():
    r = subprocess.run([sys.executable, str(SKILL / "scripts" / "sync_contract.py"), "--check"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr


def test_skill_frontmatter_and_size():
    text = _read(SKILL / "SKILL.md")
    m = re.match(r"^---\nname: mv-harness\ndescription: (.+?)\n---\n", text, re.S)
    assert m and len(m.group(1)) < 1024
    assert len(text) / 4 <= 2000  # the skill itself must be cheap to load
    for must in ("brief.md", "interview.md", "authored.json", "lines.tsv", "Never cat", "audio/mix.flac",
                 "frame0", "RECIPES.md", "§2", "§9", "do_not"):
        assert must in text, must


def _js_members() -> set[str]:
    js = _read(ROOT / "src" / "mvh" / "assets" / "mvh.js")
    names = set(re.findall(r"^export (?:async )?function (\w+)", js, re.M))
    names |= set(re.findall(r"^  (?:async )?(\w+)\(", js, re.M))
    return names


def _py_members() -> set[str]:
    py = _read(ROOT / "src" / "mvh" / "assets" / "mvh_load.py")
    return set(re.findall(r"^\s*def (\w+)\(", py, re.M))


def test_recipes_only_use_real_helpers():
    text = _read(SKILL / "SKILL.md") + _read(SKILL / "references" / "RECIPES.md")
    js, py = _js_members(), _py_members()
    called = set(re.findall(r"song\.(\w+)\(", text)) | set(re.findall(r"\.(next|prev|at|allAt|between|inFrame|frame)\(", text))
    missing = [n for n in called if n not in js and n not in py]
    assert not missing, missing
    for n in re.findall(r"mvh\.(\w+)\(", text):
        assert n in py, n
    imported = re.findall(r"import \{([^}]+)\} from '[^']*mvh\.js'", text)
    for grp in imported:
        for n in (x.strip() for x in grp.split(",")):
            assert n in js, n


def test_recipes_name_real_events_and_channels():
    text = _read(SKILL / "SKILL.md") + _read(SKILL / "references" / "RECIPES.md")
    for name in set(re.findall(r"events\('([\w.]+)'\)", text)) | set(re.findall(r"pulse\('([\w.]+)'", text)):
        catalog.event_def(name)  # raises KeyError for an unknown events name
    for cid in set(re.findall(r"curve\('([\w.]+)'\)", text)) | set(re.findall(r'curve\("([\w.]+)"\)', text)):
        assert registry.match_channel(cid) is not None, cid
