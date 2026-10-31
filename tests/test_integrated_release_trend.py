"""Check the release-to-trend data boundary on a small synthetic archive."""
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd


def test_hidden_reference_changes_scores_but_not_release_states(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    spec = importlib.util.spec_from_file_location("integrated_trend_test", root / "scripts/532_integrated_release_trend.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    archive = tmp_path / "archive"
    folder = archive / "crossed/offline/replicate_00/synthetic"
    folder.mkdir(parents=True)
    monkeypatch.setattr(module, "ARCHIVE", archive)

    class VisibleOnly:
        @staticmethod
        def visible_quality(job, c, exposed):
            return pd.Series(np.ones(len(c)), index=c.index)

    monkeypatch.setattr(module.T, "load_script", lambda *args: VisibleOnly)
    design = {"station_key":"synthetic", "region":"region", "independence_group":"group",
              "masks":{"2001":"100:30", "2004":"120:30", "2005":"130:30"}}
    (folder / "design.json").write_text(json.dumps(design))
    cases = pd.DataFrame({"year":[2001, 2004, 2005], "D2":[10.5, 10.5, np.nan],
                          "risk_score":[0.01, 0.9, np.nan], "n_complete_years":[5, 5, 5],
                          "visible_edge_anomaly":[0.0, 0.0, 0.0],
                          "observed_lower_bound__observed_days":[10.0, 9.0, np.nan]})
    path = folder / "annual_predictions.parquet"
    cases.to_parquet(path, index=False)
    years = np.arange(2000, 2006)
    truth = {("crossed", "synthetic"): pd.Series([8, 10, 9, 10, 11, 12], index=years)}
    limits = {"leave_one_year_out":{"region":{"visible_edge_anomaly":2.0}}}
    first_rows, first = module.one(path, truth, {"synthetic":{}}, limits)
    changed = truth[("crossed", "synthetic")].copy()
    changed.loc[[2001, 2004, 2005]] += 100
    second_rows, second = module.one(path, {("crossed", "synthetic"):changed}, {"synthetic":{}}, limits)
    fields = ["year", "output_state", "released_estimate", "observed_lower_bound", "quality_flag"]
    pd.testing.assert_frame_equal(first[fields], second[fields])
    assert first.output_state.value_counts().to_dict() == {
        "complete_observed":3, "estimate":1, "observed_bound":1, "unknown":1}
    assert all(r["n_estimates"] + r["n_bounds"] + r["n_unknown"] == r["n_masked"] == 3 for r in first_rows)
    assert first_rows[0]["truth_slope"] != second_rows[0]["truth_slope"]
