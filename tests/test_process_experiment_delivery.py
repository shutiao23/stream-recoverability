"""Fail-closed checks for the new delivery path; no archive replay is run here."""
from importlib.util import module_from_spec,spec_from_file_location
from pathlib import Path
import shutil

import pandas as pd
import pytest

ROOT=Path(__file__).resolve().parents[1]


def load(filename,name):
    spec=spec_from_file_location(name,ROOT/'scripts'/filename);m=module_from_spec(spec);spec.loader.exec_module(m);return m


M=load('978_process_experiment_delivery.py','delivery_978_test')


def source_receipt():
    r=dict(status='passed',mode='frozen_input_replay',source_cases=2370,target_cases=27,target_layer_cases=729,
           reestimated_offset_cells=288,source_case_budget_quantiles=21330,source_role_offsets_reestimated=True,
           source_only_calibration=True,source_eligibility_and_fallback_unchanged=True,source_target_random_stream_intersections=0,limits=['Frozen inputs only'])
    for field in ['daily_model_fit','D2_model_fit','original_daily_panels_opened','original_case_caches_opened','original_model_joblibs_opened','audited_results_overwritten']:r[field]=False
    for field in ['source_budget_quantile_max_abs_error','new_source_offset_max_abs_error','target_quantile_metric_max_abs_error','fixed_reference_metric_max_abs_error',
                  'native_source_draw_max_abs_error','native_source_quantile_max_abs_error','native_target_draw_max_abs_error','native_target_quantile_max_abs_error']:r[field]=0.
    return r


def test_new_source_scope_cannot_accept_old_unexecuted_calibration_flags():
    r=source_receipt();assert M.check_source_receipt(r)['source_role_offsets_reestimated'] is True
    r['source_role_offsets_reestimated']=False
    with pytest.raises(M.DeliveryFailure,match='calibration scope'):M.check_source_receipt(r)
    r=source_receipt();r['original_case_caches_opened']=True
    with pytest.raises(M.DeliveryFailure,match='fit/opened/wrote'):M.check_source_receipt(r)


def test_time_replay_requires_exact_current_denominators_and_scope():
    r=dict(status='passed',mode='frozen_saved_annual_input_replay',frozen_annual_rows=10860,raw_archives=820,
           original_common=807,actual_mask_common=805,choice_only=468,all_feasible_subsets=5758,
           exact_conditional_random_expectations=807,weighted_summary_checks=63,maximum_abs_numeric_error=2.5e-11,
           original_case_caches_opened=False,original_daily_panels_opened=False,models_fit=False,audited_results_overwritten=False,
           primary_equal_archive_summaries=[],exact_random_estimand='Within-archive expected MSE',
           not_replayed=['200 seed realizations','group intervals','daily gaps'],daily_gap_scope='Local 974 audit only')
    assert M.check_time_receipt(r)['choice_only']==468
    r['all_feasible_subsets']=5757
    with pytest.raises(M.DeliveryFailure,match='denominators'):M.check_time_receipt(r)


def test_catalog_hash_and_key_checks_happen_without_replay_writes(tmp_path):
    cat=load('972_experiment_data_catalog.py','catalog_for_delivery_test')
    base=tmp_path/M.EXPERIMENT;base.mkdir(parents=True)
    (tmp_path/'scripts').mkdir();shutil.copyfile(ROOT/'scripts/972_experiment_data_catalog.py',tmp_path/'scripts/972_experiment_data_catalog.py')
    file=base/'time_archive_accounting.csv'
    frame=pd.DataFrame({'station_key':['a','b'],'replicate':[0,0],'independence_group':['g1','g2']})
    frame.to_csv(file,index=False);cat.generate(base)
    report,_=M.check_catalog(tmp_path,M.zip_helpers());assert report['tabular_files_checked']==1
    file.write_text(file.read_text()+'a,1,g1\n')
    with pytest.raises(M.DeliveryFailure,match='content hash'):M.check_catalog(tmp_path,M.zip_helpers())
    assert not (base/'source_calibration/replay_receipt.json').exists()
    pd.concat([frame,frame.iloc[:1]],ignore_index=True).to_csv(file,index=False);cat.generate(base)
    with pytest.raises(M.DeliveryFailure,match='key violation'):M.check_catalog(tmp_path,M.zip_helpers())
