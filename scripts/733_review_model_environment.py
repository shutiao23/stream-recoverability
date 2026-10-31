#!/usr/bin/env python3
"""Inspect version warnings when loading the 13 locally saved review models.

This reads trusted local joblib files. It does not distribute model objects,
test arbitrary pickle files, re-fit models, or validate numerical predictions.
"""
from __future__ import annotations
import argparse
from collections import Counter
from importlib import metadata
import json
from pathlib import Path
import re
import warnings
import joblib

ROOT=Path(__file__).resolve().parents[1]
MODELS=ROOT/'private/wrr_open_source_sensitivity_20261026/refits'
PACKAGES=['numpy','pandas','pyarrow','scipy','scikit-learn','matplotlib','torch','lightgbm','joblib']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    paths=sorted((MODELS/'before_2010/seed_00').glob('*.joblib'))+sorted((MODELS/'leave_one_year_out/seed_00').glob('*.joblib'))
    if len(paths)!=13:raise ValueError('Expected 13 locally saved source models')
    by_type=Counter();versions=Counter();other=Counter();models_with_warning=0
    for path in paths:
        with warnings.catch_warnings(record=True) as observed:
            warnings.simplefilter('always')
            bundle=joblib.load(path)
        if 'quantile_models' not in bundle:raise ValueError('Unexpected saved model format')
        any_version=False
        for warning in observed:
            text=str(warning.message)
            match=re.search(r'Trying to unpickle estimator (\S+) from version (\S+) when using version (\S+)',text)
            if match:
                any_version=True
                by_type[match.group(1)]+=1
                versions[match.group(2).rstrip('.')+' -> '+match.group(3).rstrip('.')]+=1
            else:other[warning.category.__name__]+=1
        models_with_warning+=any_version
    report={'status':'passed','source_models_loaded':len(paths),'models_with_version_warning':models_with_warning,
            'warning_count_by_estimator':dict(by_type),'warning_count_by_version':dict(versions),
            'other_warning_count_by_category':dict(other),
            'environment':{name:metadata.version(name) for name in PACKAGES},
            'scope':'Only warning and loadability audit on 13 trusted local saved models. Numerical outputs, other models, fitting and future library compatibility are not established by this check.'}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
