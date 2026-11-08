"""R-PLATFORM (W1b) finding: every title written in a non-Latin script maps to the same song folder
``out/song/``, and the second song silently inherits the first song's user inputs.

``ids.slugify`` keeps only the ASCII residue of NFKD (``"曲" -> ""``; Cyrillic, Greek, CJK, Arabic titles
too) and falls back to the constant ``"song"``. ``mvh analyze <file>`` then reuses ``out/song/`` for a
DIFFERENT input without a word: the previous song's ``overrides.json`` (e.g. ``rhythm.bpm``) and
``meaning/intent.md`` are user inputs the runner never deletes, so they are applied to the new song and enter
its cache keys and provenance;
the previous song's results are replaced. PLAN §7.4 makes ``tëst ♪ 曲.flac`` the Unicode acceptance case.

Expected: distinct inputs get distinct folders by default (e.g. a short hash suffix when the slug degenerates
or collides), or ``mvh analyze`` refuses to reuse a folder whose recorded input is another file.
"""

from __future__ import annotations

import json

import pytest

from mvh import cli, testing


@pytest.fixture
def fx(monkeypatch, skeleton, no_heavy_locks):
    monkeypatch.setenv("MVH_FIXTURE_DIR", str(skeleton))
    return skeleton


def test_two_non_latin_titles_do_not_share_a_song_folder(tmp_path, tone48, fx, monkeypatch, capsys):
    monkeypatch.setenv("MVH_OUT", str(tmp_path / "out"))
    a = testing.tone(tmp_path / "in" / "曲.flac", seconds=3.0, sr=48000, freq=440.0)
    b = testing.tone(tmp_path / "in" / "песня.flac", seconds=3.0, sr=48000, freq=660.0)

    assert cli.main(["analyze", str(a)]) == 0
    folder_a = json.loads(capsys.readouterr().out.strip().splitlines()[-1])["manifest"]
    song_a = tmp_path / "out" / json.loads(open(folder_a, encoding="utf-8").read())["slug"]
    (song_a / "overrides.json").write_text(json.dumps({"rhythm": {"bpm": 99.0}}), encoding="utf-8")

    rc = cli.main(["analyze", str(b)])
    out = capsys.readouterr().out.strip().splitlines()
    folder_b = json.loads(out[-1])["manifest"] if rc == 0 and out else None
    assert folder_b != folder_a, (
        f"'{b.name}' was analysed into the folder of '{a.name}' ({folder_a}); it inherited that song's "
        "overrides.json (rhythm.bpm=99) and replaced its results"
    )
