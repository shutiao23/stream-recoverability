import json
D = '/home/lzq/workspace/parttime/stream-recoverability/results/wrr_submission_ready/major_revision_20261014/p0_05_power_and_independence/'
d = json.load(open(D + 'protocol_fingerprint.json'))
print(json.dumps({k: d[k] for k in ('script', 'script_sha256', 'generated_utc', 'git', 'fingerprint_sha256')}, indent=1))
print('draw_reduction_reason:', d['config'].get('draw_reduction_reason'))
print('outputs:', d['outputs'])
print('timing:', {k: round(v, 1) for k, v in d['timing_seconds'].items()})
