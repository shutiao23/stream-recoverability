import subprocess
import sys
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

from stream_recoverability.masks import save_mask_library


def test_baseline_script_reads_prepared_wide_and_fixed_library(tmp_path):
    train_dates = pd.date_range("2019-01-01", periods=30, freq="D")
    test_dates = pd.date_range("2020-01-01", periods=30, freq="D")
    dates = train_dates.append(test_dates)
    values = np.sin(np.arange(60) * 2 * np.pi / 30.0) + 10.0
    wide = pd.DataFrame(
        {
            "date": dates,
            "split": ["train"] * 30 + ["test"] * 30,
            "B1_T": values,
        }
    )
    quality = pd.DataFrame(
        {
            "date": dates,
            "station_id": "B1",
            "variable": "T",
            "quality_approved": True,
        }
    )
    wide_path = tmp_path / "wide.csv"
    quality_path = tmp_path / "long.csv"
    wide.to_csv(wide_path, index=False)
    quality.to_csv(quality_path, index=False)

    artificial = np.zeros((60, 1, 1), dtype=bool)
    artificial[40:43, 0, 0] = True
    mask_dir = tmp_path / "masks"
    save_mask_library(
        [
            (
                artificial,
                {
                    "scenario_id": "BLK1-B1-T-D003",
                    "split": "test",
                    "seed": 3,
                    "mask_type": "block",
                    "station_ids": ["B1"],
                    "variables": ["T"],
                    "missing_rate": None,
                    "gap_lengths": [3],
                },
            )
        ],
        mask_dir,
        dates=dates,
        station_ids=["B1"],
        variable_names=["T"],
    )

    daily_path = tmp_path / "daily.csv"
    event_path = tmp_path / "events.csv"
    script = Path(__file__).parents[1] / "scripts/04_run_baselines.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--data",
            str(wide_path),
            "--quality-data",
            str(quality_path),
            "--masks",
            str(mask_dir),
            "--models",
            "climatology",
            "linear",
            "pchip",
            "--daily-output",
            str(daily_path),
            "--event-output",
            str(event_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    daily = pd.read_csv(daily_path)
    events = pd.read_csv(event_path)
    assert len(daily) == 9
    assert set(daily["model"]) == {"climatology", "linear", "pchip"}
    assert len(events) == 3
    assert events["n_evaluated"].eq(3).all()


def test_runner_connects_multisource_and_flow_specific_models(tmp_path, monkeypatch):
    dates = pd.date_range("2019-01-01", periods=120, freq="D")
    phase = np.arange(120, dtype=float)
    b1_flow = 100.0 + 15.0 * np.sin(phase / 8.0)
    s2_flow = np.roll(b1_flow, -1) * 1.05
    wide = pd.DataFrame(
        {
            "date": dates,
            "split": ["train"] * 80 + ["test"] * 40,
            "B1_T": 10.0 + np.sin(phase / 12.0),
            "B1_F": b1_flow,
            "B1_L": 2.0 + b1_flow / 100.0,
            "B1_Ta": 12.0 + 3.0 * np.sin(phase / 12.0),
            "S2_T": 10.5 + np.sin((phase + 1.0) / 12.0),
            "S2_F": s2_flow,
            "S2_L": 2.5 + s2_flow / 100.0,
            "S2_Ta": 12.5 + 3.0 * np.sin((phase + 1.0) / 12.0),
        }
    )
    wide_path = tmp_path / "wide.csv"
    wide.to_csv(wide_path, index=False)
    quality_rows = []
    for station in ("B1", "S2"):
        for variable in ("T", "F", "L"):
            quality_rows.append(
                pd.DataFrame(
                    {
                        "date": dates,
                        "station_id": station,
                        "variable": variable,
                        "quality_approved": True,
                    }
                )
            )
    quality_path = tmp_path / "long.csv"
    pd.concat(quality_rows, ignore_index=True).to_csv(quality_path, index=False)

    artificial = np.zeros((120, 2, 3), dtype=bool)
    artificial[90:93, 0, 0] = True
    artificial[100:103, 0, 1] = True
    mask_dir = tmp_path / "masks"
    save_mask_library(
        [
            (
                artificial,
                {
                    "scenario_id": "MULTI-B1-TF",
                    "split": "test",
                    "seed": 5,
                    "mask_type": "block",
                    "station_ids": ["B1"],
                    "variables": ["T", "F"],
                    "missing_rate": None,
                    "gap_lengths": [3],
                },
            )
        ],
        mask_dir,
        dates=dates,
        station_ids=["B1", "S2"],
        variable_names=["T", "F", "L"],
    )

    script = Path(__file__).parents[1] / "scripts/04_run_baselines.py"
    spec = importlib.util.spec_from_file_location("run_baselines_script", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module._event_gap_length({"gap_lengths": []}) is None
    daily, events = module.run_baselines(
        wide_path,
        mask_dir,
        quality_path=quality_path,
        models=[
            "air_only",
            "air_hydro",
            "donor_regression",
            "random_forest",
            "rating_curve",
            "independent_flow",
        ],
    )
    assert set(events.loc[events["target"] == "T", "model"]) == {
        "air_only",
        "air_hydro",
        "donor_regression",
        "random_forest",
    }
    assert set(events.loc[events["target"] == "F", "model"]) == {
        "donor_regression",
        "random_forest",
        "rating_curve",
        "independent_flow",
    }
    assert events["model_status"].eq("ok").all()
    independent, reason = module._build_trainable_model(
        "independent_flow", wide, ["B1", "S2"], "B1", "F"
    )
    assert reason is None
    assert "B1_L" not in independent.feature_cols
    assert len(daily) == 24

    seen_predictions = []

    class MaskCheckingModel:
        def fit(self, frame, train_mask):
            return self

        def predict(self, frame):
            assert frame.loc[90:92, "B1_T"].isna().all()
            assert frame.loc[100:102, "B1_F"].isna().all()
            seen_predictions.append(True)
            return pd.Series(0.0, index=frame.index)

    with monkeypatch.context() as scoped:
        scoped.setattr(
            module,
            "_build_trainable_model",
            lambda *args, **kwargs: (MaskCheckingModel(), None),
        )
        module.run_baselines(
            wide_path,
            mask_dir,
            quality_path=quality_path,
            models=["random_forest"],
        )
    assert len(seen_predictions) == 2

    with monkeypatch.context() as scoped:
        scoped.setattr(
            module.XGBoostBaseline, "is_available", staticmethod(lambda: False)
        )
        skipped_daily, skipped_events = module.run_baselines(
            wide_path,
            mask_dir,
            quality_path=quality_path,
            models=["xgboost"],
        )
    assert skipped_daily.empty
    assert len(skipped_events) == 2
    assert skipped_events["model_status"].eq("skipped").all()
    assert skipped_events["skip_reason"].str.contains("not installed").all()
