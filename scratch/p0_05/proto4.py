import sys
from pathlib import Path
ROOT = Path('/home/lzq/workspace/parttime/stream-recoverability')
sys.path.insert(0, str(ROOT/'src'))
import numpy as np, pandas as pd
from stream_recoverability.experiments.v17_fitness.paths import PRIMARY_TOLERANCE_C
TOL = PRIMARY_TOLERANCE_C; RET=0.70

def build(cases, certs, prov, seed=991):
    f = cases[['network_id']].copy()
    f['provider'] = cases['provider'].astype(str).to_numpy() if prov else ''
    f['cert_score'] = pd.to_numeric(certs['certificate_bound'], errors='coerce').fillna(np.inf).to_numpy()
    f['cert_error'] = pd.to_numeric(certs['certificate_abs_error'], errors='coerce').to_numpy()
    rng = np.random.default_rng(seed)
    f['length'] = pd.to_numeric(cases['longest_run'], errors='coerce').to_numpy() + rng.random(len(cases))
    f['policy_error'] = pd.to_numeric(cases['abserr_policy'], errors='coerce').to_numpy()
    return f

def analyse(f, label):
    n = len(f); k = max(1, int(round(RET*n)))
    cs = f['cert_score'].to_numpy(); ln = f['length'].to_numpy()
    ce = f['cert_error'].to_numpy(); pe = f['policy_error'].to_numpy()
    ci = np.argpartition(cs, k-1)[:k]; li = np.argpartition(ln, k-1)[:k]
    x = np.zeros(n); y = np.zeros(n)
    x[ci] = ((~np.isfinite(ce[ci])) | (ce[ci] > TOL)).astype(float)
    y[li] = ((~np.isfinite(pe[li])) | (pe[li] > TOL)).astype(float)
    d = (x - y) / RET
    pooled = d.mean()
    f = f.assign(x=x, y=y, d=d)
    per = f.groupby('network_id').agg(n=('d','size'), dbar=('d','mean'), xbar=('x','mean'), ybar=('y','mean'))
    # per-network own-selection contrast
    rows=[]
    for nid, b in f.groupby('network_id'):
        kk = max(1, int(round(RET*len(b))))
        if kk > len(b): continue
        c2 = b['cert_score'].to_numpy(); l2 = b['length'].to_numpy()
        ce2 = b['cert_error'].to_numpy(); pe2 = b['policy_error'].to_numpy()
        c2i = np.argpartition(c2, kk-1)[:kk]; l2i = np.argpartition(l2, kk-1)[:kk]
        fr = lambda e: float(((~np.isfinite(e)) | (e > TOL)).mean())
        rows.append((nid, len(b), (fr(ce2[c2i]) - fr(pe2[l2i]))*100, fr(ce2[c2i])*100, fr(pe2[l2i])*100))
    pn = pd.DataFrame(rows, columns=['network_id','n_cases','contrast_pp','cert_fail_pp','len_fail_pp']).set_index('network_id')
    print('==', label, 'n_cases', n, 'n_net', f.network_id.nunique(), 'pooled pp', round(pooled*100,4))
    print('   within-network contrast pp: mean %.3f sd %.3f median %.3f min %.2f max %.2f  share<0 %.3f  exactly0 %d/%d' % (
        pn.contrast_pp.mean(), pn.contrast_pp.std(ddof=1), pn.contrast_pp.median(), pn.contrast_pp.min(), pn.contrast_pp.max(),
        (pn.contrast_pp<0).mean(), (pn.contrast_pp==0).sum(), len(pn)))
    print('   influence dbar pp: unweighted sd %.3f  weighted sd %.3f  case-weighted mean %.3f (check %.3f)' % (
        per.dbar.std(ddof=1)*100, np.sqrt(np.average((per.dbar-per.dbar.mean())**2, weights=per.n))*100, np.average(per.dbar, weights=per.n)*100, pooled*100))
    for col, nm in (('x','screen-fail'),('y','length-fail'),('d','contrast')):
        vals = f[col].to_numpy()
        grp = f.groupby('network_id')[col]
        sizes = grp.size().to_numpy(); means = grp.mean().to_numpy()
        N = len(vals); G = len(sizes); gm = vals.mean()
        per_mean = grp.mean().reindex(f['network_id'].to_numpy()).to_numpy()
        ssb = float((sizes*(means-gm)**2).sum()); ssw = float(((vals-per_mean)**2).sum())
        msb = ssb/(G-1); msw = ssw/(N-G)
        n0 = (N - (sizes**2).sum()/N)/(G-1)
        icc = (msb-msw)/(msb+(n0-1)*msw)
        nbar = N/G; deff = 1+(nbar-1)*icc
        print('   ICC(1) %-12s = %.4f  msb %.3e msw %.3e n0 %.1f nbar %.1f DEFF %.2f N_eff %.1f' % (nm, icc, msb, msw, n0, nbar, deff, G/deff))
    print('   provider case shares:', (f.groupby('provider').size()/n).round(4).to_dict())

dev = pd.read_parquet(ROOT/'results/v17_fitness/step4_ceiling/development_cases.parquet', columns=['network_id','provider','longest_run','abserr_policy']).reset_index(drop=True)
devc = pd.read_parquet(ROOT/'results/v17_fitness/step6_screen/development_certificates.parquet', columns=['certificate_bound','certificate_abs_error'])
w2 = pd.read_parquet(ROOT/'results/wrr_submission_ready/p0_07_wave2_ingest/p0_07_wave2_confirmation/wave2_cases.parquet', columns=['network_id','provider','longest_run','abserr_policy']).reset_index(drop=True)
w2c = pd.read_parquet(ROOT/'results/wrr_submission_ready/p0_07_wave2_ingest/p0_07_wave2_confirmation/wave2_certificates.parquet', columns=['certificate_bound','certificate_abs_error'])
fd = build(dev, devc, True); fw = build(w2, w2c, True)
analyse(fd, 'dev'); analyse(fw, 'wave2')
analyse(pd.concat([fd.assign(src='dev'), fw.assign(src='wave2')], ignore_index=True), 'pooled')

def pooled_implied(f, label):
    n=len(f); k=max(1,int(round(RET*n)))
    cs=f['cert_score'].to_numpy(); ln=f['length'].to_numpy()
    ce=f['cert_error'].to_numpy(); pe=f['policy_error'].to_numpy()
    ci=np.argpartition(cs,k-1)[:k]; li=np.argpartition(ln,k-1)[:k]
    x=np.zeros(n); y=np.zeros(n)
    x[ci]=((~np.isfinite(ce[ci]))|(ce[ci]>TOL)).astype(float); y[li]=((~np.isfinite(pe[li]))|(pe[li]>TOL)).astype(float)
    d=(x-y)/RET
    g=pd.DataFrame({'network_id':f['network_id'].to_numpy(),'d':d}).groupby('network_id')['d']
    n_g=g.size().to_numpy(dtype=float); dbar=g.mean().to_numpy()
    N=len(n_g); nbar=n_g.mean()
    v_emp=np.var(n_g*dbar, ddof=1)
    sd_pooled=np.sqrt(v_emp/N)/nbar
    print(f'   {label}: implied pooled sd from size-weighted influence = {sd_pooled*100:.3f} pp (nbar {nbar:.0f}, N {N})')
pooled_implied(fd,'dev'); pooled_implied(fw,'wave2')
