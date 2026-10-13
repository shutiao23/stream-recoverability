#!/usr/bin/env python3
"""Side-by-side look at the final four candidates, year-scoped."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path("/home/lzq/workspace/parttime/stream-recoverability")
W = 30
SHOW = [
    ("gkd_bayern_main", "24028000", 2010, "development"),
    ("gkd_bayern_isar", "16008007", 2010, "reserved"),
    ("chmi_labe", "0-203-1-245000", 2013, "reserved"),
    ("chmi_berounka", "0-203-1-198600", 2013, "reserved"),
]
ROOTS = [
    ROOT / "results/development_v11/confirmation_daily_qc/networks",
    ROOT / "results/development_v11/second_confirmation/daily_qc/networks",
]

fig, axes = plt.subplots(2, len(SHOW), figsize=(4.0 * len(SHOW), 6.0))
for col, (net, sid, year, role) in enumerate(SHOW):
    path = next(r / net / "daily_wide_temperature.csv" for r in ROOTS if (r / net).is_dir())
    frame = pd.read_csv(path, index_col=0, parse_dates=True)
    series = pd.to_numeric(frame[sid], errors="coerce")
    idx = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
    block = series.reindex(idx)
    roll = block.rolling(W, min_periods=W).mean()
    truth_h = float(np.nanmax(roll.to_numpy()))
    truth_m = float(block.mean())
    ps = int(np.nanargmax(roll.to_numpy())) - (W - 1)
    a = block.copy(); a.iloc[ps : ps + W] = np.nan
    b = block.copy(); b.loc[f"{year}-11-01":f"{year}-11-30"] = np.nan
    a_h = float(np.nanmax(a.rolling(W, min_periods=W).mean().to_numpy()))
    b_m = float(b.dropna().mean())
    ax = axes[0, col]
    ax.plot(idx, block.to_numpy(), lw=1.0, color="#2a78d6")
    ax.plot(idx, roll.to_numpy(), lw=1.1, color="#eb6834")
    ax.axvspan(idx[ps], idx[ps + W - 1], color="#eb6834", alpha=0.18)
    ax.axvspan(pd.Timestamp(f"{year}-11-01"), pd.Timestamp(f"{year}-11-30"), color="#1baf7a", alpha=0.18)
    ax.axhline(truth_m, color="#52514e", ls=":", lw=0.9)
    ax.axhline(truth_h, color="#eb6834", ls=":", lw=0.9)
    ax.set_title(f"{net}/{sid}  {year}  [{role}]\nhot30 {truth_h:.2f}  ann {truth_m:.2f}  "
                 f"peak {idx[ps].date()}..{idx[ps+W-1].date()}", fontsize=8)
    starts = list(range(0, len(idx) - W + 1))
    hot = []
    ann = []
    for s in starts:
        c = block.copy(); c.iloc[s : s + W] = np.nan
        r = c.rolling(W, min_periods=W).mean().to_numpy()
        hot.append(np.nanmax(r) - truth_h)
        ann.append(c.dropna().mean() - truth_m)
    ax = axes[1, col]
    ax.plot([idx[s] for s in starts], hot, lw=1.1, color="#2a78d6", label="hottest-30 error")
    ax.plot([idx[s] for s in starts], ann, lw=1.1, color="#1baf7a", label="annual-mean error")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_ylim(-6.2, 1.4)
    ax.legend(fontsize=7)
    ax.set_title(f"gap A: hot30 err {a_h - truth_h:+.2f} C, ann err {float(a.dropna().mean()) - truth_m:+.2f} C\n"
                 f"gap B: ann err {b_m - truth_m:+.2f} C", fontsize=8)
fig.tight_layout()
out = ROOT / "scratch/265_shortlist.png"
fig.savefig(out, dpi=110)
print(out)
