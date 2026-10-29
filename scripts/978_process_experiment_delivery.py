#!/usr/bin/env python3
"""Check a packaged experiment version before replaying its frozen inputs.

Uses a temporary extraction and fresh subprocesses with the current installed
Python/TeX tools. This is not a clean-environment or raw-data/model-fit rebuild.
Scientific catalog content is checked before any replay writes a fresh receipt.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
EXPERIMENT=Path('results/wrr_process_experiments_20261029')
SOURCE=EXPERIMENT/'source_calibration'
TIME=EXPERIMENT/'time_frozen_replay'
OBSERVATIONS=Path('results/wrr_process_revision_20261029/replay_integrity')


class DeliveryFailure(RuntimeError):
    pass


def require(condition,message):
    if not condition:raise DeliveryFailure(message)


def load_module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def zip_helpers():
    # Only these ZIP/environment functions are called. In particular this must
    # never invoke 966's historical 962 replay or its old calibration flags.
    return load_module(ROOT/'scripts/966_process_revision_delivery.py','experiment_delivery_zip_helpers')


def safe_file(root,relative,helper):
    path=helper.safe_member_path(str(relative));target=root/str(path)
    require(target.is_file() and not target.is_symlink() and target.resolve().is_relative_to(root.resolve()),
            'Required packaged file is missing or unsafe: '+str(relative))
    return target


def read_json(root,relative,helper):
    return json.loads(safe_file(root,relative,helper).read_text())


def check_catalog(root,helper):
    """Read only: verify catalog bytes, table sizes and actual declared keys."""
    base=root/EXPERIMENT
    report=read_json(root,EXPERIMENT/'dataset_catalog_report.json',helper)
    generator=safe_file(root,'scripts/972_experiment_data_catalog.py',helper)
    require(report.get('generator_sha256')==helper.sha256(generator),'Packaged catalog generator hash changed')
    catalog_module=load_module(generator,'packaged_catalog_exclusion_policy')
    exclusions=set(catalog_module.EXCLUDE)
    require(set(report.get('exclusions',[]))==exclusions,'Catalog exclusion policy differs from its generator')
    for filename in ['dataset_catalog.csv','data_dictionary.csv']:
        expected=report.get('output_sha256',{}).get(filename)
        require(expected and helper.sha256(base/filename)==expected,'Catalog or dictionary content hash differs: '+filename)
    catalog=pd.read_csv(base/'dataset_catalog.csv',dtype=str,keep_default_na=False)
    dictionary=pd.read_csv(base/'data_dictionary.csv',dtype=str,keep_default_na=False)
    require(catalog.dataset_path.is_unique,'Catalog repeats a dataset path')
    require(len(catalog)==int(report['catalogued_artifacts']) and len(dictionary)==int(report['dictionary_fields']),
            'Catalog/dictionary reported lengths differ')
    require(not report.get('declared_key_violations'),'Catalog discloses a declared-key violation')
    hashes={};tables=0;key_tables=0;rows=0
    for row in catalog.itertuples(index=False):
        relative=helper.safe_member_path(row.dataset_path)
        require(relative.name not in exclusions and 'delivery_logs' not in relative.parts,
                'Catalog includes a self/validation/delivery-log exclusion: '+row.dataset_path)
        file=safe_file(root,EXPERIMENT/str(relative),helper)
        require(file.stat().st_size==int(row.bytes) and helper.sha256(file)==row.sha256,
                'Catalog content hash or bytes differ: '+row.dataset_path)
        require(row.format==file.suffix.lstrip('.'),'Catalog file format differs: '+row.dataset_path)
        hashes[str(EXPERIMENT/str(relative))]=row.sha256
        if row.format in {'csv','parquet'}:
            frame=pd.read_csv(file) if row.format=='csv' else pd.read_parquet(file)
            require(len(frame)==int(row.row_count) and len(frame.columns)==int(row.column_count),
                    'Catalog table dimensions differ: '+row.dataset_path)
            keys=json.loads(row.key_columns)
            require(isinstance(keys,list) and len(keys)==len(set(keys)) and set(keys).issubset(frame.columns),
                    'Invalid catalog key fields: '+row.dataset_path)
            if keys:
                duplicates=int(frame.duplicated(keys,keep=False).sum())
                unique=len(frame.drop_duplicates(keys));missing=int(frame[keys].isna().any(axis=1).sum())
                require((duplicates,unique,missing)==(int(row.duplicate_key_rows),int(row.unique_key_rows),int(row.missing_key_rows)),
                        'Catalog key counts differ: '+row.dataset_path)
                if row.key_kind=='declared':require(duplicates==0,'Declared dataset key is duplicated: '+row.dataset_path)
                expected='verified_empty_table' if not len(frame) else ('verified_unique' if not duplicates else 'duplicate_keys')
                require(row.key_status==expected,'Catalog key status differs: '+row.dataset_path)
                key_tables+=1
            elif row.key_kind=='declared':
                raise DeliveryFailure('Declared dataset key is empty: '+row.dataset_path)
            fields=dictionary.loc[dictionary.dataset_path.eq(row.dataset_path),'column'].tolist()
            require(len(fields)==len(frame.columns) and set(fields)==set(frame.columns),
                    'Data dictionary fields differ: '+row.dataset_path)
            tables+=1;rows+=len(frame)
        elif row.format=='npz':
            with np.load(file,allow_pickle=False) as arrays:
                require(len(arrays.files)==int(row.column_count),'Catalog array field count differs: '+row.dataset_path)
                fields=dictionary.loc[dictionary.dataset_path.eq(row.dataset_path),'column'].tolist()
                require(len(fields)==len(arrays.files) and set(fields)==set(arrays.files),
                        'Data dictionary array fields differ: '+row.dataset_path)
    return dict(status='passed',ordering='Before compilation or replay receipt writes',artifacts_hashed=len(catalog),
                tabular_files_checked=tables,table_rows_checked=rows,key_tables_checked=key_tables,
                dictionary_fields_checked=len(dictionary),catalog_sha256=helper.sha256(base/'dataset_catalog.csv'),
                dictionary_sha256=helper.sha256(base/'data_dictionary.csv'),exclusions=sorted(exclusions),
                delivery_logs_excluded=True,coverage='Only catalog-listed artifacts are required; later acceptance reports/logs are not scientific data rows'),hashes


def check_dependency_manifest(root,relative,helper):
    doc=read_json(root,relative,helper);files=doc.get('required_files')
    require(isinstance(files,dict) and bool(files),'Frozen dependency manifest has no pinned files: '+str(relative))
    for label,record in files.items():
        file=safe_file(root,label,helper)
        require(record.get('sha256')==helper.sha256(file) and int(record.get('bytes',-1))==file.stat().st_size,
                'Frozen dependency content changed: '+label)
    additional=doc.get('additionally_package',[])
    require(str(relative) in additional,'Dependency manifest does not name its own package requirement')
    for label in additional:safe_file(root,label,helper)
    return dict(manifest=str(relative),sha256=helper.sha256(root/relative),required_files=len(files),
                additional_metadata_files=len(additional),total_package_files=len(set(files)|set(additional)))


def check_probe(root,helper,catalog_hashes):
    relative=SOURCE/'calibration_leakage_probe.json'
    probe=read_json(root,relative,helper)
    require(str(relative) in catalog_hashes and helper.sha256(root/relative)==catalog_hashes[str(relative)],
            'Executed probe is not pinned by the scientific data catalog')
    require(probe.get('status')=='passed' and probe.get('formal_results_unchanged') is True
            and probe.get('no_calibration_guard_disabled') is True and probe.get('temporary_outputs_only') is True,
            'Local calibration-label probe scope or execution record is incomplete')
    before=probe.get('input_hashes_before',{});after=probe.get('input_hashes_after',{})
    require(before==after and len(before)==int(probe.get('formal_result_files_checked',-1))==19,
            'Probe did not preserve its 19 formal result files')
    for label,expected in before.items():
        file=safe_file(root,SOURCE/label,helper)
        require(helper.sha256(file)==expected,'Probe-bound formal file changed: '+label)
    module=safe_file(root,probe['tested_module'],helper)
    require(helper.sha256(module)==probe.get('tested_module_sha256'),'Probe-tested module content changed')
    controls=probe.get('target_label_negative_controls',[])
    require({row['scenario'] for row in controls}=={'target_truth_permuted','target_truth_plus_one'},'Probe negative controls are incomplete')
    require(all(row.get('executed') is True and row.get('offset_cells_unchanged_exactly')==288
                and row.get('offset_csv_bytes_unchanged') is True for row in controls),'Probe did not preserve source offsets under target-label changes')
    positive=probe.get('source_label_positive_control',{})
    require(positive.get('executed') is True and positive.get('offset_scalar_values_checked')==2016
            and positive.get('maximum_abs_error_from_plus_one',1.)<=1e-10,'Probe source-label positive control is incomplete')
    return dict(status='verified_record_and_content_hashes_only',probe=str(relative),sha256=helper.sha256(root/relative),
                tested_module=probe['tested_module'],formal_result_files_unchanged=19,
                probe_executed_during_delivery=False,scope=probe['scope'],not_tested=probe['not_tested'])


def check_source_receipt(report):
    require(report.get('status')=='passed' and report.get('mode')=='frozen_input_replay','Source frozen replay did not pass')
    require((report.get('source_cases'),report.get('target_cases'),report.get('target_layer_cases'),report.get('reestimated_offset_cells'))==(2370,27,729,288),
            'Source/target calibration replay denominators differ')
    for field in ['source_role_offsets_reestimated','source_only_calibration','source_eligibility_and_fallback_unchanged']:
        require(report.get(field) is True,'Source replay calibration scope differs: '+field)
    false_fields=['daily_model_fit','D2_model_fit','original_daily_panels_opened','original_case_caches_opened','original_model_joblibs_opened','audited_results_overwritten']
    for field in false_fields:
        require(report.get(field) is False,'Frozen source replay unexpectedly fit/opened/wrote: '+field)
    require(report.get('source_target_random_stream_intersections')==0,'Source and target random streams overlap')
    fields=['source_budget_quantile_max_abs_error','new_source_offset_max_abs_error','target_quantile_metric_max_abs_error','fixed_reference_metric_max_abs_error']
    for field in fields:require(np.isfinite(report.get(field,np.nan)) and report[field]<=1e-10,'Source numeric replay differs: '+field)
    native_fields=['native_source_draw_max_abs_error','native_source_quantile_max_abs_error','native_target_draw_max_abs_error','native_target_quantile_max_abs_error']
    for field in native_fields:require(np.isfinite(report.get(field,np.nan)) and report[field]<=1e-8,'Native20 source/target replay differs: '+field)
    return {key:report[key] for key in ['status','mode','source_cases','target_cases','target_layer_cases','source_case_budget_quantiles',
                                       'reestimated_offset_cells','source_role_offsets_reestimated','source_only_calibration',
                                       'source_target_random_stream_intersections',*fields,*native_fields,*false_fields,'limits']}


def check_time_receipt(report):
    require(report.get('status')=='passed' and report.get('mode')=='frozen_saved_annual_input_replay','Annual frozen replay did not pass')
    expected=dict(frozen_annual_rows=10860,raw_archives=820,original_common=807,actual_mask_common=805,choice_only=468,
                  all_feasible_subsets=5758,exact_conditional_random_expectations=807,weighted_summary_checks=63)
    require(all(report.get(key)==value for key,value in expected.items()),'Annual replay denominators or 63 weighted summaries differ')
    false_fields=['original_case_caches_opened','original_daily_panels_opened','models_fit','audited_results_overwritten']
    for field in false_fields:
        require(report.get(field) is False,'Annual frozen replay unexpectedly fit/opened/wrote: '+field)
    require(np.isfinite(report.get('maximum_abs_numeric_error',np.nan)) and report['maximum_abs_numeric_error']<=1e-9,
            'Annual numeric replay differs')
    return {key:report[key] for key in ['status','mode',*expected,'maximum_abs_numeric_error','primary_equal_archive_summaries',
                                       'exact_random_estimand',*false_fields,'not_replayed','daily_gap_scope']}


def execute(command,root,environment,log,timeout):
    log.parent.mkdir(parents=True,exist_ok=True)
    with log.open('w') as stream:
        process=subprocess.run(command,cwd=root,env=environment,stdout=stream,stderr=subprocess.STDOUT,timeout=timeout,text=True)
    require(process.returncode==0,'Packaged subprocess failed; see '+str(log))


def isolated_validation(archive,logs,helper):
    with tempfile.TemporaryDirectory(prefix='wrr_experiment_delivery_') as temporary:
        root=Path(temporary)
        with zipfile.ZipFile(archive) as zipped:zipped.extractall(root)
        catalog,catalog_hashes=check_catalog(root,helper)
        source_dependencies=check_dependency_manifest(root,SOURCE/'frozen_replay_dependency_manifest.json',helper)
        time_dependencies=check_dependency_manifest(root,TIME/'required_files.json',helper)
        require(source_dependencies['total_package_files']==142 and time_dependencies['total_package_files']==10,
                'Frozen C/B dependency closure sizes differ')
        probe=check_probe(root,helper,catalog_hashes)
        (logs/'catalog_preflight.json').write_text(json.dumps(catalog,indent=2)+'\n')
        environment=os.environ.copy();environment.update(helper.installed_environment()['subprocess_overrides'])
        environment['MPLCONFIGDIR']=str(root/'.delivery_cache/matplotlib')
        environment['PYTHONDONTWRITEBYTECODE']='1'
        worker=r'''
import importlib.util,json,sys
from pathlib import Path
root=Path.cwd()
spec=importlib.util.spec_from_file_location("packaged_930",root/"scripts/930_delivery_consistency.py")
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
result={"transcription":module.check_tree(root),"compile":module.compile_pdfs(root),"module":str(module.__file__)}
Path(sys.argv[1]).write_text(json.dumps(result,indent=2)+"\n")
'''
        transcription_file=logs/'transcription_compile_report.json'
        execute([sys.executable,'-c',worker,str(transcription_file)],root,environment,logs/'transcription_compile.log',1800)
        transcription=json.loads(transcription_file.read_text())
        execute([sys.executable,'scripts/975_replay_source_calibration.py'],root,environment,logs/'source_calibration_replay.log',600)
        source_raw=read_json(root,SOURCE/'replay_receipt.json',helper)
        source=check_source_receipt(source_raw)
        (logs/'source_replay_receipt.json').write_text(json.dumps(source_raw,indent=2)+'\n')
        require(check_dependency_manifest(root,SOURCE/'frozen_replay_dependency_manifest.json',helper)==source_dependencies,
                'Source replay changed its frozen scientific dependencies')
        time_file=logs/'time_replay_receipt.json'
        execute([sys.executable,'scripts/977_replay_time_support.py','--output',str(time_file)],root,environment,logs/'time_support_replay.log',600)
        time_raw=json.loads(time_file.read_text());time_check=check_time_receipt(time_raw)
        require(check_dependency_manifest(root,TIME/'required_files.json',helper)==time_dependencies,
                'Annual replay changed its frozen scientific dependencies')
        observation_output=logs/'observations';observation_output.mkdir()
        for name in ['open_observed_current_manifest.json','usgs_observed_current_manifest.json']:
            shutil.copy2(safe_file(root,OBSERVATIONS/name,helper),observation_output/name)
        execute([sys.executable,'scripts/967_current_observation_replay.py','replay','--output',str(observation_output)],
                root,environment,logs/'observation_replay.log',1200)
        observed=json.loads((observation_output/'replay_report.json').read_text())
        require(observed.get('status')=='passed' and observed.get('historical_provenance_authenticated') is False,
                'Current-content observation replay did not pass with the stated scope')
        counts={name:record['actual_report_counts'] for name,record in observed['checks'].items()}
        require(counts['open_observed']['included_stations']==95 and counts['open_observed']['witness_station_years']==35,
                'Main observation replay does not preserve the 95-station/35-witness scope')
        require(counts['usgs_observed']['station_count']==10 and counts['usgs_observed']['complete_reference_station_years']==8,
                'Additional USGS observation scope changed')
        return dict(catalog_preflight=catalog,frozen_source_dependency_manifest=source_dependencies,
                    frozen_time_dependency_manifest=time_dependencies,local_calibration_probe_record=probe,
                    transcription_and_pdf_compile=transcription,source_calibration_frozen_replay=source,
                    time_support_frozen_replay=time_check,current_observation_replay=counts,
                    catalog_checked_before_replay_receipts=True,scientific_dependencies_unchanged_after_replay=True,
                    receipt_comparison='Fresh reports checked for numeric results, denominators and scope; timestamps, runtimes and report bytes are not compared to historical receipts',
                    isolation=dict(temporary_extraction=True,fresh_subprocesses=True,cwd_and_project_imports='Extracted package',
                                   original_workspace_hidden_by_namespace=False,network_namespace_isolated=False,
                                   environment='Current Python and TeX installation; no new environment or dependency installation'),
                    not_replayed=['Original raw-data preparation and model fitting','Full D2 prediction regeneration',
                                  'B 200-seed realized selections, group-bootstrap intervals and actual daily overlap (local 974 audit content is packaged, not rerun here)',
                                  '976 evaluation-label probe (existing record/content hashes checked only)',
                                  'Strict independent external climate confirmation, data rights or permanent deposit'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,default=Path('dist/wrr_process_experiments_20261029.zip'))
    parser.add_argument('--output',type=Path,default=ROOT/EXPERIMENT/'delivery_check.json')
    args=parser.parse_args();archive=args.archive if args.archive.is_absolute() else ROOT/args.archive
    output=args.output if args.output.is_absolute() else ROOT/args.output
    output.parent.mkdir(parents=True,exist_ok=True);helper=zip_helpers()
    report=dict(status='running',created_utc=datetime.now(timezone.utc).isoformat(),archive=str(archive),environment=helper.installed_environment(),
                scope='Packaged/workspace byte identity and safe extraction; pre-replay scientific catalog hashes/rows/keys; packaged 930 transcription/PDF compilation, 975 source-calibration frozen replay, 977 annual frozen replay and 967 current observation arithmetic replay')
    try:
        require(archive.is_file(),'Experiment archive does not exist: '+str(archive))
        report['archive_sha256']=helper.sha256(archive)
        with zipfile.ZipFile(archive) as zipped:report['archive_integrity_and_workspace_match']=helper.validate_members(zipped)
        logs=ROOT/EXPERIMENT/'delivery_logs'/report['archive_sha256'];logs.mkdir(parents=True,exist_ok=True)
        report['delivery_log_directory']=str(logs.relative_to(ROOT))
        report['extracted_package_checks']=isolated_validation(archive,logs,helper)
        require(helper.sha256(archive)==report['archive_sha256'],'Archive changed during verification')
        report['status']='passed'
    except Exception as error:
        report['status']='failed';report['failure']=str(error).replace(str(ROOT),'{workspace}')
    report['completed_utc']=datetime.now(timezone.utc).isoformat()
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'report':str(output),'archive_sha256':report.get('archive_sha256'),'failure':report.get('failure')},ensure_ascii=False))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
