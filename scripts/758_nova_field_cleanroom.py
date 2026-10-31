#!/usr/bin/env python3
"""Download and replay the field-date check from an extracted candidate ZIP.

The official public source is downloaded into an empty temporary directory.
The original workspace is hidden during acquisition and calculation; the
arithmetic runs with a separate network namespace. No field data are copied
into the candidate ZIP or retained by this check.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
SCRIPT='scripts/758_nova_field_cleanroom.py'
ARCHIVE=ROOT/'dist/wrr_review_response_candidate.zip'
REPORT=ROOT/'results/wrr_review_response_20261027/audit/isolated_nova_field_review_check.json'
OUT='results/wrr_review_response_20261027/external_nova_field_checks'
TABLES=['range_summary.csv','selected_year_range_summary.csv','hour_membership_summary.csv']

def inspect(z,destination):
    root=destination.resolve()
    for item in z.infolist():
        if not (destination/item.filename).resolve().is_relative_to(root):raise ValueError('Unsafe ZIP path')
        if stat.S_ISLNK(item.external_attr>>16):raise ValueError('ZIP symlink is not permitted')
        if Path(item.filename).parts and Path(item.filename).parts[0]=='private':raise ValueError('Candidate ZIP contains private data')

def check_python_location(origin,executable,prefix):
    if Path(executable).absolute().is_relative_to(origin) or Path(prefix).resolve().is_relative_to(origin):
        raise ValueError('Python environment is inside the hidden workspace; use an environment outside it')

def analysis(args):
    package=args.package.resolve();out=package/OUT
    expected={name:pd.read_csv(out/name) for name in TABLES}
    expected_values=(package/'paper/wrr_tr/nova_field_values.tex').read_text()
    expected_text=(package/'paper/wrr_tr/nova_field_supporting.tex').read_text()
    env=os.environ.copy();env.pop('TR_CONFIG',None);env['PYTHONPATH']=str(package/'src')
    env['PYTHONNOUSERSITE']='1';env['PYTHONDONTWRITEBYTECODE']='1'
    for name in ['753_nova_field_range_check.py','755_nova_field_hour_membership.py',
                 '756_nova_field_independent_audit.py','757_nova_field_report.py']:
        result=subprocess.run([sys.executable,str(package/'scripts'/name)],cwd=package,env=env,capture_output=True,text=True)
        if result.returncode:raise RuntimeError(name+' failed: '+(result.stdout+result.stderr)[-3000:])
    for name,prior in expected.items():
        pd.testing.assert_frame_equal(pd.read_csv(out/name),prior,check_dtype=False,check_exact=False,rtol=0,atol=1e-10)
    if (package/'paper/wrr_tr/nova_field_values.tex').read_text()!=expected_values or (package/'paper/wrr_tr/nova_field_supporting.tex').read_text()!=expected_text:
        raise ValueError('Regenerated field manuscript text differs')
    audit=json.loads((out/'independent_audit.json').read_text());status=json.loads((out/'status.json').read_text())
    if audit['status']!='passed' or audit['field_rows_rechecked']!=146 or status['distinct_site_dates']!=73:
        raise ValueError('Field audit or denominator differs')
    args.child_result.write_text(json.dumps({'status':'passed','field_rows':audit['field_rows_rechecked'],
        'site_dates':audit['field_site_dates'],'range_summary_rows':audit['reported_day_range_rows_rechecked'],
        'proximity_summary_rows':audit['hour_proximity_rows_rechecked'],'aggregate_tables_reproduced':len(TABLES),
        'manuscript_inputs_reproduced':True},indent=2)+'\n')
    print('Offline field arithmetic and manuscript inputs reproduced',flush=True)

def child(args):
    package=args.package.resolve();origin=args.origin.resolve()
    os.chdir(package)
    subprocess.run(['mount','-t','tmpfs','-o','size=1m','tmpfs',str(origin)],check=True)
    if (origin/'README.md').exists():raise RuntimeError('Original workspace remains visible')
    source=package/'private/wrr_nova_scotia_field_checks_20261027/nova_scotia_field_v6.csv'
    if source.exists():raise ValueError('Candidate unexpectedly contains the field-source file')
    env=os.environ.copy();env.pop('TR_CONFIG',None);env['PYTHONPATH']=str(package/'src')
    env['PYTHONNOUSERSITE']='1';env['PYTHONDONTWRITEBYTECODE']='1'
    print('Downloading the fixed public field dataset into the isolated directory',flush=True)
    result=subprocess.run([sys.executable,str(package/'scripts/750_nova_field_source.py'),'acquire'],cwd=package,env=env,capture_output=True,text=True)
    if result.returncode:raise RuntimeError('Public field download failed: '+(result.stdout+result.stderr)[-2000:])
    if not source.is_file():raise ValueError('Provider download did not produce the expected file')
    print('Running field calculations in a separate network namespace',flush=True)
    result=subprocess.run(['unshare','--net',sys.executable,str(package/SCRIPT),'--analysis','--package',str(package),
                           '--child-result',str(args.child_result)],cwd=package,env=env,capture_output=True,text=True)
    if result.returncode:raise RuntimeError('Offline field audit failed: '+(result.stdout+result.stderr)[-3000:])
    print(result.stdout.strip(),flush=True)

def parent(args):
    archive=args.archive.resolve();origin=ROOT.resolve();check_python_location(origin,sys.executable,sys.prefix)
    if not archive.is_file():raise FileNotFoundError('Candidate ZIP missing')
    if shutil.which('unshare') is None or shutil.which('mount') is None:raise RuntimeError('Linux unshare and mount are required')
    scratch=Path(args.scratch).resolve() if args.scratch else Path('/dev/shm') if Path('/dev/shm').is_dir() else Path(tempfile.gettempdir())
    if scratch.is_relative_to(origin):raise ValueError('Scratch must be outside the hidden workspace')
    with tempfile.TemporaryDirectory(prefix='wrr_nova_field_',dir=scratch) as temp:
        work=Path(temp);work.chmod(0o700);package=work/'package';package.mkdir(mode=0o700)
        with zipfile.ZipFile(archive) as z:
            bad=z.testzip()
            if bad:raise ValueError('ZIP CRC failed: '+bad)
            inspect(z,package)
            z.extractall(package)
        result=work/'child.json'
        command=['unshare','--user','--map-root-user','--mount','--propagation','private',sys.executable,
                 str(package/SCRIPT),'--child','--package',str(package),'--origin',str(origin),'--child-result',str(result)]
        process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
        tail=[]
        for line in process.stdout:
            tail.append(line);tail=tail[-30:]
            if line.startswith(('Downloading ','Running ','Offline ')):print(line.strip(),flush=True)
        if process.wait()!=0:raise RuntimeError('Isolated field check failed: '+''.join(tail)[-3000:])
        report=json.loads(result.read_text());report.update(created_utc=datetime.now(timezone.utc).isoformat(),
            original_workspace_hidden=True,public_field_data_downloaded_fresh=True,
            arithmetic_network_isolated=True,field_data_retained_by_check=False,
            scope='Fresh public-source download and calculation using extracted candidate code and the current installed Python environment.',
            limitations='Provider field times, timezone, preliminary flags, sensor independence and physical quality remain unresolved. This checks data access and arithmetic, not H30 accuracy, legal rights to other data, model training or independent-climate validation.')
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',type=Path,default=ARCHIVE)
    p.add_argument('--report',type=Path,default=REPORT);p.add_argument('--scratch',type=Path)
    p.add_argument('--child',action='store_true',help=argparse.SUPPRESS);p.add_argument('--analysis',action='store_true',help=argparse.SUPPRESS)
    for name in ['package','origin','child-result']:p.add_argument('--'+name,type=Path,help=argparse.SUPPRESS)
    args=p.parse_args()
    if args.analysis:analysis(args)
    elif args.child:child(args)
    else:
        try:parent(args)
        except Exception as error:
            args.report.parent.mkdir(parents=True,exist_ok=True)
            args.report.write_text(json.dumps({'status':'failed','error':f'{type(error).__name__}: {error}',
                                               'scope':'No unisolated fallback was attempted.'},indent=2)+'\n')
            raise

if __name__=='__main__':main()
