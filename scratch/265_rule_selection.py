#!/usr/bin/env python3
"""Apply the preregistered selection rule to the candidate scan.

Rule, in order:
  1. complete calendar year in a confirmation daily-QC panel;
  2. clear seasonality: July mean - January mean >= 15 C;
  3. the truth hottest-30 window lies wholly inside June-August;
  4. a designed 1-30 November gap leaves the hottest-30 mean exact
     (the realised peak is intact);
  5. among survivors, maximise err(hottest_30 | gap over the peak window)
     minus err(annual mean | gap in late autumn).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/lzq/workspace/parttime/stream-recoverability")
W = 30


def main() -> int:
    rows = []
    for root_name, root in (
        ("development_v11", ROOT / "results/development_v11/confirmation_daily_qc/networks"),
        ("second_confirmation", ROOT / "results/development_v11/second_confirmation/daily_qc/networks"),
    ):
        for net_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            path = net_dir / "daily_wide_temperature.csv"
            if not path.is_file():
                continue
            frame = pd.read_csv(path, index_col=0, parse_dates=True)
            for sid in frame.columns:
                series = pd.to_numeric(frame[sid], errors="coerce")
                for year in range(1990, 2027):
                    idx = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
                    if not pd.Timestamp(f"{year}-01-01") in series.index:
                        continue
                    block = series.reindex(idx)
                    if block.isna().any() or len(block) != len(idx):
                        continue
                    roll = block.rolling(W, min_periods=W).mean().to_numpy()
                    truth_h = float(np.nanmax(roll))
                    truth_m = float(block.mean())
                    ps = int(np.nanargmax(roll)) - (W - 1)
                    peak = idx[ps : ps + W]
                    if not set(peak.month).issubset({6, 7, 8}):
                        continue
                    if not (block.loc[block.index.month == 7].mean()
                            - block.loc[block.index.month == 1].mean()) >= 15.0:
                        continue
                    a = block.copy(); a.iloc[ps : ps + W] = np.nan
                    a_h = float(np.nanmax(a.rolling(W, min_periods=W).mean().to_numpy()))
                    a_m = float(a.dropna().mean())
                    b0 = int(np.argmax(np.asarray(idx >= pd.Timestamp(f"{year}-11-01"))))
                    b = block.copy(); b.iloc[b0 : b0 + W] = np.nan
                    b_h = float(np.nanmax(b.rolling(W, min_periods=W).mean().to_numpy()))
                    b_m = float(b.dropna().mean())
                    if not (abs(b_h - truth_h) < 1e-9):
                        continue
                    rows.append({
                        "root": root_name, "network": net_dir.name, "station": sid, "year": year,
                        "path": str(path.relative_to(ROOT)),
                        "truth_annual": truth_m, "truth_hottest30": truth_h,
                        "peak_start": str(peak[0].date()), "peak_end": str(peak[-1].date()),
                        "gapA_hottest30": a_h, "gapA_annual": a_m,
                        "gapB_hottest30": b_h, "gapB_annual": b_m,
                        "errA_hottest30": abs(a_h - truth_h), "errA_annual": abs(a_m - truth_m),
                        "errB_hottest30": abs(b_h - truth_h), "errB_annual": abs(b_m - truth_m),
                        "contrast": abs(a_h - truth_h) - abs(b_m - truth_m),
                        "ratio": abs(a_h - truth_h) / abs(b_m - truth_m) if b_m != truth_m else np.inf,
                    })
    out = pd.DataFrame(rows).sort_values("contrast", ascending=False)
    out.to_csv(ROOT / "scratch/265_rule_selection.csv", index=False)
    print(f"survivors of the rule: {len(out)}")
    cols = ["root", "network", "station", "year", "peak_start", "peak_end", "truth_annual",
            "truth_hottest30", "errA_hottest30", "errA_annual", "errB_hottest30",
            "errB_annual", "ratio"]
    print(out.head(15)[cols].to_string(index=False))
    print()
    print("primary root only:")
    prim = out.loc[out["root"].eq("development_v11")]
    print(prim.head(10)[cols].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
