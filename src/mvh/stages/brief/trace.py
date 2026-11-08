# ruff: noqa: E501
"""Traceability check for brief.md (CONTRACT §12: every number traces back to a file).

Every decimal number in the brief must equal (at its printed precision) some numeric value in the song folder's
JSON/CSV/TSV files. IDs (S01, L012, Q0034 ...), hex colours, note names, m:ss times (the seconds next to them are
checked), meters and file names are not numbers. Integers and percentages are counts/aggregates computed from the
named files and are not checked here.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Iterable

__all__ = ["untraceable_numbers", "folder_values", "decimals_in"]

_STRIP = [
    re.compile(r"#[0-9a-fA-F]{6}\b"),                      # colours
    re.compile(r"\b\d+:\d{2}\.\d\b"),                      # m:ss.s
    re.compile(r"\b[A-Z]{1,2}\d+(?:\.\d+)?\b"),            # ids (S01, L001.03, VP001, Q0001)
    re.compile(r"\b[A-G]#?-?\d\b"),                         # note names
    re.compile(r"\b\d+/\d+\b"),                             # meters
    re.compile(r"[\w./-]+\.(?:json|csv|tsv|md|js|py|flac)\b"),  # file names
    re.compile(r"\bx\d+(?:\.\d+)?\b"),                      # tempo relations (x0.5, x2)
    re.compile(r"[A-Za-z_]+#\d+"),                          # occurrence labels (chorus#2)
]
_DEC = re.compile(r"(?<![\w.])-?\d+\.\d+(?![\w.])")


def _walk(x: Any, out: list[float]) -> None:
    if isinstance(x, bool):
        return
    if isinstance(x, (int, float)):
        out.append(float(x))
    elif isinstance(x, dict):
        for v in x.values():
            _walk(v, out)
    elif isinstance(x, list):
        for v in x:
            _walk(v, out)


def folder_values(folder: Path | str, rels: Iterable[str] | None = None) -> list[float]:
    folder = Path(folder)
    paths = [folder / r for r in rels] if rels else [p for p in folder.rglob("*") if p.suffix in (".json", ".csv", ".tsv")
                                                     and ".cache" not in p.parts and "frames" not in p.parts]
    vals: list[float] = []
    for p in paths:
        if not p.is_file():
            continue
        if p.suffix == ".json":
            with open(p, encoding="utf-8") as fh:
                _walk(json.load(fh), vals)
        else:
            with open(p, encoding="utf-8", newline="") as fh:
                for row in csv.reader(fh, delimiter="\t" if p.suffix == ".tsv" else ","):
                    for c in row:
                        try:
                            vals.append(float(c))
                        except ValueError:
                            pass
    return vals


def decimals_in(text: str) -> list[str]:
    for rx in _STRIP:
        text = rx.sub(" ", text)
    return _DEC.findall(text)


def untraceable_numbers(text: str, values: Iterable[float]) -> list[str]:
    vals = list(values)
    fmt: dict[int, set[str]] = {}
    bad = []
    for tok in decimals_in(text):
        k = len(tok.split(".")[1])
        if k not in fmt:
            fmt[k] = {f"{v:.{k}f}" for v in vals}
            fmt[k] |= {s.lstrip("-") for s in fmt[k] if float(s) == 0.0}  # '-0.0' prints as '0.0' too
        if tok not in fmt[k]:
            bad.append(tok)
    return bad
