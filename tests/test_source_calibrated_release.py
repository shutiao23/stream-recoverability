"""Source-derived score threshold handles bootstrap weights and tied scores."""
import importlib.util
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
spec=importlib.util.spec_from_file_location('source_release',Path(__file__).resolve().parents[1]/'scripts/558_source_calibrated_release.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_weighted_threshold_only_uses_source_scores_and_admits_ties_together():
    score=np.array([.1,.2,.2,.9]);weight=np.array([1.,1.,2.,1.])
    threshold,rate=m.fit_threshold(score,[True]*4,weight,.78)
    assert threshold==.2 and rate==.8
    threshold,rate=m.fit_threshold(score,[True]*4,weight,.01)
    assert threshold is None and rate==0
    threshold,rate=m.fit_threshold(score,[False]*4,weight,.5)
    assert threshold is None and rate==0
