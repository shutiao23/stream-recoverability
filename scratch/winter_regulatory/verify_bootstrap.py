"""Confirm the vectorised cluster bootstrap reproduces the repo's own cluster_bootstrap."""
import sys, json
from pathlib import Path
ROOT = Path("/home/lzq/workspace/parttime/stream-recoverability")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import numpy as np, pandas as pd
from stream_recoverability.experiments.v17_fitness.paths import STEP3_CASES
from stream_recoverability.experiments.v17_fitness.policies import information_conditioned_choice, gather
from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap
from sklearn.metrics import roc_auc_score
import importlib.util
spec = importlib.util.spec_from_file_location("m251", ROOT / "scripts" / "251_wrr_winter_regulatory_endpoints.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

cases = pd.read_parquet(STEP3_CASES / "cases.parquet")
cases = cases.loc[cases["split_role"].eq("development")].reset_index(drop=True)
sup = pd.read_parquet(ROOT / "results/wrr_submission_ready/amendments/winter_regulatory/cold_support_cases.parquet")
key = ["network_id", "station_id", "year", "realization_id"]
merged = cases.merge(sup, on=key, how="inner", suffixes=("", "_regen"), validate="one_to_one")
err = m.policy_error(merged, "coldest30")
tol = m.TOLERANCE_LITERAL_C
keep = np.isfinite(err)
cold_obs = pd.to_numeric(merged["cold_window_overlap"], errors="coerce").to_numpy(float)[keep]
lrun = pd.to_numeric(merged["longest_run"], errors="coerce").to_numpy(float)[keep]
e = err[keep]
clusters = merged["network_id"].to_numpy()[keep]

def auc_gap_frame(sub):
    lab = (sub["error"].to_numpy(float) > tol).astype(float)
    return float(roc_auc_score(lab, sub["cold_obs"])) - float(roc_auc_score(lab, sub["longest_run"]))

frame = pd.DataFrame({"network_id": clusters, "error": e, "cold_obs": cold_obs, "longest_run": lrun})
slow = cluster_bootstrap(frame, auc_gap_frame, draws=300, seed=0)
arrays = {"error": e, "cold_obs": cold_obs, "longest_run": lrun}
def auc_gap_np(v):
    lab = (v["error"] > tol).astype(float)
    return float(roc_auc_score(lab, v["cold_obs"])) - float(roc_auc_score(lab, v["longest_run"]))
fast = m.numpy_cluster_bootstrap(arrays, auc_gap_np, clusters, draws=300, seed=0)
print("slow(repo)", {k: round(v, 8) for k, v in slow.items() if k != "se"})
print("fast(numpy)", {k: round(v, 8) for k, v in fast.items() if k != "se"})
recorded = json.load(open(ROOT / "results/wrr_submission_ready/amendments/winter_regulatory/summary.json"))
print("recorded 1200-draw:", recorded["clustered_bootstrap"]["coldest30__literal_0.5C__auc_gap_cold_window_minus_length"])
