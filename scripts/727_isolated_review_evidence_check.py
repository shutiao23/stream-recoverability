#!/usr/bin/env python3
"""Test extracted review code with explicitly supplied local evidence.

Linux user, mount and network namespaces hide the original workspace from the
child and expose the evidence directory read-only. This is a local audit, not
authorization to distribute evidence, a fresh dependency installation, a raw
source rebuild or independent physical-data validation.
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

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE=ROOT/'dist/wrr_review_response_candidate.zip'
DEFAULT_EVIDENCE=ROOT/'private/wrr_review_case_evidence_20261027'
DEFAULT_REPORT=ROOT/'results/wrr_review_response_20261027/audit/isolated_private_review_check.json'
SCRIPT='scripts/727_isolated_review_evidence_check.py'

def inspect_members(archive,destination):
    """Reject paths escaping extraction root or archive-stored symbolic links."""
    root=destination.resolve()
    for entry in archive.infolist():
        if not (destination/entry.filename).resolve().is_relative_to(root):raise ValueError('Unsafe ZIP path')
        if stat.S_ISLNK(entry.external_attr >> 16):raise ValueError('ZIP symbolic links are not permitted')

def run_child(args):
    package=args.package.resolve();origin=args.origin.resolve();evidence=args.evidence.resolve()
    bound=args.bound.resolve();view=args.view.resolve();result=args.child_result.resolve()
    # The bind mount is read-only and exists only inside the new mount namespace.
    subprocess.run(['mount','--bind',str(evidence),str(bound)],check=True)
    subprocess.run(['mount','-o','remount,bind,ro',str(bound)],check=True)
    # Leave the original cwd before hiding its mount; otherwise cwd can retain
    # a directory handle to the underlying source tree despite the new mount.
    os.chdir(package)
    subprocess.run(['mount','-t','tmpfs','-o','size=1m','tmpfs',str(origin)],check=True)
    if (origin/'README.md').exists():raise RuntimeError('Original workspace was not hidden')
    for name in ['data','results','scratch','annual_source_cases']:
        source=bound/name
        if not source.exists():raise FileNotFoundError('Evidence component missing: '+name)
        (view/name).symlink_to(source,target_is_directory=source.is_dir())
    env=os.environ.copy();env.pop('TR_CONFIG',None);env['PYTHONPATH']=str(package/'src')
    env['PYTHONNOUSERSITE']='1';env['PYTHONDONTWRITEBYTECODE']='1'
    # Verify the imported project module belongs to the extracted package.
    probe=subprocess.run([sys.executable,'-c','import stream_recoverability; print(stream_recoverability.__file__)'],cwd=package,env=env,capture_output=True,text=True)
    if probe.returncode or not Path(probe.stdout.strip()).resolve().is_relative_to((package/'src').resolve()):
        raise RuntimeError('Project import did not resolve to the extracted package')
    checks=[('case arithmetic','569_verify_private_case_evidence.py',['--evidence',str(view)]),
            ('annual predictions','576_verify_private_annual_predictions.py',['--evidence',str(view),'--report',str(result.parent/'annual_report.json')])]
    for name,script,parameters in checks:
        print('Checking '+name+' using extracted code and read-only supplied evidence',flush=True)
        proc=subprocess.Popen([sys.executable,str(package/'scripts'/script),*parameters],cwd=package,env=env,
                              stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
        tail=[]
        for line in proc.stdout:
            tail.append(line);tail=tail[-30:]
            if line.startswith('Verified seed '):print(line.strip(),flush=True)
        if proc.wait()!=0:raise RuntimeError(name+' failed: '+''.join(tail)[-2000:])
    case=json.loads((view/'local_case_audit.json').read_text())
    annual=json.loads((result.parent/'annual_report.json').read_text())
    if case.get('status')!='passed' or annual.get('status')!='passed' or annual.get('seeds')!=20:
        raise ValueError('Extracted private-evidence checks did not fully pass')
    report={'status':'passed','case_audit_checks':list(case['checks']),
            'canonical_daily_stations':case['checks']['canonical_daily_record_reaudit']['stations'],
            'canonical_complete_reference_years':case['checks']['canonical_daily_record_reaudit']['complete_reference_years'],
            'canonical_witnesses':case['checks']['canonical_daily_record_reaudit']['witnesses'],
            'annual_source_seeds':annual['seeds'],'annual_source_case_rows':annual['cases'],
            'annual_scorecard_cells':sum(x['scorecard_cells'] for x in annual['details']),
            'annual_paired_cells':sum(x['paired_cells'] for x in annual['details']),
            'source_import_from_extracted_package':True,'original_workspace_hidden':True,
            'evidence_bind_read_only':True,'network_namespace_isolated':True,
            'scope':'Extracted package code with an explicitly supplied local-only evidence directory and the current installed Python environment.',
            'limits':'No provider-native raw reconstruction, source-model training or independent physical/climate validation; this test does not establish legal rights, reviewer access or a permanent deposit.'}
    result.write_text(json.dumps(report,indent=2)+'\n')
    print('Isolated case and annual scoring checks passed',flush=True)

def run_parent(args):
    archive=args.archive.resolve();evidence=args.evidence.resolve();origin=ROOT.resolve()
    check_python_location(origin,sys.executable,sys.prefix)
    if not archive.is_file() or not evidence.is_dir():raise FileNotFoundError('Archive or explicit local evidence directory is missing')
    if origin.is_relative_to(evidence):raise ValueError('Evidence cannot contain the workspace being hidden')
    if any(path.is_symlink() for path in evidence.rglob('*')):raise ValueError('Evidence tree contains a symbolic link; review it before isolation')
    if shutil.which('unshare') is None or shutil.which('mount') is None:raise RuntimeError('Linux unshare and mount are required; no unisolated fallback is used')
    scratch=Path(args.scratch).resolve() if args.scratch else Path('/dev/shm') if Path('/dev/shm').is_dir() else Path(tempfile.gettempdir())
    if scratch.is_relative_to(origin):raise ValueError('Scratch directory must be outside the hidden workspace')
    with tempfile.TemporaryDirectory(prefix='wrr_isolated_review_',dir=scratch) as temporary:
        temp=Path(temporary);temp.chmod(0o700)
        package=temp/'package';bound=temp/'bound_evidence';view=temp/'evidence_view'
        for path in (package,bound,view):path.mkdir(mode=0o700)
        with zipfile.ZipFile(archive) as z:
            bad=z.testzip()
            if bad:raise ValueError('ZIP CRC failed: '+bad)
            inspect_members(z,package)
            z.extractall(package)
        result=temp/'child_report.json'
        cmd=['unshare','--user','--map-root-user','--mount','--net','--propagation','private',sys.executable,
             str(package/SCRIPT),'--namespace-child','--package',str(package),'--origin',str(origin),
             '--evidence',str(evidence),'--bound',str(bound),'--view',str(view),'--child-result',str(result)]
        proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
        tail=[]
        for line in proc.stdout:
            tail.append(line);tail=tail[-30:]
            if line.startswith(('Checking ','Verified seed ','Isolated ')):print(line.strip(),flush=True)
        if proc.wait()!=0:raise RuntimeError('Namespace audit failed; no unisolated fallback: '+''.join(tail)[-3000:])
        report=json.loads(result.read_text())
        report.update(created_utc=datetime.now(timezone.utc).isoformat(),evidence_is_authorized_for_distribution=False)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)

def check_python_location(origin,executable,prefix):
    if Path(executable).absolute().is_relative_to(origin) or Path(prefix).resolve().is_relative_to(origin):
        raise ValueError('Python environment is inside the workspace hidden by isolation; use an environment outside the workspace')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,default=DEFAULT_ARCHIVE);p.add_argument('--evidence',type=Path,default=DEFAULT_EVIDENCE)
    p.add_argument('--report',type=Path,default=DEFAULT_REPORT);p.add_argument('--scratch',type=Path)
    p.add_argument('--namespace-child',action='store_true',help=argparse.SUPPRESS)
    for name in ['package','origin','bound','view','child-result']:p.add_argument('--'+name,type=Path,help=argparse.SUPPRESS)
    args=p.parse_args()
    if args.namespace_child:run_child(args)
    else:run_parent(args)

if __name__=='__main__':main()
