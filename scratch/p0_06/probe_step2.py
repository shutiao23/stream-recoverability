import importlib.util, sys, json, time
from pathlib import Path
import pandas as pd, numpy as np
ROOT = Path('.').resolve()
spec = importlib.util.spec_from_file_location("m315", ROOT/"scripts/315_wrr_p0_06_coverage_and_recompute.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
dev = m.prep_cases(pd.read_parquet(m.INPUTS['development_cases']))
t0=time.time()
scores = m.independent_rule_scores(dev, seed=17)
for name, feats in (("generic", m.GENERIC_FEATURES), ("generic_plus_support", m.SUPPORT_SET)):
    scores[name] = m.independent_oof_scores(dev, feats, seed=17, n_splits=5)
    print(name, 'done', round(time.time()-t0,1),'s  n_features', len(feats), flush=True)
stored = pd.read_csv(m.INPUTS['step2_operating_points'])
err = pd.to_numeric(dev['abserr_policy'], errors='coerce').to_numpy(float)
for name in ('generic','generic_plus_support','peak_overlap_rule'):
    row = stored.loc[stored['screen'].eq(name)].iloc[0]
    mine = m.rate_at_retention(err, scores[name].to_numpy(float), 0.7, 0.5)
    st = float(row['rate_above_0.5_at_70'])
    print('%-24s stored %.12f  mine %.12f  diff %.3g' % (name, st, mine, abs(mine-st)))
