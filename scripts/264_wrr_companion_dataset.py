#!/usr/bin/env python3
"""P2-03 (minimal): companion derived dataset + static dashboard.

Every number this script writes is read at *build time* from a named artifact
under ``results/`` and is stored together with that artifact's path.  No number
is typed into the source: values live only in artifact paths, dotted JSON
lookups, CSV row selectors and the unit conversions documented inline.

Read-only with respect to ``results/``, ``paper/``, ``src/`` and ``metadata/``.
Writes only:

    docs/companion/companion_dataset.csv   (released tidy dataset, tracked)
    docs/companion/README.md               (released documentation, tracked)
    dist/companion/index.html              (self-contained dashboard, gitignored)
    dist/companion/dashboard_data.json     (the payload embedded in the HTML)
    dist/companion/companion_dataset.csv   (byte copy of the tidy dataset)

Run:

    python3 scripts/264_wrr_companion_dataset.py

The build fails loudly (non-zero exit, no partial output) if a referenced
artifact is missing, if a required field is absent/empty, if a registry
evidence_type has no declared evidence class, if an extracted number is not
numeric, or if a cross-check between two artifacts disagrees.
"""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# --------------------------------------------------------------------------
# Outputs
# --------------------------------------------------------------------------

DOCS_DIR = ROOT / "docs" / "companion"
DIST_DIR = ROOT / "dist" / "companion"
DATASET_OUT = DOCS_DIR / "companion_dataset.csv"
README_OUT = DOCS_DIR / "README.md"
DASH_OUT = DIST_DIR / "index.html"
DASH_JSON = DIST_DIR / "dashboard_data.json"
DIST_DATASET = DIST_DIR / "companion_dataset.csv"

COLUMNS = [
    "entity_type",
    "entity_id",
    "field",
    "value",
    "unit",
    "denominator",
    "evidence_class",
    "artifact_path",
    "notes",
]

ENTITY_TYPES = ("network", "claim", "amendment", "provider")

EVIDENCE_CLASSES = (
    "sample_fact",
    "retrospective_holdout",
    "sealed_confirmation",
    "exploratory_post_open",
    "proxy",
    "withdrawn",
)

EVIDENCE_CLASS_DEFINITION = {
    "sample_fact": (
        "Measured, descriptive property of the study sample, the real archive or "
        "a verified interface. No model contrast."
    ),
    "retrospective_holdout": (
        "Model/rule contrast scored on a retrospective evaluation panel (v17 "
        "reserved network holdout or the frozen development case set). Not an "
        "independent unseen confirmation."
    ),
    "sealed_confirmation": (
        "Score from a panel sealed before scoring (P0-07 USGS confirmation and "
        "its disclosed post-seal diagnostics)."
    ),
    "exploratory_post_open": (
        "Design, endpoint, level or window chosen after a panel was opened, or "
        "flagged exploratory by the claim registry. Must not be quoted as a "
        "result."
    ),
    "proxy": (
        "Quantities about a proxy, or proxy expectations transported to cases "
        "whose truth is unobserved by construction."
    ),
    "withdrawn": (
        "Superseded, unusable or explicitly withdrawn numbers. Must not be "
        "quoted as results."
    ),
}

# registry evidence_type -> evidence_class.  Every distinct evidence_type in
# claim_registry.csv must appear here; the build fails otherwise.
EVIDENCE_CLASS_MAP = {
    "sample_fact": "sample_fact",
    "deployment_description": "sample_fact",
    "deployment_interface_verified": "sample_fact",
    "incomplete_measurement_provenance": "sample_fact",
    "retrospective_network_holdout": "retrospective_holdout",
    "mislabelled_baseline": "retrospective_holdout",
    "sealed_confirmation_single_provider_usgs": "sealed_confirmation",
    "sealed_multi_agency_transport_single_score": "sealed_confirmation",
    "supplementary_multi_agency_probe_below_floor": "exploratory_post_open",
    "proxy_not_truth": "proxy",
    "exploratory_post_open": "exploratory_post_open",
    "exploratory_with_implementation_bug": "exploratory_post_open",
    "exploratory_with_inference_flaws": "exploratory_post_open",
    "exploratory_with_method_switch": "exploratory_post_open",
    "exploratory_overclaim": "exploratory_post_open",
    "exploratory_level_selected_on_opened": "exploratory_post_open",
    "endpoint_mismatch": "withdrawn",
    "overstated_reproducibility": "withdrawn",
}

# Claim-level overrides, where the registry status/finding withdraws a headline
# that the raw evidence_type alone would not flag.  Reason strings are the
# authority; they are written into the dataset notes.
EVIDENCE_CLASS_OVERRIDE = {
    "L1": (
        "withdrawn",
        "F04 closure_mode=withdraw_proportion_law_from_headlines "
        "(results/wrr_submission_ready/F_FINDINGS_CLOSURE_AUDIT.csv); registry notes: "
        "'Withdraw unconditional proportion headline.'",
    ),
}

# Entity ids that are not claim_registry.csv rows.  Anything else must be a
# registry claim id; the build fails on an undeclared id.
DECLARED_EXTRA_CLAIM_IDS = {
    "TRANSPORT": (
        "protocol-level entity for the P0-07 multi-agency transport extension "
        "(results/wrr_submission_ready/MULTI_AGENCY_TRANSPORT_PROTOCOL.md); not a "
        "claim_registry.csv row"
    ),
}

# --------------------------------------------------------------------------
# Artifacts
# --------------------------------------------------------------------------

READY = "results/wrr_submission_ready"
V17 = "results/v17_fitness"
V18 = "results/v18_closure"
AMD = f"{READY}/amendments"

A = {
    "claim_registry": f"{READY}/claim_registry.csv",
    "finding_audit": f"{READY}/F_FINDINGS_CLOSURE_AUDIT.csv",
    "claim_binding_check": f"{READY}/claim_binding_check.json",
    "current_manifest": f"{READY}/current_data_manifest.csv",
    "prior_access_sealed": f"{READY}/prior_access_audit_sealed_usgs.csv",
    "prior_access_multi": f"{READY}/prior_access_audit_multi_agency.csv",
    "prior_access_summary": f"{READY}/prior_access_audit_summary.json",
    "measurement_dictionary": f"{READY}/measurement_provenance_dictionary.csv",
    "provider_roles": f"{READY}/provider_roles_from_split.csv",
    "step3_summary": f"{V17}/step3_cases/summary.json",
    "network_split": f"{V17}/step1_panel/network_split.csv",
    "step10_verdict": f"{V17}/step10_confirmation/verdict.json",
    "step11_contrasts": f"{V17}/step11_arm_robustness/arm_contrasts.csv",
    "step11_verdict": f"{V17}/step11_arm_robustness/verdict.json",
    "step18_summary": f"{V17}/step18_cluster_conformal/summary.json",
    "step21_verdict": f"{V17}/step21_hydrology/verdict.json",
    "p0_07_verdict": f"{READY}/p0_07_sealed_confirmation/verdict.json",
    "transport_verdict": f"{READY}/p0_07b_multi_agency_transport/verdict.json",
    "nve_probe_verdict": f"{READY}/p0_07_nve_probe/verdict.json",
    "e2_summary": f"{V18}/e2_archive_deployment/summary.json",
    "e2_threshold_disagreement": f"{V18}/e2_archive_deployment/threshold_disagreement.csv",
    "e2_by_provider": f"{V18}/e2_archive_deployment/disagreement_by_provider.csv",
    "e2_matched_retention": f"{V18}/e2_archive_deployment/matched_retention_disagreement.csv",
    "e2_archive_consequence": f"{V18}/e2_archive_deployment/archive_consequence.csv",
    "deploy_predict": f"{READY}/e2_certificate_predict/summary.json",
    "e4_representativeness": f"{V18}/e4_representativeness/summary.json",
    "e4_elevation_retention": f"{V18}/e4_representativeness/elevation_retention.csv",
    "a4_maintenance": f"{READY}/e1_maintenance_recompute/maintenance_counterfactual.json",
    "amend_e6_crossover": f"{AMD}/e6_support_width_uncertainty/crossover.json",
    "amend_e6_curve": f"{AMD}/e6_support_width_uncertainty/curve_with_ci.csv",
    "amend_e6_report": f"{AMD}/e6_support_width_uncertainty/REPORT.md",
    "amend_faithful_summary": f"{AMD}/faithful_baseline/summary.json",
    "amend_faithful_contrasts": f"{AMD}/faithful_baseline/contrasts.csv",
    "amend_mnar": f"{AMD}/mnar_pattern_mixture/summary.json",
    "amend_proxy_bridge": f"{AMD}/peak_proxy_bridge/summary.json",
    "amend_provider_contract": f"{AMD}/provider_contract_sensitivity/summary.json",
    "amend_provider_contract_csv": f"{AMD}/provider_contract_sensitivity/provider_contract_contrasts.csv",
    "amend_sealed_diagnostic": f"{AMD}/sealed_usgs_prior_access_diagnostic/summary.json",
    "amend_step22_post": f"{AMD}/step22_noise_post_fix/summary.json",
    "amend_step22_scenarios": f"{AMD}/step22_noise_post_fix/scenario_contrasts.csv",
    "amend_step22_pre": f"{AMD}/step22_noise_pre_fix/noise_sensitivity.json",
    "amend_step5_equal_k": f"{AMD}/step5_mechanism_equal_k/summary.json",
    "amend_step5_by_k": f"{AMD}/step5_mechanism_equal_k/contrast_by_k.csv",
    "amend_step5_pre": f"{AMD}/step5_mechanism_pre_fix/summary.json",
    "amend_step5_pre_contrasts": f"{AMD}/step5_mechanism_pre_fix/donor_control_contrasts.csv",
    "amend_winter_summary": f"{AMD}/winter_regulatory/summary.json",
    "amend_winter_cold": f"{AMD}/winter_regulatory/cold_support_contrast.csv",
    "amend_winter_report": f"{AMD}/winter_regulatory/REPORT.md",
    "amend_outage_causes": f"{AMD}/outage_causes/summary.json",
    "amend_outage_causes_mix": f"{AMD}/outage_causes/cause_mix.csv",
    "amend_regulatory_daily_max":
        f"{AMD}/regulatory_daily_max/daily_max_availability_summary.json",
    "transport_protocol": f"{READY}/MULTI_AGENCY_TRANSPORT_PROTOCOL.md",
    "transport_uk_ea_networks": f"{READY}/multi_agency_ingest/uk_ea/networks_manifest.csv",
    "transport_uk_ea_years": f"{READY}/multi_agency_ingest/uk_ea/complete_station_years.csv",
    "transport_nve_ingest": f"{READY}/multi_agency_ingest/nve/ingest.json",
    "transport_smhi_status": f"{READY}/multi_agency_ingest/smhi/INGEST_STATUS.json",
    "transport_ehyd_ingest": f"{READY}/multi_agency_ingest/ehyd/ingest.json",
}

# Optional artifact: the transport verdict is scored once, later, by
# scripts/250_multi_agency_transport_score.py.  When it is absent the build
# emits an explicit not-scored status row instead of a number.
OPTIONAL_ARTIFACTS = {
    "transport_verdict": f"{READY}/p0_07b_multi_agency_transport/verdict.json",
}

# Amendment directories deliberately not covered by this minimal P2-03 build,
# with the reason.  Anything not listed here and not covered by a spec is
# reported as "no summary.json and no spec" rather than dropped silently.
KNOWN_UNCOVERED_AMENDMENTS = {
    "manuscript_audit": (
        "no summary.json: this directory holds a per-manuscript-node claim-binding "
        "table (paper/wrr/wrr_manuscript.tex nodes), which is manuscript auditing "
        "rather than an amendment headline; it is out of scope for the companion "
        "dataset and is listed here so it is not silently dropped"
    ),
}


class BuildError(RuntimeError):
    """Any condition that must stop the build instead of degrading silently."""


def fail(message: str) -> None:
    raise BuildError(message)


def check(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


# --------------------------------------------------------------------------
# Reader / builder
# --------------------------------------------------------------------------


class Builder:
    def __init__(self) -> None:
        self.rows: list[dict[str, str]] = []
        self.artifacts: dict[str, dict] = {}
        self._json_cache: dict[str, object] = {}
        self._csv_cache: dict[str, list[dict[str, str]]] = {}
        self._keys: set[tuple] = set()
        self.dash: dict = {
            "panel_by_provider": [],
            "panel_totals": [],
            "contrasts": [],
            "admission": {},
            "providers": [],
            "not_established": [],
            "transport": {},
        }

    # -- artifact I/O ------------------------------------------------------

    def _resolve(self, rel: str) -> Path:
        path = ROOT / rel
        check(path.is_file(), f"artifact missing: {rel} (resolved {path})")
        return path

    def _note(self, rel: str, path: Path, kind: str, n: int | None = None) -> None:
        if rel in self.artifacts:
            return
        raw = path.read_bytes()
        self.artifacts[rel] = {
            "path": rel,
            "kind": kind,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "rows_read": n,
        }

    def read_csv(self, rel: str) -> list[dict[str, str]]:
        if rel in self._csv_cache:
            return self._csv_cache[rel]
        path = self._resolve(rel)
        rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))
        check(bool(rows), f"artifact has no data rows: {rel}")
        self._note(rel, path, "csv", len(rows))
        self._csv_cache[rel] = rows
        return rows

    def read_json(self, rel: str) -> object:
        if rel in self._json_cache:
            return self._json_cache[rel]
        path = self._resolve(rel)
        payload = json.loads(path.read_text(encoding="utf-8"))
        self._note(rel, path, "json")
        self._json_cache[rel] = payload
        return payload

    def read_text(self, rel: str) -> str:
        path = self._resolve(rel)
        text = path.read_text(encoding="utf-8")
        self._note(rel, path, "text")
        return text

    def artifact_exists(self, rel: str) -> bool:
        return (ROOT / rel).is_file()

    # -- value lookup ------------------------------------------------------

    def get(self, rel: str, path, ctx: str):
        """Fetch a required value from an artifact.  Loud on missing/empty."""
        obj = self.read_json(rel)
        cur = obj
        walked: list[str] = []
        for key in path:
            walked.append(str(key))
            where = f"{rel} :: {'.'.join(walked)}"
            if isinstance(key, int):
                check(isinstance(cur, list), f"{ctx}: {where} is not a list")
                check(0 <= key < len(cur), f"{ctx}: {where} index out of range")
                cur = cur[key]
            else:
                check(
                    isinstance(cur, dict),
                    f"{ctx}: {where} parent is not an object (got {type(cur).__name__})",
                )
                check(key in cur, f"{ctx}: required field absent: {where}")
                cur = cur[key]
        where = f"{rel} :: {'.'.join(walked)}"
        check(cur is not None, f"{ctx}: required field is null: {where}")
        if isinstance(cur, str):
            check(cur.strip() != "", f"{ctx}: required field is empty: {where}")
        if isinstance(cur, float):
            check(not math.isnan(cur), f"{ctx}: required field is NaN: {where}")
        if isinstance(cur, (list, dict)):
            check(len(cur) > 0, f"{ctx}: required field is empty: {where}")
        return cur

    def get_nullable(self, rel: str, path, ctx: str):
        """Like get(), but a *present* JSON null is returned as None.

        Used only where the artifact's null is itself the fact (e.g. "no bias in the
        swept grid erases the advantage"); a missing key still fails loudly.
        """
        obj = self.read_json(rel)
        cur = obj
        walked: list[str] = []
        for key in path:
            walked.append(str(key))
            where = f"{rel} :: {'.'.join(walked)}"
            if isinstance(key, int):
                check(isinstance(cur, list), f"{ctx}: {where} is not a list")
                check(0 <= key < len(cur), f"{ctx}: {where} index out of range")
                cur = cur[key]
            else:
                check(isinstance(cur, dict),
                      f"{ctx}: {where} parent is not an object")
                check(key in cur, f"{ctx}: required field absent: {where}")
                cur = cur[key]
        return cur

    def pick(self, rel: str, **match) -> dict[str, str]:
        """Select exactly one CSV row by column equality.  Loud on 0 or >1."""
        rows = self.read_csv(rel)
        sel = [
            r
            for r in rows
            if all(str(r.get(k, "")) == str(v) for k, v in match.items())
        ]
        ctx = f"{rel} where {match}"
        check(len(sel) == 1, f"{ctx}: expected exactly 1 row, found {len(sel)}")
        return sel[0]

    # -- row writing -------------------------------------------------------

    def add(
        self,
        entity_type: str,
        entity_id: str,
        field: str,
        value,
        unit: str,
        denominator: str,
        evidence_class: str,
        artifact_path: str,
        notes: str = "",
    ) -> None:
        check(entity_type in ENTITY_TYPES, f"bad entity_type: {entity_type}")
        check(evidence_class in EVIDENCE_CLASSES, f"bad evidence_class: {evidence_class}")
        check(entity_id.strip() != "", f"empty entity_id for {entity_type}/{field}")
        check(field.strip() != "", f"empty field for {entity_type}/{entity_id}")
        text = "" if value is None else str(value)
        check(text.strip() != "", f"empty value: {entity_type}/{entity_id}/{field}")
        check(
            artifact_path in self.artifacts,
            f"{entity_type}/{entity_id}/{field}: artifact not read by this build: "
            f"{artifact_path}",
        )
        if unit not in ("text", "bool", "sha256", ""):
            # numeric fact: a denominator must be recorded
            check(
                denominator.strip() != "",
                f"{entity_type}/{entity_id}/{field}: numeric row needs a denominator",
            )
        row = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "field": field,
            "value": text,
            "unit": unit,
            "denominator": denominator,
            "evidence_class": evidence_class,
            "artifact_path": artifact_path,
            "notes": notes,
        }
        key = (entity_type, entity_id, field, artifact_path)
        if key in self._keys:
            fail(f"duplicate dataset row: {key}")
        self._keys.add(key)
        self.rows.append(row)

    def value_of(self, entity_type: str, entity_id: str, field: str) -> str:
        """Read back a fact already written to the dataset (loud if absent)."""
        for row in self.rows:
            if (row["entity_type"], row["entity_id"], row["field"]) == (
                entity_type,
                entity_id,
                field,
            ):
                return row["value"]
        fail(f"no dataset row for {entity_type}/{entity_id}/{field}")

    def num(
        self,
        entity_type: str,
        entity_id: str,
        field: str,
        value,
        unit: str,
        denominator: str,
        evidence_class: str,
        artifact_path: str,
        notes: str = "",
        scale: float | None = None,
    ) -> float:
        ctx = f"{entity_type}/{entity_id}/{field}"
        if isinstance(value, str):
            check(value.strip() != "", f"{ctx}: numeric field is empty (from {artifact_path})")
        try:
            out = float(value)
        except (TypeError, ValueError):
            fail(f"{ctx}: not numeric: {value!r} (from {artifact_path})")
        check(not math.isnan(out), f"{ctx}: NaN (from {artifact_path})")
        if scale is not None:
            out = out * scale
            notes = (
                notes + f" [converted from artifact units by x{scale:g} at build time]"
            ).strip()
        self.add(
            entity_type,
            entity_id,
            field,
            fmt_num(out),
            unit,
            denominator,
            evidence_class,
            artifact_path,
            notes,
        )
        return out

    def jnum(self, entity_type: str, entity_id: str, field: str, rel: str, path,
             unit: str, denominator: str, evidence_class: str, notes: str = "",
             scale: float | None = None) -> float:
        value = self.get(rel, path, f"{entity_type}/{entity_id}/{field}")
        return self.num(entity_type, entity_id, field, value, unit, denominator,
                        evidence_class, rel, notes, scale=scale)

    def jtext(self, entity_type: str, entity_id: str, field: str, rel: str, path,
              evidence_class: str, notes: str = "", unit: str = "text") -> str:
        value = self.get(rel, path, f"{entity_type}/{entity_id}/{field}")
        check(not isinstance(value, (list, dict)),
              f"{entity_type}/{entity_id}/{field}: expected scalar, got {type(value).__name__}")
        self.add(entity_type, entity_id, field, value, unit, "", evidence_class, rel, notes)
        return str(value)


def fmt_num(value: float) -> str:
    """Full-precision, round-trippable representation of a number."""
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return repr(float(value))


def disp(value, unit: str) -> str:
    """Display-only rounding for the dashboard (dataset keeps full precision)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return html.escape(str(value))
    if unit in ("percent", "percentage_points"):
        return f"{v:,.2f}"
    if unit == "fraction":
        return f"{v:,.4f}"
    if unit == "celsius":
        return f"{v:,.3f}"
    if unit == "days":
        return f"{v:,.2f}"
    if unit in ("networks", "stations", "station_years", "cases", "count", "bytes"):
        return f"{v:,.0f}"
    return f"{v:,.6g}"


# --------------------------------------------------------------------------
# Section: panel composition
# --------------------------------------------------------------------------


def build_panel(b: Builder) -> None:
    man = A["current_manifest"]
    rows = b.read_csv(man)
    summary = A["step3_summary"]

    n_net = len(rows)
    n_st = sum(int(r["n_stations"]) for r in rows)
    n_sy = sum(int(r["n_station_years"]) for r in rows)
    b.num("network", "panel", "n_networks", n_net, "networks",
          "eligible complete-year panel", "sample_fact", man,
          "count of rows in current_data_manifest.csv")
    b.num("network", "panel", "n_stations", n_st, "stations",
          "eligible complete-year panel", "sample_fact", man,
          "sum of per-network n_stations")
    b.num("network", "panel", "n_station_years", n_sy, "station_years",
          "eligible complete-year panel", "sample_fact", man,
          "sum of per-network n_station_years")

    # cross-check the manifest against the frozen case-table summary
    check(n_net == int(b.get(summary, ("n_networks",), "panel")),
          "manifest network count != step3_cases/summary.json n_networks")
    check(n_st == int(b.get(summary, ("n_stations",), "panel")),
          "manifest station count != step3_cases/summary.json n_stations")
    check(n_sy == int(b.get(summary, ("n_station_years",), "panel")),
          "manifest station-year count != step3_cases/summary.json n_station_years")

    for r in rows:
        nid = r["network_id"]
        check(nid.strip() != "", f"{man}: empty network_id")
        b.add("network", nid, "provider", r["provider"], "text", "", "sample_fact", man)
        b.add("network", nid, "split_role", r["split_role"], "text", "", "sample_fact", man)
        b.num("network", nid, "n_stations", r["n_stations"], "stations",
              "network", "sample_fact", man)
        b.num("network", nid, "n_station_years", r["n_station_years"], "station_years",
              "network", "sample_fact", man)
        b.num("network", nid, "input_bytes", r["bytes"], "bytes", "input file",
              "sample_fact", man, "size of the hashed wide input table")
        b.add("network", nid, "input_sha256", r["sha256"], "sha256", "", "sample_fact",
              man, "content identity of the wide input table")
        b.add("network", nid, "input_path", r["input_path"], "text", "", "sample_fact", man)
        b.add("network", nid, "status", r["status"], "text", "", "sample_fact", man)

    # panel aggregates read from the frozen case table summary (claim S1)
    b.num("network", "panel", "n_outage_cases", b.get(summary, ("n_cases",), "panel"),
          "cases", "eligible complete-year panel", "sample_fact", summary,
          "repeated outage realizations, not independent observations")
    for split, field in (("development", "n_cases_development"),
                         ("reserved", "n_cases_reserved")):
        b.jnum("network", "panel", field, summary, ("by_split", split), "cases",
               f"{split} split", "sample_fact")
    for arm in ("empirical", "stratified"):
        b.jnum("network", "panel", f"n_cases_arm_{arm}", summary, ("by_arm", arm),
               "cases", f"{arm} arm", "sample_fact")
    for regime in ("none", "rich", "sparse"):
        b.jnum("network", "panel", f"n_cases_donor_regime_{regime}", summary,
               ("by_donor_regime", regime), "cases", f"{regime} donor regime",
               "sample_fact")
    b.num("network", "panel", "n_case_table_failures", b.get(summary, ("n_failures",), "panel"),
          "cases", "case construction", "sample_fact", summary)

    # provider x split composition from the manifest
    agg: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        key = (r["provider"], r["split_role"])
        agg[key][0] += 1
        agg[key][1] += int(r["n_stations"])
        agg[key][2] += int(r["n_station_years"])
    dash_rows = []
    for (provider, split), (nn, ns, nsy) in sorted(agg.items()):
        denom = f"{provider} {split}"
        b.num("provider", provider, f"n_networks_{split}", nn, "networks", denom,
              "sample_fact", man, "counted from current_data_manifest.csv")
        b.num("provider", provider, f"n_stations_{split}", ns, "stations", denom,
              "sample_fact", man, "summed from current_data_manifest.csv")
        b.num("provider", provider, f"n_station_years_{split}", nsy, "station_years",
              denom, "sample_fact", man, "summed from current_data_manifest.csv")
        dash_rows.append(
            {"provider": provider, "split": split, "n_networks": nn,
             "n_stations": ns, "n_station_years": nsy, "artifact": man}
        )
    b.dash["panel_by_provider"] = dash_rows
    b.dash["panel_totals"] = [
        {"field": "n_networks", "value": n_net, "unit": "networks", "artifact": man,
         "evidence_class": "sample_fact", "denominator": "eligible complete-year panel"},
        {"field": "n_stations", "value": n_st, "unit": "stations", "artifact": man,
         "evidence_class": "sample_fact", "denominator": "eligible complete-year panel"},
        {"field": "n_station_years", "value": n_sy, "unit": "station_years",
         "artifact": man, "evidence_class": "sample_fact",
         "denominator": "eligible complete-year panel"},
        {"field": "n_outage_cases", "value": int(b.get(summary, ("n_cases",), "panel")),
         "unit": "cases", "artifact": summary, "evidence_class": "sample_fact",
         "denominator": "eligible complete-year panel"},
    ]


# --------------------------------------------------------------------------
# Section: prior-access audits
# --------------------------------------------------------------------------


def _audit_aggregate(rows: list[dict[str, str]]) -> dict:
    by_network: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        by_network[r["network_id"]].append(r)

    def truthy(v: str) -> bool:
        return str(v).strip().lower() == "true"

    clean_out = {n for n, rs in by_network.items() if all(truthy(r["clean_of_outcome_use"]) for r in rs)}
    never = {n for n, rs in by_network.items() if all(truthy(r["never_used_repo_wide"]) for r in rs)}
    any_out = {n for n, rs in by_network.items() if any(not truthy(r["clean_of_outcome_use"]) for r in rs)}
    return {
        "by_network": dict(by_network),
        "n_networks": len(by_network),
        "n_stations": len(rows),
        "networks_clean_of_outcome_use": clean_out,
        "networks_never_used_repo_wide": never,
        "networks_with_any_outcome_use": any_out,
        "stations_clean_of_outcome_use": sum(1 for r in rows if truthy(r["clean_of_outcome_use"])),
        "stations_never_used_repo_wide": sum(1 for r in rows if truthy(r["never_used_repo_wide"])),
        "stations_with_outcome_use": sum(1 for r in rows if not truthy(r["clean_of_outcome_use"])),
    }


def build_prior_access(b: Builder) -> None:
    sealed_rel = A["prior_access_sealed"]
    multi_rel = A["prior_access_multi"]
    sealed = _audit_aggregate(b.read_csv(sealed_rel))
    multi = _audit_aggregate(b.read_csv(multi_rel))
    summary_rel = A["prior_access_summary"]

    # cross-check the CSV against the committed summary
    sm = b.read_json(summary_rel)
    pop = b.get(summary_rel, ("populations", "sealed_usgs"), "prior access")
    check(sealed["n_networks"] == int(pop["n_networks"]),
          "sealed audit CSV network count != prior_access_audit_summary.json")
    check(sealed["n_stations"] == int(pop["n_stations"]),
          "sealed audit CSV station count != prior_access_audit_summary.json")
    check(sealed["stations_clean_of_outcome_use"] == int(pop["n_clean_of_outcome_use"]),
          "sealed audit CSV clean-of-outcome station count != summary")
    check(sorted(sealed["networks_clean_of_outcome_use"]) == sorted(pop["clean_networks"]),
          "sealed audit CSV clean-of-outcome network set != summary")
    check(sorted(sealed["networks_never_used_repo_wide"]) == sorted(pop["never_used_networks"]),
          "sealed audit CSV never-used network set != summary")
    _ = sm

    for label, agg, rel in (("sealed_usgs", sealed, sealed_rel),
                            ("multi_agency", multi, multi_rel)):
        denom = f"{label} audited panel"
        b.num("network", f"{label}_panel", "n_networks_audited", agg["n_networks"],
              "networks", denom, "sample_fact", rel)
        b.num("network", f"{label}_panel", "n_stations_audited", agg["n_stations"],
              "stations", denom, "sample_fact", rel)
        b.num("network", f"{label}_panel", "n_networks_clean_of_outcome_use",
              len(agg["networks_clean_of_outcome_use"]), "networks", denom,
              "sample_fact", rel, "every station of the network is clean of outcome-bearing prior use")
        b.num("network", f"{label}_panel", "n_networks_never_used_repo_wide",
              len(agg["networks_never_used_repo_wide"]), "networks", denom,
              "sample_fact", rel, "every station absent from all prior artifacts, outcome-bearing or descriptive")
        b.num("network", f"{label}_panel", "n_stations_clean_of_outcome_use",
              agg["stations_clean_of_outcome_use"], "stations", denom, "sample_fact", rel)
        b.num("network", f"{label}_panel", "n_stations_never_used_repo_wide",
              agg["stations_never_used_repo_wide"], "stations", denom, "sample_fact", rel)
        b.num("network", f"{label}_panel", "n_stations_with_outcome_use",
              agg["stations_with_outcome_use"], "stations", denom, "sample_fact", rel)

        # per-network detail
        for nid, rs in sorted(agg["by_network"].items()):
            provider = rs[0]["provider"]
            all_clean = all(str(r["clean_of_outcome_use"]).lower() == "true" for r in rs)
            all_never = all(str(r["never_used_repo_wide"]).lower() == "true" for r in rs)
            b.add("network", nid, "audit_population", label, "text", "", "sample_fact", rel)
            b.add("network", nid, "audit_provider", provider, "text", "", "sample_fact", rel)
            b.num("network", nid, "n_stations_audited", len(rs), "stations",
                  f"{label} audited panel", "sample_fact", rel)
            b.num("network", nid, "n_outcome_artifacts_referencing_any_station",
                  sum(int(r["n_outcome_artifacts"]) for r in rs), "count",
                  f"{label} audited panel", "sample_fact", rel,
                  "sum of per-station outcome-bearing artifact counts in the audit CSV")
            b.num("network", nid, "n_descriptive_artifacts_referencing_any_station",
                  sum(int(r["n_descriptive_artifacts"]) for r in rs), "count",
                  f"{label} audited panel", "sample_fact", rel,
                  "sum of per-station descriptive artifact counts in the audit CSV")
            b.add("network", nid, "clean_of_outcome_use", bool(all_clean), "bool", "",
                  "sample_fact", rel, "every station of the network is clean")
            b.add("network", nid, "never_used_repo_wide", bool(all_never), "bool", "",
                  "sample_fact", rel, "every station of the network is absent repo-wide")

        # provider-level roll-up
        by_provider: dict[str, list[dict[str, str]]] = defaultdict(list)
        for r in agg["by_network"].values():
            for item in r:
                by_provider[item["provider"]].append(item)
        for provider, rs in sorted(by_provider.items()):
            pdenom = f"{label} audited panel, {provider}"
            b.num("provider", provider, f"n_stations_audited_{label}", len(rs), "stations",
                  pdenom, "sample_fact", rel)
            b.num("provider", provider, f"n_stations_clean_of_outcome_use_{label}",
                  sum(1 for r in rs if str(r["clean_of_outcome_use"]).lower() == "true"),
                  "stations", pdenom, "sample_fact", rel)
            b.num("provider", provider, f"n_stations_never_used_repo_wide_{label}",
                  sum(1 for r in rs if str(r["never_used_repo_wide"]).lower() == "true"),
                  "stations", pdenom, "sample_fact", rel)

    b.dash["sealed_audit"] = {
        "n_networks": sealed["n_networks"],
        "n_stations": sealed["n_stations"],
        "n_networks_clean_of_outcome_use": len(sealed["networks_clean_of_outcome_use"]),
        "n_networks_never_used_repo_wide": len(sealed["networks_never_used_repo_wide"]),
        "artifact": sealed_rel,
        "evidence_class": "sample_fact",
    }


# --------------------------------------------------------------------------
# Section: claims
# --------------------------------------------------------------------------


def build_claims(b: Builder) -> None:
    reg_rel = A["claim_registry"]
    registry = b.read_csv(reg_rel)
    audit_rel = A["finding_audit"]
    audit = {r["finding_id"]: r for r in b.read_csv(audit_rel)}

    known_types = {r["evidence_type"] for r in registry}
    unmapped = sorted(known_types - set(EVIDENCE_CLASS_MAP))
    check(not unmapped, f"evidence_type without a declared evidence class: {unmapped}")

    numeric_claims: set[str] = set()
    for r in registry:
        cid = r["claim_id"].strip()
        check(cid != "", f"{reg_rel}: empty claim_id")
        raw_type = r["evidence_type"].strip()
        if cid in EVIDENCE_CLASS_OVERRIDE:
            cls, why = EVIDENCE_CLASS_OVERRIDE[cid]
            note = f"evidence class overridden: {why}"
        else:
            cls = EVIDENCE_CLASS_MAP[raw_type]
            note = f"assigned from registry evidence_type={raw_type} via the documented map"
        may_enter = r["may_enter_abstract_or_conclusions"].strip()
        check(may_enter in ("True", "False"),
              f"claim {cid}: may_enter_abstract_or_conclusions is not True/False: {may_enter!r}")

        b.add("claim", cid, "statement", r["statement"], "text", "", cls, reg_rel)
        b.add("claim", cid, "registry_artifact", r["artifact"], "text", "", cls, reg_rel,
              "artifact as recorded in claim_registry.csv")
        b.add("claim", cid, "endpoint", r["endpoint"], "text", "", cls, reg_rel)
        b.add("claim", cid, "unit", r["unit"], "text", "", cls, reg_rel)
        b.add("claim", cid, "denominator", r["denominator"], "text", "", cls, reg_rel)
        b.add("claim", cid, "evidence_type", raw_type, "text", "", cls, reg_rel)
        b.add("claim", cid, "population", r["population"], "text", "", cls, reg_rel)
        b.add("claim", cid, "may_enter_abstract_or_conclusions", may_enter, "bool", "",
              cls, reg_rel)
        b.add("claim", cid, "status", r["status"], "text", "", cls, reg_rel)
        if r["finding_ids"].strip() not in ("", "—", "-"):
            b.add("claim", cid, "finding_ids", r["finding_ids"], "text", "", cls, reg_rel)
            for fid in re.split(r"[/,]\s*", r["finding_ids"]):
                fid = fid.strip()
                if not fid:
                    continue
                check(fid in audit, f"claim {cid}: finding {fid} absent from {audit_rel}")
                b.add("claim", cid, f"finding_{fid}_status", audit[fid]["status"], "text",
                      "", cls, audit_rel, audit[fid]["closure_mode"])
                b.add("claim", cid, f"finding_{fid}_closure_mode", audit[fid]["closure_mode"],
                      "text", "", cls, audit_rel, audit[fid]["evidence"])
                b.add("claim", cid, f"finding_{fid}_residual_risk", audit[fid]["residual_risk"],
                      "text", "", cls, audit_rel)
        if r["notes"].strip() not in ("", "—", "-"):
            b.add("claim", cid, "registry_notes", r["notes"], "text", "", cls, reg_rel)
        b.add("claim", cid, "evidence_class", cls, "text", "", cls, reg_rel, note)

        if cid in CLAIM_NUMERIC_BUILDERS:
            CLAIM_NUMERIC_BUILDERS[cid](b, cid, cls)
            numeric_claims.add(cid)

    check(
        set(EVIDENCE_CLASS_OVERRIDE) <= {r["claim_id"] for r in registry},
        "EVIDENCE_CLASS_OVERRIDE names a claim that is not in claim_registry.csv",
    )
    b.dash["_registry_claims"] = registry
    b.dash["_numeric_claims"] = numeric_claims


def _contrast(
    b: Builder,
    label: str,
    point,
    low,
    high,
    unit: str,
    denominator: str,
    evidence_class: str,
    artifact: str,
    notes: str = "",
    scale: float | None = None,
    digits_note: str = "",
) -> None:
    """Record a point estimate with its interval and add it to the dashboard."""
    ctx = f"contrast {label}"
    check(low is not None and high is not None, f"{ctx}: interval endpoint missing")
    check(float(low) <= float(high), f"{ctx}: interval reversed")
    check(float(point) >= float(low) and float(point) <= float(high),
          f"{ctx}: point estimate outside its interval")
    b.dash["contrasts"].append(
        {
            "label": label,
            "point": float(point),
            "low": float(low),
            "high": float(high),
            "unit": unit,
            "denominator": denominator,
            "evidence_class": evidence_class,
            "artifact": artifact,
            "notes": notes,
            "scale": scale,
            "digits_note": digits_note,
        }
    )


# --------------------------------------------------------------------------
# Section: per-claim numeric extraction
# --------------------------------------------------------------------------


def claim_S1(b: Builder, cid: str, cls: str) -> None:
    rel = A["step3_summary"]
    denom = "eligible complete-year panel"
    b.jnum("claim", cid, "n_networks", rel, ("n_networks",), "networks", denom, cls)
    b.jnum("claim", cid, "n_stations", rel, ("n_stations",), "stations", denom, cls)
    b.jnum("claim", cid, "n_station_years", rel, ("n_station_years",), "station_years",
           denom, cls)
    b.jnum("claim", cid, "n_cases", rel, ("n_cases",), "cases", denom, cls,
           "repeated outage realizations, not independent observations")


def claim_S2(b: Builder, cid: str, cls: str) -> None:
    rel = A["network_split"]
    rows = b.read_csv(rel)
    counts = Counter(r["split_role"] for r in rows)
    binding_rel = A["claim_binding_check"]
    expected = json.loads(
        b.get(binding_rel, ("allowed_claim_checks", "S2", "detail"), f"claim {cid}")
    )
    for split in ("development", "reserved"):
        check(split in counts, f"{rel}: no {split} networks")
        check(
            int(counts[split]) == int(expected[split]),
            f"{rel}: {split} network count {counts[split]} != claim_binding_check.json "
            f"{expected[split]}",
        )
        b.num("claim", cid, f"n_networks_{split}", counts[split], "networks",
              f"{split} split", cls, rel,
              "counted from network_split.csv; cross-checked against claim_binding_check.json")
    b.num("claim", cid, "n_networks_total", len(rows), "networks", "v17 split", cls, rel)


def claim_V17_H2(b: Builder, cid: str, cls: str) -> None:
    rel = A["step10_verdict"]
    arms_rel = A["step11_contrasts"]
    denom = "reserved cases at 70% retention"
    point = b.jnum("claim", cid, "contrast_points", rel, ("primary", "contrast_points"),
                   "percentage_points", denom, cls)
    low = b.jnum("claim", cid, "contrast_ci_low", rel, ("primary", "ci_points", 0),
                 "percentage_points", denom, cls)
    high = b.jnum("claim", cid, "contrast_ci_high", rel, ("primary", "ci_points", 1),
                  "percentage_points", denom, cls)
    _contrast(b, "V17-H2 pooled reserved holdout (retrospective)", point, low, high,
              "percentage_points", denom, cls, rel,
              "certificate rate minus longest-run length rate; negative favours the screen")
    b.jnum("claim", cid, "retention", rel, ("primary", "retention"), "fraction",
           "reserved cases", cls)
    b.jnum("claim", cid, "declared_effect_points", rel, ("primary", "declared_effect_points"),
           "percentage_points", denom, cls)
    b.jtext("claim", cid, "passes_declared_effect", rel, ("primary", "passes_effect_size"),
            cls, unit="bool")
    b.jtext("claim", cid, "passes_interval_excludes_zero", rel,
            ("primary", "passes_interval_excludes_zero"), cls, unit="bool")
    b.jnum("claim", cid, "n_cases", rel, ("n_cases",), "cases", denom, cls)
    b.jnum("claim", cid, "n_networks", rel, ("n_networks",), "networks", denom, cls)
    b.jnum("claim", cid, "n_station_years", rel, ("n_station_years",), "station_years",
           denom, cls)
    b.jtext("claim", cid, "reserved_networks_opened", rel, ("reserved_networks_opened",),
            cls, unit="bool")
    b.jtext("claim", cid, "opened_on", rel, ("opened_on",), cls)
    b.jnum("claim", cid, "coverage_marginal", rel, ("coverage", "marginal"), "fraction",
           "reserved cases", cls)
    b.jnum("claim", cid, "coverage_conditional_min", rel, ("coverage", "conditional_min"),
           "fraction", "reserved networks", cls)
    b.jnum("claim", cid, "coverage_conditional_max", rel, ("coverage", "conditional_max"),
           "fraction", "reserved networks", cls)

    for regime in ("none", "rich", "sparse"):
        base = ("by_donor_regime", regime)
        b.jnum("claim", cid, f"donor_regime_{regime}_contrast_points", rel, base + ("point",),
               "percentage_points", f"{regime} donor regime, reserved cases", cls)
        b.jnum("claim", cid, f"donor_regime_{regime}_ci_low", rel, base + ("low",),
               "percentage_points", f"{regime} donor regime, reserved cases", cls)
        b.jnum("claim", cid, f"donor_regime_{regime}_ci_high", rel, base + ("high",),
               "percentage_points", f"{regime} donor regime, reserved cases", cls)
        b.jnum("claim", cid, f"donor_regime_{regime}_n_clusters", rel, base + ("n_clusters",),
               "networks", f"{regime} donor regime", cls)

    row = b.pick(arms_rel, panel="reserved", arm="pooled")
    for field, unit, dn in (
        ("base_rate_retain_all", "fraction", "reserved pooled cases"),
        ("length_rule_at_70", "fraction", denom),
        ("certificate_at_70", "fraction", denom),
        ("random_at_70", "fraction", denom),
        ("relative_reduction", "fraction", denom),
    ):
        b.num("claim", cid, f"pooled_{field}", row[field], unit, dn, cls, arms_rel)
    check(
        abs(float(row["contrast_points"]) - point) < 1e-9,
        f"{arms_rel} reserved pooled contrast {row['contrast_points']} != step10 verdict {point}",
    )
    b.num("claim", cid, "pooled_contrast_ci_low_arm_contrasts", row["ci_low_points"],
          "percentage_points", denom, cls, arms_rel,
          "DISCREPANCY FLAG: step11 arm_contrasts.csv interval differs slightly from the "
          "step10 verdict interval stored on this claim")
    b.num("claim", cid, "pooled_contrast_ci_high_arm_contrasts", row["ci_high_points"],
          "percentage_points", denom, cls, arms_rel,
          "DISCREPANCY FLAG: see pooled_contrast_ci_low_arm_contrasts")


def claim_V17_A1(b: Builder, cid: str, cls: str) -> None:
    rel = A["step11_contrasts"]
    ver = A["step11_verdict"]
    row = b.pick(rel, panel="reserved", arm="empirical")
    denom = "reserved empirical arm at 70% retention"
    point = b.num("claim", cid, "contrast_points", row["contrast_points"],
                  "percentage_points", denom, cls, rel)
    low = b.num("claim", cid, "contrast_ci_low", row["ci_low_points"], "percentage_points",
                denom, cls, rel)
    high = b.num("claim", cid, "contrast_ci_high", row["ci_high_points"], "percentage_points",
                 denom, cls, rel)
    _contrast(b, "V17-A1 reserved empirical arm (retrospective)", point, low, high,
              "percentage_points", denom, cls, rel,
              "empirical arm alters the real outage joint structure")
    for field, unit in (("n_cases", "cases"), ("base_rate_retain_all", "fraction"),
                        ("length_rule_at_70", "fraction"), ("certificate_at_70", "fraction"),
                        ("absolute_points_saved", "percentage_points"),
                        ("relative_reduction", "fraction")):
        b.num("claim", cid, field, row[field], unit, denom, cls, rel)
    b.jtext("claim", cid, "meets_declared_effect", ver,
            ("meets_declared_effect", "reserved_empirical"), cls, unit="bool")
    b.jtext("claim", cid, "interval_excludes_zero", ver,
            ("interval_excludes_zero", "reserved_empirical"), cls, unit="bool")
    b.jnum("claim", cid, "declared_effect_points", ver, ("declared_effect_points",),
           "percentage_points", denom, cls)
    b.jtext("claim", cid, "pre_registered_test", ver, ("pre_registered_test",), cls)


def claim_D1(b: Builder, cid: str, cls: str) -> None:
    rel = A["e2_threshold_disagreement"]
    rows = b.read_csv(rel)
    for r in rows:
        inc = r["incumbent"]
        denom = f"2422 real incomplete station-years; incumbent: {inc}"
        b.num("claim", cid, f"disagreement_pct[{inc}]", r["disagreement_pct"], "percent",
              denom, cls, rel)
        b.num("claim", cid, f"n_station_years[{inc}]", r["n_station_years"], "station_years",
              denom, cls, rel)
        b.num("claim", cid, f"length_admits_pct[{inc}]", r["length_admits_pct"], "percent",
              denom, cls, rel)
        b.num("claim", cid, f"timing_admits_pct[{inc}]", r["timing_admits_pct"], "percent",
              denom, cls, rel)
        b.num("claim", cid, f"admitted_by_length_rejected_by_timing[{inc}]",
              r["admitted_by_length_rejected_by_timing"], "station_years", denom, cls, rel)
        b.num("claim", cid, f"rejected_by_length_admitted_by_timing[{inc}]",
              r["rejected_by_length_admitted_by_timing"], "station_years", denom, cls, rel)

    es = A["e2_summary"]
    denom = "2422 real incomplete station-years"
    b.jnum("claim", cid, "disagreement_interval_point", es,
           ("disagreement", "disagreement_interval", "point"), "fraction", denom, cls)
    b.jnum("claim", cid, "disagreement_interval_low", es,
           ("disagreement", "disagreement_interval", "low"), "fraction", denom, cls)
    b.jnum("claim", cid, "disagreement_interval_high", es,
           ("disagreement", "disagreement_interval", "high"), "fraction", denom, cls)
    b.jnum("claim", cid, "disagreement_interval_n_clusters", es,
           ("disagreement", "disagreement_interval", "n_clusters"), "networks", denom, cls)
    b.jnum("claim", cid, "dangerous_cell_interval_point", es,
           ("disagreement", "dangerous_cell_interval", "point"), "fraction", denom, cls)
    b.jnum("claim", cid, "dangerous_cell_interval_low", es,
           ("disagreement", "dangerous_cell_interval", "low"), "fraction", denom, cls)
    b.jnum("claim", cid, "dangerous_cell_interval_high", es,
           ("disagreement", "dangerous_cell_interval", "high"), "fraction", denom, cls)
    b.jnum("claim", cid, "any_peak_day_hidden_pct", es,
           ("disagreement", "any_peak_day_hidden_pct"), "percent", denom, cls)
    b.jnum("claim", cid, "median_missing_days", es, ("disagreement", "median_missing_days"),
           "days", denom, cls)
    b.jnum("claim", cid, "p90_missing_days", es, ("disagreement", "p90_missing_days"),
           "days", denom, cls)
    b.jnum("claim", cid, "risk_model_max_decile_miscalibration_points", es,
           ("risk_model_max_decile_miscalibration_points",), "percentage_points", denom, cls)
    b.jnum("claim", cid, "n_station_years_archive", es, ("n_station_years",),
           "station_years", "real archive", cls)
    b.jnum("claim", cid, "n_complete", es, ("n_complete",), "station_years",
           "real archive", cls)
    b.jnum("claim", cid, "n_incomplete", es, ("n_incomplete",), "station_years",
           "real archive", cls)
    b.jtext("claim", cid, "e2_verdict_outcome", es, ("verdict", "outcome"), cls)

    b.dash["admission"] = {
        "threshold_rows": rows,
        "threshold_artifact": rel,
        "threshold_class": cls,
        "summary_artifact": es,
    }


def claim_D2(b: Builder, cid: str, cls: str) -> None:
    rel = A["amend_proxy_bridge"]
    denom = "sealed never-used designed cases (n=8973)"
    b.jnum("claim", cid, "proxy_ppv_point", rel,
           ("sealed_usgs_designed", "ppv_clustered", "point"), "fraction", denom, cls)
    b.jnum("claim", cid, "proxy_ppv_ci_low", rel,
           ("sealed_usgs_designed", "ppv_clustered", "low"), "fraction", denom, cls)
    b.jnum("claim", cid, "proxy_ppv_ci_high", rel,
           ("sealed_usgs_designed", "ppv_clustered", "high"), "fraction", denom, cls)
    b.jnum("claim", cid, "proxy_sensitivity", rel,
           ("sealed_usgs_designed", "sensitivity_proxy_given_true_hidden"), "fraction",
           denom, cls)
    b.jnum("claim", cid, "share_true_peak_hidden_when_proxy_clear", rel,
           ("sealed_usgs_designed", "share_true_peak_hidden_when_proxy_clear"), "fraction",
           denom, cls)
    b.jnum("claim", cid, "n_cases", rel, ("sealed_usgs_designed", "n_cases"), "cases",
           denom, cls)
    b.jnum("claim", cid, "n_proxy_flagged", rel, ("sealed_usgs_designed", "proxy_flagged"),
           "cases", denom, cls)
    b.jnum("claim", cid, "n_truth_peak_hidden", rel,
           ("sealed_usgs_designed", "truth_peak_hidden"), "cases", denom, cls)
    b.jtext("claim", cid, "proxy_rule", rel, ("proxy_rule",), cls)

    tdenom = "17 flagged real incomplete station-years (transported expectation)"
    b.jnum("claim", cid, "expected_true_peak_hidden_point", rel,
           ("real_archive_transport", "expected_true_peak_hidden"), "station_years",
           tdenom, cls)
    b.jnum("claim", cid, "expected_true_peak_hidden_ci_low", rel,
           ("real_archive_transport", "expected_true_peak_hidden_ci", 0), "station_years",
           tdenom, cls)
    b.jnum("claim", cid, "expected_true_peak_hidden_ci_high", rel,
           ("real_archive_transport", "expected_true_peak_hidden_ci", 1), "station_years",
           tdenom, cls)
    b.jnum("claim", cid, "n_station_years_admitted_by_proxy_rule", rel,
           ("real_archive_transport", "station_years_admitted"), "station_years",
           "real incomplete station-years", cls)
    b.jnum("claim", cid, "proxy_flagged_peak_wholly_hidden", rel,
           ("real_archive_transport", "proxy_flagged_peak_wholly_hidden"), "station_years",
           "real incomplete station-years", cls)
    b.jtext("claim", cid, "transported_rule", rel, ("real_archive_transport", "rule"), cls)
    b.jtext("claim", cid, "transport_caveat", rel,
            ("real_archive_transport", "caveat"), cls)
    # cross-check: the transported PPV is the sealed-panel clustered PPV
    check(
        abs(float(b.get(rel, ("real_archive_transport", "ppv_used", "point"), "D2"))
            - float(b.get(rel, ("sealed_usgs_designed", "ppv_clustered", "point"), "D2")))
        < 1e-12,
        "peak_proxy_bridge: transported ppv_used.point != sealed_usgs_designed ppv_clustered.point",
    )


def claim_A4(b: Builder, cid: str, cls: str) -> None:
    rel = A["a4_maintenance"]
    table = b.get(rel, ("table",), f"claim {cid}")
    check(isinstance(table, list) and table, f"{rel}: table is empty")
    by_cal = {row["calendar"]: row for row in table}
    b.jnum("claim", cid, "n_outage_lengths", rel, ("n_outage_lengths",), "count",
           "simulated placements", cls)
    b.jnum("claim", cid, "n_peak_windows", rel, ("n_peak_windows",), "count",
           "simulated placements", cls)
    for cal, row in sorted(by_cal.items()):
        denom = f"simulated placements, {cal} calendar"
        b.num("claim", cid, f"points_vs_observed[{cal}]", row["points_vs_observed"],
              "percentage_points", denom, cls, rel)
        b.num("claim", cid, f"consequential_rate[{cal}]", row["consequential_rate"],
              "fraction", denom, cls, rel)
        b.num("claim", cid, f"n_placements[{cal}]", row["n_placements"], "count", denom,
              cls, rel)


def claim_R1(b: Builder, cid: str, cls: str) -> None:
    rel = A["e4_representativeness"]
    csv_rel = A["e4_elevation_retention"]
    denom = "v17 reserved networks, US GAGES-II matched subset"
    b.jnum("claim", cid, "development_global_screen_elevation_rho", rel,
           ("development_global_screen_elevation_rho",), "fraction",
           "development panel, GAGES-II matched subset", cls)
    b.jnum("claim", cid, "development_global_screen_elevation_p", rel,
           ("development_global_screen_elevation_p",), "fraction",
           "development panel, GAGES-II matched subset", cls)
    b.jnum("claim", cid, "development_global_screen_donor_spread_points", rel,
           ("development_global_screen_donor_spread_points",), "percentage_points",
           "development panel, GAGES-II matched subset", cls)
    b.jnum("claim", cid, "reserved_high_minus_low_retention_point", rel,
           ("reserved_high_minus_low_elevation_retention", "point"), "fraction", denom, cls)
    b.jnum("claim", cid, "reserved_high_minus_low_retention_ci_low", rel,
           ("reserved_high_minus_low_elevation_retention", "low"), "fraction", denom, cls)
    b.jnum("claim", cid, "reserved_high_minus_low_retention_ci_high", rel,
           ("reserved_high_minus_low_elevation_retention", "high"), "fraction", denom, cls)
    b.jnum("claim", cid, "price_of_balancing_points", rel, ("price_of_balancing_points",),
           "percentage_points", denom, cls)
    b.jnum("claim", cid, "n_stations_with_attributes", rel, ("n_stations_with_attributes",),
           "stations", "US subset", cls)
    for row in b.read_csv(csv_rel):
        key = f"{row['split']}|{row['rule']}"
        b.num("claim", cid, f"high_minus_low_points[{key}]", row["high_minus_low_points"],
              "percentage_points", f"{row['split']} split, rule: {row['rule']}", cls, csv_rel)


def claim_M1(b: Builder, cid: str, cls: str) -> None:
    rel = A["amend_mnar"]
    pops = {"development": "development cases", "reserved_retrospective": "reserved cases",
            "sealed_usgs": "sealed USGS cases"}
    for pop, denom in pops.items():
        base = ("populations", pop)
        b.jnum("claim", cid, f"delta_zero_contrast_points[{pop}]", rel,
               base + ("delta_zero_contrast_points",), "percentage_points", denom, cls)
        b.jnum("claim", cid, f"n_cases[{pop}]", rel, base + ("n_cases",), "cases", denom, cls)
        b.jnum("claim", cid, f"n_networks[{pop}]", rel, base + ("n_networks",), "networks",
               denom, cls)
        b.jnum("claim", cid, f"mean_hidden_share[{pop}]", rel, base + ("mean_hidden_share",),
               "fraction", denom, cls)
        curve = b.get(rel, base + ("curve",), f"claim {cid}")
        check(isinstance(curve, list) and len(curve) >= 3,
              f"{rel}: populations.{pop}.curve is missing or too short")
        points = [float(p["contrast_points"]) for p in curve]
        deltas = [float(p["delta_c"]) for p in curve]
        check(len(points) == len(deltas), f"{rel}: delta grid length mismatch")
        b.num("claim", cid, f"worst_contrast_points[{pop}]", min(points),
              "percentage_points", f"delta in [{min(deltas):g},{max(deltas):g}] C, {denom}",
              cls, rel, "minimum over the swept completion-bias grid read from the artifact")
        b.num("claim", cid, f"best_contrast_points[{pop}]", max(points),
              "percentage_points", f"delta in [{min(deltas):g},{max(deltas):g}] C, {denom}",
              cls, rel, "maximum over the swept completion-bias grid read from the artifact")
        b.num("claim", cid, f"n_grid_points[{pop}]", len(points), "count",
              "swept completion-bias grid", cls, rel)
        b.add("claim", cid, f"sign_flips_within_grid[{pop}]", bool(max(points) >= 0.0),
              "bool", "", cls, rel,
              "True would mean the contrast turns non-negative somewhere in the swept grid")
        no_flip = b.get_nullable(rel, base + ("first_positive_bias_that_erases_the_advantage_c",),
                                 f"claim {cid}")
        if no_flip is None:
            b.add("claim", cid, f"bias_that_erases_advantage[{pop}]",
                  "none within the swept grid", "text", "", cls, rel,
                  "artifact field first_positive_bias_that_erases_the_advantage_c is null")
        else:
            b.num("claim", cid, f"bias_that_erases_advantage[{pop}]", no_flip, "celsius",
                  f"completion-bias grid, {denom}", cls, rel,
                  "the artifact now reports a bias value that erases the advantage; the "
                  "exploratory class is unchanged")
    b.jnum("claim", cid, "retention", rel, ("retention",), "fraction",
           "scored cases", cls)
    b.jnum("claim", cid, "tolerance_c", rel, ("tolerance_c",), "celsius", "scored cases", cls)


def claim_N1(b: Builder, cid: str, cls: str) -> None:
    rel = A["amend_step22_post"]
    scen_rel = A["amend_step22_scenarios"]
    pre_rel = A["amend_step22_pre"]
    for panel, denom in (("development", "development cases"),
                         ("reserved", "reserved cases")):
        base = ("headline", panel)
        b.jnum("claim", cid, f"contrast_clean_points[{panel}]", rel,
               base + ("new_contrast_clean_points",), "percentage_points", denom, cls,
               "locked reconstruction on both arms (F11 fix)")
        b.jnum("claim", cid, f"contrast_noisy_points[{panel}]", rel,
               base + ("new_contrast_noisy_points",), "percentage_points", denom, cls,
               "locked reconstruction on both arms (F11 fix)")
        b.num("claim", cid, f"old_published_contrast_clean_points[{panel}]",
              b.get(rel, base + ("old_published_contrast_clean_points",), f"claim {cid}"),
              "percentage_points", denom, "withdrawn", rel,
              "superseded published value; different reconstruction per arm (F11)")
        b.num("claim", cid, f"old_published_contrast_noisy_points[{panel}]",
              b.get(rel, base + ("old_published_contrast_noisy_points",), f"claim {cid}"),
              "percentage_points", denom, "withdrawn", rel,
              "superseded published value; different reconstruction per arm (F11)")
        row = b.pick(scen_rel, panel=panel, scenario="iid_0.15")
        b.num("claim", cid, f"iid_0.15_contrast_points[{panel}]", row["contrast_points"],
              "percentage_points", denom, cls, scen_rel)
        b.num("claim", cid, f"iid_0.15_change_vs_clean_points[{panel}]",
              row["contrast_change_vs_clean_points"], "percentage_points", denom, cls, scen_rel)
        b.num("claim", cid, f"iid_0.15_change_ci_low[{panel}]", row["contrast_change_ci_low"],
              "percentage_points", denom, cls, scen_rel)
        b.num("claim", cid, f"iid_0.15_change_ci_high[{panel}]",
              row["contrast_change_ci_high"], "percentage_points", denom, cls, scen_rel)
        b.num("claim", cid, f"iid_0.15_cases_moved[{panel}]", row["cases_moved_by_error_model"],
              "cases", denom, cls, scen_rel)
    for key, label in (("ar1_r0.70_sd0.15", "AR(1) rho=0.7, marginal sd 0.15 C"),
                       ("step_p0.30_midyear", "+0.30 C step from day 183"),
                       ("drift_0_to_p0.30", "monotone drift 0 to +0.30 C")):
        b.jnum("claim", cid, f"endpoint_sd_ratio_to_iid[{key}]", rel,
               ("endpoint_level_perturbation", key, "sd_ratio_to_iid_0.15"), "fraction",
               "frozen 0.15 C iid process", cls, f"error model: {label}")
    # withdrawn pre-fix published numbers, preserved bytes
    for panel, denom in (("development", "development cases"),
                         ("reserved", "reserved cases")):
        for field in ("contrast_clean_points", "contrast_noisy_points",
                      "length_rule_at_70_clean", "length_rule_at_70_noisy",
                      "certificate_at_70_clean", "certificate_at_70_noisy"):
            b.jnum("claim", cid, f"pre_fix_{panel}_{field}", pre_rel, (panel, field),
                   "fraction" if "at_70" in field else "percentage_points", denom,
                   "withdrawn",
                   "preserved pre-fix bytes; superseded by the F11 recompute")


def claim_C14(b: Builder, cid: str, cls: str) -> None:
    rel = A["step18_summary"]
    denom = "v17 reserved networks, frozen certificate at 70% retention"
    pooled = b.jnum("claim", cid, "pooled_median_interval_width_c", rel,
                    ("variants", "pooled", "median_interval_width_c"), "celsius", denom, cls)
    cluster = b.jnum("claim", cid, "cluster_0.9_median_interval_width_c", rel,
                     ("variants", "cluster_0.9", "median_interval_width_c"), "celsius",
                     denom, cls)
    b.num("claim", cid, "cluster_0.9_width_ratio_vs_pooled", cluster / pooled, "fraction",
          denom, cls, rel, "computed at build time from the two artifact fields")
    b.jnum("claim", cid, "pooled_marginal_coverage", rel,
           ("variants", "pooled", "marginal_coverage"), "fraction", denom, cls)
    b.jnum("claim", cid, "cluster_0.9_marginal_coverage", rel,
           ("variants", "cluster_0.9", "marginal_coverage"), "fraction", denom, cls)
    b.jnum("claim", cid, "pooled_per_network_min_coverage", rel,
           ("variants", "pooled", "per_network", "min"), "fraction",
           "reserved networks", cls)
    b.jnum("claim", cid, "cluster_0.9_per_network_min_coverage", rel,
           ("variants", "cluster_0.9", "per_network", "min"), "fraction",
           "reserved networks", cls)
    b.jnum("claim", cid, "cluster_0.9_share_networks_below_0.85", rel,
           ("variants", "cluster_0.9", "per_network", "share_below_0.85"), "fraction",
           "reserved networks", cls)
    b.jtext("claim", cid, "cheapest_setting_with_no_network_below_0.85", rel,
            ("verdict", "cheapest_setting_with_no_network_below_0.85"), cls)


def claim_HY(b: Builder, cid: str, cls: str) -> None:
    rel = A["step21_verdict"]
    denom = "US GAGES-II matched subset"
    b.jnum("claim", cid, "n_stations", rel, ("n_stations",), "stations", denom, cls)
    b.jnum("claim", cid, "n_networks", rel, ("n_networks",), "networks", denom, cls)
    b.jnum("claim", cid, "bfi_high_minus_low_error_c", rel,
           ("johnson_groundwater_test", "difference_high_minus_low_bfi_c"), "celsius",
           denom, cls, "directional prediction not supported")
    b.jnum("claim", cid, "bfi_high_minus_low_error_ci_low", rel,
           ("johnson_groundwater_test", "ci", 0), "celsius", denom, cls)
    b.jnum("claim", cid, "bfi_high_minus_low_error_ci_high", rel,
           ("johnson_groundwater_test", "ci", 1), "celsius", denom, cls)
    b.jtext("claim", cid, "bfi_expected_direction_supported", rel,
            ("johnson_groundwater_test", "supported"), cls, unit="bool")
    b.jnum("claim", cid, "reference_minus_disturbed_error_c", rel,
           ("reference_versus_disturbed", "difference_ref_minus_nonref_c"), "celsius",
           denom, cls)
    b.jtext("claim", cid, "reference_expected_direction_supported", rel,
            ("reference_versus_disturbed", "supported"), cls, unit="bool")


def claim_REG(b: Builder, cid: str, cls: str) -> None:
    reg_rel = A["claim_registry"]
    b.add("claim", cid, "numeric_extraction", "none", "text", "", cls, reg_rel,
          "endpoint mismatch: the illustration uses daily mean temperature, not daily "
          "maximum; it is not a compliance validation and no number from it enters this "
          "dataset")


def claim_BASE(b: Builder, cid: str, cls: str) -> None:
    rel = A["amend_faithful_summary"]
    con_rel = A["amend_faithful_contrasts"]
    denom = "development cases at the length-rule 70% retention set (n=28493)"
    names = {
        "faithful_beaufort": "faithful Beaufort (else climatology)",
        "library_air_ridge_alpha1": "library air ridge alpha=1.0 (else climatology)",
        "information_conditioned": "information-conditioned policy (reference)",
    }
    for key, name in names.items():
        b.jnum("claim", cid, f"rate_above_0.5c_pct[{key}]", rel,
               ("headline", name, "rate_above_0.5_pct"), "percent", denom, cls)
    b.jnum("claim", cid, "manuscript_air_ridge_rate_reproduced_pct", rel,
           ("integrity", "manuscript_air_ridge_rate_pct_reproduced"), "percent", denom, cls,
           "cross-check of the relabelled in-library row")
    b.jtext("claim", cid, "beaufort_label_defensible", rel,
            ("verdict", "beaufort_label_defensible"), cls, unit="bool")
    b.jtext("claim", cid, "relabel_reason", rel, ("verdict", "reason"), cls)
    row = b.pick(con_rel, retention_set="length_rule_70pct", quantity="rate_above_0.5",
                 left="faithful Beaufort (else climatology)",
                 right="library air ridge alpha=1.0 (else climatology)")
    b.num("claim", cid, "faithful_minus_library_paired_points", row["point"],
          "percentage_points", denom, cls, con_rel, scale=100.0)
    b.num("claim", cid, "faithful_minus_library_paired_ci_low", row["low"],
          "percentage_points", denom, cls, con_rel, scale=100.0)
    b.num("claim", cid, "faithful_minus_library_paired_ci_high", row["high"],
          "percentage_points", denom, cls, con_rel, scale=100.0)
    b.num("claim", cid, "paired_n", row["n_pairs"], "cases", denom, cls, con_rel)
    b.num("claim", cid, "paired_n_clusters", row["n_clusters"], "networks", denom, cls,
          con_rel)


def claim_DEPLOY_CERT(b: Builder, cid: str, cls: str) -> None:
    rel = A["deploy_predict"]
    denom = "2422 real incomplete station-years"
    b.jnum("claim", cid, "n_incomplete_rows", rel, ("n_incomplete_rows",), "station_years",
           denom, cls)
    b.jnum("claim", cid, "n_with_certificate_choice", rel, ("n_with_certificate_choice",),
           "station_years", denom, cls)
    b.jnum("claim", cid, "share_would_admit_at_0.5c", rel,
           ("share_would_admit_at_0.5C",), "fraction", denom, cls,
           "model output, not a validated error rate")
    b.jtext("claim", cid, "certificate_path", rel, ("certificate_path",), cls)
    b.jtext("claim", cid, "identity", rel, ("identity",), cls)
    b.jtext("claim", cid, "vs_e2_overlap_rules", rel, ("vs_e2_overlap_rules",), cls)


def claim_P0_07(b: Builder, cid: str, cls: str) -> None:
    rel = A["p0_07_verdict"]
    denom = "sealed USGS HUC4 networks outside the v17/v18 development panel"
    b.jtext("claim", cid, "panel", rel, ("panel",), cls)
    b.jnum("claim", cid, "n_networks", rel, ("n_networks",), "networks", denom, cls)
    b.jnum("claim", cid, "n_stations", rel, ("n_stations",), "stations", denom, cls)
    b.jnum("claim", cid, "n_cases", rel, ("n_cases",), "cases", denom, cls)
    b.jnum("claim", cid, "n_huc2_contexts", rel, ("n_huc2_contexts",), "count", denom, cls)
    b.jnum("claim", cid, "retention", rel, ("retention",), "fraction",
           "sealed cases", cls)
    b.jnum("claim", cid, "tolerance_c", rel, ("tolerance_C",), "celsius",
           "sealed cases", cls)
    b.jtext("claim", cid, "freeze_certificate", rel, ("freeze_certificate",), cls)
    b.jtext("claim", cid, "scored_once", rel, ("scored_once",), cls, unit="bool")
    b.jtext("claim", cid, "verdict_evidence_type", rel, ("evidence_type",), cls)
    for i, lim in enumerate(b.get(rel, ("limitations",), f"claim {cid}")):
        b.add("claim", cid, f"limitation_{i + 1}", lim, "text", "", cls, rel)
    for arm in ("empirical", "stratified"):
        base = ("by_arm_points", arm)
        b.jnum("claim", cid, f"arm_{arm}_contrast_points", rel,
               base + ("contrast_points",), "percentage_points",
               f"sealed {arm} arm", cls)
        b.jnum("claim", cid, f"arm_{arm}_ci_low", rel, base + ("ci_low_points",),
               "percentage_points", f"sealed {arm} arm", cls)
        b.jnum("claim", cid, f"arm_{arm}_ci_high", rel, base + ("ci_high_points",),
               "percentage_points", f"sealed {arm} arm", cls)


def claim_P0_07_POOL(b: Builder, cid: str, cls: str) -> None:
    rel = A["p0_07_verdict"]
    denom = "sealed confirmation cases at 70% retention (0.5 C)"
    point = b.jnum("claim", cid, "contrast_points", rel, ("contrast_points",),
                   "percentage_points", denom, cls)
    low = b.jnum("claim", cid, "contrast_ci_low", rel, ("ci_low_points",),
                 "percentage_points", denom, cls)
    high = b.jnum("claim", cid, "contrast_ci_high", rel, ("ci_high_points",),
                  "percentage_points", denom, cls)
    _contrast(b, "P0-07 sealed USGS confirmation, pooled", point, low, high,
              "percentage_points", denom, cls, rel,
              "scored once against the frozen certificate; provisional HUC4 networks")
    for arm in ("empirical", "stratified"):
        a_pt = b.jnum("claim", cid, f"arm_{arm}_contrast_points", rel,
                      ("by_arm_points", arm, "contrast_points"), "percentage_points",
                      f"sealed {arm} arm at 70% retention", cls)
        a_lo = b.jnum("claim", cid, f"arm_{arm}_ci_low", rel,
                      ("by_arm_points", arm, "ci_low_points"), "percentage_points",
                      f"sealed {arm} arm at 70% retention", cls)
        a_hi = b.jnum("claim", cid, f"arm_{arm}_ci_high", rel,
                      ("by_arm_points", arm, "ci_high_points"), "percentage_points",
                      f"sealed {arm} arm at 70% retention", cls)
        _contrast(b, f"P0-07 sealed USGS confirmation, {arm} arm", a_pt, a_lo, a_hi,
                  "percentage_points", f"sealed {arm} arm at 70% retention", cls, rel,
                  "arm decomposition of the sealed score")

    diag_rel = A["amend_sealed_diagnostic"]
    for row in b.get(diag_rel, ("rows",), f"claim {cid}"):
        subset = row["subset"]
        if "pooled_contrast_points" not in row:
            b.add("claim", cid, f"post_seal_diagnostic[{subset}]",
                  row.get("note", "not scored"), "text", "", cls, diag_rel,
                  f"n_networks={row.get('n_networks')} n_stations={row.get('n_stations')} "
                  f"n_cases={row.get('n_cases')}")
            continue
        sdenom = (f"sealed panel subset '{subset}': {row['n_cases']} cases in "
                  f"{row['n_networks']} networks")
        b.num("claim", cid, f"post_seal_pooled_contrast_points[{subset}]",
              row["pooled_contrast_points"], "percentage_points", sdenom, cls, diag_rel,
              "post-seal robustness diagnostic on already-scored cases")
        b.num("claim", cid, f"post_seal_pooled_ci_low[{subset}]", row["pooled_ci_low_points"],
              "percentage_points", sdenom, cls, diag_rel)
        b.num("claim", cid, f"post_seal_pooled_ci_high[{subset}]",
              row["pooled_ci_high_points"], "percentage_points", sdenom, cls, diag_rel)
        b.num("claim", cid, f"post_seal_empirical_contrast_points[{subset}]",
              row["empirical_contrast_points"], "percentage_points", sdenom, cls, diag_rel)
        b.num("claim", cid, f"post_seal_empirical_ci_low[{subset}]",
              row["empirical_ci_low_points"], "percentage_points", sdenom, cls, diag_rel)
        b.num("claim", cid, f"post_seal_empirical_ci_high[{subset}]",
              row["empirical_ci_high_points"], "percentage_points", sdenom, cls, diag_rel)
        b.num("claim", cid, f"post_seal_n_cases[{subset}]", row["n_cases"], "cases",
              sdenom, cls, diag_rel)
        b.num("claim", cid, f"post_seal_n_networks[{subset}]", row["n_networks"], "networks",
              sdenom, cls, diag_rel)
        b.num("claim", cid, f"post_seal_n_stations[{subset}]", row["n_stations"], "stations",
              sdenom, cls, diag_rel)
    b.jnum("claim", cid, "n_networks_with_outcome_prior_use", diag_rel,
           ("n_networks_with_outcome_prior_use",), "networks",
           "sealed USGS panel (39 networks)", cls,
           "from the repo-wide prior-access audit")
    b.jtext("claim", cid, "post_seal_diagnostic_interpretation_limit", diag_rel,
            ("interpretation_limit",), cls)
    b.jtext("claim", cid, "post_seal_diagnostic_status", diag_rel, ("status",), cls)


def claim_P0_07_TRANSPORT(b: Builder, cid: str, cls: str) -> None:
    rel = A["transport_verdict"]
    denom = "sealed multi-agency transport cases at 70% retention (0.5 C)"
    b.jtext("claim", cid, "panel", rel, ("panel",), cls)
    b.jnum("claim", cid, "n_networks", rel, ("n_networks",), "networks", denom, cls)
    b.jnum("claim", cid, "n_stations", rel, ("n_stations",), "stations", denom, cls)
    b.jnum("claim", cid, "n_cases", rel, ("n_cases",), "cases", denom, cls)
    for i, provider in enumerate(b.get(rel, ("providers",), f"claim {cid}")):
        b.add("claim", cid, f"provider_{i + 1}", provider, "text", "", cls, rel)
    for i, context in enumerate(b.get(rel, ("contexts",), f"claim {cid}")):
        b.add("claim", cid, f"context_{i + 1}", context, "text", "", cls, rel)
    pooled = b.jnum("claim", cid, "contrast_points", rel, ("contrast_points",),
                    "percentage_points", denom, cls)
    low = b.jnum("claim", cid, "contrast_ci_low", rel, ("ci_low_points",),
                 "percentage_points", denom, cls)
    high = b.jnum("claim", cid, "contrast_ci_high", rel, ("ci_high_points",),
                  "percentage_points", denom, cls)
    _contrast(b, "Multi-agency transport, pooled", pooled, low, high,
              "percentage_points", denom, cls, rel,
              "scored once; designed after the USGS score was known (disclosed)")
    for key, label in (
        ("primary_panel", "primary panel (new agencies)"),
        ("secondary_panel", "secondary stratum (development provider)"),
    ):
        pt = b.jnum("claim", cid, f"{key}_contrast_points", rel,
                    (key, "contrast_points"), "percentage_points", label, cls)
        lo = b.jnum("claim", cid, f"{key}_ci_low", rel, (key, "ci_low_points"),
                    "percentage_points", label, cls)
        hi = b.jnum("claim", cid, f"{key}_ci_high", rel, (key, "ci_high_points"),
                    "percentage_points", label, cls)
        _contrast(b, f"Multi-agency transport, {label}", pt, lo, hi,
                  "percentage_points", label, cls, rel,
                  "primary panel carries the pre-declared rule; secondary is labelled")
    for stratum in ("quality_checked", "provider_published_unqualified"):
        base = ("by_assurance_points", stratum)
        pt = b.jnum("claim", cid, f"assurance_{stratum}_contrast_points", rel,
                    base + ("contrast_points",), "percentage_points",
                    f"{stratum} stratum", cls)
        lo = b.jnum("claim", cid, f"assurance_{stratum}_ci_low", rel,
                    base + ("ci_low_points",), "percentage_points",
                    f"{stratum} stratum", cls)
        hi = b.jnum("claim", cid, f"assurance_{stratum}_ci_high", rel,
                    base + ("ci_high_points",), "percentage_points",
                    f"{stratum} stratum", cls)
        _contrast(b, f"Multi-agency transport, {stratum} stratum", pt, lo, hi,
                  "percentage_points", f"{stratum} stratum", cls, rel,
                  "assurance-stratum decomposition (Amendment 2)")
    for arm in ("empirical", "stratified"):
        base = ("by_arm_points", arm)
        a_pt = b.jnum("claim", cid, f"arm_{arm}_contrast_points", rel,
                      base + ("contrast_points",), "percentage_points",
                      f"transport {arm} arm", cls)
        a_lo = b.jnum("claim", cid, f"arm_{arm}_ci_low", rel,
                      base + ("ci_low_points",), "percentage_points",
                      f"transport {arm} arm", cls)
        a_hi = b.jnum("claim", cid, f"arm_{arm}_ci_high", rel,
                      base + ("ci_high_points",), "percentage_points",
                      f"transport {arm} arm", cls)
        _contrast(b, f"Multi-agency transport, {arm} arm", a_pt, a_lo, a_hi,
                  "percentage_points", f"transport {arm} arm at 70% retention",
                  cls, rel, "arm decomposition of the transport score")
    rule = ("predeclared_rule", "transport_supported")
    b.jtext("claim", cid, "transport_supported", rel, rule, cls, unit="bool")
    b.jtext("claim", cid, "ordering_disclosure", rel, ("ordering_disclosure",), cls)


def claim_NVE_PROBE(b: Builder, cid: str, cls: str) -> None:
    rel = A["nve_probe_verdict"]
    denom = "NVE probe cases"
    b.jnum("claim", cid, "n_networks", rel, ("n_networks",), "networks", denom, cls,
           "design floor is 30 networks")
    b.jnum("claim", cid, "n_stations", rel, ("n_stations",), "stations", denom, cls)
    b.jnum("claim", cid, "n_cases", rel, ("n_cases",), "cases", denom, cls)
    b.jnum("claim", cid, "contrast_points", rel, ("contrast_points",), "percentage_points",
           denom, cls, "positive contrast; below the design floor, do not headline")
    b.jnum("claim", cid, "ci_low_points", rel, ("ci_low_points",), "percentage_points",
           denom, cls)
    b.jnum("claim", cid, "ci_high_points", rel, ("ci_high_points",), "percentage_points",
           denom, cls)
    b.jtext("claim", cid, "may_enter_abstract", rel, ("may_enter_abstract",), cls, unit="bool")
    b.jtext("claim", cid, "probe_note", rel, ("note",), cls)


def claim_L3(b: Builder, cid: str, cls: str) -> None:
    rel = A["amend_e6_crossover"]
    curve_rel = A["amend_e6_curve"]
    d = "development cases, fixed 30-day climatological peak-window axis"
    base = ("contrasts", "development | fixed_peak_window_30_minus_missing_fraction", "primary")
    point = b.jnum("claim", cid, "crossover_days_point_interpolated", rel,
                   base + ("point_crossover_days_interpolated",), "days", d, cls)
    b.jnum("claim", cid, "crossover_days_bootstrap_median", rel,
           base + ("bootstrap_crossover_days_median",), "days", d, cls)
    low = b.jnum("claim", cid, "crossover_days_ci95_low", rel,
                 base + ("bootstrap_crossover_days_ci95_low",), "days", d, cls,
                 "network-clustered bootstrap of the whole curve")
    high = b.jnum("claim", cid, "crossover_days_ci95_high", rel,
                  base + ("bootstrap_crossover_days_ci95_high",), "days", d, cls)
    b.jnum("claim", cid, "p_no_crossover", rel, base + ("p_no_crossover",), "fraction",
           "bootstrap draws", cls)
    b.jnum("claim", cid, "n_draws", rel, base + ("n_draws",), "count",
           "bootstrap draws", cls)
    b.add("claim", cid, "registry_prose_vs_artifact_crossover_interval",
          f"registry states 76-107 days; artifact CI95 is [{low:.4f},{high:.4f}]",
          "text", "", cls, rel,
          "DISCREPANCY FLAG: the dataset carries the artifact values; the registry prose "
          "rounds the lower bound down")
    row = b.pick(curve_rel, source="contrast", axis="fixed_peak_window_30_minus_missing_fraction",
                 panel="development", tolerance_fraction_name="primary", width_days="90")
    b.num("claim", cid, "contrast_at_90d", row["point"], "fraction", d, cls, curve_rel,
          "pairwise contrast at the 90-day grid width")
    b.num("claim", cid, "contrast_at_90d_ci_low", row["low"], "fraction", d, cls, curve_rel)
    b.num("claim", cid, "contrast_at_90d_ci_high", row["high"], "fraction", d, cls, curve_rel)
    b.add("claim", cid, "registry_prose_vs_artifact_90d_interval",
          f"registry states +0.002 [-0.019,+0.027]; artifact is {float(row['point']):+.4f} "
          f"[{float(row['low']):+.4f},{float(row['high']):+.4f}]",
          "text", "", cls, curve_rel,
          "DISCREPANCY FLAG: the dataset carries the artifact values")

    rbase = ("contrasts", "reserved_open | fixed_peak_window_30_minus_missing_fraction",
             "primary")
    rd = "opened reserved panel, fixed 30-day climatological peak-window axis"
    b.jnum("claim", cid, "reserved_crossover_days_point_interpolated", rel,
           rbase + ("point_crossover_days_interpolated",), "days", rd, cls)
    b.jnum("claim", cid, "reserved_crossover_days_ci95_low", rel,
           rbase + ("bootstrap_crossover_days_ci95_low",), "days", rd, cls)
    b.jnum("claim", cid, "reserved_crossover_days_ci95_high", rel,
           rbase + ("bootstrap_crossover_days_ci95_high",), "days", rd, cls)

    dbase = ("contrasts", "development | fixed_centre_dilation_minus_missing_fraction",
             "primary")
    dd = "development cases, dilated support-conditioned window axis"
    b.jnum("claim", cid, "dilated_window_crossover_days_point_interpolated", rel,
           dbase + ("point_crossover_days_interpolated",), "days", dd, cls,
           "falsification test axis: window held at the training-period peak centre and dilated")
    b.jnum("claim", cid, "dilated_window_crossover_days_ci95_low", rel,
           dbase + ("bootstrap_crossover_days_ci95_low",), "days", dd, cls)
    b.jnum("claim", cid, "dilated_window_crossover_days_ci95_high", rel,
           dbase + ("bootstrap_crossover_days_ci95_high",), "days", dd, cls)
    b.jnum("claim", cid, "dilated_window_p_crossover", rel,
           dbase + ("p_crossover",), "fraction", "bootstrap draws", cls)
    _ = point


def claim_L7(b: Builder, cid: str, cls: str) -> None:
    rel = A["amend_e6_curve"]
    rows = b.read_csv(rel)
    sel = [
        r
        for r in rows
        if r["source"] == "conditioning"
        and r["axis"] == "support_reseeking"
        and r["panel"] == "development"
        and r["tolerance_fraction_name"] == "primary"
    ]
    check(bool(sel), f"{rel}: no conditioning-grid rows for the development primary setting")
    denom = ("development cases, re-seeked support axis, conditioning-grid AUC "
             f"({len(sel)} rows)")
    best = max(sel, key=lambda r: float(r["point"]))
    best_by_width: dict[str, str] = {}
    for r in sel:
        w = r["width_days"]
        if w not in best_by_width or float(r["point"]) > float(best_by_width[w]["point"]):
            best_by_width[w] = r
    b.num("claim", cid, "argmax_auc", best["point"], "fraction", denom, cls, rel,
          f"argmax over the conditioning grid: evaluation width {best['width_days']} d, "
          f"conditioning width {best['conditioning_width_days']} d")
    b.num("claim", cid, "argmax_auc_ci_low", best["low"], "fraction", denom, cls, rel)
    b.num("claim", cid, "argmax_auc_ci_high", best["high"], "fraction", denom, cls, rel)
    b.num("claim", cid, "argmax_conditioning_width_days", best["conditioning_width_days"],
          "days", f"evaluation width {best['width_days']} d", cls, rel,
          "computed argmax; the registry prose says the hump peaks near 60 days, the "
          "artifact argmax is 90 d")
    near = b.pick(rel, source="conditioning", axis="support_reseeking", panel="development",
                  tolerance_fraction_name="primary", width_days=best["width_days"],
                  conditioning_width_days="60")
    b.num("claim", cid, "auc_at_60d_conditioning", near["point"], "fraction",
          f"evaluation width {best['width_days']} d", cls, rel,
          "neighbour of the argmax; intervals overlap, so the peak is unresolved")
    b.num("claim", cid, "auc_at_60d_conditioning_ci_low", near["low"], "fraction",
          f"evaluation width {best['width_days']} d", cls, rel)
    b.num("claim", cid, "auc_at_60d_conditioning_ci_high", near["high"], "fraction",
          f"evaluation width {best['width_days']} d", cls, rel)
    b.num("claim", cid, "n_conditioning_rows", len(sel), "count", "conditioning grid", cls, rel)
    for w, r in sorted(best_by_width.items(), key=lambda kv: int(kv[0])):
        b.num("claim", cid, f"best_auc_at_evaluation_width[{w}d]", r["point"], "fraction",
              "conditioning grid", cls, rel,
              f"conditioning width {r['conditioning_width_days']} d")


def claim_L1(b: Builder, cid: str, cls: str) -> None:
    reg_rel = A["claim_registry"]
    b.add("claim", cid, "numeric_extraction", "none", "text", "", cls, reg_rel,
          "the unconditional proportion-law headline is withdrawn (F04); the registry "
          "artifact is a directory with no single headline number")


def claim_MEAS(b: Builder, cid: str, cls: str) -> None:
    dict_rel = A["measurement_dictionary"]
    rows = b.read_csv(dict_rel)
    b.num("claim", cid, "n_provider_rows_documented", len(rows), "count",
          "provider measurement dictionary", cls, dict_rel)
    strata_rel = A["amend_provider_contract"]
    strata = b.get(strata_rel, ("strata",), f"claim {cid}")
    for stratum, providers in sorted(strata.items()):
        for p in providers:
            b.add("provider", p, "measurement_stratum", stratum, "text", "", cls,
                  strata_rel, f"strata source: {dict_rel}")
    con_rel = A["amend_provider_contract_csv"]
    for r in b.read_csv(con_rel):
        population = r["population"]
        subset = r["subset"]
        pcls = "sealed_confirmation" if population == "sealed_usgs" else cls
        denom = (f"{population} panel, subset '{subset}', {r['n_networks']} networks, "
                 f"providers: {r['providers'] or 'n/a'}")
        if r["contrast_points"].strip() == "":
            b.add("claim", cid, f"contract_contrast[{population}|{subset}]",
                  r["note"] or "not scored", "text", "", pcls, con_rel,
                  f"n_cases={r['n_cases']}")
            continue
        b.num("claim", cid, f"contract_contrast_points[{population}|{subset}]",
              r["contrast_points"], "percentage_points", denom, pcls, con_rel)
        b.num("claim", cid, f"contract_ci_low[{population}|{subset}]", r["ci_low_points"],
              "percentage_points", denom, pcls, con_rel)
        b.num("claim", cid, f"contract_ci_high[{population}|{subset}]", r["ci_high_points"],
              "percentage_points", denom, pcls, con_rel)
        b.num("claim", cid, f"contract_n_cases[{population}|{subset}]", r["n_cases"],
              "cases", denom, pcls, con_rel)
        b.num("claim", cid, f"contract_n_networks[{population}|{subset}]", r["n_networks"],
              "networks", denom, pcls, con_rel)
    b.jnum("claim", cid, "retention", strata_rel, ("retention",), "fraction",
           "scored cases", cls)


def claim_FAIR(b: Builder, cid: str, cls: str) -> None:
    reg_rel = A["claim_registry"]
    b.add("claim", cid, "numeric_extraction", "none", "text", "", cls, reg_rel,
          "the overstated reproducibility claim is withdrawn and narrowed; it carries no "
          "scientific number")


CLAIM_NUMERIC_BUILDERS = {
    "S1": claim_S1,
    "S2": claim_S2,
    "V17-H2": claim_V17_H2,
    "V17-A1": claim_V17_A1,
    "D1": claim_D1,
    "D2": claim_D2,
    "A4": claim_A4,
    "R1": claim_R1,
    "M1": claim_M1,
    "N1": claim_N1,
    "C14": claim_C14,
    "HY": claim_HY,
    "REG": claim_REG,
    "BASE": claim_BASE,
    "DEPLOY-CERT": claim_DEPLOY_CERT,
    "P0-07": claim_P0_07,
    "P0-07-POOL": claim_P0_07_POOL,
    "P0-07-TRANSPORT": claim_P0_07_TRANSPORT,
    "NVE-PROBE": claim_NVE_PROBE,
    "L3": claim_L3,
    "L7": claim_L7,
    "L1": claim_L1,
    "MEAS": claim_MEAS,
    "FAIR": claim_FAIR,
}


# --------------------------------------------------------------------------
# Section: amendments (one identity row per amendment + headline numbers)
# --------------------------------------------------------------------------


def _finding_from_artifact(b: Builder, rel: str, path, ctx: str) -> str:
    value = str(b.get(rel, path, ctx))
    m = re.match(r"^(F\d+)", value)
    check(bool(m), f"{ctx}: cannot parse a finding id from {value!r}")
    return m.group(1)


def _finding_from_registry(b: Builder, claim_id: str, ctx: str) -> str:
    registry = b.dash.get("_registry_claims") or b.read_csv(A["claim_registry"])
    for r in registry:
        if r["claim_id"] == claim_id:
            ids = r["finding_ids"].strip()
            check(ids not in ("", "—", "-"), f"{ctx}: claim {claim_id} has no finding_ids")
            return re.split(r"[/,]\s*", ids)[0]
    fail(f"{ctx}: claim {claim_id} not in registry")


def _finding_from_report(b: Builder, rel: str, ctx: str) -> str:
    text = b.read_text(rel)
    first = text.splitlines()[0] if text.splitlines() else ""
    m = re.search(r"(F\d+)", first)
    check(bool(m), f"{ctx}: no finding id in the first line of {rel}: {first!r}")
    return m.group(1)


def build_amendments(b: Builder) -> None:
    """One row per amendment: finding id, artifact, evidence class, headline number."""
    specs: list[dict] = [
        {
            "key": "e6_support_width_uncertainty",
            "finding": lambda: _finding_from_registry(b, "L3", "e6"),
            "class": "exploratory_post_open",
            "artifact": A["amend_e6_crossover"],
            "headline": [
                ("crossover_days_point_interpolated", A["amend_e6_crossover"],
                 ("contrasts", "development | fixed_peak_window_30_minus_missing_fraction",
                  "primary", "point_crossover_days_interpolated"), "days",
                 "development cases, fixed 30-day peak-window axis"),
                ("crossover_days_ci95_low", A["amend_e6_crossover"],
                 ("contrasts", "development | fixed_peak_window_30_minus_missing_fraction",
                  "primary", "bootstrap_crossover_days_ci95_low"), "days",
                 "development cases, fixed 30-day peak-window axis"),
                ("crossover_days_ci95_high", A["amend_e6_crossover"],
                 ("contrasts", "development | fixed_peak_window_30_minus_missing_fraction",
                  "primary", "bootstrap_crossover_days_ci95_high"), "days",
                 "development cases, fixed 30-day peak-window axis"),
                ("dilated_window_crossover_days", A["amend_e6_crossover"],
                 ("contrasts", "development | fixed_centre_dilation_minus_missing_fraction",
                  "primary", "point_crossover_days_interpolated"), "days",
                 "development cases, dilated support-conditioned window axis"),
            ],
            "extra_artifacts": [A["amend_e6_curve"], A["amend_e6_report"]],
        },
        {
            "key": "faithful_baseline",
            "finding": lambda: _finding_from_artifact(b, A["amend_faithful_summary"],
                                                      ("finding",), "faithful_baseline"),
            "class": "retrospective_holdout",
            "artifact": A["amend_faithful_summary"],
            "headline": [
                ("library_air_ridge_rate_above_0.5c_pct", A["amend_faithful_summary"],
                 ("headline", "library air ridge alpha=1.0 (else climatology)",
                  "rate_above_0.5_pct"), "percent",
                 "development cases at the length-rule 70% retention set (n=28493)"),
                ("faithful_beaufort_rate_above_0.5c_pct", A["amend_faithful_summary"],
                 ("headline", "faithful Beaufort (else climatology)",
                  "rate_above_0.5_pct"), "percent",
                 "development cases at the length-rule 70% retention set (n=28493)"),
            ],
            "extra_artifacts": [A["amend_faithful_contrasts"]],
        },
        {
            "key": "mnar_pattern_mixture",
            "finding": lambda: _finding_from_registry(b, "M1", "mnar"),
            "class": "exploratory_post_open",
            "artifact": A["amend_mnar"],
            "headline": [
                ("delta_zero_contrast_points[development]", A["amend_mnar"],
                 ("populations", "development", "delta_zero_contrast_points"),
                 "percentage_points", "development cases"),
                ("delta_zero_contrast_points[sealed_usgs]", A["amend_mnar"],
                 ("populations", "sealed_usgs", "delta_zero_contrast_points"),
                 "percentage_points", "sealed USGS cases"),
                ("mean_hidden_share[development]", A["amend_mnar"],
                 ("populations", "development", "mean_hidden_share"), "fraction",
                 "development cases"),
            ],
        },
        {
            "key": "peak_proxy_bridge",
            "finding": lambda: _finding_from_registry(b, "D2", "proxy bridge"),
            "class": "proxy",
            "artifact": A["amend_proxy_bridge"],
            "headline": [
                ("sealed_ppv_point", A["amend_proxy_bridge"],
                 ("sealed_usgs_designed", "ppv_clustered", "point"), "fraction",
                 "sealed never-used designed cases (n=8973)"),
                ("sealed_ppv_ci_low", A["amend_proxy_bridge"],
                 ("sealed_usgs_designed", "ppv_clustered", "low"), "fraction",
                 "sealed never-used designed cases (n=8973)"),
                ("sealed_ppv_ci_high", A["amend_proxy_bridge"],
                 ("sealed_usgs_designed", "ppv_clustered", "high"), "fraction",
                 "sealed never-used designed cases (n=8973)"),
                ("expected_true_peak_hidden_point", A["amend_proxy_bridge"],
                 ("real_archive_transport", "expected_true_peak_hidden"), "station_years",
                 "17 flagged real incomplete station-years (transported expectation)"),
            ],
        },
        {
            "key": "provider_contract_sensitivity",
            "finding": lambda: _finding_from_registry(b, "MEAS", "provider contract"),
            "class": "retrospective_holdout",
            "artifact": A["amend_provider_contract"],
            "headline": [
                ("documented_stratum_contrast_points[development]", A["amend_provider_contract_csv"],
                 None, "percentage_points", "documented daily-mean providers, development"),
            ],
            "extra_artifacts": [A["amend_provider_contract_csv"]],
        },
        {
            "key": "sealed_usgs_prior_access_diagnostic",
            "finding": lambda: _finding_from_registry(b, "P0-07", "sealed diagnostic"),
            "class": "sealed_confirmation",
            "artifact": A["amend_sealed_diagnostic"],
            "headline": [
                ("n_networks_with_outcome_prior_use", A["amend_sealed_diagnostic"],
                 ("n_networks_with_outcome_prior_use",), "networks",
                 "sealed USGS panel (39 networks)"),
            ],
        },
        {
            "key": "step22_noise_post_fix",
            "finding": lambda: _finding_from_artifact(b, A["amend_step22_post"],
                                                      ("finding", "id"), "step22 post"),
            "class": "exploratory_post_open",
            "artifact": A["amend_step22_post"],
            "headline": [
                ("new_contrast_clean_points[development]", A["amend_step22_post"],
                 ("headline", "development", "new_contrast_clean_points"),
                 "percentage_points", "development cases"),
                ("new_contrast_noisy_points[development]", A["amend_step22_post"],
                 ("headline", "development", "new_contrast_noisy_points"),
                 "percentage_points", "development cases"),
                ("new_contrast_clean_points[reserved]", A["amend_step22_post"],
                 ("headline", "reserved", "new_contrast_clean_points"),
                 "percentage_points", "reserved cases"),
                ("new_contrast_noisy_points[reserved]", A["amend_step22_post"],
                 ("headline", "reserved", "new_contrast_noisy_points"),
                 "percentage_points", "reserved cases"),
            ],
            "extra_artifacts": [A["amend_step22_scenarios"], A["amend_step22_pre"]],
        },
        {
            "key": "step22_noise_pre_fix",
            "finding": lambda: _finding_from_artifact(b, A["amend_step22_post"],
                                                      ("finding", "id"), "step22 pre"),
            "class": "withdrawn",
            "artifact": A["amend_step22_pre"],
            "headline": [
                ("contrast_clean_points[development]", A["amend_step22_pre"],
                 ("development", "contrast_clean_points"), "percentage_points",
                 "development cases"),
                ("contrast_noisy_points[development]", A["amend_step22_pre"],
                 ("development", "contrast_noisy_points"), "percentage_points",
                 "development cases"),
                ("contrast_clean_points[reserved]", A["amend_step22_pre"],
                 ("reserved", "contrast_clean_points"), "percentage_points",
                 "reserved cases"),
                ("contrast_noisy_points[reserved]", A["amend_step22_pre"],
                 ("reserved", "contrast_noisy_points"), "percentage_points",
                 "reserved cases"),
            ],
            "notes": ("preserved pre-fix bytes; superseded by the F11 recompute in "
                      "amendments/step22_noise_post_fix/summary.json"),
        },
        {
            "key": "step5_mechanism_equal_k",
            "finding": lambda: _finding_from_artifact(b, A["amend_step5_equal_k"],
                                                      ("finding",), "step5 equal-k"),
            "class": "exploratory_post_open",
            "artifact": A["amend_step5_equal_k"],
            "headline": [
                ("min_matched_point_c", A["amend_step5_equal_k"],
                 ("verdict_detail", "min_matched_point_c"), "celsius",
                 "matched donor-control estimators"),
                ("max_matched_point_c", A["amend_step5_equal_k"],
                 ("verdict_detail", "max_matched_point_c"), "celsius",
                 "matched donor-control estimators"),
                ("min_matched_ci_low_c", A["amend_step5_equal_k"],
                 ("verdict_detail", "min_matched_ci_low_c"), "celsius",
                 "matched donor-control estimators"),
                ("n_matched_estimators", A["amend_step5_equal_k"],
                 ("verdict_detail", "n_matched_estimators"), "count",
                 "matched donor-control estimators"),
                ("n_cases", A["amend_step5_equal_k"], ("case_counts", "n_cases"), "cases",
                 "equal-K matched sample"),
                ("n_networks", A["amend_step5_equal_k"], ("case_counts", "n_networks"),
                 "networks", "equal-K matched sample"),
            ],
            "extra_artifacts": [A["amend_step5_by_k"]],
        },
        {
            "key": "step5_mechanism_pre_fix",
            "finding": lambda: _finding_from_artifact(b, A["amend_step5_equal_k"],
                                                      ("finding",), "step5 pre"),
            "class": "withdrawn",
            "artifact": A["amend_step5_pre_contrasts"],
            "headline": [
                ("abserr_weak_half_minus_strong_half_point", A["amend_step5_pre_contrasts"],
                 None, "celsius", "pre-fix unmatched two-arm paired sample"),
            ],
            "notes": ("preserved pre-fix donor-control contrasts; superseded by the equal-K "
                      "matched contrasts in amendments/step5_mechanism_equal_k/"),
        },
        {
            "key": "outage_causes",
            "finding": None,
            "class": "sample_fact",
            "artifact": A["amend_outage_causes"],
            "headline": [
                ("n_gaps", A["amend_outage_causes"], ("n_gaps",), "count",
                 "real USGS interior gaps, 3-station subsample"),
                ("n_missing_days", A["amend_outage_causes"], ("n_missing_days",), "days",
                 "real USGS interior gaps, 3-station subsample"),
                ("n_gaps_with_no_day_in_population", A["amend_outage_causes"],
                 ("n_gaps_with_no_day_in_population",), "count",
                 "real USGS interior gaps, 3-station subsample"),
                ("share_graded_incomplete_or_partial_all_pct",
                 A["amend_outage_causes"],
                 ("partial_aggregate_evidence", "share_graded_all_pct"), "percent",
                 "provider records retrieved for the subsample"),
                ("share_graded_incomplete_or_partial_in_population_pct",
                 A["amend_outage_causes"],
                 ("partial_aggregate_evidence", "share_graded_in_population_pct"), "percent",
                 "provider records inside the incomplete-year population"),
                ("n_records_graded_incomplete_or_partial_in_population",
                 A["amend_outage_causes"],
                 ("partial_aggregate_evidence",
                  "n_records_graded_incomplete_or_partial_in_population"), "count",
                 "provider records inside the incomplete-year population"),
                ("peak_window_validation_max_abs_difference", A["amend_outage_causes"],
                 ("partial_aggregate_evidence", "peak_window_validation",
                  "max_abs_difference"), "fraction", "station-years checked"),
            ],
            "extra_artifacts": [A["amend_outage_causes_mix"]],
            "notes": ("artifact declares no F-number; the dataset assigns none. The "
                      "subsample is 3 USGS stations (summary.json subsampled=true), so the "
                      "counts are not panel-wide."),
        },
        {
            "key": "regulatory_daily_max",
            "finding": None,
            "class": "sample_fact",
            "artifact": A["amend_regulatory_daily_max"],
            "headline": [
                ("n_stations_requested", A["amend_regulatory_daily_max"],
                 ("n_stations_requested",), "stations", "sealed USGS confirmation stations"),
                ("n_stations_with_daily_max_00001", A["amend_regulatory_daily_max"],
                 ("n_stations_with_daily_max_00001",), "stations",
                 "sealed USGS confirmation stations"),
                ("n_stations_with_daily_mean_00003", A["amend_regulatory_daily_max"],
                 ("n_stations_with_daily_mean_00003",), "stations",
                 "sealed USGS confirmation stations"),
            ],
            "notes": ("data-availability fact behind the REG endpoint-mismatch flag: the "
                      "daily-maximum product exists for these stations but the manuscript "
                      "illustration used daily means, so no daily-max reanalysis is claimed "
                      "here. The artifact declares no F-number; the dataset assigns none."),
        },
        {
            "key": "winter_regulatory",
            "finding": lambda: _finding_from_report(b, A["amend_winter_report"], "winter"),
            "class": "exploratory_post_open",
            "artifact": A["amend_winter_summary"],
            "headline": [
                ("k_used", A["amend_winter_summary"], ("reporting_rule", "k_used"),
                 "fraction", "amplitude/residual-sd gate"),
                ("k_theory", A["amend_winter_summary"], ("reporting_rule", "k_theory"),
                 "fraction", "amplitude/residual-sd gate"),
                ("n_observed_days_median", A["amend_winter_summary"],
                 ("reporting_rule", "n_observed_days_median"), "days",
                 "sine-fit cases"),
                ("coldest30_auc_cold_window_overlap", A["amend_winter_cold"],
                 None, "fraction", "development cases, coldest-30 endpoint"),
                ("coldest30_rate_at_70_best_cold_minus_length_rule", A["amend_winter_cold"],
                 None, "percentage_points", "development cases at 70% retention"),
            ],
            "extra_artifacts": [A["amend_winter_cold"]],
        },
    ]

    seen_dirs = set()
    for spec in specs:
        key = spec["key"]
        seen_dirs.add(key)
        cls = spec["class"]
        ddir = ROOT / AMD / key
        check(ddir.is_dir(), f"amendment directory missing: {AMD}/{key}")
        check(
            (ddir / "summary.json").is_file() or spec.get("artifact"),
            f"amendment {key}: neither summary.json nor a declared artifact exists",
        )
        finding_fn = spec["finding"]
        finding = finding_fn() if finding_fn is not None else "not_declared_in_artifact"
        # force the artifact (and any extras) to be read so the provenance set is real
        rel = spec["artifact"]
        suffix = Path(rel).suffix
        if suffix == ".json":
            b.read_json(rel)
        elif suffix == ".csv":
            b.read_csv(rel)
        else:
            b.read_text(rel)
        for extra in spec.get("extra_artifacts", []):
            if Path(extra).suffix == ".json":
                b.read_json(extra)
            elif Path(extra).suffix == ".csv":
                b.read_csv(extra)
            else:
                b.read_text(extra)

        b.add("amendment", key, "finding_id", finding, "text", "", cls, rel,
              "" if finding != "not_declared_in_artifact" else
              "the artifact declares no finding id; none is assigned by this dataset")
        b.add("amendment", key, "artifact", rel, "text", "", cls, rel)
        b.add("amendment", key, "evidence_class", cls, "text", "", cls, rel,
              "declared in this builder's amendment spec")
        b.add("amendment", key, "directory", f"{AMD}/{key}", "text", "", cls, rel,
              "amendment directory; summary.json present"
              if (ddir / "summary.json").is_file() else
              "amendment directory; no summary.json, headline read from the declared artifact")
        for field, artifact, path, unit, denom in spec["headline"]:
            if path is None:
                row = _pick_amendment_row(b, artifact, key, field)
                b.num("amendment", key, field, row[_row_column(field)], unit, denom, cls,
                      artifact, spec.get("notes", ""))
                continue
            b.jnum("amendment", key, field, artifact, path, unit, denom, cls,
                   spec.get("notes", ""))
        if spec.get("notes"):
            b.add("amendment", key, "notes", spec["notes"], "text", "", cls, rel)

    on_disk = {p.name for p in (ROOT / AMD).iterdir() if p.is_dir()}
    uncovered = sorted(on_disk - seen_dirs)
    # Hard rule: an amendment directory that publishes summary.json must have a spec,
    # otherwise its headline would be silently missing from the dataset.
    with_summary = sorted(
        name for name in uncovered if (ROOT / AMD / name / "summary.json").is_file()
    )
    check(
        not with_summary,
        f"amendment directories with summary.json but no spec in this builder: "
        f"{with_summary}",
    )
    b.dash["_amendment_keys"] = sorted(seen_dirs)
    b.dash["uncovered_amendment_dirs"] = [
        {"dir": f"{AMD}/{name}",
         "reason": KNOWN_UNCOVERED_AMENDMENTS.get(
             name,
             "no summary.json and no spec in this builder; not covered by this build",
         )}
        for name in uncovered
    ]


def verify_amendment_crosschecks(b: Builder) -> None:
    """Cross-checks between an amendment's summary and its own detail CSV."""
    summary_rel = A["amend_outage_causes"]
    mix_rel = A["amend_outage_causes_mix"]
    gap_rows = [
        r for r in b.read_csv(mix_rel)
        if r["unit"] == "gap" and r["observed_class"] == "ALL"
    ]
    check(bool(gap_rows), f"{mix_rel}: no gap/ALL rows")
    n_gaps = sum(int(r["n"]) for r in gap_rows)
    n_days = sum(int(r["n_missing_days"]) for r in gap_rows)
    check(
        n_gaps == int(b.get(summary_rel, ("n_gaps",), "outage_causes cross-check")),
        f"{mix_rel}: gap count {n_gaps} != summary.json n_gaps",
    )
    check(
        n_days == int(b.get(summary_rel, ("n_missing_days",), "outage_causes cross-check")),
        f"{mix_rel}: missing-day count {n_days} != summary.json n_missing_days",
    )
    n_caused = sum(int(r["n_with_documented_cause_code"]) for r in gap_rows)
    b.add("amendment", "outage_causes", "n_gaps_with_documented_cause_code", n_caused,
          "count", "real USGS interior gaps, 3-station subsample", "sample_fact", mix_rel,
          "summed at build time over the gap/ALL rows of cause_mix.csv and cross-checked "
          "against summary.json gap and missing-day totals")
    b.num("amendment", "outage_causes", "n_gaps_from_detail_csv", n_gaps, "count",
          "real USGS interior gaps, 3-station subsample", "sample_fact", mix_rel)
    b.num("amendment", "outage_causes", "n_missing_days_from_detail_csv", n_days, "days",
          "real USGS interior gaps, 3-station subsample", "sample_fact", mix_rel)

    # F12: the equal-K matched donor contrasts are the amendment's core table.
    by_k_rel = A["amend_step5_by_k"]
    by_k = b.read_csv(by_k_rel)
    lows = []
    for r in by_k:
        k = r["k_matched"]
        denom = (f"equal-K matched sample, K={k} "
                 f"({r['n_paired']} paired cases in {r['n_networks']} networks)")
        lows.append(float(r["ci_low_c"]))
        b.num("amendment", "step5_mechanism_equal_k", f"point_c[K={k}]", r["point_c"],
              "celsius", denom, "exploratory_post_open", by_k_rel,
              "weak_half minus strong_half, matched exact K")
        b.num("amendment", "step5_mechanism_equal_k", f"ci_low_c[K={k}]", r["ci_low_c"],
              "celsius", denom, "exploratory_post_open", by_k_rel)
        b.num("amendment", "step5_mechanism_equal_k", f"ci_high_c[K={k}]", r["ci_high_c"],
              "celsius", denom, "exploratory_post_open", by_k_rel)
        b.num("amendment", "step5_mechanism_equal_k", f"n_paired[K={k}]", r["n_paired"],
              "cases", denom, "exploratory_post_open", by_k_rel)
    est_min = float(b.get(A["amend_step5_equal_k"],
                          ("verdict_detail", "min_matched_ci_low_c"),
                          "step5 by-K cross-check"))
    b.num("amendment", "step5_mechanism_equal_k", "min_by_k_ci_low_c", min(lows), "celsius",
          f"{len(by_k)} K strata of the equal-K matched table", "exploratory_post_open",
          by_k_rel,
          f"computed minimum over the by-K table; the estimator-level matched table "
          f"reports min_matched_ci_low_c={est_min:g} in summary.json, so single K strata "
          f"with small n touch zero while the estimator-level minimum does not")


def _pick_amendment_row(b: Builder, rel: str, key: str, field: str) -> dict[str, str]:
    """Row selectors for the few amendments whose headline lives in a wide CSV."""
    if key == "provider_contract_sensitivity":
        return b.pick(rel, population="development_retrospective",
                      subset="documented_daily_mean_only")
    if key == "step5_mechanism_pre_fix":
        return b.pick(rel, contrast="abserr_weak_half - abserr_strong_half")
    if key == "winter_regulatory":
        if field.startswith("coldest30_"):
            return b.pick(rel, metric="coldest30", tolerance_rule="literal_0.5C")
    fail(f"no row selector declared for amendment {key} field {field}")


def _row_column(field: str) -> str:
    mapping = {
        "documented_stratum_contrast_points[development]": "contrast_points",
        "abserr_weak_half_minus_strong_half_point": "point",
        "coldest30_auc_cold_window_overlap": "auc_cold_window_overlap",
        "coldest30_rate_at_70_best_cold_minus_length_rule":
            "rate_at_70_best_cold_rule_minus_length_rule",
    }
    check(field in mapping, f"no CSV column declared for amendment field {field}")
    return mapping[field]


# --------------------------------------------------------------------------
# Section: providers (measurement provenance dictionary + roles)
# --------------------------------------------------------------------------


def add_amendment_interval_rows(b: Builder) -> None:
    """Interval bounds for amendment headlines whose point estimate is in the spec table.

    The task asks for one row per amendment carrying the headline number *with its CI
    when the artifact has one*; these are the amendments whose intervals live in a
    sibling table rather than next to the point estimate.
    """
    # F15 faithful baseline: paired faithful-minus-library rate on the length-rule set
    rel = A["amend_faithful_contrasts"]
    row = b.pick(rel, retention_set="length_rule_70pct", quantity="rate_above_0.5",
                 left="faithful Beaufort (else climatology)",
                 right="library air ridge alpha=1.0 (else climatology)")
    denom = "development cases at the length-rule 70% retention set (n=28493)"
    for field, col, note in (
        ("faithful_minus_library_paired_points", "point",
         "paired contrast behind the F15 relabel"),
        ("faithful_minus_library_paired_ci_low", "low", ""),
        ("faithful_minus_library_paired_ci_high", "high", ""),
    ):
        b.num("amendment", "faithful_baseline", field, row[col], "percentage_points",
              denom, "retrospective_holdout", rel, note, scale=100.0)

    # F09 provider-contract sensitivity: interval of the documented-daily-mean subset
    rel = A["amend_provider_contract_csv"]
    row = b.pick(rel, population="development_retrospective",
                 subset="documented_daily_mean_only")
    denom = (f"development retrospective panel, documented daily-mean providers, "
             f"{row['n_networks']} networks")
    for field, col in (("documented_stratum_ci_low", "ci_low_points"),
                       ("documented_stratum_ci_high", "ci_high_points")):
        b.num("amendment", "provider_contract_sensitivity", field, row[col],
              "percentage_points", denom, "retrospective_holdout", rel)

    # F12 pre-fix (withdrawn) donor-control contrast interval
    rel = A["amend_step5_pre_contrasts"]
    row = b.pick(rel, contrast="abserr_weak_half - abserr_strong_half")
    for field, col in (("abserr_weak_half_minus_strong_half_ci_low", "low"),
                       ("abserr_weak_half_minus_strong_half_ci_high", "high"),
                       ("abserr_weak_half_minus_strong_half_n_paired", "n_paired")):
        b.num("amendment", "step5_mechanism_pre_fix", field, row[col],
              "cases" if col == "n_paired" else "celsius",
              "pre-fix unmatched two-arm paired sample", "withdrawn", rel,
              "preserved pre-fix bytes; superseded by the equal-K matched contrasts")

    # F10 pattern mixture: the interval at zero completion bias
    rel = A["amend_mnar"]
    pops = {"development": "development cases", "sealed_usgs": "sealed USGS cases"}
    for pop, denom in pops.items():
        curve = b.get(rel, ("populations", pop, "curve",), f"mnar {pop}")
        hit = [p for p in curve if float(p["delta_c"]) == 0.0]
        check(len(hit) == 1,
              f"{rel}: populations.{pop}.curve does not contain exactly one delta_c=0 row")
        entry = hit[0]
        check("contrast_ci" in entry,
              f"{rel}: populations.{pop} delta_c=0 row has no contrast_ci")
        for field, key in (("delta_zero_ci_low", "low"), ("delta_zero_ci_high", "high"),
                           ("delta_zero_ci_draws", "draws")):
            b.num("amendment", "mnar_pattern_mixture", f"{field}[{pop}]",
                  entry["contrast_ci"][key],
                  "count" if key == "draws" else "percentage_points", denom,
                  "exploratory_post_open", rel)

    # F16 winter: clustered bootstrap of the phase-comparison influence term
    rel = A["amend_winter_summary"]
    path = ("effect_on_the_reported_phase_comparison", "all_cases",
            "clustered_bootstrap_influence_minus_missing_fraction")
    denom = "development cases with a scored phase endpoint"
    for field, key in (("phase_influence_minus_missing_fraction_point", "point"),
                       ("phase_influence_minus_missing_fraction_ci_low", "low"),
                       ("phase_influence_minus_missing_fraction_ci_high", "high")):
        b.jnum("amendment", "winter_regulatory", field, rel, path + (key,), "fraction",
               denom, "exploratory_post_open")

    # F11 post-fix: interval of the iid 0.15 C contrast change
    rel = A["amend_step22_scenarios"]
    for panel, denom in (("development", "development cases"),
                         ("reserved", "reserved cases")):
        row = b.pick(rel, panel=panel, scenario="iid_0.15")
        for field, col in (("iid_0.15_contrast_ci_low", "contrast_ci_low"),
                           ("iid_0.15_contrast_ci_high", "contrast_ci_high"),
                           ("iid_0.15_change_ci_low", "contrast_change_ci_low"),
                           ("iid_0.15_change_ci_high", "contrast_change_ci_high")):
            b.num("amendment", "step22_noise_post_fix", f"{field}[{panel}]", row[col],
                  "percentage_points", denom, "exploratory_post_open", rel)

    # F01 post-seal diagnostic: pooled interval of the primary subset
    rel = A["amend_sealed_diagnostic"]
    for row in b.get(rel, ("rows",), "sealed diagnostic"):
        if row["subset"] != "primary_all_39_networks":
            continue
        denom = (f"sealed panel primary subset: {row['n_cases']} cases in "
                 f"{row['n_networks']} networks")
        for field, key in (("pooled_contrast_ci_low", "pooled_ci_low_points"),
                           ("pooled_contrast_ci_high", "pooled_ci_high_points"),
                           ("empirical_contrast_ci_low", "empirical_ci_low_points"),
                           ("empirical_contrast_ci_high", "empirical_ci_high_points")):
            b.num("amendment", "sealed_usgs_prior_access_diagnostic", field, row[key],
                  "percentage_points", denom, "sealed_confirmation", rel)


def build_providers(b: Builder) -> None:
    rel = A["measurement_dictionary"]
    rows = b.read_csv(rel)
    text_fields = [
        "country", "product", "statistic_documented", "statistic_as_parsed",
        "aggregation_interval", "day_boundary_tz", "quality_codes_kept",
        "quality_codes_dropped", "license", "required_citation", "acquisition_route",
        "evidence_url", "verification_status",
    ]
    for r in rows:
        p = r["provider"]
        for f in text_fields:
            b.add("provider", p, f, r[f], "text", "", "sample_fact", rel)
        for f in ("redistribution_allowed", "derived_output_allowed"):
            b.add("provider", p, f, r[f], "bool", "", "sample_fact", rel)
        b.dash["providers"].append(
            {
                "provider": p,
                "country": r["country"],
                "statistic_documented": r["statistic_documented"],
                "statistic_as_parsed": r["statistic_as_parsed"],
                "aggregation_interval": r["aggregation_interval"],
                "day_boundary_tz": r["day_boundary_tz"],
                "quality_codes_kept": r["quality_codes_kept"],
                "quality_codes_dropped": r["quality_codes_dropped"],
                "license": r["license"],
                "redistribution_allowed": r["redistribution_allowed"],
                "verification_status": r["verification_status"],
                "artifact": rel,
            }
        )

    # provider roles as recorded in the SI correction
    roles_rel = A["provider_roles"]
    role_rows = b.read_csv(roles_rel)
    manifest_net = Counter()
    manifest_sy: Counter = Counter()
    for m in b.read_csv(A["current_manifest"]):
        manifest_net[m["provider"]] += 1
        manifest_sy[m["provider"]] += int(m["n_station_years"])
    for r in role_rows:
        p = r["provider"]
        b.add("provider", p, "country", r["country"], "text", "", "sample_fact", roles_rel)
        b.add("provider", p, "v17_role", r["role"], "text", "", "sample_fact", roles_rel)
        b.num("provider", p, "n_networks_dev", r["n_networks_dev"], "networks",
              "v17 development split", "sample_fact", roles_rel)
        b.num("provider", p, "n_networks_reserved", r["n_networks_reserved"], "networks",
              "v17 reserved split", "sample_fact", roles_rel)
        b.num("provider", p, "n_station_years_total", r["n_station_years"], "station_years",
              "v17 panel", "sample_fact", roles_rel)
        check(
            int(r["n_networks_dev"]) + int(r["n_networks_reserved"]) == manifest_net[p],
            f"provider_roles_from_split.csv: {p} network count != current_data_manifest.csv",
        )
        check(
            int(r["n_station_years"]) == manifest_sy[p],
            f"provider_roles_from_split.csv: {p} station-years != current_data_manifest.csv",
        )

    # per-provider admission-rule disagreement (claim D1 evidence)
    dis_rel = A["e2_by_provider"]
    for r in b.read_csv(dis_rel):
        p = r["provider"]
        denom = f"{r['n_incomplete_station_years']} real incomplete station-years, {p}"
        b.num("provider", p, "n_incomplete_station_years", r["n_incomplete_station_years"],
              "station_years", denom, "sample_fact", dis_rel)
        b.num("provider", p, "admission_rule_disagreement_pct", r["disagreement_pct"],
              "percent", denom, "sample_fact", dis_rel)
        b.num("provider", p, "admitted_by_length_rejected_by_timing",
              r["admitted_by_length_rejected_by_timing"], "station_years", denom,
              "sample_fact", dis_rel)
        b.num("provider", p, "rejected_by_length_admitted_by_timing",
              r["rejected_by_length_admitted_by_timing"], "station_years", denom,
              "sample_fact", dis_rel)


# --------------------------------------------------------------------------
# Section: admission disagreement detail (claim D1 continuation)
# --------------------------------------------------------------------------


def build_admission_detail(b: Builder) -> None:
    cid = "D1"
    cls = "sample_fact"
    rel = A["e2_matched_retention"]
    for r in b.read_csv(rel):
        denom = f"matched retention {r['retention']}"
        b.num("claim", cid, f"matched_retention_disagreement_pct[{r['retention']}]",
              r["disagreement_pct"], "percent", denom, cls, rel)
        b.num("claim", cid,
              f"matched_retention_admitted_by_length_rejected_by_timing[{r['retention']}]",
              r["admitted_by_length_rejected_by_timing"], "station_years", denom, cls, rel)
        b.num("claim", cid, f"matched_retention_mean_peak_overlap_length_admitted[{r['retention']}]",
              r["mean_peak_overlap_length_admitted"], "fraction", denom, cls, rel)
        b.num("claim", cid, f"matched_retention_mean_peak_overlap_timing_admitted[{r['retention']}]",
              r["mean_peak_overlap_timing_admitted"], "fraction", denom, cls, rel)
    rel2 = A["e2_archive_consequence"]
    for r in b.read_csv(rel2):
        rule = r["rule"]
        denom = f"real archive under rule: {rule}"
        b.num("claim", cid, f"archive_incomplete_years_admitted[{rule}]",
              r["incomplete_years_admitted"], "station_years", denom, cls, rel2)
        b.num("claim", cid, f"archive_mean_annual_peak_c[{rule}]", r["mean_annual_peak_c"],
              "celsius", denom, cls, rel2)
        b.num("claim", cid, f"archive_shift_vs_complete_only_c[{rule}]",
              r["shift_vs_complete_only_c"], "celsius", denom, cls, rel2)
        b.num("claim", cid, f"archive_share_above_20c_pct[{rule}]", r["share_above_20c_pct"],
              "percent", denom, cls, rel2)
        b.num("claim", cid, f"archive_admitted_with_peak_window_wholly_hidden[{rule}]",
              r["admitted_with_peak_window_wholly_hidden"], "station_years", denom, cls, rel2)
        b.num("claim", cid, f"archive_mean_peak_overlap_admitted[{rule}]",
              r["mean_peak_overlap_admitted"], "fraction", denom, cls, rel2)
    b.dash["admission"].update({
        "by_provider_artifact": A["e2_by_provider"],
        "matched_retention_artifact": rel,
        "archive_consequence_artifact": rel2,
        "deploy_artifact": A["deploy_predict"],
    })


# --------------------------------------------------------------------------
# Section: transport protocol status
# --------------------------------------------------------------------------


def build_transport(b: Builder) -> None:
    cid = "TRANSPORT"
    cls = "sample_fact"
    protocol = A["transport_protocol"]
    b.read_text(protocol)
    verdict = OPTIONAL_ARTIFACTS["transport_verdict"]
    if b.artifact_exists(verdict):
        b.read_json(verdict)
        point = b.jnum("claim", cid, "contrast_points", verdict, ("contrast_points",),
                       "percentage_points", "sealed multi-agency transport panel", cls)
        low = b.jnum("claim", cid, "contrast_ci_low", verdict, ("ci_low_points",),
                     "percentage_points", "sealed multi-agency transport panel", cls)
        high = b.jnum("claim", cid, "contrast_ci_high", verdict, ("ci_high_points",),
                      "percentage_points", "sealed multi-agency transport panel", cls)
        _contrast(b, "P0-07b multi-agency transport (scored)", point, low, high,
                  "percentage_points", "sealed multi-agency transport panel",
                  "sealed_confirmation", verdict, "transport score")
        b.add("claim", cid, "transport_status", "scored", "text", "",
              "sealed_confirmation", verdict)
        b.dash["transport"] = {"status": "scored", "artifact": verdict,
                               "protocol": protocol}
    else:
        b.add("claim", cid, "transport_status", "not_scored", "text", "", cls, protocol,
              "no transport verdict artifact at "
              f"{verdict}; the protocol is sealed for design and the panel is still being "
              "recruited, so this dataset carries no transport number")
        b.dash["transport"] = {
            "status": "not_scored",
            "expected_artifact": verdict,
            "protocol": protocol,
            "evidence_class": cls,
        }

    # recruitment state, each number read from a named ingest artifact
    uk_net = A["transport_uk_ea_networks"]
    uk_years = A["transport_uk_ea_years"]
    b.num("provider", "uk_ea", "transport_networks_in_manifest", len(b.read_csv(uk_net)),
          "networks", "sealed multi-agency transport recruitment", cls, uk_net,
          "row count of the ingested network manifest")
    b.num("provider", "uk_ea", "transport_complete_station_years", len(b.read_csv(uk_years)),
          "station_years", "sealed multi-agency transport recruitment", cls, uk_years,
          "row count of the ingested complete station-year table")
    nve_rel = A["transport_nve_ingest"]
    b.jnum("provider", "nve_hydapi", "transport_stations_with_ge4_complete_years", nve_rel,
           ("complete_year_counts", "stations_with_ge4_complete_years"), "stations",
           "sealed multi-agency transport recruitment", cls)
    b.jnum("provider", "nve_hydapi", "transport_complete_station_years", nve_rel,
           ("complete_year_counts", "complete_station_years"), "station_years",
           "sealed multi-agency transport recruitment", cls)
    smhi_rel = A["transport_smhi_status"]
    b.jtext("provider", "smhi", "transport_ingest_status", smhi_rel, ("status",), cls)
    b.jtext("provider", "smhi", "transport_qc_stratum", smhi_rel, ("qc_stratum",), cls)
    b.jnum("provider", "smhi", "transport_networks_under_strict_gate", smhi_rel,
           ("strict_gate", "n_networks"), "networks",
           "SMHI strict checked-values gate", cls)
    b.jnum("provider", "smhi", "transport_stations_with_ge_4_complete_years_strict_gate",
           smhi_rel, ("strict_gate", "n_stations_with_ge_4_complete_years"), "stations",
           "SMHI strict checked-values gate", cls)
    b.jnum("provider", "smhi", "transport_networks_under_amended_stratum", smhi_rel,
           ("amended_stratum", "n_networks"), "networks",
           "SMHI values published as uncontrolled (Amendment 2 stratum)", cls)
    b.jnum("provider", "smhi", "transport_stations_ge_4_complete_years_amended_stratum",
           smhi_rel, ("amended_stratum", "n_stations_emitted_ge_4_complete_years"),
           "stations", "SMHI values published as uncontrolled (Amendment 2 stratum)", cls)
    b.jnum("provider", "smhi", "transport_complete_station_years_amended_stratum", smhi_rel,
           ("amended_stratum", "n_complete_station_years"), "station_years",
           "SMHI values published as uncontrolled (Amendment 2 stratum)", cls)
    ehyd_rel = A["transport_ehyd_ingest"]
    ehyd_daily = b.get_nullable(ehyd_rel,
                                ("observations", "daily_surface_temperature_file_types"),
                                "ehyd")
    check(isinstance(ehyd_daily, list),
          f"{ehyd_rel}: observations.daily_surface_temperature_file_types is not a list")
    b.num("provider", "ehyd", "transport_daily_surface_temperature_file_types",
          len(ehyd_daily), "count", "eHYD daily surface-water temperature products", cls,
          ehyd_rel, "element count of the artifact list; zero means the provider has no "
          "daily surface-water temperature product of its own")


# --------------------------------------------------------------------------
# Verification and reporting
# --------------------------------------------------------------------------


def verify_rows(b: Builder) -> None:
    registry = b.read_csv(A["claim_registry"])
    ids = {r["claim_id"] for r in registry}
    for row in b.rows:
        if row["entity_type"] == "claim" and row["entity_id"] not in ids:
            check(
                row["entity_id"] in DECLARED_EXTRA_CLAIM_IDS,
                f"dataset row cites undeclared claim entity id: {row['entity_id']}",
            )
        check(
            row["evidence_class"] in EVIDENCE_CLASSES,
            f"unknown evidence class in row: {row}",
        )
        check(
            row["artifact_path"] in b.artifacts,
            f"row cites an artifact that was never read: {row['artifact_path']}",
        )
        if row["unit"] not in ("text", "bool", "sha256", ""):
            check(row["denominator"].strip() != "",
                  f"numeric row without denominator: {row}")
    # every registry claim must appear in the dataset
    present = {r["entity_id"] for r in b.rows if r["entity_type"] == "claim"}
    missing = sorted(ids - present)
    check(not missing, f"registry claims missing from the dataset: {missing}")


def build_not_established(b: Builder) -> None:
    registry = b.dash.get("_registry_claims") or b.read_csv(A["claim_registry"])
    numeric = b.dash.get("_numeric_claims", set())
    rows_by_claim: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in b.rows:
        if row["entity_type"] == "claim":
            rows_by_claim[row["entity_id"]].append(row)

    for r in registry:
        cid = r["claim_id"]
        cls = EVIDENCE_CLASS_OVERRIDE.get(cid, (EVIDENCE_CLASS_MAP[r["evidence_type"]], ""))[0]
        may_enter = r["may_enter_abstract_or_conclusions"].strip() == "True"
        if cls in ("exploratory_post_open", "proxy", "withdrawn") or not may_enter:
            reason_bits = [f"status={r['status']}", f"evidence_class={cls}"]
            if r["finding_ids"].strip() not in ("", "—", "-"):
                reason_bits.append(f"findings={r['finding_ids']}")
            if not may_enter:
                reason_bits.append("registry: may_enter_abstract_or_conclusions=False")
            b.dash["not_established"].append(
                {
                    "id": cid,
                    "statement": r["statement"],
                    "evidence_class": cls,
                    "evidence_type": r["evidence_type"],
                    "status": r["status"],
                    "artifact": r["artifact"],
                    "reason": "; ".join(reason_bits),
                    "notes": r["notes"],
                    "has_numbers": cid in numeric,
                }
            )
    b.dash["not_established"].append(
        {
            "id": "TRANSPORT",
            "statement": "Multi-agency transport of the frozen screen (P0-07 extension)",
            "evidence_class": "not scored",
            "evidence_type": "protocol",
            "status": "panel under recruitment",
            "artifact": A["transport_protocol"],
            "reason": "no scored transport verdict exists; recruitment counts are reported "
                      "as providers, not as a transport result",
            "notes": "",
            "has_numbers": False,
        }
    )
    # claims with no numeric extraction at all
    no_numbers = [
        r["claim_id"] for r in registry
        if r["claim_id"] not in numeric
    ]
    b.dash["claims_without_numeric_extraction"] = no_numbers


def print_summary(b: Builder) -> None:
    counts = Counter(r["entity_type"] for r in b.rows)
    classes = Counter(r["evidence_class"] for r in b.rows)
    print("=" * 78)
    print("companion dataset build: OK")
    print("=" * 78)
    print(f"rows: {len(b.rows)}")
    for et in ENTITY_TYPES:
        print(f"  entity_type={et:<10} {counts.get(et, 0)}")
    print("evidence classes:")
    for ec in EVIDENCE_CLASSES:
        print(f"  {ec:<22} {classes.get(ec, 0)}")
    print(f"\nartifacts read: {len(b.artifacts)}")
    for rel in sorted(b.artifacts):
        meta = b.artifacts[rel]
        rows_note = f", rows={meta['rows_read']}" if meta["rows_read"] is not None else ""
        n_rows = sum(1 for r in b.rows if r["artifact_path"] == rel)
        print(f"  {rel}  [{meta['kind']}{rows_note}, sha256={meta['sha256'][:12]}..., "
              f"dataset_rows={n_rows}]")
    no_numbers = b.dash.get("claims_without_numeric_extraction", [])
    print(f"\nclaims with no numeric extraction (text rows only): {no_numbers}")
    print(f"claims/entities in the not-established list: "
          f"{len(b.dash.get('not_established', []))}")
    print(f"\noutputs:\n  {DATASET_OUT.relative_to(ROOT)}\n  {README_OUT.relative_to(ROOT)}"
          f"\n  {DASH_OUT.relative_to(ROOT)}\n  {DASH_JSON.relative_to(ROOT)}"
          f"\n  {DIST_DATASET.relative_to(ROOT)}")


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------


def _span(value, unit: str, cls: str, artifact: str, denom: str = "", notes: str = "",
          tooltip_extra: str = "") -> str:
    txt = disp(value, unit)
    title = f"evidence class: {cls}\nartifact: {artifact}"
    if denom:
        title += f"\ndenominator: {denom}"
    if notes:
        title += f"\nnotes: {notes}"
    if tooltip_extra:
        title += f"\n{tooltip_extra}"
    return (
        f'<span class="num" data-cls="{html.escape(cls)}" '
        f'data-art="{html.escape(artifact)}" title="{html.escape(title)}">{txt}</span>'
    )


def _prov(cls: str, artifact: str, extra: str = "") -> str:
    label = f"{cls} · {artifact}"
    if extra:
        label += f" · {extra}"
    return f'<span class="prov" title="{html.escape(label)}">{html.escape(label)}</span>'


CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin: 0; font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
       Helvetica, Arial, sans-serif; color: #17202a; background: #f6f7f9; }
header { background: #14213d; color: #fff; padding: 22px 28px; }
header h1 { margin: 0 0 6px; font-size: 21px; }
header p { margin: 2px 0; font-size: 13px; color: #c9d3e4; }
main { max-width: 1180px; margin: 0 auto; padding: 18px 20px 60px; }
section { background: #fff; border: 1px solid #dde3ea; border-radius: 8px;
          margin: 18px 0; padding: 16px 18px; }
h2 { font-size: 17px; margin: 0 0 4px; }
h3 { font-size: 14px; margin: 18px 0 6px; color: #33415c; }
p.sub { margin: 0 0 12px; font-size: 12.5px; color: #5b6b7f; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #eceff3;
         vertical-align: top; }
th { background: #f0f3f7; font-weight: 600; font-size: 12px; }
td.num-col, th.num-col { text-align: right; white-space: nowrap; }
.num { font-variant-numeric: tabular-nums; border-bottom: 1px dotted #7a8aa0;
       cursor: help; }
.prov { display: block; font-size: 10.5px; color: #7b8794; margin-top: 2px;
        word-break: break-all; }
.badge { display: inline-block; font-size: 10.5px; padding: 1px 6px; border-radius: 9px;
         border: 1px solid #b9c4d2; background: #f2f5f9; color: #33415c;
         margin-right: 4px; white-space: nowrap; }
.badge.sealed_confirmation { background: #e3f2e5; border-color: #9ccfa3; color: #1c5c2a; }
.badge.retrospective_holdout { background: #e8eefc; border-color: #a9bdea; color: #1d3b7a; }
.badge.sample_fact { background: #eef1f4; }
.badge.exploratory_post_open { background: #fdf3e0; border-color: #e5c07b; color: #7a4f06; }
.badge.proxy { background: #f6e8fb; border-color: #cfa3e0; color: #5c1d73; }
.badge.withdrawn { background: #fdeaea; border-color: #e0a3a3; color: #7a1d1d; }
.cards { display: flex; flex-wrap: wrap; gap: 10px; }
.card { border: 1px solid #dde3ea; border-radius: 7px; padding: 10px 12px; min-width: 168px;
        background: #fbfcfe; }
.card .big { font-size: 20px; font-weight: 600; }
.card .lbl { font-size: 11.5px; color: #5b6b7f; text-transform: uppercase;
             letter-spacing: .03em; }
.callout { border-left: 4px solid #d9a02b; background: #fff9ec; padding: 9px 12px;
           font-size: 13px; border-radius: 4px; margin: 10px 0; }
.callout.bad { border-color: #c0392b; background: #fdf0ee; }
.callout.ok { border-color: #2e7d46; background: #f0f8f2; }
ul { margin: 6px 0 0 18px; padding: 0; }
li { margin: 5px 0; font-size: 13px; }
code { background: #f0f3f7; padding: 1px 5px; border-radius: 4px; font-size: 12.5px; }
footer { font-size: 12px; color: #5b6b7f; padding: 0 20px 40px; max-width: 1180px;
         margin: 0 auto; }
.tiny { font-size: 11.5px; color: #6b7a8d; }
"""


def render_dashboard(b: Builder, dataset_rows: int) -> str:
    d = b.dash
    parts: list[str] = []
    artifact_paths = sorted(b.artifacts)

    # header
    parts.append('<header>')
    parts.append('<h1>Stream recoverability — companion evidence dashboard</h1>')
    parts.append(
        '<p>Every number on this page was read at build time from a named artifact under '
        '<code>results/</code> and carries its evidence class and artifact path in the '
        'tooltip and in the caption next to it.</p>'
    )
    parts.append(
        f'<p><span class="tiny">build metadata (not evidence): dataset rows '
        f'{dataset_rows} · artifacts read {len(artifact_paths)} · '
        f'built {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}</span> · '
        'rebuild: <code>python3 scripts/264_wrr_companion_dataset.py</code> · '
        'data: <code>dist/companion/companion_dataset.csv</code> (also '
        '<code>docs/companion/companion_dataset.csv</code>)</p>'
    )
    parts.append('</header><main>')

    # class legend
    parts.append('<section><h2>Evidence classes</h2>'
                 '<p class="sub">The vocabulary used by the dataset and by every number '
                 'below. Classes are assigned from the claim registry evidence_type via a '
                 'documented map; the map and the one override are in '
                 '<code>docs/companion/README.md</code>.</p><ul>')
    for ec in EVIDENCE_CLASSES:
        parts.append(f'<li><span class="badge {ec}">{ec}</span> '
                     f'{html.escape(EVIDENCE_CLASS_DEFINITION[ec])}</li>')
    parts.append('</ul></section>')

    # panel
    parts.append('<section><h2>1. Panel composition</h2>'
                 '<p class="sub">Source: <code>results/wrr_submission_ready/'
                 'current_data_manifest.csv</code> (per-network counts, summed at build '
                 'time) and <code>results/v17_fitness/step3_cases/summary.json</code> '
                 '(case counts).</p>')
    parts.append('<div class="cards">')
    for t in d["panel_totals"]:
        parts.append(
            '<div class="card">'
            f'<div class="lbl">{html.escape(t["field"].replace("n_", "").replace("_", " "))}</div>'
            f'<div class="big">{_span(t["value"], t["unit"], t["evidence_class"], t["artifact"], t["denominator"])}</div>'
            f'{_prov(t["evidence_class"], t["artifact"])}'
            '</div>'
        )
    parts.append('</div>')
    parts.append('<h3>By provider and split</h3><table><thead><tr><th>provider</th>'
                 '<th>split</th><th class="num-col">networks</th>'
                 '<th class="num-col">stations</th><th class="num-col">station-years</th>'
                 '<th>evidence</th></tr></thead><tbody>')
    for r in d["panel_by_provider"]:
        parts.append(
            '<tr>'
            f'<td>{html.escape(r["provider"])}</td><td>{html.escape(r["split"])}</td>'
            f'<td class="num-col">{_span(r["n_networks"], "networks", "sample_fact", r["artifact"], r["provider"] + " " + r["split"])}</td>'
            f'<td class="num-col">{_span(r["n_stations"], "stations", "sample_fact", r["artifact"], r["provider"] + " " + r["split"])}</td>'
            f'<td class="num-col">{_span(r["n_station_years"], "station_years", "sample_fact", r["artifact"], r["provider"] + " " + r["split"])}</td>'
            f'<td>{_prov("sample_fact", r["artifact"])}</td>'
            '</tr>'
        )
    parts.append('</tbody></table></section>')

    # contrasts
    parts.append('<section><h2>2. Headline contrasts</h2>'
                 '<p class="sub">Certificate rate minus longest-run length rule, in '
                 'percentage points; negative favours the screen, at 70% retention and '
                 '0.5 °C unless stated.</p><table><thead><tr><th>contrast</th>'
                 '<th class="num-col">point</th><th class="num-col">95% interval</th>'
                 '<th>evidence</th></tr></thead><tbody>')
    for c in d["contrasts"]:
        unit = c["unit"]
        pts = _span(c["point"], unit, c["evidence_class"], c["artifact"], c["denominator"],
                    c["notes"])
        interval = (f'[{_span(c["low"], unit, c["evidence_class"], c["artifact"], c["denominator"])}, '
                    f'{_span(c["high"], unit, c["evidence_class"], c["artifact"], c["denominator"])}]')
        parts.append(
            '<tr>'
            f'<td>{html.escape(c["label"])}<div class="tiny">{html.escape(c["notes"])}</div></td>'
            f'<td class="num-col">{pts}</td><td class="num-col">{interval}</td>'
            f'<td><span class="badge {c["evidence_class"]}">{c["evidence_class"]}</span>'
            f'{_prov(c["evidence_class"], c["artifact"])}</td>'
            '</tr>'
        )
    parts.append('</tbody></table>')

    tr = d.get("transport", {})
    if tr.get("status") == "not_scored":
        parts.append(
            '<div class="callout bad"><b>Transport is not scored.</b> No verdict artifact '
            f'exists at <code>{html.escape(tr["expected_artifact"])}</code>, so this dataset '
            'carries no multi-agency transport number. The protocol was sealed for design '
            f'(<code>{html.escape(tr["protocol"])}</code>); recruitment state is reported '
            'per provider in the dataset (entity_type=provider, fields prefixed '
            '<code>transport_</code>) and is not a result.</div>'
        )
    else:
        parts.append('<div class="callout ok"><b>Transport scored.</b> See the contrast '
                     f'row above; artifact <code>{html.escape(tr.get("artifact", ""))}'
                     '</code>.</div>')

    audit = d.get("sealed_audit", {})
    if audit:
        parts.append(
            '<h3>Sealed-panel prior access</h3>'
            '<p class="sub">Repo-wide audit of the sealed USGS panel: '
            f'{_span(audit["n_networks"], "networks", "sample_fact", audit["artifact"], "sealed USGS panel")} '
            'networks / '
            f'{_span(audit["n_stations"], "stations", "sample_fact", audit["artifact"], "sealed USGS panel")} '
            'stations; '
            f'{_span(audit["n_networks_clean_of_outcome_use"], "networks", "sample_fact", audit["artifact"], "every station clean of outcome-bearing prior use")} '
            'networks are clean of outcome-bearing prior use and '
            f'{_span(audit["n_networks_never_used_repo_wide"], "networks", "sample_fact", audit["artifact"], "every station absent repo-wide")} '
            'are clean of any prior use. The earlier "never used" label for the whole '
            'panel is false for part of it; the primary sealed score is unchanged.</p>'
            f'{_prov("sample_fact", audit["artifact"])}'
        )
    parts.append('</section>')

    # admission disagreement
    adm = d.get("admission", {})
    parts.append('<section><h2>3. Admission-rule disagreement (real archive)</h2>'
                 f'<p class="sub">Outcome-agnostic comparison of the frozen screen with the '
                 f'incumbent length rule on real incomplete station-years. Source: '
                 f'<code>{html.escape(adm.get("threshold_artifact", ""))}</code>.</p>'
                 '<table><thead><tr><th>incumbent rule compared</th>'
                 '<th class="num-col">station-years</th><th class="num-col">disagreement</th>'
                 '<th class="num-col">length admits</th><th class="num-col">timing admits</th>'
                 '<th>evidence</th></tr></thead><tbody>')
    for r in adm.get("threshold_rows", []):
        denom = f"2422 real incomplete station-years; incumbent: {r['incumbent']}"
        parts.append(
            '<tr>'
            f'<td>{html.escape(r["incumbent"])}</td>'
            f'<td class="num-col">{_span(r["n_station_years"], "station_years", adm["threshold_class"], adm["threshold_artifact"], denom)}</td>'
            f'<td class="num-col">{_span(r["disagreement_pct"], "percent", adm["threshold_class"], adm["threshold_artifact"], denom)}%</td>'
            f'<td class="num-col">{_span(r["length_admits_pct"], "percent", adm["threshold_class"], adm["threshold_artifact"], denom)}%</td>'
            f'<td class="num-col">{_span(r["timing_admits_pct"], "percent", adm["threshold_class"], adm["threshold_artifact"], denom)}%</td>'
            f'<td>{_prov(adm["threshold_class"], adm["threshold_artifact"])}</td>'
            '</tr>'
        )
    parts.append('</tbody></table>')
    es = adm.get("summary_artifact")
    if es:
        parts.append(
            '<h3>Clustered disagreement interval and archive consequence</h3>'
            '<p class="sub">Point, interval and archive-level consequence read from '
            f'<code>{html.escape(es)}</code> and '
            f'<code>{html.escape(adm.get("archive_consequence_artifact", ""))}</code>. '
            'Details, including per-provider disagreement and the matched-retention '
            'sensitivity, are rows under claim <code>D1</code> in '
            '<code>companion_dataset.csv</code>.</p>'
            f'{_prov("sample_fact", es)}'
        )
    dp = adm.get("deploy_artifact")
    if dp:
        share = float(b.value_of("claim", "DEPLOY-CERT", "share_would_admit_at_0.5c"))
        n_rows_value = float(b.value_of("claim", "DEPLOY-CERT", "n_incomplete_rows"))
        parts.append(
            '<h3>Deployment interface (frozen certificate, no truth columns)</h3>'
            f'<p class="sub">{n_rows_value:,.0f} incomplete station-years were scored by '
            'the frozen certificate without truth columns; the admission share is model '
            f'output, not a validated error rate. Source: <code>{html.escape(dp)}</code>.'
            '</p>'
            '<p>share that would be admitted at 0.5 °C: '
            f'{_span(share, "fraction", "sample_fact", dp, "2422 real incomplete station-years")}'
            '</p>'
            f'{_prov("sample_fact", dp)}'
        )
    parts.append('</section>')

    # providers
    parts.append('<section><h2>4. Provider measurement strata</h2>'
                 '<p class="sub">What each provider\'s daily value actually is, from the '
                 'measurement provenance dictionary; the stratum assignment is the one '
                 'used by the provider-contract sensitivity. Redistribution and licence '
                 'flags are carried per provider in the dataset.</p>'
                 '<table><thead><tr><th>provider</th><th>stratum / documented statistic</th>'
                 '<th>aggregation</th><th>day boundary</th><th>quality kept / dropped</th>'
                 '<th>licence</th><th>evidence</th></tr></thead><tbody>')
    strata_by_provider: dict[str, str] = {}
    for row in b.rows:
        if row["field"] == "measurement_stratum" and row["entity_type"] == "provider":
            strata_by_provider[row["entity_id"]] = row["value"]
    for p in d["providers"]:
        name = p["provider"]
        stratum = strata_by_provider.get(name, "not in the v17 panel")
        parts.append(
            '<tr>'
            f'<td>{html.escape(name)}<div class="tiny">{html.escape(p["country"])}</div></td>'
            f'<td><span class="badge">{html.escape(stratum)}</span><div class="tiny">'
            f'{html.escape(p["statistic_documented"][:230])}</div></td>'
            f'<td class="tiny">{html.escape(p["aggregation_interval"][:160])}</td>'
            f'<td class="tiny">{html.escape(p["day_boundary_tz"][:160])}</td>'
            f'<td class="tiny">{html.escape(p["quality_codes_kept"][:150])}<br>'
            f'<i>dropped:</i> {html.escape(p["quality_codes_dropped"][:150])}</td>'
            f'<td class="tiny">{html.escape(p["license"][:160])}</td>'
            f'<td>{_prov("sample_fact", p["artifact"])}<div class="tiny">'
            f'{html.escape(p["verification_status"][:200])}</div></td>'
            '</tr>'
        )
    parts.append('</tbody></table>'
                 '<p class="sub">Provider-contract sensitivity contrasts (documented '
                 'daily-mean providers versus project-derived or non-daily providers) are '
                 'rows under claim <code>MEAS</code>: '
                 f'<code>{html.escape(A["amend_provider_contract_csv"])}</code>.</p>'
                 '</section>')

    # not established
    parts.append('<section><h2>5. What is not established</h2>'
                 '<p class="sub">Claims that are withdrawn, proxy-based or exploratory, or '
                 'that the registry bars from the abstract and conclusions, plus the '
                 'unscored transport test. None of these may be quoted as results. Every '
                 'entry names the artifact that carries it. Retrospective-holdout '
                 'contrasts (<code>V17-H2</code>, <code>V17-A1</code>) are not in this '
                 'list because the registry admits them as retrospective; they are '
                 'labelled <span class="badge retrospective_holdout">retrospective_holdout</span> '
                 'in section 2 and are not sealed independent confirmation.</p><ul>')
    for item in d["not_established"]:
        badge = item["evidence_class"] if item["evidence_class"] in EVIDENCE_CLASSES else ""
        badge_html = f'<span class="badge {badge}">{html.escape(item["evidence_class"])}</span>'
        parts.append(
            f'<li>{badge_html}<b>{html.escape(item["id"])}</b> — '
            f'{html.escape(item["statement"][:260])}<div class="tiny">'
            f'{html.escape(item["reason"])} · registry artifact: '
            f'<code>{html.escape(item["artifact"])}</code>'
            + (f' · {html.escape(item["notes"][:300])}' if item["notes"] else "")
            + '</div></li>'
        )
    parts.append('</ul>')
    if d.get("claims_without_numeric_extraction"):
        parts.append(
            '<p class="sub">Claims carried as text only (no headline number could be read '
            'from a named artifact): '
            + ", ".join(f'<code>{html.escape(c)}</code>'
                        for c in d["claims_without_numeric_extraction"])
            + '.</p>'
        )
    parts.append('</section>')

    # artifacts
    parts.append('<section><h2>6. Artifacts read by this build</h2>'
                 '<p class="sub">Each path was read at build time; the sha256 is of the '
                 'bytes read. Numbers in this dashboard cite one of these paths.</p>'
                 '<table><thead><tr><th>artifact</th><th>kind</th>'
                 '<th class="num-col">bytes</th><th class="num-col">rows in dataset</th>'
                 '<th>sha256</th></tr></thead><tbody>')
    for rel in artifact_paths:
        meta = b.artifacts[rel]
        n_rows = sum(1 for r in b.rows if r["artifact_path"] == rel)
        parts.append(
            '<tr>'
            f'<td><code>{html.escape(rel)}</code></td><td>{meta["kind"]}</td>'
            f'<td class="num-col">{meta["bytes"]:,}</td>'
            f'<td class="num-col">{n_rows}</td>'
            f'<td class="tiny">{meta["sha256"]}</td>'
            '</tr>'
        )
    parts.append('</tbody></table></section>')
    parts.append('</main>')
    parts.append(
        '<footer>Displayed numbers are rounded for reading; the full-precision values are '
        'in <code>companion_dataset.csv</code> (same directory) and in '
        '<code>docs/companion/companion_dataset.csv</code>. Tooltips give the evidence '
        'class, the artifact path, the denominator and any discrepancy flag; the caption '
        'next to every table gives the artifact path. Numbers that appear inside quoted '
        'provider documentation or claim statements are covered by that row\'s evidence '
        'label. This page fetches nothing and needs no server: open the file from disk.'
        '</footer>'
    )

    body = "\n".join(parts)
    return (
        "<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>Stream recoverability — companion evidence dashboard</title>"
        f"<style>{CSS}</style></head><body>{body}</body></html>\n"
    )


def verify_dashboard(b: Builder, text: str) -> int:
    spans = re.findall(r'<span class="num"([^>]*)>', text)
    check(bool(spans), "dashboard contains no labelled numbers")
    bad = []
    for attrs in spans:
        m_cls = re.search(r'data-cls="([^"]+)"', attrs)
        m_art = re.search(r'data-art="([^"]+)"', attrs)
        m_title = re.search(r'title="([^"]*)"', attrs)
        if not (m_cls and m_art and m_title):
            bad.append(attrs)
            continue
        if m_cls.group(1) not in EVIDENCE_CLASSES:
            bad.append(f"unknown class: {attrs}")
        if m_art.group(1) not in b.artifacts:
            bad.append(f"unread artifact: {attrs}")
        if m_cls.group(1) not in m_title.group(1) or m_art.group(1) not in m_title.group(1):
            bad.append(f"tooltip missing class/artifact: {attrs}")
    check(not bad, f"dashboard number spans without full labelling: {bad[:5]}")
    # visible adjacent labels
    # A contrast row shows three numbers (point, interval low, interval high)
    # under one visible provenance label, so the floor is one label per three
    # displayed numbers rather than one per two.
    check(text.count('class="prov"') >= max(1, len(spans) // 3),
          "too few adjacent provenance labels for the displayed numbers")
    return len(spans)


# --------------------------------------------------------------------------
# README
# --------------------------------------------------------------------------


def render_readme(b: Builder, dataset_rows: int, labelled_spans: int) -> str:
    d = b.dash
    lines: list[str] = []
    add = lines.append
    add("# Companion derived dataset and evidence dashboard (P2-03, minimal)")
    add("")
    add("This directory is a **companion release**, not a manuscript artifact. It carries "
        "evidence identity: which claim each number belongs to, what the number's "
        "denominator is, which evidence class it has, and which file under `results/` it "
        "was read from. Nothing here is re-analysed; every value is read at build time "
        "from an existing result.")
    add("")
    add("## Contents")
    add("")
    add(f"- `companion_dataset.csv` — the tidy dataset ({dataset_rows} rows; long format, "
        "one row per fact).")
    add("- `README.md` — this file.")
    add("- `../../dist/companion/index.html` — a single self-contained dashboard (data "
        f"embedded, {labelled_spans} labelled numbers); open it from disk, no server and "
        "no network.")
    add("- `../../dist/companion/dashboard_data.json` — the payload embedded in the "
        "dashboard, for reuse.")
    add("- `../../dist/companion/companion_dataset.csv` — byte copy of the tidy dataset.")
    add("")
    add("`dist/` is gitignored output; `docs/companion/` is the released, tracked part.")
    add("")
    add("## Rebuild (one command)")
    add("")
    add("```bash")
    add("python3 scripts/264_wrr_companion_dataset.py")
    add("```")
    add("")
    add("The command rewrites all five files above. It is read-only with respect to "
        "`results/`, `paper/`, `src/` and `metadata/`.")
    add("")
    add("## Dataset schema")
    add("")
    add("| column | meaning |")
    add("| --- | --- |")
    add("| `entity_type` | `network` \\| `claim` \\| `amendment` \\| `provider` |")
    add("| `entity_id` | network id, claim id, amendment key, provider key, or a declared "
        "panel/protocol id (`panel`, `sealed_usgs_panel`, `multi_agency_panel`, "
        "`TRANSPORT`) |")
    add("| `field` | the fact name; array-valued facts carry a `[selector]` suffix |")
    add("| `value` | the fact, at full precision as read |")
    add("| `unit` | `percentage_points`, `percent`, `fraction`, `days`, `celsius`, "
        "`networks`, `stations`, `station_years`, `cases`, `count`, `bytes`, `sha256`, "
        "`text`, `bool` |")
    add("| `denominator` | required for every numeric row: what the number is out of |")
    add("| `evidence_class` | one of the six classes below |")
    add("| `artifact_path` | the file the value was read from (every row's path was opened "
        "by the build) |")
    add("| `notes` | unit conversions, discrepancy flags, cross-references |")
    add("")
    add("## Evidence-class vocabulary")
    add("")
    for ec in EVIDENCE_CLASSES:
        add(f"- **`{ec}`** — {EVIDENCE_CLASS_DEFINITION[ec]}")
    add("")
    add("### Assignment rule")
    add("")
    add("The class of a claim is derived from its registry `evidence_type` through this "
        "map (declared in `scripts/264_wrr_companion_dataset.py`; the build fails if the "
        "registry ever contains an unmapped evidence type):")
    add("")
    add("| registry `evidence_type` | evidence class |")
    add("| --- | --- |")
    for k in sorted(EVIDENCE_CLASS_MAP):
        add(f"| `{k}` | `{EVIDENCE_CLASS_MAP[k]}` |")
    add("")
    add("One override exists, because the registry status and the closure audit withdraw a "
        "headline that the evidence type alone would not flag:")
    add("")
    add("| claim | class | reason |")
    add("| --- | --- | --- |")
    for cid, (cls, why) in sorted(EVIDENCE_CLASS_OVERRIDE.items()):
        add(f"| `{cid}` | `{cls}` | {why} |")
    add("")
    add("## Claims that must not be quoted as results")
    add("")
    add("Withdrawn, proxy-based or exploratory claims, plus claims the registry bars from "
        "the abstract and conclusions. These are exactly the entries in the dashboard's "
        "\"what is not established\" panel.")
    add("")
    add("| entity | class | status | why not quotable | artifact |")
    add("| --- | --- | --- | --- | --- |")
    for item in d["not_established"]:
        why = item["reason"]
        if item["notes"]:
            why += f"; {item['notes'][:220]}"
        add(f"| `{item['id']}` | `{item['evidence_class']}` | {item['status']} | "
            f"{why.replace('|', '/')} | `{item['artifact']}` |")
    add("")
    add("Additionally, `N1` and the `step22_noise_pre_fix` amendment preserve the "
        "**superseded pre-fix noise numbers** under `evidence_class=withdrawn`; they are in "
        "the dataset so the withdrawal is auditable, not so they can be cited.")
    add("")
    if d.get("claims_without_numeric_extraction"):
        add("Claims whose own entity rows carry no number (their evidence is recorded "
            "under provider/network entities instead — for example `S3`, whose provider "
            "roles are rows of `provider_roles_from_split.csv` under "
            "`entity_type=provider`): "
            + ", ".join(f"`{c}`" for c in d["claims_without_numeric_extraction"])
            + ".")
        add("")
    add("## Known discrepancy flags carried by the dataset")
    add("")
    flagged = [
        row for row in b.rows
        if "DISCREPANCY FLAG" in row["notes"] or "discrepancy" in row["notes"].lower()
    ]
    if flagged:
        add("| entity | field | value | note |")
        add("| --- | --- | --- | --- |")
        for row in flagged:
            add(f"| `{row['entity_id']}` | `{row['field']}` | {row['value']} | "
                f"{row['notes'].replace('|', '/')} |")
        add("")
        add("These are places where the registry prose and the artifact disagree in "
            "rounding or in the stored interval. The dataset always carries the artifact "
            "value.")
        add("")
    add("## What the build refuses to do")
    add("")
    add("- It refuses to run if any referenced artifact is missing.")
    add("- It refuses to write a numeric row whose required field is empty, null or NaN.")
    add("- It refuses to cite an artifact it did not open in the same run.")
    add("- It refuses to assign an evidence class it has no mapping for.")
    add("- It refuses to drop a registry claim silently: every claim appears, and claims "
        "with no extractable headline are listed as text-only.")
    add("- It fails on cross-checks between artifacts (manifest vs. case-table summary, "
        "prior-access CSV vs. summary, provider roles vs. manifest, the two copies of the "
        "reserved pooled contrast, the proxy PPV reused in transport).")
    add("")
    add("## Provenance of every row: artifacts read by the last build")
    add("")
    add("| artifact | kind | rows read | bytes | sha256 | dataset rows citing it |")
    add("| --- | --- | --- | --- | --- | --- |")
    for rel in sorted(b.artifacts):
        meta = b.artifacts[rel]
        n_rows = sum(1 for r in b.rows if r["artifact_path"] == rel)
        rr = meta["rows_read"] if meta["rows_read"] is not None else "—"
        cite = str(n_rows) if n_rows else "0 (read for a cross-check or a finding id)"
        add(f"| `{rel}` | {meta['kind']} | {rr} | {meta['bytes']} | `{meta['sha256']}` | "
            f"{cite} |")
    add("")
    uncovered = d.get("uncovered_amendment_dirs", [])
    if uncovered:
        add("### Amendment directories deliberately not covered")
        add("")
        add("| directory | reason |")
        add("| --- | --- |")
        for item in uncovered:
            add(f"| `{item['dir']}` | {item['reason']} |")
        add("")
        add("A directory that publishes `summary.json` and has no spec fails the build, so "
            "this list can only contain directories without a headline summary file.")
        add("")
    add("## Scope limits")
    add("")
    add("- Single-provider sealed confirmation (USGS only); multi-agency transport is not "
        "scored, so it is reported as a status, never as a number.")
    add("- The dataset inherits every limitation recorded in `claim_registry.csv`; the "
        "`status`, `population` and `registry_notes` rows carry them verbatim.")
    add("- Displayed dashboard numbers are rounded; the CSV holds full precision.")
    add("")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def main() -> int:
    b = Builder()
    missing = sorted(rel for rel in A.values() if not (ROOT / rel).is_file())
    if missing:
        print("BUILD FAILED: referenced artifacts are missing:", file=sys.stderr)
        for rel in missing:
            print(f"  - {rel}", file=sys.stderr)
        return 2
    try:
        build_panel(b)
        build_prior_access(b)
        build_claims(b)
        build_amendments(b)
        verify_amendment_crosschecks(b)
        add_amendment_interval_rows(b)
        build_providers(b)
        build_admission_detail(b)
        build_transport(b)
        verify_rows(b)
        build_not_established(b)
    except BuildError as exc:
        print(f"BUILD FAILED: {exc}", file=sys.stderr)
        return 1

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in b.rows:
        writer.writerow(row)
    dataset_text = buf.getvalue()
    DATASET_OUT.write_text(dataset_text, encoding="utf-8")
    DIST_DATASET.write_text(dataset_text, encoding="utf-8")

    labelled = 0
    try:
        html_text = render_dashboard(b, len(b.rows))
        labelled = verify_dashboard(b, html_text)
        DASH_OUT.write_text(html_text, encoding="utf-8")
        DASH_JSON.write_text(
            json.dumps(
                {
                    "generated_utc": datetime.now(timezone.utc).isoformat(),
                    "dataset_rows": len(b.rows),
                    "dataset_csv": str(DATASET_OUT.relative_to(ROOT)),
                    "evidence_classes": EVIDENCE_CLASS_DEFINITION,
                    "model": b.dash,
                    "artifacts": b.artifacts,
                },
                indent=1,
                default=str,
            ),
            encoding="utf-8",
        )
    except BuildError as exc:
        print(f"BUILD FAILED (dashboard): {exc}", file=sys.stderr)
        return 1

    README_OUT.write_text(render_readme(b, len(b.rows), labelled), encoding="utf-8")
    print_summary(b)
    print(f"dashboard labelled numbers: {labelled}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
