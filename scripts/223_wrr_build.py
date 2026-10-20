#!/usr/bin/env python3
"""Build the Water Resources Research submission.

AGU's own class does the typesetting; this runs the LaTeX cycle against the
vendored copy in `paper/wrr/template/` and then checks the limits a desk editor
checks first, because a manuscript that fails those is returned without review:

* exactly three key points, each 140 characters or fewer;
* an abstract of 250 words or fewer;
* a plain language summary of 200 words or fewer, which WRR requires;
* an Open Research Statement, which WRR requires;
* every cited reference present in the bibliography and every entry cited.

It also refuses to call the manuscript submission-ready while the author block
is still a placeholder. `paper_archived/author_information_required.md` records why the
repository must not invent names, affiliations or ORCID identifiers.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper" / "wrr"
TEMPLATE = PAPER / "template"
MAIN = "wrr_manuscript"
SI = "wrr_supporting_information"
PUBLISHED = "wrr_manuscript_published"

KEY_POINT_CHARS = 140
ABSTRACT_WORDS = 250
SUMMARY_WORDS = 200
PLACEHOLDER = "AFFILIATION PENDING AUTHOR CONFIRMATION"


def environment() -> dict[str, str]:
    env = dict(os.environ)
    existing = env.get("TEXINPUTS", "")
    env["TEXINPUTS"] = f"{TEMPLATE}:{PAPER}:{existing}:"
    env["BIBINPUTS"] = f"{PAPER}:{env.get('BIBINPUTS', '')}:"
    env["TEXMFOUTPUT"] = str(PAPER)
    return env


def run(command: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    # TeX logs are not guaranteed to be UTF-8 (pdflatex writes byte strings from
    # the .tex source and from font metrics), and a decode error here would mask
    # the real LaTeX error, so decode leniently.
    return subprocess.run(
        command, cwd=cwd, env=env, capture_output=True, text=True, errors="replace"
    )


def body(text: str, macro: str) -> str:
    """The contents of a brace-delimited argument or environment."""

    start = text.find(macro)
    if start < 0:
        return ""
    if macro.startswith("\\begin"):
        name = macro[len("\\begin{") : -1]
        end = text.find(f"\\end{{{name}}}", start)
        return text[start + len(macro) : end] if end > 0 else ""
    depth, out, index = 0, [], text.index("{", start)
    for char in text[index:]:
        if char == "{":
            depth += 1
            if depth == 1:
                continue
        elif char == "}":
            depth -= 1
            if depth == 0:
                break
        out.append(char)
    return "".join(out)


def words(text: str) -> int:
    text = re.sub(r"\\begin\{plainlanguagesummary\}.*?\\end\{plainlanguagesummary\}", "", text, flags=re.S)
    text = re.sub(r"\\[a-zA-Z]+\*?", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    return len(text.split())


def key_points(text: str) -> list[str]:
    match = re.search(r"\\keypoints\s*((?:\s*\{[^{}]*\}){3})", text, re.S)
    if match is None:
        return []
    return re.findall(r"\{([^{}]*)\}", match.group(1))


#: Numbers the article's argument rests on, each settled by an artifact under
#: results/ and audited there by scripts/221_v18_audit_manuscript.py. They are
#: checked here as literal strings because a restructuring pass is exactly when
#: a number goes missing without anyone noticing: an earlier rewrite of this
#: manuscript silently dropped ten of them.
HEADLINE_NUMBERS = (
    # design
    "146", "457", "5{,}114", "53{,}721", "40{,}704", "13{,}017", "2{,}422",
    "418", "41", "1{,}899", "12",
    # the error a completeness test leaves
    "1.31", "24.9",
    # the phenomenon
    "0.64", "0.02", "0.68", "0.89", "0.41", "0.24", "1.16",
    # mechanism
    "0.66", "0.28", "0.70", "0.84", "0.88", "35", "55",
    # decision
    "39.6", "66.7", "72.9", "74.0", "60.4", "70.4", "9.7", "10.3",
    "2.2", "3.7", "8.3", "2.8", "2.6", "4.1", "93", "96",
    # hot years
    "86", "25", "26", "33", "60",
    # risk rule
    "0.4", "7.8", "12.2", "18.5", "35.9", "42", "150", "3.9",
    # repair
    "898", "6.9", "2.7", "7.2", "4.5",
)


def missing_numbers(text: str) -> list[str]:
    return [value for value in HEADLINE_NUMBERS if value not in text]


def checks(text: str, bbl: Path) -> tuple[list[dict], list[dict]]:
    failures: list[dict] = []
    passes: list[dict] = []

    points = key_points(text)
    if len(points) != 3:
        failures.append({"check": "three key points", "found": len(points)})
    else:
        passes.append({"check": "three key points", "found": 3})
    for index, point in enumerate(points, 1):
        length = len(point.strip())
        record = {"check": f"key point {index} length", "chars": length, "limit": KEY_POINT_CHARS}
        (passes if length <= KEY_POINT_CHARS else failures).append(record)

    abstract = body(text, "\\begin{abstract}")
    count = words(abstract)
    record = {"check": "abstract length", "words": count, "limit": ABSTRACT_WORDS}
    (passes if 0 < count <= ABSTRACT_WORDS else failures).append(record)

    summary = body(text, "\\begin{plainlanguagesummary}")
    count = words(summary)
    record = {"check": "plain language summary length", "words": count, "limit": SUMMARY_WORDS}
    (passes if 0 < count <= SUMMARY_WORDS else failures).append(record)

    record = {"check": "open research statement present"}
    (passes if "\\section*{Open Research Statement}" in text else failures).append(record)

    absent = missing_numbers(text)
    record = {"check": "headline numbers present", "checked": len(HEADLINE_NUMBERS), "missing": absent}
    (passes if not absent else failures).append(record)

    cited = set(re.findall(r"\\cite[A-Za-z]*\{([^}]*)\}", text))
    cited = {key.strip() for group in cited for key in group.split(",") if key.strip()}
    declared: set[str] = set()
    for name in ("references.bib", "references_additions.bib"):
        path = PAPER / name
        if path.exists():
            declared |= set(re.findall(r"^@\w+\{([^,]+),", path.read_text(), re.M))
    missing = sorted(cited - declared)
    unused = sorted(declared - cited)
    record = {"check": "every citation resolves", "missing": missing}
    (passes if not missing else failures).append(record)
    record = {"check": "no uncited bibliography entries", "unused": unused}
    (passes if not unused else failures).append(record)

    if bbl.exists():
        rendered = len(re.findall(r"\\bibitem", bbl.read_text(errors="replace")))
        record = {"check": "bibliography rendered", "entries": rendered}
        (passes if rendered >= len(cited) else failures).append(record)

    return passes, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-build", action="store_true", help="check the limits without running LaTeX")
    args = parser.parse_args()

    source = PAPER / f"{MAIN}.tex"
    text = source.read_text(encoding="utf-8")
    env = environment()

    # The class draws its marks with an explicit relative path, which kpathsea
    # will not resolve through TEXINPUTS, so they are staged beside the
    # manuscript as build artifacts.
    for mark in TEMPLATE.glob("agu-logo-*.pdf"):
        shutil.copy2(mark, PAPER / mark.name)

    if not args.skip_build:
        for binary in ("pdflatex", "bibtex"):
            if shutil.which(binary) is None:
                raise SystemExit(f"{binary} is required")
        steps = [
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", f"{MAIN}.tex"],
            ["bibtex", MAIN],
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", f"{MAIN}.tex"],
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", f"{MAIN}.tex"],
        ]
        for step in steps:
            result = run(step, cwd=PAPER, env=env)
            # BibTeX warns about non-fatal things and returns non-zero for them.
            if result.returncode != 0 and step[0] != "bibtex":
                log = (PAPER / f"{MAIN}.log").read_text(errors="replace")
                errors = [line for line in log.splitlines() if line.startswith("!")]
                sys.stderr.write("\n".join(errors[-20:]) + "\n")
                raise SystemExit(f"{step[0]} failed")

    if not args.skip_build:
        # The supporting information is a separate document, as AGU requires.
        for step in (
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", f"{SI}.tex"],
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", f"{SI}.tex"],
        ):
            result = run(step, cwd=PAPER, env=env)
            if result.returncode != 0:
                log = (PAPER / f"{SI}.log").read_text(errors="replace")
                errors = [line for line in log.splitlines() if line.startswith("!")]
                sys.stderr.write("\n".join(errors[-20:]) + "\n")
                raise SystemExit("supporting information failed to build")

    if not args.skip_build:
        # AGU's draft option sets a 20 pt baseline at every size, which is the
        # double-spaced copy a reviewer marks up. The published option renders
        # close to the version of record, which is the copy an author reads to
        # judge length and layout. Both come from the same source.
        # The class option is rewritten rather than added: "draft" is also a
        # graphics option, and leaving it in place makes graphicx replace every
        # figure with a box showing its filename.
        wrapper = PAPER / f"{PUBLISHED}.tex"
        published_source = text.replace(
            "\\documentclass[draft]{agujournal2025}",
            "%% Generated by scripts/223_wrr_build.py from wrr_manuscript.tex.\n"
            "%% Do not edit; edit the manuscript.\n"
            "\\documentclass[published]{agujournal2025}",
        )
        assert "published]{agujournal2025}" in published_source
        wrapper.write_text(published_source, encoding="utf-8")
        # The published option loads fontspec for the version-of-record fonts,
        # which needs XeTeX. A missing font here is not fatal to the
        # submission, so this layout is built best-effort and reported only if
        # it succeeded.
        for step in (
            ["xelatex", "-interaction=nonstopmode", f"{PUBLISHED}.tex"],
            ["bibtex", PUBLISHED],
            ["xelatex", "-interaction=nonstopmode", f"{PUBLISHED}.tex"],
            ["xelatex", "-interaction=nonstopmode", f"{PUBLISHED}.tex"],
        ):
            run(step, cwd=PAPER, env=env)

    pdf = PAPER / f"{MAIN}.pdf"
    passes, failures = checks(text, PAPER / f"{MAIN}.bbl")

    placeholder = PLACEHOLDER in text
    report = {
        "pdf": str(pdf.relative_to(ROOT)) if pdf.exists() else None,
        "checks_passed": passes,
        "checks_failed": failures,
        "submission_ready": not failures and not placeholder,
        "blocked_on_author_information": placeholder,
    }
    si_pdf = PAPER / f"{SI}.pdf"
    published_pdf = PAPER / f"{PUBLISHED}.pdf"
    report["supporting_information"] = str(si_pdf.relative_to(ROOT)) if si_pdf.exists() else None
    report["published_layout"] = str(published_pdf.relative_to(ROOT)) if published_pdf.exists() else None
    for key, target in (
        ("pages", pdf),
        ("supporting_information_pages", si_pdf),
        ("published_layout_pages", published_pdf),
    ):
        if target.exists():
            info = run(["pdfinfo", str(target)], cwd=PAPER, env=env).stdout
            report[key] = next(
                (line.split()[-1] for line in info.splitlines() if line.startswith("Pages:")), None
            )
    (PAPER / "build_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    for record in passes:
        print("  ok  ", record)
    for record in failures:
        print("  FAIL", record)
    if pdf.exists():
        print(f"\n{pdf.relative_to(ROOT)} — {report.get('pages', '?')} pages")
    if si_pdf.exists():
        print(f"{si_pdf.relative_to(ROOT)} — {report.get('supporting_information_pages', '?')} pages")
    if published_pdf.exists():
        print(
            f"{published_pdf.relative_to(ROOT)} — "
            f"{report.get('published_layout_pages', '?')} pages (published layout)"
        )
    if placeholder:
        print(
            "\nNOT submission-ready: the author block is a placeholder. "
            "See paper_archived/author_information_required.md."
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
