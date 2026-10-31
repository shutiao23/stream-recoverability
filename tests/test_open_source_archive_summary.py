"""A paired source sensitivity cannot report an incomplete or changed cohort."""
import importlib.util
import json
import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace
import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('open_source_summary', SCRIPTS / '661_open_source_archive_summary.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def setup_case(tmp_path, monkeypatch):
    rev = tmp_path / 'results'; out = rev / 'open_source_sensitivity'; base = rev / 'whole_archive'; private = tmp_path / 'private'
    for p in [out, base, private]: p.mkdir(parents=True)
    (out / 'plan.json').write_text(json.dumps({'target_mode_region_stations': [{'mode': 'offline', 'region': 'region', 'stations': 1}], 'limitations': 'synthetic'}))
    (out / 'candidate_input_integrity.json').write_text('{"status":"passed"}')
    model = private / 'refits/leave_one_year_out/seed_00/region.joblib'; model.parent.mkdir(parents=True); model.write_bytes(b'model')
    cal = private / 'calibrations/offline/region.json'; cal.parent.mkdir(parents=True); cal.write_bytes(b'calibration')
    (private / 'refit_receipts.json').write_text(json.dumps({'offline|region': {}}))
    all_old = []
    for family in ['calendar', 'crossed']:
        for rep in range(20):
            rel = Path(family) / 'offline' / f'replicate_{rep:02d}' / 'station'
            original, target = base / rel, private / 'whole_archive' / rel
            original.mkdir(parents=True); target.mkdir(parents=True)
            old_input, new_input = original / 'annual_predictions.parquet', target / 'annual_predictions.parquet'
            old_input.write_bytes(b'original'); new_input.write_bytes(b'candidate')
            design = {'region': 'region', 'station_key': 'test|1', 'masks': {'2015': '1:3'}, 'hidden_values_present_in_visible_archive': 0}
            (original / 'design.json').write_text(json.dumps(design)); (target / 'design.json').write_text(json.dumps(design))
            old_rows, new_rows = [], []
            for est, error, other in [('plug_in', .4, .4), ('D2', .1, .2), ('stochastic_calibrated', .3, .2)]:
                for retention in ['all', 'warm90']:
                    row = {'family': family, 'mode': 'offline', 'region': 'region', 'station_key': 'test|1', 'replicate': rep,
                           'estimator': est, 'retention': retention, 'dependence': 'point', 'independence_group': 'g1',
                           'available': True, 'n_retained': 5, 'truth_slope': 1., 'slope': 1.+error,
                           'error': error, 'squared_error': error**2, 'missing_coverage95': 0., 'width95': 0., 'interval_score95': 0.}
                    old_rows.append(row); new_rows.append(row | {'slope': 1.+other, 'error': other, 'squared_error': other**2})
            pd.DataFrame(old_rows).to_csv(original / 'trends.csv', index=False)
            pd.DataFrame(new_rows).to_csv(target / 'trends.csv', index=False)
            all_old.extend(old_rows)
            receipt = {'same_masks': True, 'hidden_target_values_present': 0}
            (target / 'open_source_receipt.json').write_text(json.dumps(receipt))
    pd.DataFrame(all_old).to_csv(base / 'trends.csv', index=False)
    for name, value in {'ROOT': tmp_path, 'REV': rev, 'OUT': out, 'BASE': base, 'PRIVATE': private}.items(): monkeypatch.setattr(m, name, value)
    monkeypatch.setattr(m.T, 'load_script', lambda *args: SimpleNamespace(
        sha=lambda path: hashlib.sha256(path.read_bytes()).hexdigest(), verify_plugin=lambda *args: None))
    return out, private

def test_complete_paired_summary_uses_four_way_common_cases(tmp_path, monkeypatch):
    out, _ = setup_case(tmp_path, monkeypatch)
    m.main()
    result = pd.read_csv(out / 'archive_four_way_comparison.csv')
    assert result.common_four_way_cases.tolist() == [20, 20]
    assert result.D2_original_rmse.tolist() == pytest.approx([.1, .1])
    assert result.D2_candidate_rmse.tolist() == pytest.approx([.2, .2])
    assert result.stochastic_calibrated_original_rmse.tolist() == pytest.approx([.3, .3])
    assert result.common_groups.tolist() == [1, 1]
    assert result.gap_change_bootstrap_low.tolist() == pytest.approx([.08, .08])
    assert result.gap_change_bootstrap_high.tolist() == pytest.approx([.08, .08])
    factorial = pd.read_csv(out / 'archive_factorial_paired.csv')
    assert len(factorial) == 4
    assert factorial.n_common.tolist() == [20, 20, 20, 20]
    assert factorial.original_retention_fraction.tolist() == pytest.approx([0., 0., 0., 0.])

def test_missing_archive_setting_blocks_pooled_summary(tmp_path, monkeypatch):
    out, private = setup_case(tmp_path, monkeypatch)
    (private / 'whole_archive/calendar/offline/replicate_00/station/open_source_receipt.json').unlink()
    with pytest.raises(ValueError, match='planned settings'):
        m.main()
    assert not (out / 'archive_four_way_comparison.csv').exists()
