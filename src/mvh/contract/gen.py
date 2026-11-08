# ruff: noqa: E501  (long catalogue tables / docstrings)
"""Regenerate the contract artefacts from catalog.py / registry.py.

    python -m mvh.contract.gen            # write schema/**.schema.json and the generated parts of docs/CONTRACT.md
    python -m mvh.contract.gen --check    # exit 1 when anything is out of date (used by tests)

Generated regions in CONTRACT.md sit between ``<!-- BEGIN GENERATED: <name> -->`` and ``<!-- END GENERATED: <name> -->``.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import catalog, registry, schemas

REPO = Path(__file__).resolve().parents[3]
CONTRACT_MD = REPO / "docs" / "CONTRACT.md"


def _schema_text(s: dict) -> str:
    return json.dumps(s, ensure_ascii=False, indent=1) + "\n"


def _cell(x) -> str:
    s = "" if x is None else str(x)
    return s.replace("|", "\\|").replace("\n", " ")


def _desc(s: dict) -> str:
    d = s.get("description", "")
    if "enum" in s:
        d = (d + " " if d else "") + "one of " + ", ".join(str(e) for e in s["enum"] if e is not None)
    if "pattern" in s and "id" in d:
        pass
    return d


def _type(s: dict) -> str:
    t = s.get("type", "any")
    t = "|".join(t) if isinstance(t, list) else t
    if t in ("array", "array|null") and isinstance(s.get("items"), dict):
        it = s["items"].get("type", "object")
        t = t.replace("array", f"{'|'.join(it) if isinstance(it, list) else it}[]")
    return t


def section_catalogue() -> str:
    rows = ["| Path | Kind | Producer | Schema | Req | Description |", "|---|---|---|---|---|---|"]
    order = ["_runner", "_user"] + _stage_order()
    items = []
    for f in catalog.FILES + catalog.RUNNER_FILES:
        if f.public:
            items.append((f.stage, f.path, f.kind, f.schema, f.required, f.description))
    for e in catalog.EVENTS:
        items.append((e.stage, e.file, "events", e.schema_id, e.required, f"events `{e.name}` ({e.kind}): {e.description}"))
    for t in catalog.TABLES:
        items.append((t.stage, t.path, "table", t.schema, True, t.description))
    for cf in registry.CURVE_FILES.values():
        stages = sorted({c.stage for c in registry.CHANNELS.values() if c.file == cf.id})
        items.append(("_runner", cf.path, "curve" if cf.layout == "column-major" else "matrix", None, True,
                      f"{cf.description}; channels from {', '.join(stages)} (packed by the runner)"))
    items = [i for i in items if not (i[0] == "_runner" and i[1].startswith("curves/") and i[1].endswith((".f32", ".u8"))
                                      and "packed by the runner" not in i[5])]
    items.sort(key=lambda i: (order.index(i[0]) if i[0] in order else 99, i[1]))
    for st, path, kind, sch, req, desc in items:
        rows.append(f"| `{path}` | {kind} | {st} | {('`mvh/' + sch + '`') if sch else '-'} | {'yes' if req else 'opt'} | {_cell(desc)} |")
    return "\n".join(rows)


def section_events() -> str:
    out = []
    for e in catalog.EVENTS:
        out.append(f"#### `{e.name}` - {e.kind}, by **{e.stage}**{'' if e.required else ' (optional file)'}")
        out.append(f"`{e.file}` · schema `mvh/{e.schema_id}`{(' · ids `' + e.id_kind + '`') if e.id_kind else ''} · {e.description}\n")
        out.append("| Field | Type | Unit | Frozen | Description |")
        out.append("|---|---|---|---|---|")
        for f in e.fields:
            out.append(f"| `{f.name}` | {_type(f.schema)} | {_cell(f.unit or '')} | {'yes' if f.required else 'no'} | {_cell(_desc(f.schema))} |")
        out.append("")
    return "\n".join(out).rstrip()


def section_channels() -> str:
    rows = ["| Channel id | File | Unit | Range | Resample | Norm / special | Twin | Stage | Description |",
            "|---|---|---|---|---|---|---|---|---|"]
    for c in registry.CHANNELS.values():
        ns = []
        if c.norm:
            ns.append(c.norm["method"] + (f" of `{c.norm['of']}`" if "of" in c.norm else ""))
        if c.special:
            ns.append(", ".join(f"{k}={v}" for k, v in c.special.items()))
        rows.append(f"| `{c.id}` | {c.file} | {c.unit} | {c.range[0]:g}..{c.range[1]:g} | {c.resample} | {_cell('; '.join(ns))} | "
                    f"{('`' + c.twin + '`') if c.twin else ''} | {c.stage} | {_cell(c.description)} |")
    return "\n".join(rows)


def section_files() -> str:
    out = []
    for sid, s in catalog.FILE_SCHEMAS.items():
        paths = [f.path for f in catalog.FILES + catalog.RUNNER_FILES if f.schema == sid]
        out.append(f"#### `mvh/{sid}` - {', '.join('`' + p + '`' for p in paths) or '(intermediate)'}\n")
        out.append("| Key | Type | Unit | Description |")
        out.append("|---|---|---|---|")
        for k in s.get("required", []):
            p = s["properties"][k]
            sub = ""
            if isinstance(p, dict) and p.get("type") in ("object", ["object", "null"]) and p.get("properties"):
                sub = " - keys: " + ", ".join(f"`{x}`" for x in p.get("required", []))
            if isinstance(p, dict) and str(p.get("type", "")).startswith("array") and isinstance(p.get("items"), dict) \
                    and p["items"].get("properties"):
                sub = " - item keys: " + ", ".join(f"`{x}`" for x in p["items"].get("required", []))
            out.append(f"| `{k}` | {_type(p) if isinstance(p, dict) else ''} | {_cell(p.get(catalog.U, '') if isinstance(p, dict) else '')} | "
                       f"{_cell(_desc(p) if isinstance(p, dict) else '')}{sub} |")
        out.append("")
    return "\n".join(out).rstrip()


def section_tables() -> str:
    out = []
    for t in catalog.TABLES:
        sep = "TAB" if t.sep == "\t" else "comma"
        out.append(f"- `{t.path}` ({sep}, by **{t.stage}**): " + ", ".join(
            f"`{f.name}`{(' [' + f.unit + ']') if f.unit else ''}" for f in t.columns) + f". {t.description}.")
    return "\n".join(out)


def _stage_order() -> list[str]:
    from mvh.runner.spec import load_stage_specs, topo_order
    return topo_order(load_stage_specs())


def section_consumed() -> str:
    from mvh.runner.spec import load_stage_specs
    specs = load_stage_specs()
    rows = ["| Stage | Env | Deps (§3.2) | Reads (target: frozen fields) |", "|---|---|---|---|"]
    for name in _stage_order():
        s = specs[name]
        reads = "<br>".join(f"`{t}`" + (": " + ", ".join(f) if f else "") for t, f in catalog.CONSUMES.get(name, []))
        deps = ", ".join(s.deps) if len(s.deps) < 12 else "all analysis stages"
        rows.append(f"| **{name}** | {s.env} | {deps or '-'} | {reads} |")
    return "\n".join(rows)


SECTIONS = {
    "catalogue": section_catalogue, "events": section_events, "channels": section_channels,
    "files": section_files, "tables": section_tables, "consumed": section_consumed,
}


def render_contract(text: str) -> str:
    for name, fn in SECTIONS.items():
        pat = re.compile(rf"(<!-- BEGIN GENERATED: {name} -->\n).*?(<!-- END GENERATED: {name} -->)", re.S)
        if not pat.search(text):
            raise ValueError(f"CONTRACT.md lacks the generated region {name!r}")
        body = fn().rstrip("\n") + "\n"
        text = pat.sub(lambda m: m.group(1) + body + m.group(2), text)
    return text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    stale: list[str] = []
    want = {schemas.schema_path(sid): _schema_text(s) for sid, s in schemas.build_all().items()}
    have = set(schemas.iter_schema_files())
    for p, txt in want.items():
        cur = p.read_text(encoding="utf-8") if p.exists() else None
        if cur != txt:
            stale.append(str(p))
            if not a.check:
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(p, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(txt)
    for p in have - set(want):
        stale.append(f"{p} (orphan)")
        if not a.check:
            p.unlink()
    if CONTRACT_MD.exists():
        cur = CONTRACT_MD.read_text(encoding="utf-8")
        new = render_contract(cur)
        if new != cur:
            stale.append(str(CONTRACT_MD))
            if not a.check:
                with open(CONTRACT_MD, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(new)
    if a.check and stale:
        print("out of date:\n  " + "\n  ".join(stale))
        return 1
    print(("checked" if a.check else "wrote") + f" {len(want)} schemas" + (f"; updated {len(stale)} files" if stale and not a.check else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
