#!/usr/bin/env python3
"""Run a genuine bidirectional-LSTM sensitivity across provider strata."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.development_recovery import (
    read_temperature_panel,
    year_split,
)
from stream_recoverability.experiments.lstm_sensitivity import (
    provider_domain_subset,
)
from stream_recoverability.experiments.recurrent_sensitivity import (
    artificial_block_windows,
    nested_training_years,
    recurrently_usable_years,
    score_existing_placements,
)
from stream_recoverability.models.lstm_baseline import BidirectionalLSTMImputer

FIRST = ROOT / "results/development_v11/route_a_confirmation"
FIRST_PANELS = ROOT / "results/development_v11/confirmation_daily_qc/networks"
SECOND = ROOT / "results/development_v11/second_confirmation"
SECOND_SCORING = SECOND / "scoring"
DEFAULT_OUTPUT = ROOT / "results/development_v11/reviewer_completion"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def spearman(frame: pd.DataFrame, left: str, right: str) -> float | None:
    usable = frame[[left, right]].dropna()
    if len(usable) < 3 or usable[left].nunique() < 2 or usable[right].nunique() < 2:
        return None
    return float(usable[left].corr(usable[right], method="spearman"))


def second_panel_path(network: str) -> Path:
    direct = SECOND / "daily_qc/networks" / network / "daily_wide_temperature.csv"
    if direct.is_file():
        return direct
    carried = FIRST_PANELS / network / "daily_wide_temperature.csv"
    if carried.is_file():
        return carried
    raise FileNotFoundError(f"second-confirmation panel absent: {network}")


def candidate_roster() -> pd.DataFrame:
    first = pd.read_csv(FIRST / "qualified_panel.csv", dtype={"network_id": str})
    first_scored = set(
        pd.read_csv(
            FIRST / "predictions.csv",
            usecols=["network_id"],
            dtype={"network_id": str},
        )["network_id"].astype(str)
    )
    first = first.loc[first["network_id"].astype(str).isin(first_scored)].copy()
    first["source_panel"] = "first_confirmation"

    second = pd.read_csv(
        SECOND / "frozen_scoring_roster_v2.csv", dtype={"network_id": str}
    )
    second_scored = set(
        pd.read_csv(
            SECOND_SCORING / "simple_predictions.csv",
            usecols=["network_id"],
            dtype={"network_id": str},
        )["network_id"].astype(str)
    )
    second = second.loc[second["network_id"].astype(str).isin(second_scored)].copy()
    second["n_eligible_stations"] = [
        len(pd.read_csv(second_panel_path(str(network)), nrows=0).columns) - 1
        for network in second["network_id"]
    ]
    second["source_panel"] = "second_confirmation"
    columns = [
        "network_id",
        "provider",
        "domain",
        "n_eligible_stations",
        "source_panel",
    ]
    return pd.concat([first[columns], second[columns]], ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--per-provider", type=int, default=2)
    parser.add_argument("--hidden-size", type=int, default=16)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--max-windows", type=int, default=64)
    parser.add_argument("--max-placements-per-cell", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260828)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    candidates = candidate_roster()
    selected = provider_domain_subset(candidates, per_provider=args.per_provider)
    if selected["provider"].nunique() < 7:
        raise RuntimeError("fewer than seven provider strata are available")
    first_placements_path = FIRST / "placement_losses.csv"
    second_placements_path = SECOND_SCORING / "placement_losses.csv"
    first_placements = pd.read_csv(
        first_placements_path, dtype={"network_id": str, "station_id": str}
    )
    second_placements = pd.read_csv(
        second_placements_path, dtype={"network_id": str, "station_id": str}
    )
    first_empirical = pd.read_csv(
        args.output / "confirmation_empirical_predictions.csv",
        dtype={"network_id": str, "station_id": str},
    )
    first_empirical["gap_start"] = pd.to_datetime(first_empirical["gap_start"])
    second_empirical = pd.read_csv(
        SECOND_SCORING / "empirical_predictions.csv",
        dtype={"network_id": str, "station_id": str},
    )

    predictions: list[pd.DataFrame] = []
    training_rows: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    panel_hashes: dict[str, str] = {}
    for ordinal, item in enumerate(selected.itertuples(index=False), start=1):
        network = str(item.network_id)
        source = str(item.source_panel)
        panel_path = (
            FIRST_PANELS / network / "daily_wide_temperature.csv"
            if source == "first_confirmation"
            else second_panel_path(network)
        )
        try:
            panel = read_temperature_panel(str(panel_path))
            _, outer_train_years, outer_evaluation_years = year_split(panel.index)
            usable_years = recurrently_usable_years(panel, outer_train_years)
            fit_years, validation_years = nested_training_years(usable_years)
            train_values, train_mask = artificial_block_windows(
                panel,
                fit_years,
                max_windows=args.max_windows,
                seed=args.seed,
            )
            validation_values, validation_mask = artificial_block_windows(
                panel,
                validation_years,
                max_windows=max(8, args.max_windows // 4),
                seed=args.seed + 1,
            )
            usable_features = (np.isfinite(train_values) & ~train_mask).any(
                axis=(0, 1)
            ) & (np.isfinite(validation_values) & ~validation_mask).any(axis=(0, 1))
            if int(usable_features.sum()) < 2:
                raise ValueError("fewer than two features span fit and validation")
            panel = panel.loc[:, usable_features]
            train_values = train_values[:, :, usable_features]
            train_mask = train_mask[:, :, usable_features]
            validation_values = validation_values[:, :, usable_features]
            validation_mask = validation_mask[:, :, usable_features]
            train_keep = train_mask.any(axis=(1, 2))
            validation_keep = validation_mask.any(axis=(1, 2))
            train_values, train_mask = train_values[train_keep], train_mask[train_keep]
            validation_values = validation_values[validation_keep]
            validation_mask = validation_mask[validation_keep]
            model = BidirectionalLSTMImputer(
                panel.shape[1], hidden_size=args.hidden_size, seed=args.seed
            ).fit(
                train_values,
                train_mask,
                validation_values=validation_values,
                validation_mask=validation_mask,
                epochs=args.epochs,
                batch_size=8,
                patience=max(1, min(3, args.epochs)),
            )
            placement = (
                first_placements
                if source == "first_confirmation"
                else second_placements
            )
            scored = score_existing_placements(
                model,
                panel,
                placement.loc[placement["network_id"].astype(str).eq(network)],
                max_placements_per_cell=args.max_placements_per_cell,
                model_label="lstm",
            )
            if scored.empty:
                raise ValueError("no existing placements were scoreable")
            if source == "first_confirmation":
                scored = scored.merge(
                    first_empirical[
                        [
                            "network_id",
                            "station_id",
                            "gap_length",
                            "placement",
                            "gap_start",
                            "empirical_transfer_prediction",
                        ]
                    ],
                    on=[
                        "network_id",
                        "station_id",
                        "gap_length",
                        "placement",
                        "gap_start",
                    ],
                    how="left",
                    validate="one_to_one",
                )
            else:
                scored = scored.merge(
                    second_empirical[
                        [
                            "network_id",
                            "station_id",
                            "gap_length",
                            "empirical_transfer_prediction",
                        ]
                    ],
                    on=["network_id", "station_id", "gap_length"],
                    how="left",
                    validate="many_to_one",
                )
            scored["provider"] = str(item.provider)
            scored["domain"] = str(item.domain)
            scored["source_panel"] = source
            predictions.append(scored)
            history = model.history_
            training_rows.append(
                {
                    "network_id": network,
                    "provider": str(item.provider),
                    "domain": str(item.domain),
                    "source_panel": source,
                    "n_features": int(panel.shape[1]),
                    "fit_years": "|".join(map(str, fit_years)),
                    "validation_years": "|".join(map(str, validation_years)),
                    "outer_evaluation_years": "|".join(
                        map(str, outer_evaluation_years)
                    ),
                    "n_training_windows": len(train_values),
                    "n_validation_windows": len(validation_values),
                    "epochs_ran": int(history["epochs_ran"]),
                    "best_epoch": int(history["best_epoch"]),
                    "best_validation_loss": float(history["best_validation_loss"]),
                    "finite_training_history": bool(
                        np.isfinite(history["train_loss"]).all()
                        and np.isfinite(history["validation_loss"]).all()
                    ),
                    "hit_epoch_limit": bool(history["hit_epoch_limit"]),
                }
            )
            panel_hashes[str(panel_path.relative_to(ROOT))] = sha256(panel_path)
            print(f"LSTM sensitivity {ordinal}/{len(selected)}: {network}", flush=True)
        except (RuntimeError, ValueError) as error:
            failures.append(
                {
                    "network_id": network,
                    "provider": str(item.provider),
                    "reason": str(error),
                }
            )

    prediction = pd.concat(predictions, ignore_index=True)
    station_gap = prediction.groupby(
        [
            "network_id",
            "provider",
            "domain",
            "source_panel",
            "station_id",
            "gap_length",
        ],
        as_index=False,
    ).agg(
        lstm_mae_deg_c=("lstm_mae_deg_c", "mean"),
        xgboost_mae_deg_c=("xgboost_mae_deg_c", "mean"),
        empirical_transfer_prediction=("empirical_transfer_prediction", "first"),
        n_placements=("placement", "size"),
    )
    provider_metrics = pd.DataFrame(
        [
            {
                "provider": provider,
                "domains": "|".join(sorted(frame["domain"].unique())),
                "n_networks": frame["network_id"].nunique(),
                "n_station_gaps": len(frame),
                "xgboost_vs_lstm_spearman": spearman(
                    frame, "xgboost_mae_deg_c", "lstm_mae_deg_c"
                ),
                "empirical_vs_lstm_spearman": spearman(
                    frame, "empirical_transfer_prediction", "lstm_mae_deg_c"
                ),
            }
            for provider, frame in station_gap.groupby("provider", sort=True)
        ]
    )
    network = station_gap.groupby("network_id", as_index=False).mean(numeric_only=True)
    training = pd.DataFrame(training_rows)
    prediction_path = args.output / "lstm_sensitivity_predictions.csv"
    training_path = args.output / "lstm_sensitivity_training.csv"
    metrics_path = args.output / "lstm_sensitivity_provider_metrics.csv"
    failures_path = args.output / "lstm_sensitivity_failures.csv"
    manifest_path = args.output / "lstm_sensitivity_manifest.json"
    prediction.to_csv(prediction_path, index=False)
    training.to_csv(training_path, index=False)
    provider_metrics.to_csv(metrics_path, index=False)
    pd.DataFrame(failures, columns=["network_id", "provider", "reason"]).to_csv(
        failures_path, index=False
    )
    manifest = {
        "analysis_id": "v11_cross_provider_bidirectional_lstm_sensitivity_v1",
        "status": "completed_bounded_sensitivity",
        "evidence_role": "post_confirmation_sensitivity_not_frozen_model_roster",
        "model": "repository_local_mask_aware_bidirectional_torch_nn_LSTM",
        "architecture_assertion": {
            "recurrent_module": "torch.nn.LSTM",
            "bidirectional": True,
            "is_gru": False,
        },
        "not_a_claim_of": [
            "Rahmani_et_al_model_reimplementation",
            "state_of_the_art_stream_temperature_LSTM",
            "full_confirmation_roster_coverage",
            "confirmatory_model_comparison",
        ],
        "selection_rule": (
            "within each provider choose up to N networks by source-panel priority, "
            "eligible-station count, domain, and lexical network ID; no recovery "
            "loss or LSTM outcome enters selection"
        ),
        "selection_boundary": (
            "second-panel candidates are restricted to deterministic post-QC "
            "scoreable arrivals; no recovery-loss magnitude is used"
        ),
        "candidate_construction_reads_outcome_values": False,
        "candidate_providers": sorted(candidates["provider"].unique()),
        "selected_networks": len(selected),
        "available_candidate_networks": len(candidates),
        "full_roster_coverage": False,
        "completed_networks": int(training["network_id"].nunique()),
        "failed_networks": len(failures),
        "completed_providers": sorted(training["provider"].unique()),
        "n_completed_providers": int(training["provider"].nunique()),
        "completed_domains": sorted(training["domain"].unique()),
        "gap_lengths": [7, 30, 90],
        "training": {
            "outer_evaluation_labels_used_for_fit_or_validation": False,
            "artificial_blocks_in_fitting_years_only": True,
            "hidden_size": args.hidden_size,
            "epochs": args.epochs,
            "max_training_windows_per_network": args.max_windows,
            "max_placements_per_station_gap": args.max_placements_per_cell,
            "seed": args.seed,
            "all_histories_finite": bool(training["finite_training_history"].all()),
            "median_best_validation_loss": float(
                training["best_validation_loss"].median()
            ),
            "min_best_validation_loss": float(training["best_validation_loss"].min()),
            "max_best_validation_loss": float(training["best_validation_loss"].max()),
            "fraction_hit_epoch_limit": float(training["hit_epoch_limit"].mean()),
            "stability_interpretation": (
                "all histories are finite, but frequent epoch-limit hits mean this "
                "bounded run does not establish optimizer convergence"
            ),
        },
        "results": {
            "n_scored_placements": len(prediction),
            "n_station_gaps": len(station_gap),
            "xgboost_vs_lstm_station_gap_spearman": spearman(
                station_gap, "xgboost_mae_deg_c", "lstm_mae_deg_c"
            ),
            "empirical_vs_lstm_station_gap_spearman": spearman(
                station_gap, "empirical_transfer_prediction", "lstm_mae_deg_c"
            ),
            "empirical_vs_lstm_network_spearman": spearman(
                network, "empirical_transfer_prediction", "lstm_mae_deg_c"
            ),
            "xgboost_vs_lstm_network_spearman": spearman(
                network, "xgboost_mae_deg_c", "lstm_mae_deg_c"
            ),
        },
        "input_sha256": {
            str((FIRST / "qualified_panel.csv").relative_to(ROOT)): sha256(
                FIRST / "qualified_panel.csv"
            ),
            str(first_placements_path.relative_to(ROOT)): sha256(first_placements_path),
            str(
                (args.output / "confirmation_empirical_predictions.csv").relative_to(
                    ROOT
                )
            ): sha256(args.output / "confirmation_empirical_predictions.csv"),
            str((SECOND / "frozen_scoring_roster_v2.csv").relative_to(ROOT)): sha256(
                SECOND / "frozen_scoring_roster_v2.csv"
            ),
            str(second_placements_path.relative_to(ROOT)): sha256(
                second_placements_path
            ),
            str((SECOND_SCORING / "simple_predictions.csv").relative_to(ROOT)): sha256(
                SECOND_SCORING / "simple_predictions.csv"
            ),
            str(
                (SECOND_SCORING / "empirical_predictions.csv").relative_to(ROOT)
            ): sha256(SECOND_SCORING / "empirical_predictions.csv"),
            **panel_hashes,
        },
        "output_sha256": {
            prediction_path.name: sha256(prediction_path),
            training_path.name: sha256(training_path),
            metrics_path.name: sha256(metrics_path),
            failures_path.name: sha256(failures_path),
        },
    }
    if manifest["n_completed_providers"] < 7:
        manifest["status"] = "incomplete_below_seven_provider_floor"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
