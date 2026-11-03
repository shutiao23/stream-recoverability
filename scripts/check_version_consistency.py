"""Check package and citation versions against each other and the latest git tag."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
CITATION = ROOT / "CITATION.cff"
ZENODO = ROOT / ".zenodo.json"


def read_pyproject_version(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    try:
        import tomllib
    except ModuleNotFoundError:
        try:
            import tomli as tomllib
        except ModuleNotFoundError:
            match = re.search(r'(?m)^\s*version\s*=\s*["\']([^"\']+)["\']', text)
            if match is None:
                raise ValueError(f"no project version in {path}")
            return match.group(1)
    data = tomllib.loads(text)
    return str(data["project"]["version"])


def read_citation_versions(path: Path) -> tuple[str, str | None, bool]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml
    except ModuleNotFoundError:
        yaml = None
    if yaml is not None:
        data = yaml.safe_load(text) or {}
        version = str(data.get("version", "")).strip()
        preferred = data.get("preferred-citation") or {}
        preferred_version = preferred.get("version")
        if preferred_version is not None:
            preferred_version = str(preferred_version).strip()
        doi_present = bool(str(data.get("doi", "")).strip()) or bool(
            str(preferred.get("doi", "")).strip()
        )
        return version, preferred_version, doi_present
    version = ""
    preferred_version = None
    section = ""
    for line in text.splitlines():
        if line and not line[0].isspace():
            section = line.split(":", 1)[0].strip()
        match = re.match(r'\s*version\s*:\s*["\']?([^"\'#\s]+)', line)
        if match is None:
            continue
        if section == "preferred-citation" and line.startswith((" ", "\t")):
            preferred_version = match.group(1)
        elif line.startswith("version"):
            version = match.group(1)
    doi_present = bool(re.search(r"(?m)^\s*doi\s*:\s*[\"']?[^\s\"'#]+", text))
    return version, preferred_version, doi_present


def read_zenodo_version(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    version = str(data.get("version", "")).strip()
    if not version:
        raise ValueError(f"no version in {path}")
    return version


def latest_git_tag(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "tag", "--sort=-v:refname"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    tags = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return tags[0] if tags else None


def tag_version(tag: str | None) -> str | None:
    if not tag:
        return None
    match = re.fullmatch(r"v?(\d+\.\d+\.\d+)", tag)
    return match.group(1) if match else None


def main() -> int:
    failures: list[str] = []
    try:
        package_version = read_pyproject_version(PYPROJECT)
    except (OSError, ValueError, KeyError) as exc:
        print(f"FAIL: cannot read version from pyproject.toml: {exc}")
        return 1
    try:
        citation_version, preferred_version, doi_present = read_citation_versions(
            CITATION
        )
    except (OSError, ValueError) as exc:
        print(f"FAIL: cannot read version from CITATION.cff: {exc}")
        return 1
    try:
        zenodo_version = read_zenodo_version(ZENODO)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot read version from .zenodo.json: {exc}")
        return 1

    print(f"pyproject.toml version: {package_version}")
    print(f"CITATION.cff version: {citation_version}")
    print(
        "CITATION.cff preferred-citation version: "
        f"{preferred_version if preferred_version is not None else 'not set'}"
    )
    print(f".zenodo.json version: {zenodo_version}")

    if not citation_version:
        failures.append("CITATION.cff has no top-level version")
    elif citation_version != package_version:
        failures.append(
            f"CITATION.cff version {citation_version} != pyproject.toml {package_version}"
        )
    if preferred_version is not None and preferred_version != package_version:
        failures.append(
            "CITATION.cff preferred-citation version "
            f"{preferred_version} != pyproject.toml {package_version}"
        )
    if zenodo_version != package_version:
        failures.append(
            f".zenodo.json version {zenodo_version} != pyproject.toml {package_version}"
        )

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
    else:
        print(
            "PASS: pyproject.toml, CITATION.cff, preferred-citation, and "
            f".zenodo.json versions are consistent at {package_version}"
        )

    tag = latest_git_tag(ROOT)
    if tag is None:
        print("WARN: no git tag found; no release tag describes the package version")
    else:
        version_from_tag = tag_version(tag)
        if version_from_tag == package_version:
            print(f"PASS: latest git tag {tag} matches package version")
        elif version_from_tag is None:
            print(
                f"WARN: latest git tag {tag} has no parseable version; "
                "package version is not represented by a release tag"
            )
        else:
            print(
                f"WARN: latest git tag {tag} is historical; it names version "
                f"{version_from_tag}, not package version {package_version}. "
                "Do not treat this tag or any DOI as the current release until "
                "a new tag and DOI exist."
            )

    if doi_present:
        print(
            "WARN: CITATION.cff declares a DOI; confirm it resolves to version "
            f"{package_version} before release"
        )
    else:
        print(
            "INFO: CITATION.cff has no DOI (expected until an archival DOI is "
            "minted and recorded)"
        )

    if failures:
        print("RESULT: FAIL")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
