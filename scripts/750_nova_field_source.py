#!/usr/bin/env python3
"""Plan and locally acquire the published Nova Scotia field-sample dataset.

The prior model and portal results have been seen. This is an exploratory
source-quality investigation, not independent sensor or model validation.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_nova_field_checks'
PRIVATE=ROOT/'private/wrr_nova_scotia_field_checks_20261027'
DATASET='eb067dfa-d3f7-4f65-8e78-72dae53cf5b7';VERSION='6.0.0';DOI='10.25976/sfmj-kf56'
EXPECTED='62dac848dc4d1b64eae3042a04c2f7deea63baab6e85827eb00dc58adca54c1e'
DATA=PRIVATE/'nova_scotia_field_v6.csv';MAX_BYTES=30_000_000

def freeze():
    path=OUT/'plan.json'
    if path.exists():raise FileExistsError('Existing field-check plan is preserved')
    if subprocess.run(['git','check-ignore','-q',str(PRIVATE.relative_to(ROOT))+'/probe'],cwd=ROOT).returncode:
        raise ValueError('Local field-source directory is not Git-ignored')
    OUT.mkdir(parents=True,exist_ok=True);PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    prior=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_exploratory/plan.json'
    portal=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_verified/portal_acquisition.json'
    if not prior.is_file() or not portal.is_file():raise FileNotFoundError('Previous source context missing')
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
          'status':'posthoc field-comparison plan after prior portal and model results; before field values are opened',
          'dataset_id':DATASET,'version':VERSION,'doi':DOI,'catalog':'https://datastream.org/en-ca/dataset/'+DATASET,
          'catalog_description':'Two candidate rivers have field temperature observations co-located with automated probes; equipment independence and timestamp relationship not established.',
          'sites':['NS01DL0009','NS01FB0001'],'site_names':['Kelley River at Eight Mile Ford','Northeast Margaree River at Margaree Valley'],
          'years':list(range(2009,2018)),
          'preliminary_scope':'Acquire version 6 once, inspect schema, site identity, date, time, quality, method and units before viewing temperature values; if clock labels and unique site identities support a comparison, define a separate matching plan before scoring.',
          'prior_exposure':'Two sites and period were previously selected using data completeness and cross-release agreement; portal water temperatures and model errors were already analyzed. Field-sample values were not accessed before this plan.',
          'limits':'Not preregistered, prospective or independent climate. Field and automatic records are co-located in the same monitoring programme; separate instruments, independence, time zone, interpolation and point-level quality are not established. Sparse visits cannot establish annual 24-hour coverage or absolute sensor accuracy.',
          'storage':'Keep original download and any row-level links local private until source-specific redistribution and identification conditions are confirmed; aggregate results only.',
          }
    path.write_text(json.dumps(plan,indent=2)+'\n')
    print('Recorded field-sample investigation plan; no field rows or values inspected.')

def acquire():
    plan=json.loads((OUT/'plan.json').read_text())
    if plan['dataset_id']!=DATASET or plan['version']!=VERSION:
        raise ValueError('Field-source plan changed')
    inside_git=subprocess.run(['git','rev-parse','--is-inside-work-tree'],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
    if inside_git and subprocess.run(['git','check-ignore','-q',str(PRIVATE.relative_to(ROOT))+'/probe'],cwd=ROOT).returncode:
        raise ValueError('Field-source directory must be Git-ignored before acquisition')
    PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700);part=DATA.with_suffix('.csv.part')
    if DATA.exists():
        pass
    else:
        if part.exists():raise ValueError('Partial download is preserved and requires review')
        endpoint=f'https://datastream.org/api/dataset/{DATASET}/{VERSION}/download'
        try:r=requests.get(endpoint,params={'name':'doi.org_10.25976_sfmj-kf56#6.0.0'},timeout=45)
        except requests.RequestException as e:raise RuntimeError('Field dataset endpoint unavailable: '+type(e).__name__) from None
        if r.status_code!=200:raise RuntimeError('Field dataset endpoint returned HTTP '+str(r.status_code))
        url=r.json().get('data',{}).get('url')
        if not isinstance(url,str) or not url.startswith('https://'):raise ValueError('Provider did not return an HTTPS download')
        n=0
        try:
            with requests.get(url,stream=True,timeout=(20,120)) as response:
                if response.status_code!=200:raise RuntimeError('Provider file returned HTTP '+str(response.status_code))
                with part.open('xb') as f:
                    os.chmod(part,0o600)
                    for chunk in response.iter_content(1024*1024):
                        n+=len(chunk)
                        if n>MAX_BYTES:raise ValueError('Field dataset exceeded size bound; partial preserved')
                        f.write(chunk)
        except requests.RequestException as e:raise RuntimeError('Field dataset download unavailable: '+type(e).__name__) from None
        part.rename(DATA)
    report={'status':'downloaded','source':plan['catalog'],'doi':DOI,'version':VERSION,
            'retrieved_utc':datetime.now(timezone.utc).isoformat(),'bytes':DATA.stat().st_size,'access':'Public dataset download under the provider terms and dataset disclaimer.',
            'local_only':True,'scope':'File acquisition; field values not inspected.',
            'limitations':plan['limits']}
    (OUT/'acquisition.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['freeze','acquire']);a=p.parse_args()
    freeze() if a.action=='freeze' else acquire()
