"""Catalogs must report actual content and distinguish scientific units."""
from importlib.util import module_from_spec,spec_from_file_location
from pathlib import Path

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
SPEC=spec_from_file_location('catalog_972',ROOT/'scripts/972_experiment_data_catalog.py')
M=module_from_spec(SPEC);SPEC.loader.exec_module(M)


def test_counts_are_not_mislabelled_as_coverage_or_correlation():
    c=Path('source_calibration/full/target_three_layer_summary.csv')
    assert M.unit_and_definition(c,'n_covered')[0]=='count_or_index'
    assert M.unit_and_definition(c,'coverage90')[0]=='dimensionless'
    w=Path('region_water/water_air_summary.csv')
    assert M.unit_and_definition(w,'correlation_valid_draws')[0]=='count_or_index'
    assert M.unit_and_definition(w,'correlation')[0]=='dimensionless'


def test_temperature_paths_and_bootstrap_draw_counts_have_distinct_units():
    assert M.unit_and_definition(Path('source_calibration/full/source_nested_draws.parquet'),'draws')[0]=='degC'
    assert M.unit_and_definition(Path('region_water/water_air_direct_observation_bootstrap_checks.csv'),'draws')[0]=='count_or_index'
    assert M.unit_and_definition(Path('time_sensitivity_summary.csv'),'estimate_mse')[0]=='(degC/decade)^2'
    assert M.unit_and_definition(Path('time_sensitivity_summary.csv'),'estimate_rmse')[0]=='degC/decade'
    assert M.unit_and_definition(Path('source_calibration/source_union_cases.parquet'),'unexplained_feature')[0]=='documented_feature'


def test_frozen_replay_keys_array_units_and_metadata_roles_are_explicit():
    source=Path('source_calibration/frozen_source_reference.parquet')
    target=Path('source_calibration/frozen_target_manifest.csv')
    assert M.resolve_key(source,pd.DataFrame())[0]==['case_id']
    assert M.resolve_key(target,pd.DataFrame())[0]==['station_key','year']
    assert M.unit_and_definition(source,'stochastic_h30_draws')[0]=='degC'
    for file in ['source_calibration/frozen_target_inputs/site_2010.npz','source_calibration/full/source_frozen_inputs/site_2005.npz']:
        for field in ['observed','mean','residual']:
            assert M.unit_and_definition(Path(file),field)[0]=='degC'
        assert M.unit_and_definition(Path(file),'residual_index')[0]=='index'
    for file in ['source_calibration/frozen_replay_dependency_manifest.json','source_calibration/replay_receipt.json','source_calibration/future_976_probe.csv']:
        assert 'not_new_observation' in M.group_description(Path(file))[1]


def test_inventory_recomputes_rows_hashes_and_key_violations(tmp_path):
    file=tmp_path/'time_archive_accounting.csv'
    frame=pd.DataFrame({'station_key':['a','b'],'replicate':[0,0],'independence_group':['g1','g2']})
    frame.to_csv(file,index=False)
    report=M.generate(tmp_path)
    assert not report['declared_key_violations']
    first=pd.read_csv(tmp_path/'dataset_catalog.csv').iloc[0]
    assert first.row_count==2 and first.unique_key_rows==2
    pd.concat([frame,frame.iloc[:1]],ignore_index=True).to_csv(file,index=False)
    report=M.generate(tmp_path)
    second=pd.read_csv(tmp_path/'dataset_catalog.csv').iloc[0]
    assert second.row_count==3 and second.duplicate_key_rows==2
    assert second.sha256!=first.sha256
    assert report['declared_key_violations']==['time_archive_accounting.csv']
    # The generated files are excluded from their own inventory, so reruns do
    # not add recursively growing self-hashes or reinterpret inventory as review.
    assert report['catalogued_artifacts']==1
    assert report['status']=='inventory_generated_not_scientific_validation'
