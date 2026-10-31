#!/usr/bin/env python3
"""Independent release review. Writes only this review's evidence directory.

The stale-receipt probe deliberately edits a temporary copy of the manuscript.
It never modifies the actual paper, package, or acceptance records.
"""
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
import contextlib
import hashlib
import importlib.util
import io
import json
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'results/wrr_release_review_20261031'
OUT.mkdir(parents=True, exist_ok=True)
PACKAGE = ROOT/'dist/wrr_final_candidate_20261031.zip'
GENERATED = {'REVIEW_PACKAGE_README.txt','dependency_inventory.json','RELEASE_RECEIPT.json','CONTENT_MANIFEST.sha256'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(name, value):
    (OUT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def load_script(filename, name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/filename)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def package_check():
    external=json.loads((ROOT/'dist/wrr_final_candidate_20261031.manifest.json').read_text())
    acceptance=json.loads((ROOT/'results/final_release_20261031/acceptance.json').read_text())
    digest=sha(PACKAGE)
    assert digest==external['package_sha256']==acceptance['package']['sha256']
    with zipfile.ZipFile(PACKAGE) as z:
        names=z.namelist();assert len(names)==len(set(names))==3329
        assert z.testzip() is None
        for info in z.infolist():
            p=PurePosixPath(info.filename)
            assert not p.is_absolute() and all(s not in ['', '.', '..'] for s in p.parts)
            assert '\\' not in info.filename and stat.S_IFMT(info.external_attr>>16) in [0,stat.S_IFREG,stat.S_IFDIR]
        entries=[line.split('  ',1) for line in z.read('CONTENT_MANIFEST.sha256').decode().splitlines()]
        assert len(entries)==len({name for _,name in entries})==3328
        content=dict((name,h) for h,name in entries)
        assert set(content)==set(names)-{'CONTENT_MANIFEST.sha256'}
        for name,h in content.items():assert hashlib.sha256(z.read(name)).hexdigest()==h,name
        differences=[]
        for name in names:
            if name in GENERATED:continue
            if not (ROOT/name).is_file() or sha(ROOT/name)!=content[name]:differences.append(name)
        receipt=json.loads(z.read('RELEASE_RECEIPT.json'))
        for label, r in receipt['manuscripts'].items():
            assert sha(ROOT/r['pdf'])==r['pdf_sha256']==acceptance['manuscripts'][label]['pdf_sha256']
            assert sha(ROOT/r['tex'])==r['tex_sha256']==acceptance['manuscripts'][label]['tex_sha256']
        assert not differences,differences
    save('package_current_identity.json',dict(status='passed',archive_sha256=digest,members=len(names),workspace_files_compared=len(names)-len(GENERATED),manifest_entries=len(entries),current_differences=differences,abstract_words=receipt['abstract_words'],manuscripts=receipt['manuscripts']))


def scientific_labels():
    folder=ROOT/'results/wrr_process_experiments_20261029'
    d=pd.read_csv(folder/'source_calibration/full/target_budget_case_deltas.csv')
    d=d.loc[d.layer.eq('reestimated_source_offset')&d.comparison.eq('nested20_to_500')]
    tails=d.groupby(['region','seed']).agg(n=('delta_q95','size'),median_signed_change=('delta_q95','median'),median_absolute_change=('abs_delta_q95','median')).reset_index()
    tails.to_csv(OUT/'abstract_endpoint_estimands.csv',index=False)
    annual=pd.read_parquet(folder/'time_frozen_replay/annual_inputs.parquet')
    years=annual.drop_duplicates(['station_key','year']).groupby('station_key').year.agg(['min','max','nunique'])
    years['interior_calendar_years_not_in_reference']=years['max']-years['min']+1-years['nunique']
    years.reset_index().to_csv(OUT/'reference_year_set_scope.csv',index=False)
    save('reference_year_set_scope.json',dict(stations=len(years),stations_with_interior_years_outside_reference=int(years.interior_calendar_years_not_in_reference.gt(0).sum()),interpretation='The slope target uses eligible complete reference station-years, which need not include every calendar year inside the observed span. No underlying numerical result is changed by this clarification.'))


def prior_evidence_identity():
    files=[ROOT/'results/wrr_multiview_review_20261031/audit_scope.json',ROOT/'results/wrr_multiview_review_20261031/source_roles_reaudit.json',ROOT/'results/wrr_multiview_review_20261031/region_water/region_water_audit_report.json']
    rows=[]
    for file in files:
        record=json.loads(file.read_text());pairs=record.get('inputs_sha256',record.get('input_sha256',{}))
        for relative, h in pairs.items():
            p=ROOT/relative
            rows.append(dict(record=str(file.relative_to(ROOT)),input=relative,unchanged=p.exists() and sha(p)==h))
    save('prior_evidence_identity.json',dict(checks=rows,n_checked=len(rows),changed=[r['input'] for r in rows if not r['unchanged']],note='Earlier executed scientific audits are reused where their bound input content is unchanged; this is not a claim that every old test was run anew.'))


def stale_acceptance_probe():
    module=load_script('980_final_release.py','release_probe_980')
    original_paper_hash=sha(ROOT/'paper/wrr_tr/review_completion_article.tex')
    original_accept_hash=sha(ROOT/'results/final_release_20261031/acceptance.json')
    with tempfile.TemporaryDirectory(prefix='stale-acceptance-probe-') as temporary:
        clone=Path(temporary);shutil.copytree(ROOT/'paper/wrr_tr',clone/'paper/wrr_tr')
        (clone/'scripts').mkdir();shutil.copy2(ROOT/'scripts/930_delivery_consistency.py',clone/'scripts/930_delivery_consistency.py')
        review=clone/'docs/reviews/wrr_multiview_review_20261031';review.mkdir(parents=True)
        shutil.copy2(ROOT/'docs/reviews/wrr_multiview_review_20261031/MINOR_REVISION_COMPLETION_ZH.md',review/'MINOR_REVISION_COMPLETION_ZH.md')
        reports=clone/'results/final_release_20261031';reports.mkdir(parents=True)
        for name in ['package_verification.json','targeted_tests_summary.json','package_delivery_check.json']:
            shutil.copy2(ROOT/'results/final_release_20261031'/name,reports/name)
        (clone/'dist').mkdir()
        cloned_manifest=clone/'dist/wrr_final_candidate_20261031.manifest.json'
        shutil.copy2(ROOT/'dist/wrr_final_candidate_20261031.manifest.json',cloned_manifest)
        # Only paths and unrelated Git reporting are redirected. All accept()
        # checks run unchanged against the real package and real prior receipts.
        module.ROOT=clone;module.OUT=reports;module.REVIEW=review;module.EXTERNAL_MANIFEST=cloned_manifest
        module.git_state=lambda: {'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'note':'Temporary reviewer fixture; Git metadata only is substituted'}
        with contextlib.redirect_stdout(io.StringIO()):module.accept(SimpleNamespace())
        baseline=json.loads((reports/'acceptance.json').read_text())
        article=clone/'paper/wrr_tr/review_completion_article.tex'
        text=article.read_text();assert 'slope RMSE 0.170' in text
        article.write_text(text.replace('slope RMSE 0.170','slope RMSE 9.170',1))
        rejected=False;message=None
        try:
            with contextlib.redirect_stdout(io.StringIO()):module.accept(SimpleNamespace())
        except Exception as exc:
            rejected=True;message=type(exc).__name__+': '+str(exc)
        after=json.loads((reports/'acceptance.json').read_text())
        expected=json.loads((ROOT/'dist/wrr_final_candidate_20261031.manifest.json').read_text())['manuscripts']['article']['tex_sha256']
        result=dict(test='Fault injection in a temporary manuscript copy only',baseline_status=baseline['status'],mutation='Only the temporary abstract RMSE literal changed from 0.170 to 9.170 after prior verification; no new build, verify, or tests',rejected=rejected,rejection_message=message,returned_status=after['status'],recorded_current_tex_matches_packaged_tex=after['manuscripts']['article']['tex_sha256']==expected,cached_pdf_text_match_flag=after['package_verification']['manuscript_pdf_text_matches_rebuild'],scope='accept() reuses old verification and captures current paper hashes without comparing them to the verified package. This does not establish that the real current candidate is mismatched.')
    result['original_manuscript_unchanged']=sha(ROOT/'paper/wrr_tr/review_completion_article.tex')==original_paper_hash
    result['original_acceptance_record_unchanged']=sha(ROOT/'results/final_release_20261031/acceptance.json')==original_accept_hash
    assert result['original_manuscript_unchanged'] and result['original_acceptance_record_unchanged']
    save('stale_acceptance_probe.json',result)


if __name__=='__main__':
    package_check();print('Current package identity passed',flush=True)
    scientific_labels();prior_evidence_identity()
    stale_acceptance_probe();print('Temporary stale-acceptance probe completed',flush=True)
