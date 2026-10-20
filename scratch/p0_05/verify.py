import json
import pandas as pd

D = '/home/lzq/workspace/parttime/stream-recoverability/results/wrr_submission_ready/major_revision_20261014/p0_05_power_independence/'
pd.set_option('display.width', 300)
pd.set_option('display.max_colwidth', 130)

fp = json.load(open(D + 'protocol_fingerprint.json'))
print('HEAD', fp['git']['commit'][:12], '| script sha', fp['script_sha256'][:16])
print('config', {k: fp['config'][k] for k in ('outer_draws', 'outer_draws_by_panel', 'inner_draws', 'n_jobs', 'seed', 'leverage_draws')})
print('inputs:')
for item in fp['inputs']:
    print('   ', item['path'], (item['sha256'] or 'MISSING')[:16], item['bytes'])
print('self_check', fp['self_check'])
print('timing', {k: round(v, 1) for k, v in fp['timing_seconds'].items()})
print()

p = pd.read_csv(D + 'power_table.csv')
print('power_table', p.shape, '| outer draws by panel:',
      p.groupby('panel')['outer_draws'].unique().to_dict())
print(p[['panel','design_n','power_mue_2pp','power_mue_3pp','power_mue_5pp','mde80_pp','mde80_z_pp',
         'empirical_alpha_at_zero','sd_point_pp','mean_bootstrap_se_pp','mean_distinct_networks','wall_seconds']].round(3).to_string())
print()

v = pd.read_csv(D + 'network_variance_table.csv')
sel = v[v.retention.eq(0.7) & v.quantity.isin([
    'pooled_case_weighted_contrast','pooled_bootstrap_se','sd_within_network_contrasts',
    'sd_implied_by_cluster_bootstrap','sd_anova_between_network','icc_case_level_contrast',
    'design_effect_case_level_contrast','effective_independent_networks',
    'mde80_analytic_network_equal','network_equal_contrast','share_cases_in_largest_provider'])]
print(sel.pivot_table(index='quantity', columns='panel', values='value').round(3).to_string())
print()

w = pd.read_csv(D + 'weighting_scenarios.csv')
print(w[w.panel.eq('wave2_external')][['scenario','contrast_pp','ci_low_pp','ci_high_pp']].round(2).to_string())
print()

r = pd.read_csv(D + 'independent_evidence_requirements.csv')
print('requirements rows', len(r), '| needs new networks:',
      sorted(set(r[r.needs_networks_not_yet_used.astype(bool)].claim_id.astype(str))))
print(r[['requirement_id','confirmation_class','confirmable_with_existing_panels']].groupby(
    ['confirmation_class','confirmable_with_existing_panels']).size().to_string())
print()

d = json.load(open(D + 'simulation_diagnostics.json'))
print('jitter sensitivity:', json.dumps(d['jitter_seed_sensitivity'], indent=1))
print('residual pool:', {k: v for k, v in d['residual_unused_pool'].items() if k != 'reused_since_audit'})
