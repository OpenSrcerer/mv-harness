"""W4 R-DOGFOOD: what a video agent hits when it follows skill/mv-harness/ only (static checks on the shipped docs).

Findings: W4D-2 (RECIPES.md contradicts UD2), W4D-3 (no cover-art palette fallback while meaning is pending),
W4D-4 (no word on what to copy / how to serve the folder for a browser page).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SKILL = ROOT / "skill" / "mv-harness"


def _text(name: str) -> str:
    with open(SKILL / name, encoding="utf-8") as fh:
        return fh.read()


def test_recipes_cut_on_song_kicks_not_the_raw_stem_curve():
    """W4D-2 (M6a, major): SKILL.md section 5 says cut on song.kicks() only; RECIPES.md, the page an agent copies code
    from, never mentions kicks() and shows `song.curve('drums.kick')` (the ungated stem curve; on MEGAFAUNA the kick stem
    is hat bleed, which is why UD2 gates it) as THE kick for choreography."""
    rec = _text("references/RECIPES.md")
    assert re.search(r"song\.kicks\(\)|pulse\('kick'", rec), "RECIPES.md never shows song.kicks() / pulse('kick', t)"
    assert "song.curve('drums.kick')" not in rec, "RECIPES.md still teaches the ungated drums.kick stem curve as the kick"


def test_palette_recipe_falls_back_to_the_cover_art_palette_when_meaning_is_pending():
    """W4D-3 (M6a, major): every new song starts `meaning: pending`: meaningAt().palette_hint = [] and
    meaning.palette = [] on all four real songs. The only palette that exists is the cover art's
    (manifest.summary.palette / meta/source.json), which brief.md prints. The palette recipe's fallback chain stops at
    meaning.palette, so a section-driven look has no colour at all until the user authors one."""
    rec = _text("references/RECIPES.md") + _text("SKILL.md")
    assert re.search(r"summary\.palette|source\.json[^\n]{0,80}palette|cover[- ]art palette", rec, re.I), (
        "no doc tells an agent to fall back to the cover-art palette (manifest.summary.palette) while meaning is pending"
    )


def test_docs_say_how_to_serve_and_what_to_copy_for_a_browser_page():
    """W4D-4 (M6a, major): a newly analysed folder is ~1.1 GB (stems 635 MB, .cache 395 MB, viewer.html 8 MB); a browser
    page needs ~7 MB of it plus audio/mix.flac. load('out/<slug>/') fails from file://, and `python -m http.server`
    has no Range support, so audio.currentTime = 84 silently stays at 0. Neither the SKILL nor RECIPES says any of it
    (the Remotion recipe says 'copy the song folder to public/song/')."""
    doc = _text("references/RECIPES.md") + _text("SKILL.md")
    assert re.search(r"\bRange\b", doc), "no mention that the static server must support HTTP Range (audio seek)"
    assert re.search(r"file://", doc) and re.search(r"stems/", doc), (
        "no mention that file:// cannot load() and which sub-folders (stems/, .cache) not to ship"
    )
