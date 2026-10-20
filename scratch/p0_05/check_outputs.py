import pandas as pd
D = '/home/lzq/workspace/parttime/stream-recoverability/results/wrr_submission_ready/major_revision_20261014/p0_05_power_independence/'
pd.set_option('display.width', 300)
pd.set_option('display.max_colwidth', 120)
r = pd.read_csv(D + 'independent_evidence_requirements.csv')
need = r[r.needs_networks_not_yet_used.astype(bool)]
print('claims needing networks used nowhere yet:', sorted(set(need.claim_id.astype(str))))
print(r[r.requirement_type.eq('provider_independence')][['requirement_id', 'blocker']].to_string())
res = pd.read_csv(D + 'residual_unused_networks.csv')
print(res.groupby('status').size().to_string())
print(res[res.status.str.startswith('residual')].to_string())
