"""Show the retained-set assertion is not vacuous: drop one evaluated case in the perturbed arm."""
import sys, json, importlib
sys.path.insert(0, 'scripts'); sys.path.insert(0, 'src'); sys.path.insert(0, '.')
import numpy as np, pandas as pd
m = importlib.import_module('202_v17_robustness')
sys.path.insert(0, 'scripts')
spec = importlib.util.spec_from_file_location('drv', 'scripts/246_wrr_noise_recompute.py')
drv = importlib.util.module_from_spec(spec); spec.loader.exec_module(drv)

cases = pd.read_parquet('results/v17_fitness/step4_ceiling/development_cases.parquet').reset_index(drop=True)
cert = pd.read_parquet('results/v17_fitness/step6_screen/development_certificates.parquet').reset_index(drop=True)
clean = pd.Series(m.gather(cases, cert['certificate_choice'], prefix='abserr_'), index=cases.index)
score = pd.to_numeric(cert['certificate_bound'], errors='coerce')
base = drv.rate_locked_detail(score, clean, clean, m.RETENTION)
broken = clean.copy(); broken.iloc[17] = np.nan
bad = drv.rate_locked_detail(score, clean, broken, m.RETENTION)
out = {
  "n_good_clean": base["n_good"], "n_good_broken": bad["n_good"],
  "retained_sets_equal": bool(np.array_equal(base["retained"], bad["retained"])),
  "assertion_would_fire": bool(not (np.array_equal(base["retained"], bad["retained"]) and base["n_good"] == bad["n_good"])),
  "note": "one NaN injected into the perturbed error column of a case with a finite clean error",
}
json.dump(out, open('scratch/f11/assertion_sensitivity.json','w'), indent=2)
print(json.dumps(out, indent=2))
