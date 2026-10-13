#!/usr/bin/env python3
"""Independent verification of scripts/264_wrr_companion_dataset.py.

Checks the released dataset and dashboard against the task's rules, and proves
that the builder fails loudly on the failure modes it claims to catch.  Read
only with respect to results/ (fixtures are written under scratch/).

Run:  python3 scratch/p2_03/verify_264.py
"""

from __future__ import annotations

import csv
import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "264_wrr_companion_dataset.py"
DATASET = ROOT / "docs" / "companion" / "companion_dataset.csv"
DIST_DATASET = ROOT / "dist" / "companion" / "companion_dataset.csv"
README = ROOT / "docs" / "companion" / "README.md"
DASH = ROOT / "dist" / "companion" / "index.html"
FIXTURES = ROOT / "scratch" / "p2_03" / "fixtures"

FAILURES: list[str] = []


def check(cond: bool, label: str) -> None:
    print(("PASS  " if cond else "FAIL  ") + label)
    if not cond:
        FAILURES.append(label)


def load_module():
    spec = importlib.util.spec_from_file_location("companion264", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = load_module()

    # ---------------------------------------------------------------- dataset
    rows = list(csv.DictReader(DATASET.open(encoding="utf-8")))
    check(DATASET.read_text() == DIST_DATASET.read_text(),
          "dist/companion/companion_dataset.csv is byte-identical to the released CSV")
    check(list(rows[0].keys()) == mod.COLUMNS, "CSV columns are the 9 declared columns")
    check(len(rows) > 500, f"dataset has a plausible size ({len(rows)} rows)")

    # every row names an artifact that exists on disk and was read by the build
    missing = [r for r in rows if not (ROOT / r["artifact_path"]).is_file()]
    check(not missing, f"every artifact_path exists on disk ({len(missing)} missing)")

    # every numeric row has a unit, a denominator and a parseable value
    bad_numeric = []
    for r in rows:
        if r["unit"] in ("text", "bool", "sha256", ""):
            continue
        if not r["denominator"].strip():
            bad_numeric.append((r["entity_id"], r["field"], "no denominator"))
            continue
        try:
            float(r["value"])
        except ValueError:
            bad_numeric.append((r["entity_id"], r["field"], r["value"]))
    check(not bad_numeric, f"every numeric row parses and has a denominator: {bad_numeric[:3]}")

    check(all(r["entity_type"] in mod.ENTITY_TYPES for r in rows),
          "entity_type is always one of the four declared values")
    check(all(r["evidence_class"] in mod.EVIDENCE_CLASSES for r in rows),
          "evidence_class is always one of the six declared classes")

    registry = list(csv.DictReader(
        (ROOT / "results/wrr_submission_ready/claim_registry.csv").open(encoding="utf-8")))
    reg_ids = {r["claim_id"] for r in registry}
    ds_claim_ids = {r["entity_id"] for r in rows if r["entity_type"] == "claim"}
    extra = ds_claim_ids - reg_ids
    check(extra <= set(mod.DECLARED_EXTRA_CLAIM_IDS),
          f"claim entities are registry ids or declared extras ({sorted(extra)})")
    check(reg_ids <= ds_claim_ids, "every registry claim appears in the dataset")

    # the registry's numeric headline claims must carry at least one numeric row
    numeric_claims = {
        r["entity_id"] for r in rows
        if r["entity_type"] == "claim" and r["unit"] not in ("text", "bool", "sha256", "")
    }
    check(len(numeric_claims) >= 18,
          f"numeric claim coverage ({len(numeric_claims)} claims with numbers)")

    # withdrawn/proxy/exploratory flags are present where required
    classes = Counter(r["evidence_class"] for r in rows)
    check(classes["withdrawn"] > 0 and classes["proxy"] > 0
          and classes["exploratory_post_open"] > 0,
          f"failure/withdrawal flags present: {dict(classes)}")
    withdrawn_claims = {r["entity_id"] for r in rows
                        if r["evidence_class"] == "withdrawn" and r["entity_type"] == "claim"}
    check({"L1", "REG", "FAIR"} <= withdrawn_claims,
          f"L1/REG/FAIR are flagged withdrawn ({sorted(withdrawn_claims)})")
    proxy_claims = {r["entity_id"] for r in rows if r["evidence_class"] == "proxy"}
    check("D2" in proxy_claims, "the proxy claim D2 is flagged proxy")

    # S1 panel counts must equal the frozen case-table summary
    step3 = json.load((ROOT / "results/v17_fitness/step3_cases/summary.json").open())
    s1 = {r["field"]: r["value"] for r in rows
          if r["entity_type"] == "claim" and r["entity_id"] == "S1"}
    check(int(s1["n_networks"]) == step3["n_networks"]
          and int(s1["n_stations"]) == step3["n_stations"]
          and int(s1["n_station_years"]) == step3["n_station_years"]
          and int(s1["n_cases"]) == step3["n_cases"],
          "S1 panel counts equal step3_cases/summary.json")

    # sealed confirmation numbers equal the verdict
    v = json.load((ROOT / "results/wrr_submission_ready/p0_07_sealed_confirmation/verdict.json").open())
    p = {r["field"]: r["value"] for r in rows
         if r["entity_type"] == "claim" and r["entity_id"] == "P0-07-POOL"}
    check(abs(float(p["contrast_points"]) - v["contrast_points"]) < 1e-12
          and abs(float(p["contrast_ci_low"]) - v["ci_low_points"]) < 1e-12,
          "sealed pooled contrast and interval equal the verdict artifact")

    # ---------------------------------------------------------------- README
    readme = README.read_text(encoding="utf-8")
    check("python3 scripts/264_wrr_companion_dataset.py" in readme,
          "README documents the single rebuild command")
    for ec in mod.EVIDENCE_CLASSES:
        if f"`{ec}`" not in readme:
            check(False, f"README documents evidence class {ec}")
    check("must not be quoted" in readme, "README states the quotability rule")
    for cid in ("L1", "L3", "L7", "D2", "REG", "FAIR", "NVE-PROBE"):
        check(f"`{cid}`" in readme, f"README lists the non-quotable claim {cid}")

    # ---------------------------------------------------------------- dashboard
    html_text = DASH.read_text(encoding="utf-8")
    check("http://" not in html_text and "https://" not in html_text.replace(
        "https://www.w3.org", "").replace("http://www.w3.org", ""),
        "dashboard makes no network references (no fetch, no CDN)")
    check("<script" not in html_text.lower() or "application/json" in html_text,
          "dashboard has no executable script tag")
    spans = re.findall(r'<span class="num"([^>]*)>([^<]*)</span>', html_text)
    check(bool(spans), f"dashboard labels its numbers ({len(spans)} spans)")
    bad = [a for a, _ in spans
           if "data-cls=" not in a or "data-art=" not in a or "title=" not in a]
    check(not bad, "every displayed number carries data-cls, data-art and a tooltip")
    bad_art = [a for a, _ in spans
               if re.search(r'data-art="([^"]+)"', a).group(1) not in {
                   r["artifact_path"] for r in rows}]
    check(not bad_art, "every dashboard artifact path is a path used by the dataset")
    for cid in ("L1", "REG", "FAIR", "TRANSPORT"):
        check(cid in html_text, f"dashboard 'what is not established' panel names {cid}")
    check("not scored" in html_text.lower(), "dashboard states that transport is not scored")

    # ------------------------------------------------- failure modes (loud)
    FIXTURES.mkdir(parents=True, exist_ok=True)

    # 1) missing artifact
    b = mod.Builder()
    saved = mod.A["step10_verdict"]
    mod.A["step10_verdict"] = "results/does/not/exist.json"
    try:
        rc = mod.main()
        loud = rc == 2
    except SystemExit as exc:
        loud = exc.code == 2
    finally:
        mod.A["step10_verdict"] = saved
    check(loud, "missing artifact stops the build with a non-zero exit")

    # 2) empty / null / non-numeric required fields
    fixture = FIXTURES / "empty_fields.json"
    fixture.write_text(json.dumps({"empty": "  ", "null": None, "nan": float("nan"),
                                   "ok": 1.0}), encoding="utf-8")
    rel = str(fixture.relative_to(ROOT))
    b2 = mod.Builder()
    cases = [("empty", "empty string"), ("null", "null"), ("nan", "NaN")]
    for key, label in cases:
        try:
            b2.get(rel, (key,), "fixture")
            check(False, f"required field {label} is rejected")
        except mod.BuildError:
            check(True, f"required field {label} is rejected")
    try:
        b2.num("claim", "S1", "x", "not-a-number", "count", "d", "sample_fact", rel)
        check(False, "non-numeric value is rejected")
    except mod.BuildError:
        check(True, "non-numeric value is rejected")

    # 3) duplicate rows and unread artifacts
    b3 = mod.Builder()
    b3.read_json(rel)
    b3.add("claim", "S1", "f", "v", "text", "", "sample_fact", rel)
    try:
        b3.add("claim", "S1", "f", "v", "text", "", "sample_fact", rel)
        check(False, "duplicate dataset row is rejected")
    except mod.BuildError:
        check(True, "duplicate dataset row is rejected")
    try:
        b3.add("claim", "S1", "g", "1", "count", "d", "sample_fact",
               "results/never/read.csv")
        check(False, "row citing an unread artifact is rejected")
    except mod.BuildError:
        check(True, "row citing an unread artifact is rejected")

    # 4) unmapped registry evidence_type
    saved_map = dict(mod.EVIDENCE_CLASS_MAP)
    mod.EVIDENCE_CLASS_MAP.pop("sample_fact")
    b4 = mod.Builder()
    try:
        mod.build_claims(b4)
        check(False, "unmapped evidence_type stops the build")
    except mod.BuildError as exc:
        check("without a declared evidence class" in str(exc),
              "unmapped evidence_type stops the build")
    finally:
        mod.EVIDENCE_CLASS_MAP.clear()
        mod.EVIDENCE_CLASS_MAP.update(saved_map)

    # ------------------------------------------------------------- summary
    print()
    if FAILURES:
        print(f"{len(FAILURES)} CHECK(S) FAILED")
        for f in FAILURES:
            print(" -", f)
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
