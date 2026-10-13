"""Independent recomputation of every headline number from the written artifacts."""
import sys, json
from pathlib import Path
ROOT = Path("/home/lzq/workspace/parttime/stream-recoverability")
sys.path.insert(0, str(ROOT / "src"))
import numpy as np, pandas as pd
from sklearn.metrics import roc_auc_score
from stream_recoverability.experiments.v17_fitness.paths import STEP3_CASES
from stream_recoverability.experiments.v17_fitness.policies import information_conditioned_choice, gather

print("=" * 30, "A. cold endpoint")
cases = pd.read_parquet(STEP3_CASES / "cases.parquet")
cases = cases.loc[cases["split_role"].eq("development")].reset_index(drop=True)
sup = pd.read_parquet(ROOT / "results/wrr_submission_ready/amendments/winter_regulatory/cold_support_cases.parquet")
m = cases.merge(sup, on=["network_id","station_id","year","realization_id"], how="inner", suffixes=("","_regen"))
err = gather(m, information_conditioned_choice(m), prefix="abserr_coldest30_")
tol = 0.5
lab = (err > tol).astype(float); keep = np.isfinite(err)
n = int(keep.sum())
print(f"n={n}, networks={m.loc[keep,'network_id'].nunique()}, base_rate={lab[keep].mean():.4f}")
for col, sign in [("cold_window_overlap", 1), ("cold_season_observed_fraction", -1), ("longest_run", 1), ("peak_overlap", 1), ("warm_observed_fraction", -1)]:
    v = sign * pd.to_numeric(m[col], errors="coerce").to_numpy(float)[keep]
    a = roc_auc_score(lab[keep], v)
    order = np.argsort(v, kind="mergesort"); k = int(round(0.7 * n))
    rate = float((err[keep][order[:k]] > tol).mean())
    print(f"  {col:32s} AUC={a:.4f}  rate@70={rate:.4f}")

print("=" * 30, "B. sine phase")
sc = pd.read_parquet(ROOT / "results/wrr_submission_ready/amendments/winter_regulatory/sine_phase_cases.parquet")
for proto in ("repaired", "observed_days_only"):
    b = sc.loc[sc["protocol"].eq(proto)]
    low = b.loc[b["amplitude_to_noise"] < 1.0]
    hi = b.loc[b["amplitude_to_noise"] >= 4.5]
    print(f"  {proto:18s} n={len(b)} below1={len(low)} median_err_below1={low['abs_phase_error_days'].median():.1f} "
          f"consq_below1={low['consequential'].mean():.3f} | retained@4.5={len(hi)} ({len(hi)/len(b):.1%}) "
          f"median_err_retained={hi['abs_phase_error_days'].median():.2f}")

print("=" * 30, "C. 7-DADMax")
c = pd.read_csv(ROOT / "results/wrr_submission_ready/amendments/regulatory_daily_max/dadmax_comparison.csv")
d = (c["dadmax7"] - c["hottest7_mean"])
print(f"  n={len(c)} stations={c['site_id'].nunique()} years={c['year'].min()}-{c['year'].max()}")
print(f"  diff mean={d.mean():.3f} median={d.median():.3f} sd={d.std(ddof=1):.3f} q05={d.quantile(.05):.3f} q95={d.quantile(.95):.3f} min={d.min():.3f} share_neg={(d<0).mean():.4f}")
for t in (16.0, 18.0, 20.0):
    em = c["hottest7_mean"] > t; ex = c["dadmax7"] > t
    print(f"  T={t:.0f}: exceed_dadmax={int(ex.sum())} exceed_mean={int(em.sum())} changes={int((em!=ex).sum())} "
          f"missed={int((~em & ex).sum())} false={int((em & ~ex).sum())} missed_share={(~em & ex).sum()/max(1,ex.sum()):.4f}")
q = np.quantile(c["hottest7_mean"], 1 - (c["dadmax7"] > 20).mean())
print(f"  equal-count threshold for T=20: {q:.3f}")

print("=" * 30, "recorded in summary.json")
sA = json.load(open(ROOT / "results/wrr_submission_ready/amendments/winter_regulatory/summary.json"))
print("  A coldest30 AUC cold_window:", [round(r["auc_cold_window_overlap"],4) for r in sA["results"] if r["metric"]=="coldest30" and r["tolerance_rule"]=="literal_0.5C"])
sC = json.load(open(ROOT / "results/wrr_submission_ready/amendments/regulatory_daily_max/summary.json"))
print("  C median diff recorded:", round(sC["paired"]["difference_c"]["median"],3), "| n:", sC["paired"]["n_station_years_analysis"])
print("  C availability:", sC["availability"]["n_stations_with_daily_max_00001"], "of", sC["availability"]["n_stations_requested"])
print("  C ingest match:", sC["download_matches_sealed_panel_mean_files"]["max_abs_difference_c"], sC["download_matches_sealed_panel_mean_files"]["n_common_rows"])
