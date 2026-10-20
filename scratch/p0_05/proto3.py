import sys, time, os
from pathlib import Path
ROOT = Path('/home/lzq/workspace/parttime/stream-recoverability')
sys.path.insert(0, str(ROOT/'src'))
import numpy as np, pandas as pd
from joblib import Parallel, delayed
from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap
from stream_recoverability.experiments.v17_fitness.paths import PRIMARY_TOLERANCE_C
TOL = PRIMARY_TOLERANCE_C; RET = 0.70
DEV_CASES = str(ROOT/'results/v17_fitness/step4_ceiling/development_cases.parquet')
DEV_CERTS = str(ROOT/'results/v17_fitness/step6_screen/development_certificates.parquet')
CACHE = {}

def panel_frames(cases_path, certs_path, seed=991):
    key = (cases_path, certs_path, seed)
    if key not in CACHE:
        cases = pd.read_parquet(cases_path, columns=['network_id','longest_run','abserr_policy']).reset_index(drop=True)
        certs = pd.read_parquet(certs_path, columns=['certificate_bound','certificate_abs_error']).reset_index(drop=True)
        frame = cases[['network_id']].copy()
        frame['cert_score'] = pd.to_numeric(certs['certificate_bound'], errors='coerce').fillna(np.inf)
        frame['cert_error'] = pd.to_numeric(certs['certificate_abs_error'], errors='coerce').to_numpy()
        rng = np.random.default_rng(seed)
        frame['length'] = pd.to_numeric(cases['longest_run'], errors='coerce').to_numpy() + rng.random(len(cases))
        frame['policy_error'] = pd.to_numeric(cases['abserr_policy'], errors='coerce').to_numpy()
        groups = {k: b for k, b in frame.groupby('network_id', sort=True)}
        CACHE[key] = groups
    return CACHE[key]

def fail_rate(err):
    return float(((~np.isfinite(err)) | (err > TOL)).mean()) if err.size else float('nan')

def stat(block):
    k = max(1, int(round(RET*len(block))))
    if k > len(block): return float('nan')
    cs = block['cert_score'].to_numpy(dtype=float); ce = block['cert_error'].to_numpy(dtype=float)
    ln = block['length'].to_numpy(dtype=float); pe = block['policy_error'].to_numpy(dtype=float)
    ci = np.argpartition(cs, k-1)[:k]; li = np.argpartition(ln, k-1)[:k]
    return fail_rate(ce[ci]) - fail_rate(pe[li])

def one_draw(cases_path, certs_path, keys, n_net, seed, inner, jseed=991):
    groups = panel_frames(cases_path, certs_path, jseed)
    rng = np.random.default_rng(seed)
    picked = rng.choice(np.asarray(keys, dtype=object), size=n_net, replace=True)
    parts = []
    for i, k in enumerate(picked):
        b = groups[str(k)].copy()
        b['cluster_key'] = i
        parts.append(b)
    frame = pd.concat(parts, ignore_index=True)
    r = cluster_bootstrap(frame, stat, cluster='cluster_key', draws=inner, seed=int(seed))
    return (r['point'], r['se'], r['low'], r['high'], len(set(picked.tolist())))

if __name__ == '__main__':
    t0=time.time()
    g = panel_frames(DEV_CASES, DEV_CERTS)
    keys = list(g)
    print('frame build', round(time.time()-t0,2), 'nets', len(keys))
    for n_net in (20, 80):
        for outer, inner in ((8, 200),):
            t=time.time()
            out = Parallel(n_jobs=8)(delayed(one_draw)(DEV_CASES, DEV_CERTS, keys, n_net, s, inner) for s in range(outer))
            dt=time.time()-t
            print(f'N={n_net} outer={outer} inner={inner} wall={dt:.1f}s  per-core-draw={dt*8/outer*1000:.0f}ms')
