import sys, time
from pathlib import Path
ROOT = Path('/home/lzq/workspace/parttime/stream-recoverability')
sys.path.insert(0, str(ROOT/'src'))
import numpy as np, pandas as pd
from stream_recoverability.experiments.v17_fitness.frontier import operating_point_contrast
from stream_recoverability.experiments.v17_fitness.paths import PRIMARY_TOLERANCE_C

def build_frame(cases, certs):
    frame = cases[['network_id']].copy()
    frame['cert_score'] = pd.to_numeric(certs['certificate_bound'], errors='coerce')
    frame['cert_error'] = pd.to_numeric(certs['certificate_abs_error'], errors='coerce')
    rng = np.random.default_rng(991)
    frame['length'] = pd.to_numeric(cases['longest_run'], errors='coerce') + rng.random(len(cases))
    frame['policy_error'] = pd.to_numeric(cases['abserr_policy'], errors='coerce')
    frame['cert_score'] = frame['cert_score'].fillna(np.inf)
    return frame

t0=time.time()
dev = pd.read_parquet(ROOT/'results/v17_fitness/step4_ceiling/development_cases.parquet').reset_index(drop=True)
devc = pd.read_parquet(ROOT/'results/v17_fitness/step6_screen/development_certificates.parquet')
w2 = pd.read_parquet(ROOT/'results/wrr_submission_ready/p0_07_wave2_ingest/p0_07_wave2_confirmation/wave2_cases.parquet').reset_index(drop=True)
w2c = pd.read_parquet(ROOT/'results/wrr_submission_ready/p0_07_wave2_ingest/p0_07_wave2_confirmation/wave2_certificates.parquet')
print('load', time.time()-t0, len(dev), len(devc), len(w2), len(w2c))

for name, cases, certs in [('dev',dev,devc),('wave2',w2,w2c)]:
    t=time.time()
    r = operating_point_contrast(cases, certs, retention=0.70, seed=0, draws=2000)
    print(name, {k:(round(v,4) if isinstance(v,float) else v) for k,v in r.items()}, 'time', round(time.time()-t,1))
