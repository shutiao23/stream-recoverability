#!/usr/bin/env python3
"""Audit shared donor identities and stress empirical versus bounded-group calibration."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import wrr_r3_common as C

from stream_recoverability.experiments.v17_fitness.independence import independence_table
from stream_recoverability.experiments.v19_revision.learning import empirical_threshold
from stream_recoverability.experiments.v19_revision.risk import select_group_threshold

OUT = C.RUN / "r3_06_independence_risk"


def original_id(provider: str, value: str) -> str:
    cleaned = str(value)
    if provider in {"foen", "hubeau"}:
        cleaned = "".join(character for character in cleaned if character.isdigit()).lstrip("0")
    return cleaned


def source_membership() -> tuple[pd.DataFrame, pd.DataFrame]:
    coverage_path = C.READY / "major_revision_20261014/p0_06_coverage_recompute/final_coverage_table.csv"
    coverage = pd.read_csv(coverage_path, dtype=str)
    base = coverage.loc[coverage.panel.eq("v17"), ["network_id", "provider", "manifest_input_path"]].dropna(subset=["manifest_input_path"]).drop_duplicates()
    wave = pd.read_csv(C.READY / "p0_07_wave2_ingest/wave2_inputs_manifest.csv", dtype=str)
    wave = wave[["network_id", "provider", "input_path"]].rename(columns={"input_path": "manifest_input_path"})
    sources = pd.concat([base, wave], ignore_index=True).drop_duplicates("network_id", keep="last")
    records = []
    for row in sources.itertuples(index=False):
        path = C.ROOT / row.manifest_input_path
        if not path.exists():
            raise FileNotFoundError(path)
        columns = pd.read_csv(path, nrows=0).columns
        for station in columns:
            if station != "date":
                provider = "nve" if row.provider.startswith("nve") else row.provider
                records.append({"network_id": row.network_id, "provider": provider, "station_id": station, "canonical_station_id": provider + "|" + original_id(provider, station), "input_path": str(path.relative_to(C.ROOT))})
    return pd.DataFrame(records), sources


def audit_external(all_known: pd.DataFrame) -> pd.DataFrame:
    roles_path = C.RUN / "r3_02_external_resource/external_station_roles.csv"
    roles = pd.read_csv(roles_path, dtype={"original_id": str})
    known = set(zip(all_known.provider, all_known.station_id.map(str)))
    extra = []
    for path in (C.ROOT / "results").rglob("daily_wide_temperature.csv"):
        network = path.parent.name
        provider = next((name for name in ["foen", "hubeau", "nve"] if network.startswith(name)), None)
        if provider is None:
            continue
        try:
            names = pd.read_csv(path, nrows=0).columns
        except (pd.errors.EmptyDataError, OSError):
            continue
        for station in names:
            if station != "date":
                extra.append((provider, station))
    known.update(extra)
    canonical = {(provider, original_id(provider, station)) for provider, station in known}
    roles["previous_raw_input_station_or_donor"] = [(row.provider, original_id(row.provider, row.original_id)) in canonical for row in roles.itertuples(index=False)]
    contaminated = set(roles.loc[roles.previous_raw_input_station_or_donor, "independence_group"])
    roles["eligible_after_full_input_audit"] = roles.eligible_new_component & ~roles.independence_group.isin(contaminated)
    roles["original_partition_retained"] = True
    roles.to_csv(OUT / "external_eligibility_addendum.csv", index=False)
    return roles


def stress(settings: dict) -> pd.DataFrame:
    rng = np.random.default_rng(settings["seed"])
    rows = []
    scenarios = [("twelve_perfectly_correlated", 12, 0.06), ("forty_perfectly_correlated", 40, 0.06), ("hundred_perfectly_correlated", 100, 0.06), ("rare_bad_group", 40, 0.02)]
    for name, n_groups, probability in scenarios:
        for repetition in range(1000):
            group_bad = rng.random(n_groups) < probability
            scores = np.zeros(n_groups * 20)
            failures = np.repeat(group_bad, 20)
            groups = np.repeat(np.arange(n_groups), 20)
            empirical = empirical_threshold(scores, failures, groups, np.array([0.0]), seed=int(rng.integers(2**31)), draws=500)
            rigorous = select_group_threshold(scores, failures, groups, np.array([0.0]))
            rows.append({"scenario": name, "repetition": repetition, "n_groups": n_groups, "true_selected_risk_if_admitted": probability, "no_observed_failed_groups": not group_bad.any(), "empirical_admits": bool(empirical["threshold"] == 0), "bounded_group_admits": rigorous.threshold == 0, "empirical_population_violation": bool(empirical["threshold"] == 0 and probability > settings["risk_cap"]), "bounded_group_population_violation": bool(rigorous.threshold == 0 and probability > settings["risk_cap"])})
    return pd.DataFrame(rows)


def main() -> int:
    settings = C.protocol()
    OUT.mkdir(parents=True, exist_ok=True)
    membership, sources = source_membership()
    membership.to_csv(OUT / "all_target_and_donor_membership.csv", index=False)
    grouped = independence_table(membership[["network_id", "canonical_station_id"]].rename(columns={"canonical_station_id": "station_id"}))
    grouped.to_csv(OUT / "complete_network_independence.csv", index=False)
    roles = audit_external(membership)
    simulations = stress(settings)
    simulations.to_csv(OUT / "cluster_risk_stress_repetitions.csv", index=False)
    summary = simulations.groupby("scenario").agg(n_repetitions=("repetition", "size"), empirical_violation_probability=("empirical_population_violation", "mean"), rigorous_violation_probability=("bounded_group_population_violation", "mean"), empirical_admission_probability=("empirical_admits", "mean"), rigorous_admission_probability=("bounded_group_admits", "mean"))
    summary.to_csv(OUT / "cluster_risk_stress_summary.csv")
    C.write_json(OUT / "summary.json", {"n_network_labels": len(grouped), "n_independent_groups_including_donors": grouped.independence_group.nunique(), "n_new_stations_after_all_input_audit": int(roles.eligible_after_full_input_audit.sum()), "new_stations_by_provider": roles.loc[roles.eligible_after_full_input_audit].groupby("provider").size().to_dict(), "independent_new_groups_by_role": roles.loc[roles.eligible_after_full_input_audit].groupby("external_role").independence_group.nunique().to_dict(), "new_test_performance_outcomes_inspected": False, "risk_bound_scope": "uniform independent deployment group and its within-group case sampling distribution; not every subgroup"})
    C.write_json(OUT / "protocol_fingerprint.json", C.fingerprint(Path(__file__), {"external_partition": C.RUN / "r3_02_external_resource/external_station_roles.csv"}, source_network_count=len(sources)))
    print(summary.to_string(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
