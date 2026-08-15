import json
from pathlib import Path

import numpy as np
import pandas as pd

from stream_recoverability.plotting import LOSO_TITLE, generate_publication_outputs


def _write_synthetic_inputs(root: Path) -> dict[str, Path]:
    results = root / "results"
    experiments = results / "experiments"
    analysis = results / "analysis"
    eda = results / "eda"
    metadata = root / "metadata"
    for directory in (experiments, analysis, eda, metadata):
        directory.mkdir(parents=True, exist_ok=True)

    stations = pd.DataFrame(
        {
            "station_id": ["B1", "S2", "P3"],
            "station_name": ["Upstream", "Middle", "Downstream"],
            "river_name": "Test River",
            "network_order": [1, 2, 3],
            "latitude": [30.0, 28.0, 26.0],
            "longitude": [99.0, 100.0, 102.0],
            "met_latitude": [30.1, 28.1, 26.1],
            "met_longitude": [99.1, 100.1, 102.1],
            "data_period": "2006-01-01/2020-12-31",
            "hydrology_source": "synthetic test fixture",
        }
    )
    station_path = metadata / "station_metadata.csv"
    stations.to_csv(station_path, index=False)
    summary = pd.DataFrame(
        [
            {"station_id": station, "variable": variable, "coverage": 0.98}
            for station in stations["station_id"]
            for variable in ("T", "F", "L", "Ta")
        ]
    )
    summary.to_csv(eda / "variable_summary.csv", index=False)

    event_rows = []
    models = ("climatology", "linear", "kalman", "proposed")
    for station_index, station in enumerate(stations["station_id"]):
        for experiment, mask_type, gap, rate in (
            ("M1", "point", np.nan, 0.3),
            ("M2", "block", 10, np.nan),
            ("M2", "block", 30, np.nan),
            ("M3", "multiblock", 30, np.nan),
            ("M4", "station_outage", 30, np.nan),
        ):
            for replicate in range(3):
                scenario = f"{experiment}-{station}-{mask_type}-{gap}-{replicate}"
                for model_index, model in enumerate(models):
                    mae = 0.35 + 0.10 * model_index + 0.01 * station_index + 0.01 * replicate
                    event_rows.append(
                        {
                            "scenario_id": scenario,
                            "experiment": experiment,
                            "mask_type": mask_type,
                            "station_id": station,
                            "model": model,
                            "target": "T",
                            "mask_seed": 101 + replicate,
                            "gap_length": gap,
                            "missing_rate": rate,
                            "pattern": "T" if experiment != "M4" else "T+F+L",
                            "MAE": mae,
                            "RMSE": mae * 1.2,
                            "skill": 1.0 - mae,
                            "validation_scope": "internal_test",
                            "is_external_validation": False,
                        }
                    )
        event_rows.append(
            {
                "scenario_id": f"M10-LOSO-{station}-T-R0101",
                "experiment": "M10",
                "mask_type": "loso",
                "station_id": station,
                "model": "pooled_loso",
                "target": "T",
                "mask_seed": 101,
                "gap_length": np.nan,
                "missing_rate": np.nan,
                "pattern": "T",
                "MAE": 0.8 + 0.1 * station_index,
                "RMSE": 1.0 + 0.1 * station_index,
                "skill": 0.3 - 0.05 * station_index,
                "validation_scope": "exploratory_internal_loso_not_external_validation",
                "is_external_validation": False,
            }
        )
    events = pd.DataFrame(event_rows)
    event_path = experiments / "event_metrics.parquet"
    events.to_parquet(event_path, index=False)

    daily_rows = []
    event_specs = (
        ("HIGH_TEMPERATURE", "high_temperature", "T", 18.0),
        ("FLOOD", "flood", "F", 3000.0),
        ("LOW_FLOW", "low_flow", "F", 300.0),
    )
    dates = pd.date_range("2020-07-01", periods=6, freq="D")
    for token, event_type, target, base in event_specs:
        scenario = f"M7-EVENT-B1-{token}-R0101"
        truth = base + np.linspace(-1.0, 1.0, len(dates))
        model_offsets = (
            (("linear", 0.4), ("kalman", 0.2), ("proposed", 0.1))
            if target == "T"
            else (
                ("linear", 0.4),
                ("kalman", 0.2),
                ("pchip", 0.3),
                ("climatology", 0.05),
            )
        )
        for model, offset in model_offsets:
            for date, value in zip(dates, truth, strict=True):
                daily_rows.append(
                    {
                        "date": date,
                        "scenario_id": scenario,
                        "experiment": "M7",
                        "mask_type": "event",
                        "event_type": event_type,
                        "station_id": "B1",
                        "target": target,
                        "model": model,
                        "training_seed": 11 if model == "proposed" else np.nan,
                        "mask_seed": 101,
                        "y_true": value,
                        "y_pred": value + offset,
                        "q05": value - 0.5 if model == "proposed" else np.nan,
                        "q95": value + 0.5 if model == "proposed" else np.nan,
                        "quality_approved": True,
                        "artificial_mask": True,
                    }
                )
    daily = pd.DataFrame(daily_rows)
    daily_path = experiments / "daily_predictions.parquet"
    daily.to_parquet(daily_path, index=False)

    curve_rows = []
    frontier_rows = []
    for station in stations["station_id"]:
        for model in ("linear", "proposed"):
            for gap, skill in ((10, 0.7), (30, 0.35), (90, -0.15)):
                curve_rows.append(
                    {
                        "station_id": station,
                        "target": "T",
                        "model": model,
                        "pattern": "T",
                        "gap_length": gap,
                        "mean_skill": skill + (0.05 if model == "proposed" else 0.0),
                        "ci_lower": skill - 0.1,
                        "ci_upper": skill + 0.1,
                    }
                )
            frontier_rows.append(
                {
                    "station_id": station,
                    "target": "T",
                    "model": model,
                    "pattern": "T",
                    "statistical_frontier_days": 65.0,
                    "frontier_ci_lower": 55.0,
                    "frontier_ci_upper": 75.0,
                    "breakpoint_days": 30.0,
                }
            )
    pd.DataFrame(curve_rows).to_csv(analysis / "skill_curves.csv", index=False)
    pd.DataFrame(frontier_rows).to_csv(analysis / "recoverability_frontiers.csv", index=False)

    shapley_rows = []
    for station in stations["station_id"]:
        for gap in (10, 30, 90):
            for source_index, source in enumerate("ABCD", start=1):
                shapley_rows.append(
                    {
                        "station_id": station,
                        "target": "T",
                        "model": "proposed",
                        "gap_length": gap,
                        "source": source,
                        "shapley": 0.02 * source_index * np.log1p(gap),
                        "total_gain": 1.0,
                        "reason": np.nan,
                    }
                )
    pd.DataFrame(shapley_rows).to_csv(analysis / "information_shapley.csv", index=False)

    resilience = pd.DataFrame(
        [
            {
                "model": "proposed",
                "target": "T",
                "gap_length": 30,
                "failure_fraction": fraction,
                "relative_skill": value,
            }
            for fraction, value in ((0.0, 1.0), (1 / 3, 0.75), (2 / 3, 0.4), (1.0, 0.0))
        ]
    )
    resilience.to_csv(analysis / "network_resilience_curve.csv", index=False)
    pd.DataFrame(
        {
            "model": "proposed",
            "target": "T",
            "station_id": stations["station_id"],
            "impact": [0.15, 0.30, 0.20],
        }
    ).to_csv(analysis / "node_importance.csv", index=False)

    return {
        "daily": daily_path,
        "events": event_path,
        "analysis": analysis,
        "station_metadata": station_path,
        "eda": eda,
    }


def _generate(root: Path, inputs: dict[str, Path]) -> dict:
    return generate_publication_outputs(
        daily_predictions_path=inputs["daily"],
        event_metrics_path=inputs["events"],
        analysis_dir=inputs["analysis"],
        station_metadata_path=inputs["station_metadata"],
        eda_dir=inputs["eda"],
        study_area_points_path=root / "missing-study-points.csv",
        availability_image_path=root / "missing-availability.png",
        online_dir=root / "missing-online",
        figure_dir=root / "figures/main",
        table_dir=root / "paper/tables",
        manifest_path=root / "results/final_results_manifest.json",
    )


def test_missing_inputs_are_explicitly_skipped_without_placeholder_results(tmp_path):
    manifest = generate_publication_outputs(
        daily_predictions_path=tmp_path / "missing-daily.parquet",
        event_metrics_path=tmp_path / "missing-events.parquet",
        analysis_dir=tmp_path / "missing-analysis",
        station_metadata_path=tmp_path / "missing-stations.csv",
        eda_dir=tmp_path / "missing-eda",
        study_area_points_path=tmp_path / "missing-points.csv",
        availability_image_path=tmp_path / "missing-availability.png",
        online_dir=tmp_path / "missing-online",
        figure_dir=tmp_path / "figures/main",
        table_dir=tmp_path / "paper/tables",
        manifest_path=tmp_path / "results/final_results_manifest.json",
    )
    assert manifest["figures"]["figure_02"]["status"] == "generated"
    assert manifest["figures"]["figure_03"]["status"] == "skipped"
    assert "missing" in manifest["figures"]["figure_03"]["reason"]
    assert not (tmp_path / "figures/main/figure_03.png").exists()
    assert manifest["tables"]["table_02"]["status"] == "skipped"
    assert (tmp_path / "figures/main/figure_manifest.json").exists()
    assert (tmp_path / "paper/tables/table_manifest.json").exists()
    serialized = json.dumps(manifest).lower()
    assert "sha256" not in serialized


def test_all_core_figures_and_tables_are_generated_from_synthetic_results(tmp_path):
    inputs = _write_synthetic_inputs(tmp_path)
    daily = pd.read_parquet(inputs["daily"])
    assert not (
        daily["target"].eq("F") & daily["model"].eq("proposed")
    ).any()
    manifest = _generate(tmp_path, inputs)
    assert {value["status"] for value in manifest["figures"].values()} == {"generated"}
    assert {value["status"] for value in manifest["tables"].values()} == {"generated"}
    for index in range(1, 9):
        path = tmp_path / f"figures/main/figure_{index:02d}.png"
        assert path.exists() and path.stat().st_size > 1_000
    for index in range(1, 6):
        table = pd.read_csv(tmp_path / f"paper/tables/table_{index:02d}.csv")
        assert not table.empty
    frozen = manifest["frozen_result_summary"]
    assert frozen["daily_predictions"]["rows"] > 0
    assert frozen["event_metrics"]["scenario_count"] > 0
    assert "proposed" in frozen["event_metrics"]["models"]

    event_details = {
        item["event"]: item
        for item in manifest["figures"]["figure_07"]["details"]["selected_cases"]
    }
    assert event_details["High temperature"]["comparison_models"] == [
        "linear",
        "kalman",
        "proposed",
    ]
    assert event_details["High temperature"]["uncertainty_model"] == "proposed"
    for event in ("Flood peak", "Long low flow"):
        assert event_details[event]["strongest_distinct_baseline"] == "kalman"
        assert event_details[event]["comparison_models"] == ["linear", "kalman"]
        assert event_details[event]["uncertainty_model"] is None


def test_loso_figure_is_labeled_internal_and_never_as_external_validation(tmp_path):
    inputs = _write_synthetic_inputs(tmp_path)
    manifest = _generate(tmp_path, inputs)
    status = manifest["figures"]["figure_08"]
    assert status["title"] == LOSO_TITLE
    assert status["details"]["validation_scope"] == "exploratory_internal_loso_not_external_validation"
    assert status["details"]["is_external_validation"] is False
    assert "not external validation" in status["title"].lower()
