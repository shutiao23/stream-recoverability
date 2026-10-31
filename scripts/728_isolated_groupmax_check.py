#!/usr/bin/env python3
"""Recheck later annual/trend sensitivities in an isolated extracted package.

Explicit local case evidence, source models, cached predictions and selected
processed panels are bound read-only. This does not authorize distribution,
retrain source models, validate sensors or reproduce the original acquisition.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
import hashlib
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/'dist/wrr_review_response_candidate.zip'
REPORT=ROOT/'results/wrr_review_response_20261027/audit/isolated_groupmax_review_check.json'
SCRIPT='scripts/728_isolated_groupmax_check.py'
GROUPMAX='results/wrr_review_response_20261027/groupmax_annual_calibration'
ORIGINAL='results/wrr_review_response_20261027/whole_archive'
PRIVATE_DIRS=['private/wrr_open_source_sensitivity_20261026',
              'private/wrr_groupmax_annual_calibration_20261027',
              'private/wrr_review_case_evidence_20261027',
              'private/wrr_projected_risk_sensitivity_20261027']
TABLES=['trend_summary.csv','trend_paired_contrasts.csv','trend_leave_region_out.csv','trend_empirical_overlap.csv']

def validate_relative(name):
    p=Path(name)
    if p.is_absolute() or not p.parts or any(part in ('..','.') for part in p.parts):raise ValueError('Unsafe manifest path: '+name)
    return p

def inspect_archive(z,dest):
    root=dest.resolve()
    for item in z.infolist():
        if not (dest/item.filename).resolve().is_relative_to(root):raise ValueError('Unsafe ZIP path')
        if stat.S_ISLNK(item.external_attr>>16):raise ValueError('Archive symbolic link is not allowed')
        if Path(item.filename).parts and Path(item.filename).parts[0]=='private':raise ValueError('Candidate ZIP unexpectedly contains private data')

def bind_readonly(source,target):
    if source.is_dir():target.mkdir(parents=True,exist_ok=True)
    else:target.parent.mkdir(parents=True,exist_ok=True);target.touch(exist_ok=False)
    subprocess.run(['mount','--bind',str(source),str(target)],check=True)
    subprocess.run(['mount','-o','remount,bind,ro',str(target)],check=True)

def require_local_repair(package,origin):
    dependency=json.loads((package/GROUPMAX/'source_repair_dependency.json').read_text())
    if dependency.get('status')!='passed' or not dependency.get('repaired_source_group_maxima_reproduced'):
        raise ValueError('Source bridge-repair dependency audit is incomplete')
    repair=validate_relative(dependency['repair_path'])
    if (package/repair).exists():raise ValueError('Bridge-repair table unexpectedly appears in candidate ZIP')
    source=origin/repair
    expected=dependency.get('input_sha256',{}).get(str(repair))
    if (not source.is_file() or source.is_symlink() or not source.resolve().is_relative_to(origin)
            or not expected or hashlib.sha256(source.read_bytes()).hexdigest()!=expected):
        raise ValueError('Required local bridge-repair table is missing or changed')
    return repair

def child(args):
    package=args.package.resolve();origin=args.origin.resolve();report_path=args.child_result.resolve()
    manifest=json.loads((origin/'private/wrr_groupmax_annual_calibration_20261027/trend_input_manifest.json').read_text())
    plan=json.loads((package/GROUPMAX/'trend_plan.json').read_text())
    missing=[]
    for row in manifest:
        relative=validate_relative(row['path']);target=package/relative
        if str(relative).startswith('private/'):continue
        if str(relative).startswith(ORIGINAL+'/'):continue
        if target.is_file():
            pass
        else:
            source=origin/relative
            if not source.is_file() or source.is_symlink() or not source.resolve().is_relative_to(origin):
                raise ValueError('Explicit local trend input missing or changed: '+str(relative))
            missing.append(relative)
    # The original annual plan omitted this optional bridge-repair table.
    # Subsequent source re-prediction established its presence and material
    # effect; require it explicitly rather than silently skipping the repair.
    repair=require_local_repair(package,origin)
    if repair not in missing:missing.append(repair)
    # Protect the package's published baseline aggregates before overlaying the
    # larger original-case cache; the package files must match that cache.
    saved=package/ORIGINAL;original=origin/ORIGINAL
    if not original.is_dir() or not original.resolve().is_relative_to(origin) or any(p.is_symlink() for p in original.rglob('*')):
        raise ValueError('Original whole-archive cache is missing or contains symbolic links')
    for p in saved.rglob('*'):
        if p.is_file():
            q=original/p.relative_to(saved)
            if not q.is_file():raise ValueError('Candidate baseline summary differs from local case cache')
    for directory in PRIVATE_DIRS:
        source=origin/directory
        if not source.is_dir() or not source.resolve().is_relative_to(origin) or any(p.is_symlink() for p in source.rglob('*')):raise ValueError('Private source missing or contains symbolic link: '+directory)
        bind_readonly(source,package/directory)
    bind_readonly(original,saved)
    for relative in missing:bind_readonly(origin/relative,package/relative)
    os_cwd=package
    # The subprocess must leave the original working directory before the
    # workspace is hidden in this private mount namespace.
    import os
    os.chdir(os_cwd)
    subprocess.run(['mount','-t','tmpfs','-o','size=1m','tmpfs',str(origin)],check=True)
    if (origin/'README.md').exists():raise RuntimeError('Original workspace was not hidden')
    env=os.environ.copy();env.pop('TR_CONFIG',None);env['PYTHONPATH']=str(package/'src')
    env['PYTHONNOUSERSITE']='1';env['PYTHONDONTWRITEBYTECODE']='1'
    probe=subprocess.run([sys.executable,'-c','import stream_recoverability; print(stream_recoverability.__file__)'],cwd=package,env=env,capture_output=True,text=True)
    if probe.returncode or not Path(probe.stdout.strip()).resolve().is_relative_to((package/'src').resolve()):
        raise RuntimeError('Project package did not load from extracted candidate')
    expected_annual=json.loads((package/GROUPMAX/'independent_audit.json').read_text())
    expected_trend=json.loads((package/GROUPMAX/'trend_independent_audit.json').read_text())
    expected_tables={name:pd.read_csv(package/GROUPMAX/name) for name in TABLES}
    for script,label in [('721_groupmax_annual_audit.py','annual group-max source and target audit'),
                         ('725_groupmax_trend_audit.py','trend distribution and overlap audit')]:
        print('Checking '+label+' with extracted code and read-only local inputs',flush=True)
        process=subprocess.run([sys.executable,str(package/'scripts'/script)],cwd=package,env=env,capture_output=True,text=True)
        if process.returncode:raise RuntimeError(label+' failed: '+(process.stdout+process.stderr)[-3000:])
    annual=json.loads((package/GROUPMAX/'independent_audit.json').read_text())
    trend=json.loads((package/GROUPMAX/'trend_independent_audit.json').read_text())
    for field in ['status','source_prediction_rows_rechecked','source_group_maxima_checked','classifier_perturbation_cases',
                  'target_case_method_rows_rechecked','target_unique_cases_rechecked','summary_cells_checked','leave_region_cells_checked']:
        if annual[field]!=expected_annual[field]:raise ValueError('Annual audit result differs: '+field)
    for field in ['status','source_supported_archive_settings','status_counts','matched_nontrivial_archives','per_case_treatment_rows_checked',
                  'previous_empirical_overlap_archives','previous_empirical_rows_compared']:
        if trend[field]!=expected_trend[field]:raise ValueError('Trend audit result differs: '+field)
    for name,before in expected_tables.items():
        try:pd.testing.assert_frame_equal(pd.read_csv(package/GROUPMAX/name),before,check_dtype=False,check_exact=False,rtol=0,atol=1e-9)
        except AssertionError as error:raise ValueError('Reproduced trend summary differs: '+name) from error
    report={'status':'passed','original_workspace_hidden':True,'network_namespace_isolated':True,
            'local_inputs_mounted_read_only':True,'source_import_from_extracted_package':True,
            'private_directories_mounted':len(PRIVATE_DIRS),'explicit_additional_local_files_mounted':len(missing),
            'annual_source_prediction_rows':annual['source_prediction_rows_rechecked'],
            'annual_source_group_maxima':annual['source_group_maxima_checked'],
            'annual_target_case_method_rows':annual['target_case_method_rows_rechecked'],
            'annual_summary_cells':annual['summary_cells_checked'],'trend_archives':trend['matched_nontrivial_archives'],
            'trend_treatment_rows':trend['per_case_treatment_rows_checked'],
            'previous_rank_overlap_archives':trend['previous_empirical_overlap_archives'],
            'trend_tables_reproduced':len(TABLES),
            'scope':'Extracted candidate code with explicitly mounted local-only cached data, trained source models and processed target inputs; current Python environment.',
            'limits':'No provider-native raw reconstruction or source-model retraining; stored ranks are checked but not regenerated from raw histories. Rights, reviewer access, exchangeability and independent-climate validation remain unresolved.'}
    report_path.write_text(json.dumps(report,indent=2)+'\n')
    print('Isolated group-maximum annual and trend audits passed',flush=True)

def parent(args):
    archive=args.archive.resolve();origin=ROOT.resolve()
    check_python_location(origin,sys.executable,sys.prefix)
    if not archive.is_file():raise FileNotFoundError('Candidate ZIP missing')
    if shutil.which('unshare') is None or shutil.which('mount') is None:raise RuntimeError('Linux unshare and mount are required; no unisolated fallback')
    scratch=Path(args.scratch).resolve() if args.scratch else Path('/dev/shm') if Path('/dev/shm').is_dir() else Path(tempfile.gettempdir())
    if scratch.is_relative_to(origin):raise ValueError('Scratch must be outside the hidden workspace')
    with tempfile.TemporaryDirectory(prefix='wrr_groupmax_isolated_',dir=scratch) as work:
        temporary=Path(work);temporary.chmod(0o700);package=temporary/'package';package.mkdir(mode=0o700)
        with zipfile.ZipFile(archive) as z:
            bad=z.testzip()
            if bad:raise ValueError('ZIP CRC failed: '+bad)
            inspect_archive(z,package)
            z.extractall(package)
        result=temporary/'child_report.json'
        cmd=['unshare','--user','--map-root-user','--mount','--net','--propagation','private',sys.executable,
             str(package/SCRIPT),'--namespace-child','--package',str(package),'--origin',str(origin),'--child-result',str(result)]
        process=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
        tail=[]
        for line in process.stdout:
            tail.append(line);tail=tail[-30:]
            if line.startswith(('Checking ','Isolated ')):print(line.strip(),flush=True)
        if process.wait()!=0:raise RuntimeError('Isolated audit failed; no unisolated fallback: '+''.join(tail)[-3000:])
        report=json.loads(result.read_text());report.update(created_utc=datetime.now(timezone.utc).isoformat(),evidence_is_authorized_for_distribution=False)
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)

def check_python_location(origin,executable,prefix):
    if Path(executable).absolute().is_relative_to(origin) or Path(prefix).resolve().is_relative_to(origin):
        raise ValueError('Python environment is inside the workspace hidden by isolation; use an environment outside the workspace')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,default=ARCHIVE);p.add_argument('--report',type=Path,default=REPORT);p.add_argument('--scratch',type=Path)
    p.add_argument('--namespace-child',action='store_true',help=argparse.SUPPRESS)
    for name in ['package','origin','child-result']:p.add_argument('--'+name,type=Path,help=argparse.SUPPRESS)
    args=p.parse_args()
    if args.namespace_child:
        child(args)
    else:
        try:
            parent(args)
        except Exception as error:
            args.report.parent.mkdir(parents=True,exist_ok=True)
            args.report.write_text(json.dumps({'status':'failed','error':f'{type(error).__name__}: {error}',
                                               'scope':'No unisolated fallback was attempted.'},indent=2)+'\n')
            raise

if __name__=='__main__':main()
