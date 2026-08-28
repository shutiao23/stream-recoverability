#!/usr/bin/env python3
"""Acquire independent forcing and score an air2stream-8-equivalent baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.data.development_auxiliary import (
    Network,
    Site,
    download,
    nwis_url,
    parse_nwis,
)
from stream_recoverability.experiments.air2stream_equivalent import (
    AIR2STREAM8_LOWER,
    AIR2STREAM8_UPPER,
    fit_air2stream8,
    simulate_air2stream8,
)
from stream_recoverability.experiments.development_recovery import (
    year_split,
)

POWER_ENDPOINT = "https://power.larc.nasa.gov/api/temporal/daily/point"
FROZEN = ROOT / "results/development_v11/second_confirmation/frozen_scoring_roster_v2.csv"
CANDIDATES = ROOT / "results/development_v11/second_confirmation/candidates.csv"
TEMPERATURE_ROOT = ROOT / "results/development_v11/second_confirmation/daily_qc/networks"
PLACEMENTS = ROOT / "results/development_v11/second_confirmation/scoring/placement_losses.csv"
ATTRITION = ROOT / "results/development_v11/second_confirmation/scoring/scoring_attrition.csv"
SIMPLE = ROOT / "results/development_v11/second_confirmation/scoring/simple_predictions.csv"
EMPIRICAL = ROOT / "results/development_v11/second_confirmation/scoring/empirical_predictions.csv"
LOCATIONS = ROOT / "results/framework/public_catalog/usgs_long_temperature_locations.csv"
DEFAULT_OUTPUT = ROOT / "results/development_v11/independent_air2stream_equivalent"
UPSTREAM_COMMIT = "d4834bccf01657c03ab60efb4c18f8a256132c53"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def site_id(value: object) -> str:
    text = str(value).strip()
    return text.zfill(8) if text.isdigit() and len(text) < 8 else text


def power_url(site: Site) -> str:
    query = urllib.parse.urlencode(
        {
            "parameters": "T2M",
            "community": "AG",
            "longitude": site.longitude,
            "latitude": site.latitude,
            "start": site.start.replace("-", ""),
            "end": site.end.replace("-", ""),
            "format": "JSON",
            "time-standard": "LST",
        }
    )
    return f"{POWER_ENDPOINT}?{query}"


def read_power_t2m(payload: bytes, station: str) -> pd.DataFrame:
    document = json.loads(payload)
    fill = float(document["header"]["fill_value"])
    values = document["properties"]["parameter"]["T2M"]
    numeric = pd.to_numeric(pd.Series(values), errors="coerce")
    numeric = numeric.mask(numeric.eq(fill))
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(numeric.index, format="%Y%m%d"),
            "station_id": station,
            "air_temperature_c": numeric.to_numpy(dtype=float),
        }
    )
    if frame["date"].duplicated().any():
        raise ValueError("NASA POWER returned duplicate dates")
    return frame


def correlation(frame: pd.DataFrame, left: str, right: str) -> float | None:
    usable = frame[[left, right]].dropna()
    if len(usable) < 3 or usable[left].nunique() < 2 or usable[right].nunique() < 2:
        return None
    return float(usable[left].corr(usable[right], method="spearman"))


def metrics(station_gap: pd.DataFrame) -> dict[str, object]:
    network = station_gap.groupby("network_id", as_index=False).mean(numeric_only=True)
    result: dict[str, object] = {
        "n_networks": int(station_gap["network_id"].nunique()),
        "n_stations": int(
            station_gap[["network_id", "station_id"]].drop_duplicates().shape[0]
        ),
        "n_station_gaps": len(station_gap),
        "n_placements": int(station_gap["n_placements"].sum()),
        "mean_air2stream_mae_deg_c": float(station_gap["air2stream_mae_deg_c"].mean()),
        "xgboost_vs_air2stream_station_gap_spearman": correlation(
            station_gap, "xgboost_mae_deg_c", "air2stream_mae_deg_c"
        ),
        "xgboost_vs_air2stream_network_spearman": correlation(
            network, "xgboost_mae_deg_c", "air2stream_mae_deg_c"
        ),
        "simple_risk_vs_air2stream_station_gap_spearman": correlation(
            station_gap, "simple_predicted_loss", "air2stream_mae_deg_c"
        ),
        "simple_risk_vs_air2stream_network_spearman": correlation(
            network, "simple_predicted_loss", "air2stream_mae_deg_c"
        ),
        "empirical_risk_vs_air2stream_station_gap_spearman": correlation(
            station_gap, "empirical_transfer_prediction", "air2stream_mae_deg_c"
        ),
        "empirical_risk_vs_air2stream_network_spearman": correlation(
            network, "empirical_transfer_prediction", "air2stream_mae_deg_c"
        ),
    }
    supported = station_gap.loc[station_gap["gap_length"].isin([7, 30, 90, 180])]
    supported_network = supported.groupby("network_id", as_index=False).mean(numeric_only=True)
    result.update(
        {
            "supported_horizon_station_gaps": len(supported),
            "supported_empirical_vs_air2stream_station_gap_spearman": correlation(
                supported, "empirical_transfer_prediction", "air2stream_mae_deg_c"
            ),
            "supported_empirical_vs_air2stream_network_spearman": correlation(
                supported_network,
                "empirical_transfer_prediction",
                "air2stream_mae_deg_c",
            ),
        }
    )
    return result


def selected_networks() -> list[str]:
    frozen = pd.read_csv(FROZEN, dtype=str)
    attrited = set(pd.read_csv(ATTRITION, usecols=["network_id"], dtype=str)["network_id"])
    eligible = frozen.loc[
        frozen["provider"].eq("usgs") & ~frozen["network_id"].isin(attrited),
        "network_id",
    ]
    return sorted(eligible.astype(str).unique())[:12]


def acquire_inputs(output: Path, *, refresh: bool, workers: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    input_path = output / "daily_forcing.parquet"
    coverage_path = output / "input_coverage.csv"
    if input_path.exists() and coverage_path.exists() and not refresh:
        return pd.read_parquet(input_path), pd.read_csv(coverage_path, dtype=str)

    locations = pd.read_csv(LOCATIONS, dtype={"site_id": str})
    locations["site_id"] = locations["site_id"].map(site_id)
    locations = locations.set_index("site_id")
    coverage_rows: list[dict[str, object]] = []
    eligible_sites: list[tuple[str, Site, pd.DatetimeIndex]] = []
    flow_frames: list[pd.DataFrame] = []
    request_rows: list[dict[str, object]] = []

    for network_id in selected_networks():
        temperature_path = TEMPERATURE_ROOT / network_id / "daily_wide_temperature.csv"
        panel = pd.read_csv(temperature_path, index_col=0, parse_dates=True).asfreq("D")
        panel.columns = panel.columns.astype(str)
        sites = []
        for station in panel.columns:
            normalized = site_id(station)
            location = locations.loc[normalized]
            sites.append(
                Site(
                    normalized,
                    str(panel.index.min().date()),
                    str(panel.index.max().date()),
                    float(location["longitude"]),
                    float(location["latitude"]),
                )
            )
        network = Network(network_id, "second_confirmation", tuple(sites))
        url = nwis_url(network)
        request_rows.append({"network_id": network_id, "station_id": None, "source": "usgs", "url": url})
        flow = parse_nwis(download(url)).loc[lambda x: x["variable"].eq("F")].copy()
        flow_frames.append(flow.assign(network_id=network_id))
        for station in panel.columns:
            normalized = site_id(station)
            station_flow = flow.loc[
                flow["site_id"].eq(normalized) & flow["quality_approved"],
                ["date", "value"],
            ].drop_duplicates("date")
            aligned = station_flow.set_index("date")["value"].reindex(panel.index)
            complete = bool(aligned.notna().all() and aligned.gt(0.0).all())
            coverage_rows.append(
                {
                    "network_id": network_id,
                    "station_id": station,
                    "panel_start": str(panel.index.min().date()),
                    "panel_end": str(panel.index.max().date()),
                    "n_panel_days": len(panel),
                    "n_approved_flow_days": int(aligned.notna().sum()),
                    "approved_flow_fraction": float(aligned.notna().mean()),
                    "strict_positive_complete_flow": complete,
                    "n_air_days": 0,
                    "complete_air_temperature": False,
                    "input_eligible": False,
                }
            )
            if complete:
                site = next(value for value in sites if value.site_id == normalized)
                eligible_sites.append((network_id, site, panel.index))

    air_frames: list[pd.DataFrame] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        pending = {
            executor.submit(download, power_url(site)): (network_id, site, index)
            for network_id, site, index in eligible_sites
        }
        for future in as_completed(pending):
            network_id, site, index = pending[future]
            url = power_url(site)
            request_rows.append(
                {"network_id": network_id, "station_id": site.site_id, "source": "nasa_power", "url": url}
            )
            frame = read_power_t2m(future.result(), site.site_id)
            frame["network_id"] = network_id
            air_frames.append(frame)
            aligned = frame.set_index("date")["air_temperature_c"].reindex(index)
            for row in coverage_rows:
                if row["network_id"] == network_id and site_id(row["station_id"]) == site.site_id:
                    row["n_air_days"] = int(aligned.notna().sum())
                    row["complete_air_temperature"] = bool(aligned.notna().all())
                    row["input_eligible"] = bool(aligned.notna().all())

    coverage = pd.DataFrame(coverage_rows)
    flow = pd.concat(flow_frames, ignore_index=True)
    flow = flow.loc[flow["quality_approved"], ["network_id", "site_id", "date", "value"]]
    flow = flow.rename(columns={"site_id": "station_id", "value": "discharge_m3s"})
    air = pd.concat(air_frames, ignore_index=True)
    forcing = air.merge(flow, on=["network_id", "station_id", "date"], how="inner")
    forcing = forcing.sort_values(["network_id", "station_id", "date"])
    forcing.to_parquet(input_path, index=False)
    coverage.to_csv(coverage_path, index=False)
    pd.DataFrame(request_rows).to_csv(output / "input_requests.csv", index=False)
    return forcing, coverage


def score(output: Path, forcing: pd.DataFrame, *, max_nfev: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    placements = pd.read_csv(PLACEMENTS, dtype={"network_id": str, "station_id": str})
    placements["gap_start"] = pd.to_datetime(placements["gap_start"])
    simple = pd.read_csv(SIMPLE, dtype={"network_id": str, "station_id": str})
    empirical = pd.read_csv(EMPIRICAL, dtype={"network_id": str, "station_id": str})
    rows: list[dict[str, object]] = []
    parameters: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []

    for (network_id, station), inputs in forcing.groupby(["network_id", "station_id"], sort=True):
        panel_path = TEMPERATURE_ROOT / network_id / "daily_wide_temperature.csv"
        panel = pd.read_csv(panel_path, index_col=0, parse_dates=True).asfreq("D")
        panel.columns = panel.columns.astype(str)
        station_column = next((value for value in panel.columns if site_id(value) == station), None)
        if station_column is None:
            failures.append({"network_id": network_id, "station_id": station, "reason": "station_absent"})
            continue
        aligned = inputs.set_index("date").reindex(panel.index)
        target = pd.to_numeric(panel[station_column], errors="coerce")
        train_mask, training_years, evaluation_years = year_split(panel.index)
        try:
            fit = fit_air2stream8(
                panel.index[train_mask],
                target.loc[train_mask].to_numpy(dtype=float),
                aligned.loc[train_mask, "air_temperature_c"].to_numpy(dtype=float),
                aligned.loc[train_mask, "discharge_m3s"].to_numpy(dtype=float),
                max_nfev=max_nfev,
            )
            evaluation_index = panel.index[~train_mask]
            evaluation_target = target.loc[~train_mask]
            finite = np.flatnonzero(evaluation_target.notna().to_numpy())
            if not len(finite):
                raise ValueError("no observed evaluation water temperature")
            first = int(finite[0])
            predicted = simulate_air2stream8(
                evaluation_index[first:],
                aligned.loc[evaluation_index[first:], "air_temperature_c"].to_numpy(dtype=float),
                aligned.loc[evaluation_index[first:], "discharge_m3s"].to_numpy(dtype=float),
                fit.parameters,
                initial_water_temperature_c=float(evaluation_target.iloc[first]),
                discharge_reference=fit.discharge_reference,
            )
        except ValueError as error:
            failures.append({"network_id": network_id, "station_id": station, "reason": str(error)})
            continue
        prediction = pd.Series(predicted, index=evaluation_index[first:])
        selected = placements.loc[
            placements["network_id"].eq(network_id)
            & placements["station_id"].map(site_id).eq(station)
            & placements["information_condition"].eq("B_union_D")
        ]
        for item in selected.itertuples(index=False):
            dates = pd.date_range(item.gap_start, periods=int(item.gap_length), freq="D")
            truth = target.reindex(dates)
            estimate = prediction.reindex(dates)
            if truth.isna().any() or estimate.isna().any():
                continue
            rows.append(
                {
                    "network_id": network_id,
                    "station_id": station,
                    "gap_length": int(item.gap_length),
                    "placement": int(item.placement),
                    "gap_start": str(pd.Timestamp(item.gap_start).date()),
                    "air2stream_mae_deg_c": float(np.mean(np.abs(estimate - truth))),
                    "xgboost_mae_deg_c": float(item.mae_deg_c),
                }
            )
        parameters.append(
            {
                "network_id": network_id,
                "station_id": station,
                **{f"a{number}": float(value) for number, value in enumerate(fit.parameters, 1)},
                "discharge_reference_m3s": fit.discharge_reference,
                "training_rmse_deg_c": fit.training_rmse,
                "n_training_observations": fit.n_training_observations,
                "n_function_evaluations": fit.n_function_evaluations,
                "optimizer_status": fit.optimizer_status,
                "training_years": "|".join(map(str, training_years)),
                "evaluation_years": "|".join(map(str, evaluation_years)),
            }
        )

    placement = pd.DataFrame(rows)
    if placement.empty:
        return placement, pd.DataFrame(parameters), pd.DataFrame(failures)
    station_gap = placement.groupby(
        ["network_id", "station_id", "gap_length"], as_index=False
    ).agg(
        air2stream_mae_deg_c=("air2stream_mae_deg_c", "mean"),
        xgboost_mae_deg_c=("xgboost_mae_deg_c", "mean"),
        n_placements=("placement", "size"),
    )
    station_gap = station_gap.merge(
        simple[["network_id", "station_id", "gap_length", "predicted_loss"]].rename(
            columns={"predicted_loss": "simple_predicted_loss"}
        ),
        on=["network_id", "station_id", "gap_length"],
        how="left",
    ).merge(
        empirical[
            ["network_id", "station_id", "gap_length", "empirical_transfer_prediction"]
        ],
        on=["network_id", "station_id", "gap_length"],
        how="left",
    )
    placement.to_csv(output / "placement_losses.csv", index=False)
    station_gap.to_csv(output / "station_gap_losses.csv", index=False)
    pd.DataFrame(parameters).to_csv(output / "model_parameters.csv", index=False)
    pd.DataFrame(failures).to_csv(output / "failures.csv", index=False)
    return station_gap, pd.DataFrame(parameters), pd.DataFrame(failures)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--refresh-inputs", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-nfev", type=int, default=500)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    forcing, coverage = acquire_inputs(
        args.output, refresh=args.refresh_inputs, workers=args.workers
    )
    station_gap, parameters, failures = score(
        args.output, forcing, max_nfev=args.max_nfev
    )
    eligible_mask = coverage["input_eligible"].astype(str).str.lower().eq("true")
    input_failures = coverage.loc[~eligible_mask, ["network_id", "station_id"]].copy()
    excluded_flow_complete = (
        coverage.loc[~eligible_mask, "strict_positive_complete_flow"]
        .astype(str)
        .str.lower()
        .eq("true")
        .to_numpy()
    )
    input_failures["reason"] = np.where(
        excluded_flow_complete,
        "incomplete_nasa_power_t2m",
        "incomplete_or_nonpositive_same_site_approved_flow",
    )
    all_failures = pd.concat([input_failures, failures], ignore_index=True)
    all_failures.to_csv(args.output / "failures.csv", index=False)
    parameter_values = (
        parameters[[f"a{number}" for number in range(1, 9)]].to_numpy(dtype=float)
        if not parameters.empty
        else np.empty((0, 8))
    )
    bound_hits = (
        np.isclose(parameter_values, AIR2STREAM8_LOWER, atol=1e-4)
        | np.isclose(parameter_values, AIR2STREAM8_UPPER, atol=1e-4)
    )
    manifest = {
        "analysis_id": "second_confirmation_air2stream8_equivalent_v1",
        "evidence_role": "independent_input_availability_subset_no_outcome_selection",
        "selection_rule": "lexical_first_12_nonattrited_frozen_US_networks_then_strict_complete_positive_same_site_approved_flow_and_complete_POWER_T2M",
        "selected_networks_before_input_qc": selected_networks(),
        "model": {
            "identity": "air2stream_8_equation_crank_nicolson_python_equivalent",
            "published_equation": True,
            "original_executable_used": False,
            "published_doi": "10.1088/1748-9326/10/11/114011",
            "upstream_repository": "https://github.com/spiccolroaz/air2stream",
            "upstream_commit_reviewed": UPSTREAM_COMMIT,
            "upstream_license": "CC-BY-SA-3.0",
            "parameter_bounds": {
                "lower": AIR2STREAM8_LOWER.tolist(),
                "upper": AIR2STREAM8_UPPER.tolist(),
                "source": "upstream Switzerland/parameters.txt",
            },
            "differences": [
                "bounded_deterministic_multistart_least_squares_replaces_particle_swarm_optimization",
                "Python_translation_of_the_published_8_parameter_equation_and_Crank_Nicolson_update",
                "NASA_POWER_local_solar_daily_T2M_date_labels_are_joined_to_USGS_station_local_civil_daily_discharge",
            ],
        },
        "input_rules": {
            "air_temperature": "NASA POWER T2M daily LST; finite non-fill values only",
            "discharge": "USGS daily mean 00060 stat 00003; qualifier prefix A only; converted ft3/s to m3/s",
            "flow_completeness": "every panel date finite and strictly positive; no interpolation",
            "calibration": "outer fitting years only; first 365 days warm-up",
            "evaluation": "second-confirmation artificial gaps; no loss used for subset selection",
        },
        "coverage": {
            "candidate_networks": 12,
            "candidate_stations": len(coverage),
            "input_eligible_networks": int(
                coverage.loc[coverage["input_eligible"].astype(str).str.lower().eq("true"), "network_id"].nunique()
            ),
            "input_eligible_stations": int(
                coverage["input_eligible"].astype(str).str.lower().eq("true").sum()
            ),
            "fitted_stations": len(parameters),
            "fit_failures": len(failures),
            "input_excluded_stations": int((~eligible_mask).sum()),
            "parameter_bound_hit_stations": int(bound_hits.any(axis=1).sum()),
            "parameter_bound_hits": int(bound_hits.sum()),
        },
        "results": metrics(station_gap) if not station_gap.empty else {},
        "input_sha256": {
            str(path.relative_to(ROOT)): sha256(path)
            for path in [FROZEN, CANDIDATES, ATTRITION, PLACEMENTS, SIMPLE, EMPIRICAL, LOCATIONS]
        },
        "output_sha256": {
            path.name: sha256(path)
            for path in sorted(args.output.iterdir())
            if path.is_file() and path.suffix in {".csv", ".parquet"}
        },
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
