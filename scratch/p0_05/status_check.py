import importlib.util
import pandas as pd

spec = importlib.util.spec_from_file_location(
    "m314", "/home/lzq/workspace/parttime/stream-recoverability/scripts/314_wrr_p0_05_power_and_independence.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
r = pd.read_csv('/home/lzq/workspace/parttime/stream-recoverability/results/wrr_submission_ready/claim_registry.csv')
unknown = sorted(set(r.status.astype(str)) - set(mod.STATUS_CLASS))
print('unmapped statuses:', unknown)
print(r.loc[r.status.astype(str).isin(unknown), ['claim_id', 'status', 'statement']].to_string(max_colwidth=100))
