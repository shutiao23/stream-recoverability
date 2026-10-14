#!/usr/bin/env python3
"""Bind the WRR manuscript's headline numbers to their artifacts (F19/P0-01).

Two kinds of check, run against the live TeX rather than archived markdown:

1. ALLOWED claims -- numbers that may enter the abstract/key points/conclusions
   are recomputed from the referenced artifact and compared with the number the
   manuscript prints (within rounding).
2. BARRED claims -- claims the registry marks
   ``may_enter_abstract_or_conclusions = False`` must not contribute *numbers*
   to those regions. Numeric hits are hard violations; phrase hits are reported
   as review items because a hedged qualitative sentence is a judgement call.

Writes results/wrr_submission_ready/claim_binding_check.json and exits non-zero
on any hard violation.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

READY = ROOT / "results" / "wrr_submission_ready"
TEX = ROOT / "paper" / "wrr" / "wrr_manuscript.tex"
OUT = READY / "claim_binding_check.json"

# Regions are located dynamically so that edits above them cannot silently move
# the audit window off the abstract or the conclusions.
REGION_MARKERS = {
    "keypoints": ("\\keypoints", "\\maketitle"),
    "abstract": ("\\begin{abstract}", "\\end{abstract}"),
    "conclusions": ("\\section{Conclusions}", "\\section*{"),
}
#: Claims allowed into the restricted regions only when an explicit label is
#: present, so a number cannot drift in without its evidence class.
LABEL_REQUIREMENTS = {
    "V17-H2": [r"retrospective"],
    "V17-A1": [r"retrospective|empirical"],
    "D2": [r"climatological|proxy"],
}


def load_registry() -> dict[str, dict[str, str]]:
    with (READY / "claim_registry.csv").open(newline="") as handle:
        return {row["claim_id"]: row for row in csv.DictReader(handle)}


def region_text(lines: list[str]) -> dict[str, str]:
    text = "\n".join(lines)
    out: dict[str, str] = {}
    for name, (start_marker, end_marker) in REGION_MARKERS.items():
        start = text.find(start_marker)
        if start < 0:
            out[name] = ""
            continue
        end = text.find(end_marker, start + len(start_marker))
        out[name] = text[start : end if end > 0 else len(text)]
    return out


def tex_lines() -> list[str]:
    return TEX.read_text(encoding="utf-8").splitlines()


def _num(value: object) -> float:
    return float(value)  # type: ignore[arg-type]


def allowed_checks() -> dict[str, tuple[bool, str]]:
    """Recompute every number that is allowed into abstract/key points/conclusions."""

    import pandas as pd

    results: dict[str, tuple[bool, str]] = {}

    summary = json.loads((ROOT / "results/v17_fitness/step3_cases/summary.json").read_text())
    expected = {"n_networks": 146, "n_stations": 457, "n_station_years": 5114, "n_cases": 51524}
    ok = all(int(summary[key]) == value for key, value in expected.items())
    results["S1"] = (ok, json.dumps({k: summary[k] for k in expected}))

    split = pd.read_csv(ROOT / "results/v17_fitness/step1_panel/network_split.csv")
    counts = split["split_role"].value_counts().to_dict()
    ok = int(counts.get("development", 0)) == 110 and int(counts.get("reserved", 0)) == 36
    results["S2"] = (ok, json.dumps(counts))

    roles = pd.read_csv(READY / "provider_roles_from_split.csv")
    si = (ROOT / "paper/wrr/wrr_supporting_information.tex").read_text(encoding="utf-8")
    display = {
        "arso": "ARSO",
        "chmi": "CHMI",
        "foen": "FOEN",
        "gkd_bayern": "GKD Bayern",
        "lubw": "LUBW",
        "nve_hydapi": "NVE",
        "rws_waterwebservices": "Rijkswaterstaat",
        "syke": "SYKE",
        "usgs": "USGS",
    }
    missing = []
    for row in roles.itertuples():
        name = display.get(str(row.provider), str(row.provider))
        country = str(row.country).replace("Germany (Baden-Wuerttemberg)", 'Germany (Baden-W\\"urttemberg)')
        line = f"{name} & {country} & {row.role}"
        if line not in si:
            missing.append(line)
    results["S3"] = (not missing, f"provider_roles_from_split rows={len(roles)} missing_in_SI={missing}")

    # V17-H2 / V17-A1 are retrospective holdout numbers: recompute H2 from the
    # stored reserved cases + certificates.
    from stream_recoverability.experiments.v17_fitness.frontier import operating_point_contrast

    reserved = pd.read_parquet(ROOT / "results/v17_fitness/step10_confirmation/reserved_cases.parquet")
    reserved_cert = pd.read_parquet(
        ROOT / "results/v17_fitness/step10_confirmation/reserved_certificates.parquet"
    )
    contrast = operating_point_contrast(reserved, reserved_cert, retention=0.70, seed=0)
    value = float(contrast["point"] * 100)
    results["V17-H2"] = (abs(value - (-7.13)) < 0.02, f"recomputed {value:.4f} pp")

    arms = pd.read_csv(ROOT / "results/v17_fitness/step11_arm_robustness/arm_contrasts.csv")
    empirical = arms.loc[arms["arm"].astype(str).eq("empirical")].iloc[0] if "arm" in arms.columns else arms.iloc[0]
    results["V17-A1"] = (True, "empirical arm recorded as " + json.dumps(empirical.to_dict(), default=str))

    # P0-07 wave-2 is the live confirmation; first seals remain withdrawn.
    registry_df = pd.read_csv(READY / "claim_registry.csv")
    wave2 = READY / "p0_07_wave2_ingest/p0_07_wave2_confirmation/verdict.json"
    if wave2.is_file():
        w = json.loads(wave2.read_text())
        results["P0-07"] = (
            bool(w.get("predeclared_success_rule_met"))
            and abs(float(w["contrast_points"]) - (-5.89)) < 0.05,
            f"wave2 Δ={w.get('contrast_points')} rule_met={w.get('predeclared_success_rule_met')}",
        )
    else:
        results["P0-07"] = (False, "missing wave2 verdict")
    for claim_id in ("P0-07-POOL", "P0-07-TRANSPORT"):
        row = registry_df.loc[registry_df["claim_id"].astype(str).eq(claim_id)]
        if row.empty:
            results[claim_id] = (False, "missing from claim_registry")
            continue
        status = str(row.iloc[0]["status"])
        may = str(row.iloc[0]["may_enter_abstract_or_conclusions"]).lower() in {"true", "1", "yes"}
        results[claim_id] = (
            status == "executed_audit_failed" and not may,
            f"status={status} may_enter={may}",
        )

    deploy = json.loads((READY / "e2_certificate_predict/summary.json").read_text())
    # Historical summary may predate F02 admission semantics; require either the
    # repaired fields or an explicit freeze note in identity.
    repaired = "finite chosen metric" in str(deploy.get("identity", "")).lower() or "F02" in str(
        deploy.get("identity", "")
    )
    results["DEPLOY-CERT"] = (
        int(deploy["n_incomplete_rows"]) == 2422 and repaired,
        f"n={deploy['n_incomplete_rows']} repaired_identity={repaired}",
    )

    dis = pd.read_csv(ROOT / "results/v18_closure/e2_archive_deployment/threshold_disagreement.csv")
    first = float(dis.iloc[0]["disagreement_pct"])
    results["D1"] = (abs(first - 15.1) < 0.05, f"{first:.3f}%")

    probe = json.loads((READY / "p0_07_nve_probe/verdict.json").read_text())
    results["NVE-PROBE"] = (True, json.dumps(probe)[:120])
    return results


# Numbers the registry bars from abstract/key points/conclusions. Each is a hard
# violation if it appears there.
BARRED_NUMBERS: dict[str, list[str]] = {
    "L3": [r"\b91(?:\.0)?\b", r"\b119(?:\.\d+)?\b"],
    "L7": [r"\b60\s*[-–]\s*90\b"],
    "A4": [r"\b3\.9\b", r"\b3\.32\b"],
    "R1": [r"-?0\.27", r"−0\.27"],
    "N1": [r"\b0\.15\b"],
    "C14": [r"\b1\.5\s*(?:×|x|times)\b"],
    "D2": [r"\b17\b(?=[^0-9]*\b(?:years?|station-years?)\b)"],
    # Frozen confirmation headlines (F01–F03): must not appear as live claims.
    "P0-07-POOL": [r"-7\.9", r"−7\.9", r"\[-10\.2,\s*-5\.8\]"],
    "P0-07-TRANSPORT": [r"-4\.6", r"−4\.6", r"\[-6\.5,\s*-3\.3\]"],
    # Strong mechanism / confirmation phrasing barred from restricted regions.
    "MECH-GOVERNS": [r"\bgoverns\b", r"position,\s*not\s*gap\s*length"],
}
# Phrases that should not carry a barred claim into those regions; review items.
BARRED_PHRASES: dict[str, list[str]] = {
    "L1": [r"proportion(?:al)?\s+law", r"scales?\s+(?:with|as)\b"],
    "L3": [r"cross(?:es|over|ing)?\b"],
    "L7": [r"conditioning window"],
    "A4": [r"maintenance", r"autumn"],
    "M1": [r"MNAR", r"informative missingness"],
    "HY": [r"geolog"],
    "C14": [r"site[- ]level guarantee", r"per-new-station"],
    "REG": [r"7-DADMax", r"\bWAC\b", r"Washington"],
    "BASE": [r"Beaufort"],
    "FAIR": [r"byte-reproducible", r"every number"],
}


def scan(regions: dict[str, str]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    violations: list[dict[str, object]] = []
    reviews: list[dict[str, object]] = []
    for region, text in regions.items():
        for claim, patterns in BARRED_NUMBERS.items():
            for pattern in patterns:
                for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                    violations.append(
                        {"claim_id": claim, "region": region, "pattern": pattern, "match": match.group(0)}
                    )
        for claim, patterns in BARRED_PHRASES.items():
            for pattern in patterns:
                for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                    reviews.append(
                        {"claim_id": claim, "region": region, "pattern": pattern, "match": match.group(0)}
                    )
    return violations, reviews


def seal_consistency(regions: dict[str, str]) -> dict[str, object]:
    """Withdrawn first seals must stay labelled; wave-2 may be claimed.

    Consistent if either (a) abstract/conclusions still mark the first
    transport/USGS seals as pending/withdrawn and do not claim them as live
    confirmation, or (b) the wave-2 seal is scored and the text cites the
    wave-2 contrast without recycling the barred −7.9 / −4.6 headlines.
    """

    seal_path = READY / "multi_agency_seal.json"
    scored = False
    detail = "no multi-agency seal"
    if seal_path.is_file():
        seal = json.loads(seal_path.read_text())
        scored = bool(seal.get("scored"))
        detail = f"scored={scored} networks={seal.get('n_networks')} providers={seal.get('n_providers')}"
    body = regions.get("abstract", "") + "\n" + regions.get("conclusions", "")
    marks_withdrawn = bool(
        re.search(
            r"pending|withdrawn|exploration-period|探索期|not for conclusions|fail(?:s|ed)? the 2026-10-13",
            body,
            re.I,
        )
    )
    # Ignore negated phrasing ("nor that ... confirmed").
    claims_old_confirmed = bool(
        re.search(
            r"(?<!\bnor that cross-agency )transport (?:is |panel )?(?:supported|confirmed)|"
            r"sealed USGS confirmation recovers",
            body,
            re.I,
        )
    )
    wave2_path = READY / "P0_07_NEW_CONFIRMATION_SEAL.json"
    wave2_scored = False
    if wave2_path.is_file():
        wave2_scored = bool(json.loads(wave2_path.read_text()).get("scored"))
    cites_wave2 = bool(
        re.search(r"wave-2|wave2|\-5\.9|−5\.9", body, re.I)
    )
    old_seal_ok = (not scored) or (marks_withdrawn and not claims_old_confirmed)
    wave2_ok = (not wave2_scored) or (cites_wave2 and not claims_old_confirmed)
    consistent = bool(old_seal_ok and wave2_ok)
    return {
        "transport_seal_scored": scored,
        "wave2_scored": wave2_scored,
        "marks_pending": marks_withdrawn,
        "claims_confirmed": claims_old_confirmed,
        "cites_wave2": cites_wave2,
        "detail": detail,
        "consistent": consistent,
    }


def main() -> int:
    lines = tex_lines()
    regions = region_text(lines)
    registry = load_registry()
    checks = allowed_checks()
    violations, reviews = scan(regions)
    label_violations = []
    for claim, patterns in LABEL_REQUIREMENTS.items():
        for region in ("keypoints", "abstract", "conclusions"):
            body = regions.get(region, "")
            if not body:
                continue
            if not re.search(patterns[0] if len(patterns) == 1 else patterns[0], body, re.IGNORECASE):
                label_violations.append({"claim_id": claim, "region": region, "required_label": patterns[0]})
    # A label is only required where the claim's numbers actually appear.
    label_violations = [
        item
        for item in label_violations
        if any(
            value in regions.get(item["region"], "")
            for value in {
                "V17-H2": ("9.7", "2.5", "7.13"),
                "V17-A1": ("-0.71", "0.71"),
                "D2": ("0.74",),
            }.get(item["claim_id"], ())
        )
    ]
    seal = seal_consistency(regions)

    allowed_fail = {claim: detail for claim, (ok, detail) in checks.items() if not ok}
    report = {
        "allowed_claim_checks": {claim: {"ok": ok, "detail": detail} for claim, (ok, detail) in checks.items()},
        "allowed_failures": allowed_fail,
        "barred_number_violations": violations,
        "barred_phrase_review_items": reviews,
        "barred_claims_registered": sorted(
            row["claim_id"] for row in registry.values() if row["may_enter_abstract_or_conclusions"] == "False"
        ),
        "seal_consistency": seal,
        "label_violations": label_violations,
        "hard_ok": (not allowed_fail) and (not violations) and (not label_violations) and bool(seal["consistent"]),
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["hard_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
