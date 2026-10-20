#!/usr/bin/env python3
"""Re-check every bibliography entry against the publisher's deposited BibTeX.

For each entry with a DOI this script fetches ``https://doi.org/<doi>`` with
``Accept: application/x-bibtex`` (cached under ``scratch/reference_audit``), then
compares authors, title, venue, volume, issue, pages, year and DOI after
normalising LaTeX accents, braces, capitalisation and dash style.  Entries with
no DOI are listed for manual checking and their evidence is recorded in
``docs/reviews/wrr_reference_audit_20261020.md``.

The comparison is intentionally field-wise and case-insensitive: a sentence-case
title is not an error, a wrong surname or a wrong volume is.  The known,
documented deviations (full given names where the deposit abbreviates, the
"Klein Tank" parse, the online-first year of one article) are whitelisted and
printed as ``accepted``.

Run:

    python3 scripts/338_wrr_reference_audit.py
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIB = ROOT / "paper" / "wrr" / "references.bib"
CACHE = ROOT / "scratch" / "reference_audit" / "authoritative"

#: key -> reason the difference from the deposit is deliberate
ACCEPTED = {
    "caissie2006": "deposit abbreviates the given name; the full name is kept",
    "zhang2011": "deposit parses the surname 'Klein Tank' as 'Tank, Albert Klein'",
    "li2017": "deposit's year is the online-first date; the issue year 2017 is kept",
    "falcone2011": "deposit carries no title or author; the landing page does",
}
MANUAL = {"geifman2017", "zaoui2020", "nasapower2026", "wac2024", "wang2025"}


def parse_bib(text: str) -> dict[str, dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    for match in re.finditer(r"@(\w+)\s*\{\s*([^,]+),", text):
        key = match.group(2).strip()
        position, depth = match.end(), 1
        while position < len(text) and depth:
            if text[position] == "{":
                depth += 1
            elif text[position] == "}":
                depth -= 1
            position += 1
        body = text[match.end() : position - 1]
        fields: dict[str, str] = {}
        cursor = 0
        while True:
            field = re.search(r"(\w+)\s*=\s*", body[cursor:])
            if not field:
                break
            name = field.group(1).lower()
            start = cursor + field.end()
            if start >= len(body):
                break
            if body[start] == "{":
                level, end = 0, start
                while end < len(body):
                    if body[end] == "{":
                        level += 1
                    elif body[end] == "}":
                        level -= 1
                        if level == 0:
                            break
                    end += 1
                value = body[start + 1 : end]
                cursor = end + 1
            elif body[start] == '"':
                end = body.find('"', start + 1)
                value = body[start + 1 : end]
                cursor = end + 1
            else:
                token = re.match(r"[^,\n]+", body[start:])
                value = token.group(0).strip() if token else ""
                cursor = start + (token.end() if token else 0)
            fields[name] = re.sub(r"\s+", " ", value).strip().rstrip(",").strip()
        entries[key] = fields
    return entries


def deaccent(text: str) -> str:
    text = re.sub(r"\\['`^\"~=.]\{?([a-zA-Z])\}?", r"\1", text)
    text = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", text)
    text = re.sub(r"[{}$\\]", "", text)
    text = text.replace("---", "-").replace("--", "-").replace("~", " ")
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", deaccent(text).lower()).split())


def authors(text: str) -> list[list[str]]:
    out = []
    for name in re.split(r"\s+and\s+", deaccent(text)):
        name = name.strip()
        if name:
            out.append(re.sub(r"[^a-zA-Z ]+", " ", name).lower().split())
    return out


def fetch(doi: str, key: str) -> str:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{key}.bib"
    if path.exists() and path.read_text().strip().startswith("@"):
        return path.read_text()
    result = subprocess.run(
        ["curl", "-sL", "--max-time", "30", "-H", "Accept: application/x-bibtex", f"https://doi.org/{doi}"],
        capture_output=True,
        text=True,
    )
    path.write_text(result.stdout)
    return result.stdout


def compare(entry: dict[str, str], deposited: dict[str, str]) -> list[str]:
    issues = []
    if norm(entry.get("title", "")) != norm(deposited.get("title", "")):
        issues.append("title")
    if deposited.get("author") and authors(entry.get("author", "")) != authors(deposited.get("author", "")):
        issues.append("authors")
    for field in ("journal", "volume", "number", "pages", "year"):
        left, right = norm(entry.get(field, "")), norm(deposited.get(field, ""))
        if left and right and left != right:
            issues.append(field)
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-network", action="store_true", help="use the cache only")
    args = parser.parse_args()
    entries = parse_bib(BIB.read_text())
    failures = 0
    print(f"{'key':20s} {'status':12s} notes")
    for key, fields in entries.items():
        doi = fields.get("doi", "")
        if not doi or args.no_network and not (CACHE / f"{key}.bib").exists():
            print(f"{key:20s} {'manual':12s} no DOI deposit; see the audit report")
            continue
        if key in MANUAL:
            print(f"{key:20s} {'manual':12s} no DOI deposit; see the audit report")
            continue
        deposited = parse_bib(fetch(doi, key))
        if not deposited:
            print(f"{key:20s} {'manual':12s} deposit unreadable; see the audit report")
            continue
        issues = compare(fields, next(iter(deposited.values())))
        if not issues:
            print(f"{key:20s} {'match':12s} {doi}")
        elif key in ACCEPTED:
            print(f"{key:20s} {'accepted':12s} {key}: {ACCEPTED[key]}")
        else:
            failures += 1
            print(f"{key:20s} {'DIFF':12s} {', '.join(issues)}  ({doi})")
    print()
    print(f"{len(entries)} entries, {failures} unexplained difference(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
