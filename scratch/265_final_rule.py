#!/usr/bin/env python3
"""Final selection rule, applied to the primary confirmation daily-QC root.

C1  primary root only: results/development_v11/confirmation_daily_qc/networks
C2  station QC verdict 'accepted' (no flags) and eligible for the network
C3  complete calendar year, no missing days
C4  clear seasonality: July mean - January mean >= 15 C
C5  truth hottest-30 window wholly inside June-August
C6  reserved (held-out) split role in the submission panel
C7  a 1-30 November gap leaves the hottest-30 exactly unchanged
rank: err(hottest-30 | 30 d gap over the peak window) - err(annual mean | gap B)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/lzq/workspace/parttime/stream-recoverability")
NETWORKS = ROOT / "results/development_v11/confirmation_daily_qc/networks"
W = 30


def main() -> int:
    prov = pd.read_csv(ROOT / "results/wrr_submission_ready/measurement_provenance_stations.csv")
    prov["split_role"] = prov["split_role"].fillna("(na)").astype(str)
    role = {
        (r.network_id, str(r.station_id)): r.split_role
        for r in prov.itertuples()
    }
    rows = []
    for net_dir in sorted(p for p in NETWORKS.iterdir() if p.is_dir()):
        path = net_dir / "daily_wide_temperature.csv"
        qc_path = net_dir / "network_qc.csv"
        if not (path.is_file() and qc_path.is_file()):
            continue
        qc = pd.read_csv(qc_path)
        good = {
            str(r.site_id): (str(r.verdict) == "accepted" and bool(r.eligible_for_network))
            for r in qc.itertuples()
        }
        frame = pd.read_csv(path, index_col=0, parse_dates=True)
        for sid in frame.columns:
            if not good.get(str(sid), False):
                continue
            if role.get((net_dir.name, str(sid)), "(na)") != "reserved":
                continue
            series = pd.to_numeric(frame[sid], errors="coerce")
            for year in range(1990, 2027):
                idx = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
                block = series.reindex(idx)
                if block.isna().any():
                    continue
                roll = block.rolling(W, min_periods=W).mean().to_numpy()
                truth_h = float(np.nanmax(roll))
                truth_m = float(block.mean())
                ps = int(np.nanargmax(roll)) - (W - 1)
                peak = idx[ps : ps + W]
                if not set(peak.month).issubset({6, 7, 8}):
                    continue
                if (block.loc[block.index.month == 7].mean()
                        - block.loc[block.index.month == 1].mean()) < 15.0:
                    continue
                a = block.copy(); a.iloc[ps : ps + W] = np.nan
                a_h = float(np.nanmax(a.rolling(W, min_periods=W).mean().to_numpy()))
                a_m = float(a.dropna().mean())
                b = block.copy(); b.loc[f"{year}-11-01":f"{year}-11-30"] = np.nan
                b_h = float(np.nanmax(b.rolling(W, min_periods=W).mean().to_numpy()))
                b_m = float(b.dropna().mean())
                if abs(b_h - truth_h) > 1e-9:
                    continue
                rows.append({
                    "network": net_dir.name, "station": str(sid), "year": year,
                    "peak_start": str(peak[0].date()), "peak_end": str(peak[-1].date()),
                    "truth_annual": truth_m, "truth_hottest30": truth_h,
                    "errA_hottest30": abs(a_h - truth_h), "errA_annual": abs(a_m - truth_m),
                    "errB_annual": abs(b_m - truth_m),
                    "contrast": abs(a_h - truth_h) - abs(b_m - truth_m),
                    "ratio": abs(a_h - truth_h) / abs(b_m - truth_m),
                })
    out = pd.DataFrame(rows).sort_values(["contrast", "ratio"], ascending=False)
    out.to_csv(ROOT / "scratch/265_final_rule.csv", index=False)
    print(f"survivors: {len(out)}")
    cols = ["network", "station", "year", "peak_start", "peak_end", "truth_annual",
            "truth_hottest30", "errA_hottest30", "errA_annual", "errB_annual", "ratio"]
    print(out.head(12)[cols].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
