#!/usr/bin/env python3
"""Contact sheet of the top candidate station-years."""

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
    ("lubw_neckar", "CYY061", 2006),
    ("foen_aare_aaregebiet", "2113", 2006),
    ("gkd_bayern_main", "24028000", 2010),
    ("arso_kolpa", "4820", 2023),
    ("arso_sava", "3850", 2018),
    ("gkd_bayern_main", "24028000", 2018),
    ("chmi_odra", "0-203-1-294000", 2013),
]


def load(net: str, sid: str):
    for root in (
        ROOT / "results/development_v11/confirmation_daily_qc/networks",
        ROOT / "results/development_v11/second_confirmation/daily_qc/networks",
    ):
        p = root / net / "daily_wide_temperature.csv"
        if p.is_file():
            frame = pd.read_csv(p, index_col=0, parse_dates=True)
            return pd.to_numeric(frame[sid], errors="coerce"), p
    raise FileNotFoundError(net)


fig, axes = plt.subplots(len(SHOW), 2, figsize=(12, 2.0 * len(SHOW)), sharex="col")
for row, (net, sid, year) in enumerate(SHOW):
    series, path = load(net, sid)
    idx = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
    block = series.reindex(idx)
    roll = block.rolling(W, min_periods=W).mean()
    ax = axes[row, 0]
    ax.plot(idx, block.to_numpy(), lw=0.8)
    ax.plot(idx, roll.to_numpy(), lw=0.8, color="C1")
    if block.isna().any():
        ax.set_title(f"{net}/{sid}/{year} INCOMPLETE", color="red")
    else:
        ps = int(np.nanargmax(roll.to_numpy())) - (W - 1)
        ax.axvspan(idx[ps], idx[ps + W - 1], color="C3", alpha=0.25)
        ax.set_title(f"{net}/{sid}/{year} peak {idx[ps].date()}..{idx[ps + W - 1].date()}")
    ax = axes[row, 1]
    errs = []
    for s in range(0, len(idx) - W + 1):
        a = block.copy()
        a.iloc[s : s + W] = np.nan
        r = a.rolling(W, min_periods=W).mean().to_numpy()
        errs.append(np.nanmax(r) - np.nanmax(roll.to_numpy()))
    ax.plot(idx[: len(errs)], errs, lw=1.0)
    ax.set_ylim(-6.2, 0.4)
fig.tight_layout()
out = ROOT / "scratch/265_contact_sheet.png"
fig.savefig(out, dpi=110)
print(out)
