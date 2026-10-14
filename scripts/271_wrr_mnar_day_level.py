#!/usr/bin/env python3
"""P0-05 / F06: day-level MNAR sensitivity with true re-peaking.

Reconstruct each reserved case's outage mask from ``stable_seed`` +
``design_for_year`` (the same path that built the case table), refill hidden
days with the certificate-chosen estimator, add a constant δ °C only on those
hidden days, then recompute the hottest-30 rolling mean. Window-switch rate is
the share of cases whose argmax window end moves after the perturbation.

Does not overwrite ``amendments/mnar_pattern_mixture/`` (the historical
approximation). Results are a reserved-subset sensitivity, not an MNAR
identification bound.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.cases import (  # noqa: E402
    station_geometry_pool,
)
from stream_recoverability.experiments.v17_fitness.estimators import (  # noqa: E402
    StationModels,
    hottest_window_mean,
    linear_interp_fill,
    usable_donors,
)
from stream_recoverability.experiments.v17_fitness.outages import (  # noqa: E402
    climatological_peak_window,
    design_for_year,
)
from stream_recoverability.experiments.v17_fitness.panel import (  # noqa: E402
    air_series_for,
    load_network_panel,
)
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    HOTTEST_WINDOW_DAYS,
    REALIZATIONS_PER_STATION_YEAR,
    TRUSTED_YEARS,
    stable_seed,
)
READY = ROOT / "results" / "wrr_submission_ready"
OUT = READY / "amendments" / "mnar_day_level"
RETENTION = 0.70
TOLERANCE_C = 0.5
BIASES = (-1.0, -0.5, 0.0, 0.5, 1.0)
WINDOW = HOTTEST_WINDOW_DAYS
N_EMPIRICAL = max(1, REALIZATIONS_PER_STATION_YEAR // 3)


def peak_end(values: np.ndarray) -> int:
    rolled = pd.Series(values, dtype=float).rolling(WINDOW, min_periods=WINDOW).mean().to_numpy()
    if not np.isfinite(rolled).any():
        return -1
    return int(np.nanargmax(rolled))


def complete_years_for(network_id: str, station_id: str, trusted: pd.DataFrame) -> tuple[int, ...]:
    block = trusted.loc[
        (trusted["network_id"].astype(str) == network_id)
        & (trusted["station_id"].astype(str) == station_id)
        & trusted["eligible_annual_truth"].astype(bool)
    ]
    return tuple(int(y) for y in sorted(block["year"].unique()))


def fill_for_choice(
    choice: str,
    *,
    models: StationModels,
    year_index: pd.DatetimeIndex,
    observed: np.ndarray,
    donors: pd.DataFrame,
    mask: np.ndarray,
) -> np.ndarray:
    if choice == "doy_climatology":
        return models.doy_climatology(year_index)
    if choice == "smooth_climatology":
        return models.smooth_climatology(year_index)
    if choice == "linear_interp":
        return linear_interp_fill(observed)
    if choice == "donor_ridge":
        visible = usable_donors(donors, year_index, mask)
        fitted = models.donor_ridge(visible) if visible else None
        if fitted is None:
            return np.full(len(year_index), np.nan)
        return models.donor_predict(fitted, year_index)
    if choice == "air_ridge":
        return models.air_predict(year_index)
    return np.full(len(year_index), np.nan)


def clustered_contrast(frame: pd.DataFrame, biased_abs: pd.Series, draws: int = 400, seed: int = 0) -> dict:
    work = frame.reset_index(drop=True)
    biased = biased_abs.reset_index(drop=True).to_numpy(dtype=float)
    codes, _ = pd.factorize(work["network_id"])
    order = np.argsort(codes, kind="mergesort")
    codes_sorted = codes[order]
    boundaries = np.searchsorted(codes_sorted, np.arange(codes.max() + 1), side="left")
    ends = np.append(boundaries[1:], len(codes_sorted))
    blocks = [order[start:end] for start, end in zip(boundaries, ends)]
    cert_bound = work["cert_bound"].to_numpy(dtype=float)
    length = work["length"].to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    values = np.empty(draws, dtype=float)
    for draw in range(draws):
        picked = rng.integers(0, len(blocks), size=len(blocks))
        index = np.concatenate([blocks[i] for i in picked])
        k = max(1, int(round(RETENTION * len(index))))
        cert_keep = index[np.argpartition(cert_bound[index], k - 1)[:k]]
        length_keep = index[np.argpartition(length[index], k - 1)[:k]]
        cert_rate = float((biased[cert_keep] > TOLERANCE_C).mean())
        length_rate = float((biased[length_keep] > TOLERANCE_C).mean())
        values[draw] = (cert_rate - length_rate) * 100
    k = max(1, int(round(RETENTION * len(work))))
    cert_keep = work["cert_bound"].nsmallest(k).index
    length_keep = work["length"].nsmallest(k).index
    cert_rate = float((biased_abs.loc[cert_keep] > TOLERANCE_C).mean())
    length_rate = float((biased_abs.loc[length_keep] > TOLERANCE_C).mean())
    return {
        "certificate_rate": cert_rate,
        "length_rate": length_rate,
        "contrast_points": (cert_rate - length_rate) * 100,
        "ci_low": float(np.nanpercentile(values, 2.5)),
        "ci_high": float(np.nanpercentile(values, 97.5)),
        "n_cases": int(len(work)),
        "n_networks": int(work["network_id"].nunique()),
        "retention_of_evaluated_cases": RETENTION,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-networks", type=int, default=6)
    parser.add_argument("--max-cases-per-network", type=int, default=80)
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    cases = pd.read_parquet(ROOT / "results/v17_fitness/step10_confirmation/reserved_cases.parquet").reset_index(
        drop=True
    )
    certs = pd.read_parquet(
        ROOT / "results/v17_fitness/step10_confirmation/reserved_certificates.parquet"
    ).reset_index(drop=True)
    cases["certificate_choice"] = certs["certificate_choice"].to_numpy()
    cases["cert_bound"] = pd.to_numeric(certs["certificate_bound"], errors="coerce")
    roster = pd.read_csv(ROOT / "results/v17_fitness/step1_panel/station_roster.csv")
    trusted = pd.read_csv(TRUSTED_YEARS)
    source_by_net = {
        str(r.network_id): str(r.source_root)
        for r in roster.drop_duplicates("network_id").itertuples(index=False)
    }

    sizes = cases.groupby("network_id").size().sort_values()
    networks = [str(n) for n in sizes.index if source_by_net.get(str(n))][: args.max_networks]

    reconstructed = []
    skipped = []
    for network_id in networks:
        source_root = source_by_net[network_id]
        try:
            daily = load_network_panel(network_id, source_root)
        except (FileNotFoundError, ValueError, KeyError) as exc:
            skipped.append({"network_id": network_id, "reason": f"panel_load:{exc}"})
            continue
        daily = daily.copy()
        daily.columns = [str(c) for c in daily.columns]
        pool = station_geometry_pool(daily)
        block = cases.loc[cases["network_id"].astype(str).eq(network_id)]
        if args.max_cases_per_network:
            block = block.groupby(["station_id", "year"], group_keys=False).head(
                max(1, args.max_cases_per_network // max(1, block["station_id"].nunique()))
            )
            block = block.head(args.max_cases_per_network)
        for (station_id, year, protocol), sub in block.groupby(
            ["station_id", "year", "fit_protocol"]
        ):
            station_id = str(station_id)
            year = int(year)
            protocol = str(protocol)
            if station_id not in daily.columns:
                skipped.append({"network_id": network_id, "station_id": station_id, "reason": "station_absent"})
                continue
            target = pd.to_numeric(daily[station_id], errors="coerce")
            donors = daily.drop(columns=[station_id])
            air = air_series_for(network_id, station_id, daily.index)
            complete_years = complete_years_for(network_id, station_id, trusted)
            year_mask = target.index.year == year
            year_index = daily.index[year_mask]
            truth = target.loc[year_mask].to_numpy(dtype=float)
            if not np.isfinite(truth).all() or len(truth) < 360:
                skipped.append(
                    {"network_id": network_id, "station_id": station_id, "year": year, "reason": "incomplete_truth"}
                )
                continue
            if protocol == "strictly_prior_years":
                train_mask = pd.Series(daily.index.year < year, index=daily.index)
                peak_source = target.loc[target.index.year < year]
            else:
                train_mask = pd.Series(~year_mask, index=daily.index)
                peak_source = target.loc[target.index.year != year]
            models = StationModels(target=target, donors=donors, air=air, train_mask=train_mask)
            peak_doys = climatological_peak_window(peak_source, exclude_year=None)
            rng = np.random.default_rng(stable_seed(network_id, station_id, year, protocol))
            realizations = {
                item.realization_id: item
                for item in design_for_year(
                    year_index, peak_doys, pool, rng=rng, n_empirical=N_EMPIRICAL, cross_overlap=False
                )
            }
            wanted = set(sub["realization_id"].astype(str))
            for _, case in sub.iterrows():
                rid = str(case["realization_id"])
                item = realizations.get(rid)
                if item is None:
                    skipped.append(
                        {
                            "network_id": network_id,
                            "station_id": station_id,
                            "year": year,
                            "realization_id": rid,
                            "reason": "realization_not_reproduced",
                        }
                    )
                    continue
                mask = item.mask(len(year_index))
                observed = truth.copy()
                observed[mask] = np.nan
                choice = str(case["certificate_choice"])
                fill = fill_for_choice(
                    choice,
                    models=models,
                    year_index=year_index,
                    observed=observed,
                    donors=donors,
                    mask=mask,
                )
                completed = observed.copy()
                completed[mask] = fill[mask]
                if not np.isfinite(completed).all():
                    skipped.append(
                        {
                            "network_id": network_id,
                            "station_id": station_id,
                            "year": year,
                            "realization_id": rid,
                            "reason": "fill_not_finite",
                            "choice": choice,
                        }
                    )
                    continue
                baseline_peak = hottest_window_mean(completed)
                baseline_end = peak_end(completed)
                truth_peak = float(case["truth_hottest30"]) if np.isfinite(case["truth_hottest30"]) else hottest_window_mean(truth)
                truth_end = peak_end(truth)
                reconstructed.append(
                    {
                        "network_id": network_id,
                        "station_id": station_id,
                        "year": year,
                        "realization_id": rid,
                        "arm": str(case["arm"]),
                        "certificate_choice": choice,
                        "cert_bound": float(case["cert_bound"]),
                        "longest_run": float(case["longest_run"]),
                        "true_peak_hidden_fraction": float(case["true_peak_hidden_fraction"]),
                        "truth_hottest30": float(truth_peak),
                        "baseline_reconstructed_hottest30": float(baseline_peak),
                        "baseline_abs_error": abs(float(baseline_peak) - float(truth_peak)),
                        "baseline_window_end": int(baseline_end),
                        "truth_window_end": int(truth_end),
                        "n_hidden_days": int(mask.sum()),
                        "_mask": mask,
                        "_completed": completed,
                    }
                )

    if not reconstructed:
        status = {
            "status": "no_cases_reconstructed",
            "claim_status": "pending_confirmation",
            "may_enter_abstract_or_conclusions": False,
            "n_skipped": len(skipped),
        }
        (OUT / "summary.json").write_text(json.dumps(status, indent=2) + "\n")
        pd.DataFrame(skipped).to_csv(OUT / "skipped.csv", index=False)
        print(json.dumps(status, indent=2))
        return 1

    frame_rows = []
    bias_rows = []
    for rec in reconstructed:
        mask = rec.pop("_mask")
        completed = rec.pop("_completed")
        frame_rows.append(rec)
        base_end = rec["baseline_window_end"]
        truth = rec["truth_hottest30"]
        for delta in BIASES:
            perturbed = completed.copy()
            perturbed[mask] = completed[mask] + float(delta)
            peak = hottest_window_mean(perturbed)
            end = peak_end(perturbed)
            bias_rows.append(
                {
                    "network_id": rec["network_id"],
                    "station_id": rec["station_id"],
                    "year": rec["year"],
                    "realization_id": rec["realization_id"],
                    "arm": rec["arm"],
                    "delta_C": float(delta),
                    "perturbed_hottest30": float(peak),
                    "abs_error_C": abs(float(peak) - float(truth)),
                    "signed_error_C": float(peak) - float(truth),
                    "window_switched": bool(end != base_end and end >= 0 and base_end >= 0),
                    "perturbed_window_end": int(end),
                }
            )

    cases_out = pd.DataFrame(frame_rows)
    biases = pd.DataFrame(bias_rows)
    cases_out.to_parquet(OUT / "reconstructed_cases.parquet", index=False)
    biases.to_parquet(OUT / "day_level_perturbations.parquet", index=False)
    pd.DataFrame(skipped).to_csv(OUT / "skipped.csv", index=False)

    curve = []
    meta = cases_out[["network_id", "station_id", "year", "realization_id", "cert_bound", "longest_run"]].copy()
    rng = np.random.default_rng(0)
    meta["length"] = meta["longest_run"] + rng.random(len(meta))
    for delta in BIASES:
        part = biases.loc[biases["delta_C"] == delta]
        merged = meta.merge(
            part,
            on=["network_id", "station_id", "year", "realization_id"],
            how="inner",
        )
        contrast = clustered_contrast(merged, merged["abs_error_C"])
        contrast["delta_C"] = float(delta)
        contrast["window_switch_rate"] = float(part["window_switched"].mean())
        by_arm = {}
        for arm, grp in merged.groupby("arm"):
            by_arm[str(arm)] = {
                "n": int(len(grp)),
                "mean_abs_error_C": float(grp["abs_error_C"].mean()),
                "window_switch_rate": float(grp["window_switched"].mean()),
            }
        contrast["by_arm"] = by_arm
        curve.append(contrast)

    summary = {
        "status": "day_level_reserved_subset",
        "claim_status": "exploratory_sensitivity_not_identification_bound",
        "may_enter_abstract_or_conclusions": False,
        "n_cases_reconstructed": int(len(cases_out)),
        "n_networks": int(cases_out["network_id"].nunique()),
        "n_skipped": int(len(skipped)),
        "networks": networks,
        "biases_C": list(BIASES),
        "window_days": WINDOW,
        "note": (
            "Perturbation is a constant offset on reconstructed hidden days only; "
            "the hottest-30 window is re-sought. This is a specified-scenario "
            "sensitivity on a reserved subset, not an MNAR identification bound. "
            "Do not cite scripts/258 approximation."
        ),
        "bias_curve": curve,
    }
    pd.DataFrame(
        [{k: v for k, v in row.items() if k != "by_arm"} | {"by_arm_json": json.dumps(row["by_arm"])} for row in curve]
    ).to_csv(OUT / "bias_curve.csv", index=False)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: summary[k] for k in summary if k != "bias_curve"}, indent=2))
    for row in curve:
        print(
            f"  δ={row['delta_C']:+.1f} Δ={row['contrast_points']:+.2f} "
            f"[{row['ci_low']:+.2f},{row['ci_high']:+.2f}] "
            f"switch={row['window_switch_rate']:.3f} n={row['n_cases']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
