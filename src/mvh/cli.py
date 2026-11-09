"""The ``mvh`` command line (PLAN §10, CONTRACT D35).

    mvh analyze <song> [--out DIR] [--slug S] [--profile max|draft] [--only a,b] [--force [a,b]] [--from S]
                [--no-network] [--threads N] [--cores N] [--lyrics FILE] [--param stage.key=JSON]
                [--no-heavy-locks]
    mvh status <song-folder> [--json]
    mvh validate <song-folder> [--json]
    mvh pack <song-folder> <dest> [--with-stems] [--with-viewer] [--force]
    mvh doctor [--quick] [--no-rocm] [--json]
    mvh models fetch|verify|list [--only id,id] [--env main|sep|ffmpeg] [--json]

``analyze`` prints progress on stderr and ONE JSON line on stdout: {manifest, brief, viewer, warnings,
pending}.
Module verbs (view, brief, frames, meaning, ...) are discovered from optional
``src/mvh/stages/<name>/cli.py`` files
that define ``register(subparsers)``; each parser they add sets ``func=callable(args) -> int``.
stdout/stderr are reconfigured to UTF-8, so the CLI works with PYTHONUTF8 and PYTHONIOENCODING removed.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import pkgutil
import sys
from pathlib import Path
from typing import Any

__all__ = ["main", "build_parser", "discover_stage_verbs", "CORE_VERBS"]

CORE_VERBS = ("analyze", "status", "validate", "pack", "doctor", "models")


def _utf8_stdio() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


def _err(msg: str) -> None:
    print(f"mvh: {msg}", file=sys.stderr, flush=True)


def _csv(s: str | None) -> tuple[str, ...] | None:
    if s is None:
        return None
    return tuple(x.strip() for x in s.split(",") if x.strip())


def _default_out_root() -> Path:
    env = os.environ.get("MVH_OUT")
    if env:
        return Path(env)
    from mvh.io.paths import repo_root

    return repo_root() / "out"


# ============================================================================================ analyze
def _parse_params(items: list[str] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for it in items or []:
        k, sep, v = it.partition("=")
        stage, dot, name = k.partition(".")
        if not sep or not dot:
            raise ValueError(f"--param expects stage.key=value, got {it!r}")
        try:
            val = json.loads(v)
        except ValueError:
            val = v
        out.setdefault(stage, {})[name] = val
    return out


def _unique_slug(slug: str, song: Path) -> str:
    """A default song folder must belong to one input. Titles with no ASCII letters (CJK, Cyrillic, ...) all
    slugify to the fallback 'song', and two files can share a name; the folder of another input (recorded in
    .cache/_run.json) is never reused: a short hash of the input path is appended instead."""
    import hashlib

    from mvh.runner import run as rr

    me = str(song.resolve())
    suffix = "-" + hashlib.sha256(me.lower().encode("utf-8")).hexdigest()[:6]
    import re
    import unicodedata

    ascii_stem = unicodedata.normalize("NFKD", song.stem).encode("ascii", "ignore").decode("ascii")
    if not re.search(r"[A-Za-z0-9]", ascii_stem):  # slugify fell back to the constant
        return slug[: 40 - len(suffix)] + suffix
    prev = rr.load_run_settings(_default_out_root() / slug).get("params_ext", {}).get("input")
    if prev and os.path.normcase(prev) != os.path.normcase(me):
        return slug[: 40 - len(suffix)] + suffix
    return slug


def _install_intent(src: Path, song_dir: Path) -> int:
    """``--intent f``: copy the user's file to ``<song>/meaning/intent.md``.

    CONTRACT §1: analyze never overwrites the user's intent.md, so an existing different file is an error."""
    from mvh.io import atomic

    if not src.is_file():
        _err(f"no such intent file: {src}")
        return 2
    data = src.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        _err(f"{src.name} is not UTF-8 text")
        return 2
    dst = song_dir / "meaning" / "intent.md"
    if dst.is_file():
        if dst.read_bytes() == data:
            return 0
        _err(f"{dst} exists and differs from {src.name}; edit it in place (or remove it) "
             "instead of passing --intent")
        return 2
    dst.parent.mkdir(parents=True, exist_ok=True)
    atomic.write_text(dst, text)
    return 0


def cmd_analyze(a: argparse.Namespace) -> int:
    from mvh.contract.ids import SLUG_RE, slugify
    from mvh.runner import run as rr

    song = Path(a.song)
    if song.is_dir():
        song_dir, song_file = song, None
        prev = rr.load_run_settings(song_dir)
        if not prev.get("params_ext", {}).get("input"):
            _err(f"{song} is a folder without a recorded input; pass the song file")
            return 2
        slug = a.slug or prev.get("slug") or song_dir.name
    else:
        if not song.is_file():
            _err(f"no such file: {song}")
            return 2
        song_file = song
        # W4P-1: relinking a moved or renamed song to its folder (--out) keeps the folder's slug
        kept = rr.load_run_settings(Path(a.out)).get("slug") if a.out and not a.slug else None
        slug = a.slug or kept or slugify(song.stem)
        if not a.slug and not a.out:
            slug = _unique_slug(slug, song)
        song_dir = Path(a.out) if a.out else _default_out_root() / slug
    if not SLUG_RE.match(slug):
        _err(f"bad slug {slug!r} (lower-case letters, digits, '-')")
        return 2
    # D52 (W3, M6b CR-2): a re-run keeps the earlier run's --lyrics file and --param values;
    # new ones win per key.
    prev_run = rr.load_run_settings(song_dir)
    params_ext: dict[str, str] = {
        k: v for k, v in (prev_run.get("params_ext") or {}).items() if k != "input" and isinstance(v, str)
    }
    if a.lyrics:
        if a.lyrics == "-":
            params_ext.pop("lyrics", None)
        else:
            params_ext["lyrics"] = str(Path(a.lyrics).resolve())
    force: tuple[str, ...] | bool = False
    if a.force is not None:
        force = True if a.force == "all" else (_csv(a.force) or True)
    try:
        new_params = _parse_params(a.param)
    except ValueError as e:
        _err(str(e))
        return 2
    cli_params: dict[str, dict[str, Any]] = {
        k: dict(v) for k, v in (prev_run.get("cli_params") or {}).items() if isinstance(v, dict)
    }
    if a.meaning_draft:
        cli_params.setdefault("meaning", {})["draft"] = a.meaning_draft
    if a.no_lyrics_to_agents:
        cli_params.setdefault("meaning", {})["lyrics_to_agents"] = False
        cli_params.setdefault("viewer", {})["inline_lyrics"] = False
    for stage, kv in new_params.items():
        cli_params.setdefault(stage, {}).update(kv)
    if a.intent:
        rc = _install_intent(Path(a.intent), song_dir)
        if rc:
            return rc
    heavy = not a.no_heavy_locks and os.environ.get("MVH_HEAVY_LOCKS", "1") != "0"
    s = rr.Settings(
        song=song_file,
        song_dir=song_dir.resolve(),
        slug=slug,
        profile=a.profile,
        threads=a.threads or rr._env_threads(),
        cores=a.cores,
        only=_csv(a.only),
        force=force,
        from_stage=a.from_stage,
        offline=a.no_network or os.environ.get("MVH_OFFLINE") == "1",
        heavy_locks=heavy,
        params_ext=params_ext,
        cli_params=cli_params,
    )
    from mvh.runner import locks

    try:
        res = rr.analyze(s)
    except ValueError as e:
        _err(str(e))
        return 2
    except locks.SongBusy as e:  # W4P-2: MVH_SONG_LOCK_TIMEOUT expired while another run held the folder
        _err(str(e))
        return 75
    if a.meaning_draft == "anthropic" and not res["failed"]:
        # PLAN §8: the API drafts the gaps into meaning/authored.json, then meaning/brief/viewer re-merge it
        from mvh.stages.meaning.cli import cmd_meaning

        rc = cmd_meaning(argparse.Namespace(folder=str(song_dir), draft="anthropic", overwrite_draft=False,
                                            no_lyrics_to_agents=a.no_lyrics_to_agents, threads=a.threads))
        if rc:
            res["warnings"] = list(res["warnings"]) + [
                f"--meaning-draft anthropic did not complete (exit {rc})"
            ]
    line = {
        "manifest": res["manifest"],
        "brief": res["brief"],
        "viewer": res["viewer"],
        "warnings": res["warnings"],
        "pending": res["pending"],
    }
    print(json.dumps(line, ensure_ascii=False), flush=True)
    return 1 if res["failed"] or not res["valid"] else 0


# ============================================================================================ status
def cmd_status(a: argparse.Namespace) -> int:
    from mvh.runner import run as rr

    folder = Path(a.folder)
    if not (folder / ".cache").is_dir():
        _err(f"{folder} has no .cache (not a song folder made by mvh analyze)")
        return 2
    states = rr.status(folder, threads=a.threads)  # MVH_THREADS unless --threads: what analyze would use
    rows = [
        {"stage": n, "status": st.status, "reason": st.reason, "key": st.key or st.pre_key}
        for n, st in states.items()
    ]
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    else:
        w = max(len(r["stage"]) for r in rows)
        for r in rows:
            print(f"{r['stage']:<{w}}  {r['status']:<8}  {(r['key'] or '')[:12]:<12}  {r['reason']}")
    return 0


# ============================================================================================ validate
def cmd_validate(a: argparse.Namespace) -> int:
    from mvh.runner.validate import validate_folder

    rep = validate_folder(Path(a.folder))
    if a.json:
        print(
            json.dumps(
                {"ok": rep.ok, "errors": rep.errors, "warnings": rep.warnings, "checked": rep.checked},
                ensure_ascii=False,
                indent=1,
            )
        )
    else:
        for e in rep.errors:
            print(f"ERROR {e}")
        for w in rep.warnings:
            print(f"WARN  {w}")
        print(
            f"{'valid' if rep.ok else 'INVALID'}: {rep.checked} files checked, {len(rep.errors)} errors, "
            f"{len(rep.warnings)} warnings"
        )
    return 0 if rep.ok else 1


# ============================================================================================ pack
#: top-level entries of a song folder a web page never needs (W4D-4): the stage cache and the stems are most
#: of the ~1-2.5 GB; viewer.html inlines all the data again
PACK_SKIP = (".cache", "stems", "viewer.html")


def pack_folder(
    folder: Path, dest: Path, *, with_stems: bool = False, with_viewer: bool = False
) -> dict[str, Any]:
    """Copy the parts of a song folder a page or a video project loads into ``dest`` (W4D-4): manifest.json,
    brief.md, lib/, curves/, events/, meta/, lyrics/, meaning/, lipsync/, notes/, tables/, artwork/, frames/,
    schema/ and audio/ (mix.flac, preview.opus). Never .cache/ or hidden files; stems/ and viewer.html only on
    request. The manifest still lists the stems, so mvh.js fails only when a page asks for one."""
    import shutil

    skip = set(PACK_SKIP) - ({"stems"} if with_stems else set()) - ({"viewer.html"} if with_viewer else set())
    n = size = 0
    for p in sorted(folder.rglob("*")):
        rel = p.relative_to(folder)
        if not p.is_file() or rel.parts[0] in skip or any(part.startswith(".") for part in rel.parts):
            continue
        dst = dest / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, dst)
        n += 1
        size += p.stat().st_size
    return {"dest": str(dest), "files": n, "bytes": size}


def cmd_pack(a: argparse.Namespace) -> int:
    folder, dest = Path(a.folder), Path(a.dest)
    if not (folder / "manifest.json").is_file():
        _err(f"{folder} has no manifest.json (not a song folder made by mvh analyze)")
        return 2
    if dest.resolve() == folder.resolve() or folder.resolve() in dest.resolve().parents:
        _err("the destination must be outside the song folder")
        return 2
    if dest.exists() and any(dest.iterdir()) and not a.force:
        _err(f"{dest} is not empty (pass --force to copy over it)")
        return 2
    res = pack_folder(folder, dest, with_stems=a.with_stems, with_viewer=a.with_viewer)
    print(json.dumps(res, ensure_ascii=False), flush=True)
    return 0


# ============================================================================================ doctor
def cmd_doctor(a: argparse.Namespace) -> int:
    from mvh.runner.doctor import run_checks

    checks = run_checks(
        quick=a.quick,
        rocm=not a.no_rocm,
        progress=None if a.json else (lambda m: print(f"  hashing {m}", file=sys.stderr, flush=True)),
    )
    if a.json:
        print(json.dumps([c.as_dict() for c in checks], ensure_ascii=False, indent=1))
    else:
        for c in checks:
            print(f"{c.level:<4}  {c.name}: {c.detail}")
    return 1 if any(c.level == "FAIL" for c in checks) else 0


# ============================================================================================ models
def cmd_models(a: argparse.Namespace) -> int:
    from mvh.runner import models as m

    ids = _csv(a.only)
    try:
        if a.action == "list":
            rows = m.list_models()
            if a.json:
                print(json.dumps(rows, ensure_ascii=False, indent=1))
            else:
                for r in rows:
                    print(
                        f"{'ok ' if r['present'] else 'MISSING'}  {r['id']:<40} {r['size'] / 1e6:9.1f} MB  "
                        f"envs={','.join(r['envs'])}  {r['licence'][:60]}"
                    )
            return 0
        if a.action == "verify":
            rows = m.verify(
                ids,
                full=True,
                use_cache=not a.no_cache,
                progress=None if a.json else (lambda s: print(f"  hashing {s}", file=sys.stderr, flush=True)),
            )
        else:
            rows = m.fetch(ids, envs=_csv(a.env), jobs=a.jobs)
    except m.ModelError as e:
        _err(str(e))
        return 1
    bad = [r for r in rows if r.status not in ("ok", "fetched")]
    if a.json:
        print(
            json.dumps(
                [{"id": r.model_id, "path": r.path, "status": r.status, "local": str(r.local)} for r in rows],
                ensure_ascii=False,
                indent=1,
            )
        )
    else:
        for r in rows:
            if r.status != "ok" or a.verbose:
                print(f"{r.status:<8} {r.model_id}/{r.path}  {r.detail}")
        print(f"{len(rows) - len(bad)}/{len(rows)} files ok")
    return 1 if bad else 0


# ============================================================================================ parser
def discover_stage_verbs(sub: argparse._SubParsersAction) -> list[str]:
    """Import ``mvh.stages.<name>.cli`` where it exists and call its ``register(subparsers)``."""
    added: list[str] = []
    try:
        import mvh.stages as stages_pkg
    except ImportError:
        return added
    for m in sorted(pkgutil.iter_modules(stages_pkg.__path__), key=lambda m: m.name):
        if not m.ispkg:
            continue
        name = f"mvh.stages.{m.name}.cli"
        try:
            if importlib.util.find_spec(name) is None:
                continue
            mod = importlib.import_module(name)
        except Exception as e:  # noqa: BLE001  (a broken module verb must not break the core CLI)
            _err(f"stage verbs of {m.name} not loaded: {type(e).__name__}: {e}")
            continue
        reg = getattr(mod, "register", None)
        if not callable(reg):
            continue
        before = set(sub.choices)
        try:
            reg(sub)
        except Exception as e:  # noqa: BLE001
            _err(f"stage verbs of {m.name} failed to register: {type(e).__name__}: {e}")
            continue
        added += sorted(set(sub.choices) - before)
    return added


def build_parser(with_stage_verbs: bool = True) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mvh", description="mv-harness: one song in, a folder of timestamped metadata out"
    )
    sub = p.add_subparsers(dest="verb", required=True)

    an = sub.add_parser("analyze", help="analyse a song into out/<slug>/")
    an.add_argument("song", help="the song file (or an existing song folder to re-run)")
    an.add_argument("--out", help="song folder (default: <repo>/out/<slug>, or MVH_OUT/<slug>)")
    an.add_argument("--slug")
    an.add_argument("--profile", choices=("max", "draft"), default="max")
    an.add_argument("--only", help="run only these stages (comma-separated; their deps must be cached)")
    an.add_argument(
        "--force", nargs="?", const="all", default=None, help="re-run all stages, or the listed ones"
    )
    an.add_argument("--from", dest="from_stage", help="re-run this stage and everything downstream")
    an.add_argument("--no-network", action="store_true")
    an.add_argument("--threads", type=int, default=None, help="threads per stage (default MVH_THREADS or 3)")
    an.add_argument(
        "--cores", type=int, default=8, help="core budget shared by concurrent stages (default 8)"
    )
    an.add_argument(
        "--lyrics", help="user lyrics file (.lrc/.srt/.vtt/.txt); kept for re-runs ('-' forgets it)"
    )
    an.add_argument(
        "--intent", help="copy this file to <song>/meaning/intent.md (never replaces a different one)"
    )
    an.add_argument(
        "--meaning-draft",
        choices=("agent", "anthropic", "off"),
        default=None,
        help="agent (default): request.md for your agent; anthropic: draft the gaps with the Claude API; off",
    )
    an.add_argument(
        "--no-lyrics-to-agents",
        action="store_true",
        help="keep lyric text out of lines.tsv, drafts, the brief and viewer.html (kept for re-runs)",
    )
    an.add_argument("--param", action="append", help="stage.key=JSON value (repeatable; kept for re-runs)")
    an.add_argument("--no-heavy-locks", action="store_true", help="do not take machine-wide heavy slots")
    an.set_defaults(func=cmd_analyze)

    st = sub.add_parser("status", help="done / stale / pending per stage, with the reason")
    st.add_argument("folder")
    st.add_argument("--json", action="store_true")
    st.add_argument("--threads", type=int, default=None, help="threads per stage (default MVH_THREADS or 3)")
    st.set_defaults(func=cmd_status)

    va = sub.add_parser("validate", help="schema-validate a song folder")
    va.add_argument("folder")
    va.add_argument("--json", action="store_true")
    va.set_defaults(func=cmd_validate)

    pk = sub.add_parser("pack", help="copy what a web page or video project loads (no stems/.cache) to DEST")
    pk.add_argument("folder", help="song folder made by mvh analyze")
    pk.add_argument("dest", help="destination folder (e.g. my-site/public/song)")
    pk.add_argument("--with-stems", action="store_true", help="also copy stems/ (large)")
    pk.add_argument("--with-viewer", action="store_true", help="also copy viewer.html")
    pk.add_argument("--force", action="store_true", help="copy into a non-empty destination")
    pk.set_defaults(func=cmd_pack)

    do = sub.add_parser("doctor", help="check ffmpeg, envs, ROCm, whisper, Rhubarb, models, disk")
    do.add_argument("--quick", action="store_true", help="sizes instead of SHA-256, no ROCm smoke test")
    do.add_argument("--no-rocm", action="store_true")
    do.add_argument("--json", action="store_true")
    do.set_defaults(func=cmd_doctor)

    mo = sub.add_parser("models", help="fetch, verify or list the models in models.lock.json")
    mo.add_argument("action", choices=("fetch", "verify", "list"))
    mo.add_argument("--only", help="model ids (comma-separated)")
    mo.add_argument("--env", help="main, sep, ffmpeg (fetch only)")
    mo.add_argument("--jobs", type=int, default=3)
    mo.add_argument("--no-cache", action="store_true", help="re-hash every file (verify)")
    mo.add_argument("--json", action="store_true")
    mo.add_argument("-v", "--verbose", action="store_true")
    mo.set_defaults(func=cmd_models)

    if with_stage_verbs:
        discover_stage_verbs(sub)
    return p


def main(argv: list[str] | None = None) -> int:
    _utf8_stdio()
    p = build_parser()
    a = p.parse_args(argv)
    from mvh.runner import locks

    try:
        return int(a.func(a) or 0)
    except locks.SongBusy as e:
        # W4VP-3: every verb that runs the pipeline (meaning, frames, module verbs) reports a busy song folder
        # the way `mvh analyze` does: one message, exit 75 (EX_TEMPFAIL), no traceback
        _err(str(e))
        return 75
    except KeyboardInterrupt:
        _err("interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
