#!/usr/bin/env python3
"""Scan confirmation daily QC panels for a clean illustration station-year."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/lzq/workspace/parttime/stream-recoverability")
ROOTS = [
    ROOT / "results/development_v11/confirmation_daily_qc/networks",
    ROOT / "results/development_v11/second_confirmation/daily_qc/networks",
]

WINDOW = 30


def hottest30(series: pd.Series) -> float:
    rolled = series.rolling(WINDOW, min_periods=WINDOW).mean()
    finite = rolled.to_numpy(dtype=float)
    if not np.isfinite(finite).any():
        return float("nan")
    return float(np.nanmax(finite))


def peak_start(series: pd.Series) -> int:
    """Position of the first day of the window achieving the maximum.

    ``rolling(i)`` is the trailing mean of ``series[i-29:i+1]``, so the window
    begins at ``argmax - (WINDOW - 1)``.
    """

    rolled = series.rolling(WINDOW, min_periods=WINDOW).mean().to_numpy(dtype=float)
    return int(np.nanargmax(rolled)) - (WINDOW - 1)


def main() -> int:
    rows = []
    for root in ROOTS:
        if not root.is_dir():
            continue
        for net_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            path = net_dir / "daily_wide_temperature.csv"
            if not path.is_file():
                continue
            frame = pd.read_csv(path, index_col=0, parse_dates=True)
            for sid in frame.columns:
                series = pd.to_numeric(frame[sid], errors="coerce")
                for year in range(1990, 2027):
                    idx = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
                    block = series.reindex(idx)
                    if block.isna().any():
                        continue
                    truth_h = hottest30(block)
                    truth_m = float(block.mean())
                    ps = peak_start(block)
                    peak_dates = idx[ps : ps + WINDOW]
                    # gap A: exactly the truth peak window
                    a = block.copy()
                    a.iloc[ps : ps + WINDOW] = np.nan
                    a_h = hottest30(a)
                    a_m = float(a.dropna().mean())
                    # gap B: a late-autumn window, 1 Nov - 30 Nov
                    b_start = int(np.where(idx == pd.Timestamp(f"{year}-11-01"))[0][0])
                    b = block.copy()
                    b.iloc[b_start : b_start + WINDOW] = np.nan
                    b_h = hottest30(b)
                    b_m = float(b.dropna().mean())
                    # seasonality diagnostics
                    jul = block.loc[block.index.month == 7].mean()
                    jan = block.loc[block.index.month == 1].mean()
                    rows.append(
                        {
                            "root": root.parent.parent.name,
                            "network": net_dir.name,
                            "station": sid,
                            "year": year,
                            "path": str(path.relative_to(ROOT)),
                            "truth_annual": truth_m,
                            "truth_hottest30": truth_h,
                            "peak_start": str(idx[ps].date()),
                            "peak_end": str(peak_dates[-1].date()),
                            "errA_hottest30": abs(a_h - truth_h),
                            "errA_annual": abs(a_m - truth_m),
                            "errB_hottest30": abs(b_h - truth_h),
                            "errB_annual": abs(b_m - truth_m),
                            "amplitude_jul_jan": float(jul - jan),
                            "sd": float(block.std()),
                            "n": int(block.notna().sum()),
                        }
                    )
    out = pd.DataFrame(rows)
    out.to_csv(ROOT / "scratch/265_candidate_scan.csv", index=False)
    print(f"candidate station-years: {len(out)}")
    if out.empty:
        return 1
    # rank: big gap-A hottest error, small gap-B annual error, clear seasonality
    out["score"] = out["errA_hottest30"] - 6.0 * out["errB_annual"]
    keep = out.loc[
        (out["errA_hottest30"] > 2.0)
        & (out["errB_annual"] < 0.35)
        & (out["errB_hottest30"] < 0.1)
        & (out["amplitude_jul_jan"] > 8.0)
    ].sort_values("score", ascending=False)
    print(keep.head(30).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
