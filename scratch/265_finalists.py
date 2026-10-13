#!/usr/bin/env python3
"""Year-scoped panels for the finalist station-years."""

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
    ("lubw_rhein", "CXX359", 2006),
    ("lubw_rhein", "CXX359", 2018),
    ("foen_aare_aaregebiet", "2113", 2006),
    ("nve_basin_151", "151.29.0", 2018),
    ("arso_sava", "3850", 2018),
    ("chmi_odra", "0-203-1-294000", 2013),
    ("gkd_bayern_donau", "10056302", 2010),
    ("arso_kolpa", "4820", 2023),
]


def load(net: str, sid: str):
    for root in (
        ROOT / "results/development_v11/confirmation_daily_qc/networks",
        ROOT / "results/development_v11/second_confirmation/daily_qc/networks",
    ):
        p = root / net / "daily_wide_temperature.csv"
        if p.is_file():
            frame = pd.read_csv(p, index_col=0, parse_dates=True)
            return pd.to_numeric(frame[sid], errors="coerce")
    raise FileNotFoundError(net)


fig, axes = plt.subplots(len(SHOW), 2, figsize=(12, 2.1 * len(SHOW)),
                         gridspec_kw={"width_ratios": [1.35, 1.0]})
for row, (net, sid, year) in enumerate(SHOW):
    series = load(net, sid)
    idx = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
    block = series.reindex(idx)
    roll = block.rolling(W, min_periods=W).mean()
    truth = float(np.nanmax(roll.to_numpy()))
    ps = int(np.nanargmax(roll.to_numpy())) - (W - 1)
    ax = axes[row, 0]
    ax.plot(idx, block.to_numpy(), lw=1.0)
    ax.plot(idx, roll.to_numpy(), lw=1.2, color="C1")
    ax.axvspan(idx[ps], idx[ps + W - 1], color="C3", alpha=0.28)
    annual = float(block.mean())
    ax.axhline(annual, color="C2", lw=1.0, ls="--")
    ax.set_title(f"{net}/{sid}/{year}  peak {idx[ps].date()}..{idx[ps+W-1].date()}  "
                 f"annual {annual:.2f}  hot30 {truth:.2f}  amp {block.loc[idx.month==7].mean()-block.loc[idx.month==1].mean():.1f}",
                 fontsize=8)
    ax.set_xlim(idx[0], idx[-1])
    ax = axes[row, 1]
    hot, ann = [], []
    starts = range(0, len(idx) - W + 1)
    for s in starts:
        a = block.copy()
        a.iloc[s : s + W] = np.nan
        r = a.rolling(W, min_periods=W).mean().to_numpy()
        hot.append(np.nanmax(r) - truth)
        ann.append(a.dropna().mean() - annual)
    ax.plot([idx[s] for s in starts], hot, lw=1.1, label="hottest-30 error")
    ax.plot([idx[s] for s in starts], ann, lw=1.1, label="annual-mean error", color="C2")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlim(idx[0], idx[-1])
    ax.set_ylim(-6, 1.6)
    ax.legend(fontsize=6.5, loc="lower left")
    ax.grid(alpha=0.3)
fig.tight_layout()
out = ROOT / "scratch/265_finalists.png"
fig.savefig(out, dpi=115)
print(out)
