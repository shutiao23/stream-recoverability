import importlib.util, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("p003", ROOT/"scripts/312_wrr_p0_03_final_method_replay.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
import pandas as pd
cases = pd.read_parquet(ROOT/"scratch/p0_03/smoke_out/replay_decisions.parquet")
me = pd.read_csv(ROOT/"scratch/p0_03/smoke_out/cofailure_by_level.csv")
est = pd.read_csv(ROOT/"scratch/p0_03/smoke_out/estimator_outcomes.csv")
audit = pd.read_csv(ROOT/"scratch/p0_03/smoke_out/degenerate_donor_audit.csv")
contrasts = pd.read_csv(ROOT/"scratch/p0_03/smoke_out/method_contrasts.csv")
fp = json.loads((ROOT/"scratch/p0_03/smoke_out/protocol_fingerprint.json").read_text())
out = ROOT/"scratch/p0_03/summary_test"; out.mkdir(exist_ok=True)
mod.write_summary(out, cases, me, est, audit, contrasts, fp, {"policy_backend_consistency_ok": fp.get("policy_backend_consistency_ok")})
print((out/"SUMMARY.md").read_text()[:4000])
