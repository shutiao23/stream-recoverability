import pandas as pd
D = '/home/lzq/workspace/parttime/stream-recoverability/results/wrr_submission_ready/major_revision_20261014/p0_05_power_independence/'
r = pd.read_csv(D + 'independent_evidence_requirements.csv')
print('rows', len(r))
print('needs-new:', sorted(set(r[r.needs_networks_not_yet_used.astype(bool)].claim_id.astype(str))))
print('confirmable yes:', sorted(set(r[r.confirmable_with_existing_panels.astype(str).str.startswith('yes')].claim_id.astype(str))))
print('pending/retro/exploratory:',
      sorted(set(r[r.confirmable_with_existing_panels.astype(str).isin(['pending_audit','no_retrospective_only','no_exploratory_only'])].claim_id.astype(str))))
text = open(D + 'SUMMARY.md').read()
for key in ('Outer draws per panel', 'This run recorded'):
    i = text.find(key)
    print('---', key, '->', text[i:i+330].replace('\n', ' ') if i >= 0 else 'NOT FOUND')
