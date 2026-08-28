#!/usr/bin/env python3
"""Run a bounded, explicitly exploratory BRITS sensitivity on confirmation one."""

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
from stream_recoverability.experiments.recurrent_sensitivity import (
    artificial_block_windows,
    nested_training_years,
    provider_stratified_subset,
    recurrently_usable_years,
    score_existing_placements,
)
from stream_recoverability.models.deep_baselines import BRITSImputer

CONFIRMATION = ROOT / "results/development_v11/route_a_confirmation"
PANELS = ROOT / "results/development_v11/confirmation_daily_qc/networks"
EMPIRICAL = (
    ROOT
    / "results/development_v11/reviewer_completion/confirmation_empirical_predictions.csv"
)
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--per-provider", type=int, default=1)
    parser.add_argument("--hidden-size", type=int, default=16)
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--max-windows", type=int, default=48)
    parser.add_argument("--max-placements-per-cell", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260828)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    qualified_path = CONFIRMATION / "qualified_panel.csv"
    placements_path = CONFIRMATION / "placement_losses.csv"
    qualified = pd.read_csv(qualified_path, dtype={"network_id": str})
    placements = pd.read_csv(
        placements_path, dtype={"network_id": str, "station_id": str}
    )
    selected = provider_stratified_subset(
        qualified,
        placements["network_id"].astype(str).unique(),
        per_provider=args.per_provider,
    )
    predictions: list[pd.DataFrame] = []
    training_rows: list[dict[str, object]] = []
    panel_hashes: dict[str, str] = {}
    for item in selected.itertuples(index=False):
        network = str(item.network_id)
        panel_path = PANELS / network / "daily_wide_temperature.csv"
        panel = read_temperature_panel(str(panel_path))
        _, outer_train_years, outer_evaluation_years = year_split(panel.index)
        usable_outer_years = recurrently_usable_years(panel, outer_train_years)
        fit_years, validation_years = nested_training_years(usable_outer_years)
        train_values, train_mask = artificial_block_windows(
            panel,
            fit_years,
            max_windows=args.max_windows,
            seed=args.seed,
        )
        validation_values, validation_mask = artificial_block_windows(
            panel,
            validation_years,
            max_windows=max(6, args.max_windows // 4),
            seed=args.seed + 1,
        )
        usable_features = (
            (np.isfinite(train_values) & ~train_mask).any(axis=(0, 1))
            & (np.isfinite(validation_values) & ~validation_mask).any(axis=(0, 1))
        )
        if int(usable_features.sum()) < 2:
            raise RuntimeError(
                f"{network} has fewer than two recurrent features represented "
                "in both nested training partitions"
            )
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
        model = BRITSImputer(
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
        network_placements = placements.loc[
            placements["network_id"].astype(str).eq(network)
        ]
        scored = score_existing_placements(
            model,
            panel,
            network_placements,
            max_placements_per_cell=args.max_placements_per_cell,
        )
        scored["provider"] = str(item.provider)
        predictions.append(scored)
        panel_hashes[str(panel_path.relative_to(ROOT))] = sha256(panel_path)
        training_rows.append(
            {
                "network_id": network,
                "provider": str(item.provider),
                "n_features": int(panel.shape[1]),
                "outer_training_years": "|".join(map(str, outer_train_years)),
                "recurrently_usable_outer_training_years": "|".join(
                    map(str, usable_outer_years)
                ),
                "fit_years": "|".join(map(str, fit_years)),
                "validation_years": "|".join(map(str, validation_years)),
                "outer_evaluation_years": "|".join(
                    map(str, outer_evaluation_years)
                ),
                "n_training_windows": len(train_values),
                "n_validation_windows": len(validation_values),
                "epochs_ran": int(model.history_["epochs_ran"]),
                "best_epoch": int(model.history_["best_epoch"]),
                "best_validation_loss": float(
                    model.history_["best_validation_loss"]
                ),
            }
        )
        print(f"exploratory BRITS sensitivity: {network}", flush=True)

    prediction = pd.concat(predictions, ignore_index=True)
    if EMPIRICAL.is_file():
        empirical = pd.read_csv(
            EMPIRICAL, dtype={"network_id": str, "station_id": str}
        )
        empirical["gap_start"] = pd.to_datetime(empirical["gap_start"])
        prediction = prediction.merge(
            empirical[
                [
                    "network_id",
                    "station_id",
                    "gap_length",
                    "placement",
                    "gap_start",
                    "empirical_transfer_prediction",
                    "empirical_transfer_source",
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
        )
    station_gap = prediction.groupby(
        ["network_id", "provider", "station_id", "gap_length"], as_index=False
    ).agg(
        brits_mae_deg_c=("brits_mae_deg_c", "mean"),
        xgboost_mae_deg_c=("xgboost_mae_deg_c", "mean"),
        empirical_transfer_prediction=("empirical_transfer_prediction", "first"),
        n_placements=("placement", "size"),
    )
    provider_metrics = pd.DataFrame(
        [
            {
                "provider": provider,
                "n_networks": frame["network_id"].nunique(),
                "n_station_gaps": len(frame),
                "xgboost_vs_brits_spearman": spearman(
                    frame, "xgboost_mae_deg_c", "brits_mae_deg_c"
                ),
                "empirical_vs_brits_spearman": spearman(
                    frame, "empirical_transfer_prediction", "brits_mae_deg_c"
                ),
            }
            for provider, frame in station_gap.groupby("provider", sort=True)
        ]
    )
    training = pd.DataFrame(training_rows)
    prediction_path = args.output / "recurrent_sensitivity_predictions.csv"
    training_path = args.output / "recurrent_sensitivity_training.csv"
    metrics_path = args.output / "recurrent_sensitivity_provider_metrics.csv"
    manifest_path = args.output / "recurrent_sensitivity_manifest.json"
    prediction.to_csv(prediction_path, index=False)
    training.to_csv(training_path, index=False)
    provider_metrics.to_csv(metrics_path, index=False)
    network_summary = station_gap.groupby("network_id", as_index=False).mean(
        numeric_only=True
    )
    manifest = {
        "analysis_id": "v11_first_confirmation_brits_exploratory_v1",
        "status": "completed_exploratory_sensitivity",
        "evidence_role": "post_confirmation_exploratory_not_confirmatory",
        "model": "repository_local_BRITSImputer_GRU_style",
        "not_a_claim_of": [
            "full_recurrent_roster_coverage",
            "state_of_the_art_LSTM_benchmark",
            "second_confirmation",
            "provider_specific_effects",
        ],
        "selection_rule": (
            "within each first-confirmation provider, choose the scored qualified "
            "network with fewest eligible stations then lexical network_id"
        ),
        "n_selected_networks": int(selected["network_id"].nunique()),
        "n_available_first_confirmation_networks": int(
            placements["network_id"].nunique()
        ),
        "n_providers": int(selected["provider"].nunique()),
        "providers": sorted(selected["provider"].astype(str).unique()),
        "gap_lengths": [7, 30, 90],
        "max_placements_per_station_gap": args.max_placements_per_cell,
        "training": {
            "outer_evaluation_labels_used_for_fit_or_validation": False,
            "artificial_blocks_only": True,
            "hidden_size": args.hidden_size,
            "epochs": args.epochs,
            "max_training_windows_per_network": args.max_windows,
            "seed": args.seed,
        },
        "results": {
            "n_scored_placements": len(prediction),
            "n_station_gaps": len(station_gap),
            "xgboost_vs_brits_station_gap_spearman": spearman(
                station_gap, "xgboost_mae_deg_c", "brits_mae_deg_c"
            ),
            "empirical_vs_brits_station_gap_spearman": spearman(
                station_gap,
                "empirical_transfer_prediction",
                "brits_mae_deg_c",
            ),
            "empirical_vs_brits_network_spearman": spearman(
                network_summary,
                "empirical_transfer_prediction",
                "brits_mae_deg_c",
            ),
        },
        "input_sha256": {
            str(qualified_path.relative_to(ROOT)): sha256(qualified_path),
            str(placements_path.relative_to(ROOT)): sha256(placements_path),
            **panel_hashes,
        },
        "output_sha256": {
            prediction_path.name: sha256(prediction_path),
            training_path.name: sha256(training_path),
            metrics_path.name: sha256(metrics_path),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest["results"], indent=2))


if __name__ == "__main__":
    main()
