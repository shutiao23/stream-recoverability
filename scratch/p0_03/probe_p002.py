import os
for v in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(v,"1")
import sys, json, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/"src"))
import numpy as np, pandas as pd
from stream_recoverability.experiments.v17_fitness.screen import Certificate, split_networks
from stream_recoverability.experiments.v17_fitness.paths import NOMINAL_COVERAGE, STEP4_CEILING, STEP6_SCREEN

cases = pd.read_parquet(STEP4_CEILING/"development_cases.parquet").reset_index(drop=True)
stored = pd.read_parquet(STEP6_SCREEN/"development_certificates.parquet").reset_index(drop=True)
print("cases", cases.shape, "stored", stored.shape)
networks = sorted(cases["network_id"].astype(str).unique())
rng = np.random.default_rng(0)
order = rng.permutation(len(networks))
folds = {networks[int(i)]: pos % 5 for pos, i in enumerate(order)}
cases["_fold"] = cases["network_id"].astype(str).map(folds)
print("fold sizes", cases["_fold"].value_counts().sort_index().to_dict())
fold_id = st["_fold"] if False else None

t0=time.time()
fold = 0
test = cases.loc[cases["_fold"].eq(fold)]
train = cases.loc[~cases["_fold"].eq(fold)]
fit_ids, cal_ids = split_networks(train["network_id"].astype(str).unique(), fraction=0.3, seed=0+fold)
model = Certificate(coverage=NOMINAL_COVERAGE).fit(train.loc[train.network_id.astype(str).isin(fit_ids)], train.loc[train.network_id.astype(str).isin(cal_ids)], seed=0+fold)
pred = model.predict(test)
print("fit+predict sec", round(time.time()-t0,1))
b_new = pd.to_numeric(pred["certificate_bound"], errors="coerce").to_numpy()
b_old = pd.to_numeric(stored.loc[test.index, "certificate_bound"], errors="coerce").to_numpy()
both = np.isfinite(b_new) & np.isfinite(b_old)
print("finite new/old", np.isfinite(b_new).sum(), np.isfinite(b_old).sum(), "both", both.sum())
print("max abs diff", float(np.max(np.abs(b_new[both]-b_old[both]))) if both.any() else None)
print("corr", float(np.corrcoef(b_new[both], b_old[both])[0,1]) if both.sum()>2 else None)
print("choice match", float((pred["certificate_choice"].astype(str).to_numpy() == stored.loc[test.index,"certificate_choice"].astype(str).to_numpy()).mean()))
# p0_02 fold assignments vs replay networks
fa = pd.read_csv(ROOT/"results/wrr_submission_ready/major_revision_20261014/p0_02_frozen_risk_thresholds/fold_assignments.csv")
print("fold_assignments panels", fa.panel.value_counts().to_dict())
mine = ['chmi_morava','chmi_vltava','gkd_bayern_iller','huc8_02040202','huc8_03110206','nve_basin_26','nve_basin_88','usgs2_huc2_08','usgs2_huc2_15','usgs2_huc4_0601','usgs2_huc4_1901','usgs2_huc6_020502','usgs2_huc6_070900','usgs2_huc6_071300','usgs2_huc6_120301','usgs2_huc6_180400']
cases_nets = ['chmi_morava','chmi_vltava','gkd_bayern_iller','huc8_03110206','nve_basin_26','nve_basin_88','usgs2_huc2_08','usgs2_huc2_15','usgs2_huc4_0601','usgs2_huc4_1901','usgs2_huc6_020502','usgs2_huc6_070900','usgs2_huc6_071300','usgs2_huc6_120301','usgs2_huc6_180400']
sub = fa[fa.panel.eq("development")]
print("dev folds available", len(sub), "missing replay nets", sorted(set(cases_nets)-set(sub.network_id.astype(str))))
print(sub[sub.network_id.astype(str).isin(cases_nets)][["network_id","fold_seed_101","fold_seed_202","fold_seed_303"]].to_string(index=False))
# p0_02 thresholds
d=json.load(open(ROOT/"results/wrr_submission_ready/major_revision_20261014/p0_02_frozen_risk_thresholds/final_admission_thresholds.json"))
for seed in (101,202,303):
    rec=[r for r in d["records"] if r["panel"]=="development" and r["score"]=="calibrated_bound" and r["fold_seed"]==seed][0]
    print(seed, {f["fold"]: round(f["threshold"],4) for f in rec["folds"]}, "pooled", round(rec["pooled_eval"]["retention"],4), round(rec["pooled_eval"]["false_admit_rate"],4))
