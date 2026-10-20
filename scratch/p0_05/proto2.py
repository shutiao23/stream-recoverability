import sys, time
from pathlib import Path
ROOT = Path('/home/lzq/workspace/parttime/stream-recoverability')
sys.path.insert(0, str(ROOT/'src'))
import numpy as np, pandas as pd
from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap
from stream_recoverability.experiments.v17_fitness.paths import PRIMARY_TOLERANCE_C
TOL = PRIMARY_TOLERANCE_C
RET = 0.70

def build_frame(cases, certs, seed=991):
    frame = cases[['network_id']].copy()
    frame['cert_score'] = pd.to_numeric(certs['certificate_bound'], errors='coerce')
    frame['cert_error'] = pd.to_numeric(certs['certificate_abs_error'], errors='coerce')
    rng = np.random.default_rng(seed)
    frame['length'] = pd.to_numeric(cases['longest_run'], errors='coerce') + rng.random(len(cases))
    frame['policy_error'] = pd.to_numeric(cases['abserr_policy'], errors='coerce')
    frame['cert_score'] = frame['cert_score'].fillna(np.inf)
    return frame

def fail_rate(err):
    bad = ~np.isfinite(err) | (err > TOL)
    return float(bad.mean()) if err.size else float('nan')

def fast_stat(block):
    k = max(1, int(round(RET * len(block))))
    if k > len(block): return float('nan')
    cs = block['cert_score'].to_numpy(dtype=float); ce = block['cert_error'].to_numpy(dtype=float)
    ln = block['length'].to_numpy(dtype=float); pe = block['policy_error'].to_numpy(dtype=float)
    ci = np.argpartition(cs, k-1)[:k]; li = np.argpartition(ln, k-1)[:k]
    return fail_rate(ce[ci]) - fail_rate(pe[li])

def pd_stat(block):
    k = max(1, int(round(RET * len(block))))
    if k > len(block): return float('nan')
    cert = block.nsmallest(k,'cert_score')['cert_error'].to_numpy(dtype=float)
    length = block.nsmallest(k,'length')['policy_error'].to_numpy(dtype=float)
    return fail_rate(cert) - fail_rate(length)

dev = pd.read_parquet(ROOT/'results/v17_fitness/step4_ceiling/development_cases.parquet').reset_index(drop=True)
devc = pd.read_parquet(ROOT/'results/v17_fitness/step6_screen/development_certificates.parquet')
w2 = pd.read_parquet(ROOT/'results/wrr_submission_ready/p0_07_wave2_ingest/p0_07_wave2_confirmation/wave2_cases.parquet').reset_index(drop=True)
w2c = pd.read_parquet(ROOT/'results/wrr_submission_ready/p0_07_wave2_ingest/p0_07_wave2_confirmation/wave2_certificates.parquet')

for nm, cases, certs in [('dev',dev,devc),('wave2',w2,w2c)]:
    f = build_frame(cases, certs)
    print(nm, 'n=',len(f), 'nets=', f.network_id.nunique(), 'fast', round(fast_stat(f),6), 'pd', round(pd_stat(f),6))
    t=time.time(); r1 = cluster_bootstrap(f, fast_stat, draws=500, seed=1); t1=time.time()-t
    t=time.time(); r2 = cluster_bootstrap(f, pd_stat, draws=500, seed=1); t2=time.time()-t
    print('  fast 500 draws %.2fs -> se %.5f ci[%.4f,%.4f]' % (t1, r1['se'], r1['low'], r1['high']))
    print('  pandas 500 draws %.2fs -> se %.5f ci[%.4f,%.4f]' % (t2, r2['se'], r2['low'], r2['high']))
