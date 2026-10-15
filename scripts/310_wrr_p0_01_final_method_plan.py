#!/usr/bin/env python3
"""Major-revision P0-01: converge on one published method and one claim set.

The review of 2026-10-14 (F01, F06, F12) found that the manuscript carried three
partly incompatible contributions at once: a transparent peak-window rule, a
same-capacity fitted risk model, and the full multi-method certificate screen,
while the prose still asserted that hidden support is the governing mechanism.
Step 2 has since shown that engineered support adds nothing measurable next to a
generic learner (0.05 pp, CI [-0.17, 0.23]), and Step 3 has shown that outage
length still matters under a fixed reconstructor.

This script does not compute science.  It reads the artifacts that exist, states
which method the paper recommends, what each claim may say, which claims are
withdrawn, and what each remaining claim still needs.  Every row carries the
artifact it rests on and an evidence class, so the manuscript can be checked
against it mechanically.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MR = ROOT / "results" / "wrr_submission_ready" / "major_revision_20261014"
OUT = MR / "p0_01_final_method"

EXISTING_REGISTRY = ROOT / "results" / "wrr_submission_ready" / "claim_registry.csv"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git_head() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:  # pragma: no cover - repository may be absent
        return "unknown"


def read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text())


# --------------------------------------------------------------------------- #
# The converged plan.
# --------------------------------------------------------------------------- #
PLAN = {
    "schema_version": 1,
    "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "git_head": git_head(),
    "question": (
        "Given an incomplete river-temperature year, should an agency admit it to an "
        "archive that will be used to compute the hottest 30-day mean?"
    ),
    "primary_method": {
        "id": "fitted_risk_calibrated",
        "name": "indicator-conditioned fitted risk score with a calibration-selected threshold",
        "what_it_reads": [
            "the target station's own observed days",
            "the stationary seasonal cycle estimated from the station's earlier years",
            "warm-season visibility: peak-window overlap, warm-season observed fraction, longest run",
            "the number and quality of visible neighbouring stations",
            "the interval half-width of the reconstruction ensemble",
        ],
        "what_it_never_reads": [
            "the true annual statistic of the year being judged",
            "any error, absolute error or truth column",
            "the labels of the evaluation records",
        ],
        "why_it_is_primary": (
            "It is the only candidate that both (a) reaches the best retention under a "
            "fixed false-admit risk on the retrospective panel and (b) can be applied to a "
            "record whose truth is unknown. Its threshold is chosen on calibration networks "
            "only; the evaluation networks are scored once."
        ),
        "evidence_status": "cross-fitted honest evaluation pending (see p0_02)",
    },
    "alternatives_reported_not_recommended_as_primary": [
        {
            "id": "transparent_support_rule",
            "name": "peak-window overlap rule (no fitting)",
            "role": "low-cost alternative for agencies that cannot fit or calibrate a model",
            "evidence": (
                "Step 2: worse than the fitted risk score by 2.60 pp at 70 % retention "
                "(CI [-3.11, -2.19])"
            ),
        },
        {
            "id": "certificate_multi_method_screen",
            "name": "frozen multi-method certificate screen with conformal bound",
            "role": (
                "the configuration on which the external wave-2 confirmation was obtained "
                "(-5.89 pp, CI [-6.92, -4.91]); retained as the validated reference"
            ),
            "evidence": "results/wrr_submission_ready/p0_07_wave2_ingest/",
        },
    ],
    "estimands_and_units": {
        "primary_endpoint": "hottest consecutive 30-day mean of daily mean water temperature",
        "tolerance_c": 0.5,
        "ranking_operating_point": "70 % retention",
        "admission_risk_target": "false-admit rate <= 5 % among admitted records",
        "units": {
            "error": "degrees C",
            "contrast": "percentage points",
            "retention": "per cent of candidates",
            "coverage": "per cent",
        },
    },
    "comparisons": {
        "primary": (
            "difference in the false-admit rate at 70 % retention between the fitted risk "
            "score and the length rule, network-clustered 95 % interval"
        ),
        "secondary": [
            "retention achieved at an equal risk target, threshold chosen without evaluation labels",
            "usable-record share after abstention, with abstentions counted in the denominator",
            "equal-budget comparison of abstention against judging everything",
        ],
    },
    "withdrawn_claims": [
        {
            "claim": "hidden support share is the governing, statistically necessary mechanism",
            "why": "Step 2: adding support to a same-capacity learner changes the error rate by +0.05 pp (CI [-0.17, +0.23])",
            "finding": "F01",
        },
        {
            "claim": "position dominates length",
            "why": "Step 3: at a fixed fully-hidden window, longer gaps still raise error (+0.153 C donor, +0.983 C linear interpolation)",
            "finding": "F06",
        },
        {
            "claim": "a 5 % risk cap has been operationally controlled",
            "why": "the published operating point was selected on evaluation labels; replaced by p0_02",
            "finding": "F02",
        },
        {
            "claim": "the final method has been confirmed under real common failure",
            "why": "the replay ran the length and peak-window rules, not the final rule; replaced by p0_03",
            "finding": "F04",
        },
        {
            "claim": "screening improves the regional hot-year composition",
            "why": "the old metric measured selection shift only; replaced by p0_04",
            "finding": "F05",
        },
        {
            "claim": "the missingness bias bound is identified",
            "why": "the day-level recompute covers 6 networks and 240 cases and is a specified-shift scenario, not an identified bound",
            "finding": "F09",
        },
    ],
    "falsification_tests": [
        "if the cross-fitted honest retention at the 5 % risk target is not distinguishable from the length rule, the admission claim reverts to a ranking-only claim",
        "if the final rule loses to the simple rules under all-donor failure, the method is limited to situations where neighbour information survives",
        "if the prediction error term does not improve on the reconstruct-all baseline, no environmental-judgement benefit is claimed",
        "if the paired learning-curve difference is not distinguishable from draw-to-draw variation, no sample-efficiency claim is made",
    ],
    "success_criteria": {
        "admission": "cross-fitted false-admit rate <= 5 % with an upper 95 % bound <= 5 %, and retention at least 5 pp above the length rule at that same target",
        "replay": "the final rule runs on every replay case with an explicit availability state, and beats the length rule on decided-case error or abstains instead of deciding wrongly",
        "closed_loop": "total deviation of the predicted hot-year share is reported as prediction error plus selection shift, and the abstaining rule is compared at an equal error budget",
        "manuscript": "every claim in the abstract and conclusions maps to a row of final_claims.csv whose evidence class permits it",
    },
    "unresolved": [
        "no panel unused anywhere in the project remains for a pristine confirmation of the converged method; the wave-2 seal belongs to the frozen certificate screen",
        "the measurement contract still mixes documented daily means with project-aggregated sub-daily values and one non-daily reference reading",
    ],
}


# --------------------------------------------------------------------------- #
# The converged claim set.
# --------------------------------------------------------------------------- #
CLAIMS = [
    dict(
        claim_id="M1",
        statement=(
            "Indicator-conditioned risk ranking admits more usable station-years than a "
            "completeness threshold at the same realised false-admit risk"
        ),
        artifact="major_revision_20261014/p0_02_frozen_risk_thresholds/crossfit_risk_cap_table.csv",
        endpoint="hottest_30",
        unit="percentage points (retention) and per cent (false-admit)",
        denominator="candidate station-year cases, network-clustered",
        evidence_type="cross_fitted_honest",
        population="wave-2 external panel, 49 networks",
        may_enter_abstract_or_conclusions="pending",
        status="pending_p0_02",
        finding_ids="F02/F03",
        notes="Quote only the cross-fitted number; the post-hoc frontier stays in the SI as contrast.",
    ),
    dict(
        claim_id="M2",
        statement=(
            "At 70 % retention the fitted risk score has a lower false-admit rate than the "
            "length rule and than the peak-window rule"
        ),
        artifact="major_revision_20261014/step2_same_info_ablation/contrasts_network_ci.json",
        endpoint="hottest_30",
        unit="percentage points",
        denominator="40 704 development cases (110 networks), out-of-fold",
        evidence_type="retrospective_development_oof",
        population="development networks",
        may_enter_abstract_or_conclusions="True",
        status="confirmed",
        finding_ids="F01",
        notes="-6.20 pp vs length ([-7.16,-5.36]); -2.60 pp vs peak-overlap rule ([-3.11,-2.19]).",
    ),
    dict(
        claim_id="M3",
        statement=(
            "Engineered hidden-support features are not uniquely necessary once seasonal "
            "visibility and uncertainty proxies enter the same learner"
        ),
        artifact="major_revision_20261014/step2_same_info_ablation/contrasts_network_ci.json",
        endpoint="hottest_30",
        unit="percentage points",
        denominator="40 704 development cases (110 networks), out-of-fold",
        evidence_type="retrospective_development_oof",
        population="development networks",
        may_enter_abstract_or_conclusions="True",
        status="confirmed",
        finding_ids="F01",
        notes="+0.05 pp ([-0.17,+0.23]) for generic+support minus generic; this is not equivalence.",
    ),
    dict(
        claim_id="M4",
        statement=(
            "On the external wave-2 panel the frozen certificate screen cuts consequential "
            "errors by 5.89 points on designed missingness, 5.46 points network-equal"
        ),
        artifact="major_revision_20261014/step7_transfer_reporting/transfer_report.json",
        endpoint="hottest_30",
        unit="percentage points",
        denominator="13 017 cases, 49 networks",
        evidence_type="sealed_confirmation",
        population="wave-2 providers (USGS-dominant, plus Hub'Eau, UK EA)",
        may_enter_abstract_or_conclusions="True",
        status="confirmed",
        finding_ids="F07",
        notes="USGS is 94.2 % of cases; non-USGS is 5 networks. Do not generalise past the tested providers.",
    ),
    dict(
        claim_id="M5",
        statement=(
            "Position and length interact: at a fixed fully-hidden peak window, longer gaps "
            "still raise error, and the size of the position effect depends on the reconstructor"
        ),
        artifact="major_revision_20261014/step3_fixed_reconstructor_mechanism/position_contrasts_network_ci.csv",
        endpoint="hottest_30",
        unit="degrees C",
        denominator="12 networks, fixed-month gaps",
        evidence_type="retrospective_conditional",
        population="development networks with donor reconstruction available",
        may_enter_abstract_or_conclusions="True",
        status="confirmed",
        finding_ids="F06",
        notes="Replaces the withdrawn dominance claim; quote both the position and the length contrast.",
    ),
    dict(
        claim_id="M6",
        statement=(
            "The final admission rule runs on real monitoring calendars and under neighbour "
            "co-failure, with an explicit availability state per case"
        ),
        artifact="major_revision_20261014/p0_03_final_method_replay/failure_mode_table.csv",
        endpoint="hottest_30",
        unit="per cent (share) and percentage points (contrast)",
        denominator="replay candidate pool, stated per failure mode",
        evidence_type="exploratory_replay",
        population="14-network replay probe unless extended",
        may_enter_abstract_or_conclusions="pending",
        status="pending_p0_03",
        finding_ids="F04/F09",
        notes="Degenerate donor cases must be reported as unavailable, never as donor reconstruction.",
    ),
    dict(
        claim_id="M7",
        statement=(
            "The closed environmental loop separates prediction error from selection shift "
            "in the hot-year share of the admitted set"
        ),
        artifact="major_revision_20261014/p0_04_env_closed_loop/share_decomposition.csv",
        endpoint="exceed_18/exceed_20",
        unit="percentage points",
        denominator="candidate station-years, per case and network-weighted",
        evidence_type="exploratory_closed_loop",
        population="wave-2 candidates",
        may_enter_abstract_or_conclusions="pending",
        status="pending_p0_04",
        finding_ids="F05",
        notes="The old hot_share_bias_pp is renamed selection_shift_pp.",
    ),
    dict(
        claim_id="M8",
        statement=(
            "The panel's measurement contract mixes documented daily means, project-aggregated "
            "sub-daily values and one non-daily reference reading, and results are reported per class"
        ),
        artifact="major_revision_20261014/p0_06_coverage_recompute/measurement_contract_table.csv",
        endpoint="panel",
        unit="stations and cases",
        denominator="457 stations, 146 networks",
        evidence_type="sample_fact",
        population="final study panel",
        may_enter_abstract_or_conclusions="True",
        status="pending_p0_06",
        finding_ids="F08",
        notes="Replaces any statement that all inputs are daily means.",
    ),
    dict(
        claim_id="M9",
        statement=(
            "No panel that is unused anywhere in this project remains for a pristine "
            "confirmation of the converged method"
        ),
        artifact="major_revision_20261014/p0_05_power_independence/independent_evidence_requirements.csv",
        endpoint="design",
        unit="networks",
        denominator="prior-access ledger",
        evidence_type="design_fact",
        population="all ingested panels",
        may_enter_abstract_or_conclusions="True",
        status="pending_p0_05",
        finding_ids="F01/F07",
        notes="State it in the limitations; the wave-2 seal belongs to the frozen certificate screen.",
    ),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    existing = []
    if EXISTING_REGISTRY.is_file():
        with EXISTING_REGISTRY.open(newline="") as handle:
            existing = list(csv.DictReader(handle))

    plan = dict(PLAN)
    plan["existing_registry_rows"] = len(existing)
    plan["existing_registry_ids"] = [row["claim_id"] for row in existing]
    (OUT / "final_analysis_plan.json").write_text(json.dumps(plan, indent=2) + "\n")

    # YAML-flavoured rendering, written by hand so no YAML dependency is needed.
    lines = ["# Final analysis plan (P0-01). Generated by scripts/310_wrr_p0_01_final_method_plan.py",
             f"# git {plan['git_head']}  {plan['generated_utc']}", ""]

    def emit(key: str, value, indent: int = 0) -> None:
        pad = "  " * indent
        if isinstance(value, dict):
            lines.append(f"{pad}{key}:")
            for sub, item in value.items():
                emit(sub, item, indent + 1)
        elif isinstance(value, list):
            lines.append(f"{pad}{key}:")
            for item in value:
                if isinstance(item, (dict, list)):
                    lines.append(f"{pad}  -")
                    if isinstance(item, dict):
                        for sub, value2 in item.items():
                            emit(sub, value2, indent + 2)
                    else:
                        for value2 in item:
                            emit("-", value2, indent + 3)
                else:
                    lines.append(f"{pad}  - {item}")
        else:
            lines.append(f"{pad}{key}: {value}")

    for key, value in plan.items():
        if key in {"existing_registry_ids"}:
            continue
        emit(key, value)
    (OUT / "final_analysis_plan.yaml").write_text("\n".join(lines) + "\n")

    fieldnames = list(CLAIMS[0].keys())
    with (OUT / "final_claims.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(CLAIMS)

    fingerprint = {
        "script": str(Path(__file__).relative_to(ROOT)),
        "script_sha256": sha256(Path(__file__)),
        "git_head": plan["git_head"],
        "inputs": {
            str(EXISTING_REGISTRY.relative_to(ROOT)): sha256(EXISTING_REGISTRY)
            if EXISTING_REGISTRY.is_file()
            else None,
        },
        "generated_utc": plan["generated_utc"],
    }
    (OUT / "protocol_fingerprint.json").write_text(json.dumps(fingerprint, indent=2) + "\n")

    withdrawn = "\n".join(
        f"- **{item['claim']}** --- {item['why']} ({item['finding']})" for item in PLAN["withdrawn_claims"]
    )
    summary = f"""# P0-01 --- one published method, one claim set

Generated by `scripts/310_wrr_p0_01_final_method_plan.py` at git `{plan['git_head']}`.

## The recommendation

**{PLAN['primary_method']['name']}** is the method the paper recommends. It reads only
decision-time visible quantities, it never reads the truth of the record it judges, and its
threshold is chosen on calibration networks. Two alternatives are reported and not
recommended as primary: the transparent peak-window rule (2.60 pp worse at 70 % retention)
and the frozen multi-method certificate screen (the configuration the wave-2 seal actually
confirmed, kept as the validated reference).

## Claims withdrawn and why

{withdrawn}

## What each remaining claim needs

| claim | evidence class | status | artifact |
|---|---|---|---|
""" + "\n".join(
        f"| {c['claim_id']} | {c['evidence_type']} | {c['status']} | `{c['artifact']}` |" for c in CLAIMS
    ) + f"""

## Falsification tests agreed before scoring

""" + "\n".join(f"- {item}" for item in PLAN["falsification_tests"]) + f"""

## What this plan does not prove

- It does not create a new independent sample. `M9` records that no unused panel remains;
  the wave-2 seal belongs to the frozen certificate screen, not to a retuned method.
- It does not demonstrate that the fitted risk score is the best possible model, only that
  it is the best of the candidates actually compared.
- {PLAN['unresolved'][1].capitalize()}.
"""
    (OUT / "SUMMARY.md").write_text(summary)

    print(json.dumps({"out": str(OUT), "claims": len(CLAIMS), "withdrawn": len(PLAN["withdrawn_claims"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
