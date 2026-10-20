import sys, time, os
from pathlib import Path
ROOT = Path('/home/lzq/workspace/parttime/stream-recoverability')
sys.path.insert(0, str(ROOT/'src'))
import numpy as np, pandas as pd
CACHE = {}
BUILDS = 0
def warm():
    global BUILDS
    key = 'x'
    if key not in CACHE:
        BUILDS += 1
        time.sleep(0.05)
        CACHE[key] = os.getpid()
    return CACHE[key]

def task(i):
    p = warm()
    return (i, p, BUILDS)

if __name__ == '__main__':
    from joblib import Parallel, delayed
    for backend in ('multiprocessing', 'loky'):
        t=time.time()
        out = Parallel(n_jobs=4, backend=backend)(delayed(task)(i) for i in range(12))
        dt=time.time()-t
        pids = sorted(set(o[1] for o in out))
        builds = sorted(set(o[2] for o in out))
        print(backend, 'wall %.2fs' % dt, 'warm_pids', pids, 'BUILDS_values', builds)
