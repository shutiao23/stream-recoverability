import importlib.util, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("p003", ROOT/"scripts/312_wrr_p0_03_final_method_replay.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
import pandas as pd
out = ROOT/"results/wrr_submission_ready/major_revision_20261014/p0_03_final_method_replay"
cases = pd.read_parquet(out/"replay_decisions.parquet")
me = pd.read_csv(out/"cofailure_by_level.csv")
est = pd.read_csv(out/"estimator_outcomes.csv")
audit = pd.read_csv(out/"degenerate_donor_audit.csv")
contrasts = pd.read_csv(out/"method_contrasts.csv")
fp = json.loads((out/"protocol_fingerprint.json").read_text())
mod.write_summary(out, cases, me, est, audit, contrasts, fp, {"policy_backend_consistency_ok": fp.get("policy_backend_consistency_ok")})
text = (out/"SUMMARY.md").read_text()
print("chars", len(text))
print(text[:1500])
