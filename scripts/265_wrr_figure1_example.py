#!/usr/bin/env python3
"""Figure 1, data-driven: one real station-year, two equal-length gaps, two statistics.

Adversarial finding F21 asked for a data-driven opening figure. The old figure 1
is a draw.io schematic that mixes definitions, results and exploratory claims.
This script draws the same mechanism on one real annual record:

  (a) the complete daily series of one station-year, with two designed 30-day
      gaps marked at different positions (one over the peak window that achieves
      the hottest 30-day mean, one in late autumn);
  (b) what each gap does to an annual mean and to a hottest 30-day mean, each
      estimate against the complete-record truth, errors annotated in degrees C;
  (c) a length-matched sweep -- every 30-day gap start day of the year -- so the
      reader sees that position, not length, decides the error.

Data contract
-------------
The curve is a real station-year read from the study panel's daily wide
temperature table; nothing is simulated, imputed or hand-entered. The statistics
are computed with the manuscript's own definitions
(``stream_recoverability.experiments.wrr_revision.thermal``):

  annual mean            mean of the days of the calendar year;
  hottest 30-day mean    maximum of the 30-day rolling mean, over windows that
                         are fully observed (``min_periods = window``).

Selection rule (fixed, applied by ``select_station_year``)
----------------------------------------------------------
C1  primary confirmation daily-QC root
    (``.../confirmation_daily_qc/networks``), the study panel;
C2  station QC verdict ``accepted`` (no flags) and eligible for its network;
C3  complete calendar year, no missing day;
C4  clear seasonality: July mean minus January mean >= 15 degC;
C5  the truth hottest-30 window lies wholly inside June-August;
C6  reserved (held-out) split role, so no station used to fit anything;
C7  the fixed late-autumn gap (1-30 November) leaves the hottest 30-day mean
    exactly unchanged, i.e. the realised peak survives it.
Among the survivors, take the station-year with the largest margin
err(hottest 30-day mean | 30-day gap over the peak window)
  - err(annual mean | 30-day gap in late autumn),
which is the contrast the figure exists to show. The winner and the survivor
count are written next to the figure, so the choice is reproducible rather than
hand-picked.

Outputs (write scope: figures/wrr/ only)
----------------------------------------
  figures/wrr/f1_example.pdf          vector, journal column width
  figures/wrr/f1_example.png          raster preview, 300 dpi
  figures/wrr/f1_example_data.json    identity, truth, gap estimates, errors
  figures/wrr/f1_example_sweep.csv    the panel (c) sweep, every start day
  figures/wrr/f1_example_caption.md   caption material, generated from the run
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.dates import DateFormatter, MonthLocator  # noqa: E402

from stream_recoverability.experiments.wrr_revision.paths import (  # noqa: E402
    FIRST_PANEL_ROOT,
    HOTTEST_WINDOW_DAYS,
)
from stream_recoverability.experiments.wrr_revision.thermal import (  # noqa: E402
    annual_hottest_consecutive_mean,
    calendar_year_is_complete,
    hottest_consecutive_mean,
    reindex_calendar_year,
)
from stream_recoverability.plotting.journal import (  # noqa: E402
    COLUMN_INCHES,
    rc_overrides,
)

# The deliverable is drawn at the printed column width, so the journal type scale
# applies unconditionally rather than behind the usual environment switch.
os.environ.setdefault("WRR_JOURNAL_FIGURES", "1")

FIGURES = ROOT / "figures" / "wrr"
PROVENANCE = ROOT / "results" / "wrr_submission_ready" / "measurement_provenance_stations.csv"
PRIOR_ACCESS = (
    ROOT / "results" / "wrr_submission_ready" / "prior_access_ledger_reserved_networks.csv"
)
NAME = "f1_example"

GAP_DAYS = 30
GAP_B_FIRST, GAP_B_LAST = "11-01", "11-30"  # late autumn, fixed by the rule
Y_TOP = 1.15  # top of panel (c), leaves room for the A/B markers
PEAK_MONTHS = {6, 7, 8}
MIN_JULY_JANUARY_RANGE_C = 15.0
YEAR_RANGE = range(1990, 2027)

# Categorical slots and surface from scripts/188_v17_figures.py and
# scripts/204_v17_figures_q1.py. Orange reads as the statistic supported on the
# peak window, blue as the annual mean and the cool-season placement.
SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
FAINT = "#c9c8c4"
BLUE, ORANGE = "#2a78d6", "#eb6834"

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "font.size": 8.5,
        "axes.labelsize": 8.5,
        "axes.titlesize": 9.5,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK_2,
        "text.color": INK,
        "xtick.color": INK_2,
        "ytick.color": INK_2,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "axes.axisbelow": True,
        "legend.frameon": False,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "lines.linewidth": 2.0,
        # Type 42 outlines keep the PDF free of Type 3 fonts, which AGU does not accept.
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
)
plt.rcParams.update(rc_overrides())


# --------------------------------------------------------------------------- #
# selection
# --------------------------------------------------------------------------- #
def _split_roles() -> dict[tuple[str, str], str]:
    table = pd.read_csv(PROVENANCE)
    table["split_role"] = table["split_role"].fillna("(na)").astype(str)
    return {
        (str(r.network_id), str(r.station_id)): r.split_role for r in table.itertuples()
    }


def _qc_verdicts(network_dir: Path) -> dict[str, tuple[str, bool]]:
    table = pd.read_csv(network_dir / "network_qc.csv")
    return {
        str(r.site_id): (str(r.verdict), bool(r.eligible_for_network)) for r in table.itertuples()
    }


def network_metadata(network_id: str) -> dict:
    """Provider, river group, panel window and recorded prior use of a network."""

    summary = pd.read_csv(FIRST_PANEL_ROOT / network_id / "network_qc_summary.csv").iloc[0]
    out = {
        "provider": str(summary["provider"]),
        "river_group": str(summary["river_group"]),
        "overlap_start": str(summary["overlap_start"]),
        "overlap_end": str(summary["overlap_end"]),
        "prior_access_bucket": "(not recorded)",
    }
    if PRIOR_ACCESS.is_file():
        ledger = pd.read_csv(PRIOR_ACCESS).set_index("network_id")
        if network_id in ledger.index:
            out["prior_access_bucket"] = str(ledger.loc[network_id, "prior_access_bucket"])
    return out


def _statistics(block: pd.Series) -> tuple[float, float]:
    """(annual mean, hottest 30-day mean) on whatever days ``block`` holds.

    Both are the manuscript's observed-only estimators, and both are computed on
    the calendar-year series with the gap left as NA -- never on the gap days
    deleted. Deleting them would make the day before a gap adjacent to the day
    after it and let a 30-day window bridge the gap, which is exactly the
    mistake the figure is about. ``annual_hottest_consecutive_mean`` cannot be
    used here: a designed gap leaves the calendar year incomplete by
    construction, so the annual wrapper returns NaN.
    """

    if block.notna().sum() < HOTTEST_WINDOW_DAYS:
        return float("nan"), float("nan")
    return float(block.mean()), hottest_consecutive_mean(block)


def select_station_year() -> dict:
    """Apply C1-C7 and return the winner plus the screening counts."""

    roles = _split_roles()
    candidates: list[dict] = []
    n_networks = 0
    n_complete_years = 0

    for network_dir in sorted(p for p in FIRST_PANEL_ROOT.iterdir() if p.is_dir()):
        panel = network_dir / "daily_wide_temperature.csv"
        qc = network_dir / "network_qc.csv"
        if not (panel.is_file() and qc.is_file()):
            continue
        n_networks += 1
        verdicts = _qc_verdicts(network_dir)
        frame = pd.read_csv(panel, index_col=0, parse_dates=True)
        for station in frame.columns:
            station = str(station)
            verdict, eligible = verdicts.get(station, ("missing", False))
            if not (verdict == "accepted" and eligible):  # C2
                continue
            if roles.get((network_dir.name, station), "(na)") != "reserved":  # C6
                continue
            series = pd.to_numeric(frame[station], errors="coerce")
            for year in YEAR_RANGE:
                if pd.Timestamp(f"{year}-01-01") not in series.index:
                    continue
                if not calendar_year_is_complete(series, year):  # C3
                    continue
                n_complete_years += 1
                block = reindex_calendar_year(series, year)
                rolled = block.rolling(HOTTEST_WINDOW_DAYS, min_periods=HOTTEST_WINDOW_DAYS).mean()
                truth_hottest = annual_hottest_consecutive_mean(block, year)
                truth_annual = float(block.mean())
                end = int(np.nanargmax(rolled.to_numpy()))  # trailing window end
                start = end - (HOTTEST_WINDOW_DAYS - 1)
                peak = block.index[start : end + 1]
                if not set(peak.month).issubset(PEAK_MONTHS):  # C5
                    continue
                july = block.loc[block.index.month == 7].mean()
                january = block.loc[block.index.month == 1].mean()
                if (july - january) < MIN_JULY_JANUARY_RANGE_C:  # C4
                    continue

                gap_a = block.copy()
                gap_a.iloc[start : end + 1] = np.nan
                a_annual, a_hottest = _statistics(gap_a)

                gap_b = block.copy()
                gap_b.loc[f"{year}-{GAP_B_FIRST}":f"{year}-{GAP_B_LAST}"] = np.nan
                b_annual, b_hottest = _statistics(gap_b)

                if abs(b_hottest - truth_hottest) > 1e-9:  # C7
                    continue

                candidates.append(
                    {
                        "network_id": network_dir.name,
                        "station_id": station,
                        "year": int(year),
                        "panel_path": str(panel.relative_to(ROOT)),
                        "truth_annual_c": truth_annual,
                        "truth_hottest_30_c": truth_hottest,
                        "peak_start": str(peak[0].date()),
                        "peak_end": str(peak[-1].date()),
                        "gap_a_annual_c": a_annual,
                        "gap_a_hottest_30_c": a_hottest,
                        "gap_b_annual_c": b_annual,
                        "gap_b_hottest_30_c": b_hottest,
                        "err_a_hottest_30_c": abs(a_hottest - truth_hottest),
                        "err_b_annual_c": abs(b_annual - truth_annual),
                        "july_minus_january_c": float(july - january),
                    }
                )

    if not candidates:
        raise SystemExit("no station-year satisfies the selection rule")
    frame = pd.DataFrame(candidates)
    frame["contrast_c"] = frame["err_a_hottest_30_c"] - frame["err_b_annual_c"]
    frame = frame.sort_values(["contrast_c", "err_a_hottest_30_c"], ascending=False)
    winner = frame.iloc[0].to_dict()
    winner["n_networks_scanned"] = n_networks
    winner["n_complete_station_years"] = n_complete_years
    winner["n_rule_survivors"] = len(frame)
    winner["split_role"] = "reserved"
    winner["qc_verdict"] = "accepted"
    winner["candidates"] = frame
    return winner


# --------------------------------------------------------------------------- #
# figure
# --------------------------------------------------------------------------- #
def _gap_frames(block: pd.Series, row: dict) -> tuple[pd.Series, pd.Series]:
    """The two designed gaps as boolean masks on the calendar year."""

    a = pd.Series(False, index=block.index)
    a.loc[row["peak_start"] : row["peak_end"]] = True
    b = pd.Series(False, index=block.index)
    b.loc[f"{row['year']}-{GAP_B_FIRST}" : f"{row['year']}-{GAP_B_LAST}"] = True
    return a, b


def _sweep(block: pd.Series) -> pd.DataFrame:
    """Length-matched sweep: every 30-day gap start of the year."""

    truth_annual = float(block.mean())
    truth_hottest = annual_hottest_consecutive_mean(block, int(block.index[0].year))
    rows = []
    for start in range(len(block) - GAP_DAYS + 1):
        gapped = block.copy()
        gapped.iloc[start : start + GAP_DAYS] = np.nan
        annual, hottest = _statistics(gapped)
        rows.append(
            {
                "gap_start": block.index[start],
                "hottest_30_error_c": hottest - truth_hottest,
                "annual_mean_error_c": annual - truth_annual,
            }
        )
    return pd.DataFrame(rows)


def _signed(value: float, digits: int = 2) -> str:
    """Signed number with the typographic minus matplotlib uses in tick labels."""

    return f"{value:+.{digits}f}".replace("-", "\u2212")


def _annotate(ax, text: str, xy, xytext, colour, *, ha="left"):
    """Small label with a leader line to the thing it names."""

    ax.annotate(
        text,
        xy=xy,
        xytext=xytext,
        fontsize=6.0,
        color=colour,
        ha=ha,
        va="center",
        arrowprops={"arrowstyle": "-", "color": colour, "lw": 0.7, "shrinkA": 0, "shrinkB": 2},
    )


def _panel_a(ax, block: pd.Series, row: dict, gap_a: pd.Series, gap_b: pd.Series) -> None:
    dates = block.index
    observed = block.where(~(gap_a | gap_b))
    rolled = observed.rolling(HOTTEST_WINDOW_DAYS, min_periods=HOTTEST_WINDOW_DAYS).mean()

    ax.axvspan(dates[gap_a][0], dates[gap_a][-1], color=ORANGE, alpha=0.15, lw=0, zorder=0)
    ax.axvspan(dates[gap_b][0], dates[gap_b][-1], color=BLUE, alpha=0.13, lw=0, zorder=0)
    ax.plot(dates, block.to_numpy(), color=FAINT, lw=0.7, zorder=1)
    ax.plot(dates, observed.to_numpy(), color=INK_2, lw=0.8, zorder=2)
    ax.plot(dates, rolled.to_numpy(), color=ORANGE, lw=1.4, zorder=3)

    ax.axhline(row["truth_hottest_30_c"], color=ORANGE, ls=(0, (1, 2)), lw=1.0, zorder=2)
    ax.axhline(row["truth_annual_c"], color=BLUE, ls=(0, (1, 2)), lw=1.0, zorder=2)

    top = float(np.nanmax(block.to_numpy()))
    ax.set_ylim(min(float(block.min()) - 1.5, 0.0), top + 5.0)
    ax.set_xlim(dates[0], dates[-1])
    ax.set_ylabel("water temperature (°C)")
    ax.set_xlabel(
        f"{row['network_id']} station {row['station_id']}, calendar year {row['year']} "
        f"({int(block.notna().sum())} complete days)",
        fontsize=6.0,
        labelpad=2.0,
    )
    ax.set_title("a  One real station-year with two 30-day gaps", loc="left", pad=6)
    ax.xaxis.set_major_locator(MonthLocator(bymonth=range(1, 13)))
    ax.xaxis.set_major_formatter(DateFormatter("%b"))
    ax.grid(axis="x", visible=False)

    ax.text(
        dates[3],
        row["truth_hottest_30_c"] + 0.9,
        f"hottest 30-day mean {row['truth_hottest_30_c']:.2f} °C",
        fontsize=6.0,
        color=ORANGE,
        va="bottom",
    )
    ax.text(
        dates[3],
        row["truth_annual_c"] + 0.9,
        f"annual mean {row['truth_annual_c']:.2f} °C",
        fontsize=6.0,
        color=BLUE,
        va="bottom",
    )
    _annotate(
        ax,
        "gap A: over the peak window",
        (dates[gap_a][len(dates[gap_a]) // 2], top + 0.5),
        (dates[gap_a][0] - pd.Timedelta(days=6), top + 3.2),
        ORANGE,
        ha="right",
    )
    _annotate(
        ax,
        "gap B: late autumn",
        (dates[gap_b][len(dates[gap_b]) // 2], float(block.loc[dates[gap_b]].max()) + 0.6),
        (dates[gap_b][len(dates[gap_b]) // 2], top + 0.5),
        BLUE,
        ha="center",
    )


def _panel_b(ax, row: dict, *, which: str) -> None:
    if which == "annual":
        truth = row["truth_annual_c"]
        est_a, est_b = row["gap_a_annual_c"], row["gap_b_annual_c"]
        ylabel = "annual mean (°C)"
        ticks = [9.0, 10.0, 11.0]
    else:
        truth = row["truth_hottest_30_c"]
        est_a, est_b = row["gap_a_hottest_30_c"], row["gap_b_hottest_30_c"]
        ylabel = "hottest 30-day mean (°C)"
        ticks = [18.0, 20.0, 22.0]

    ax.axhline(truth, color=INK_2, ls=(0, (1, 2)), lw=0.9, zorder=1)
    ax.vlines(1, est_a, truth, color=ORANGE, lw=1.0, zorder=2)
    ax.vlines(2, est_b, truth, color=BLUE, lw=1.0, zorder=2)
    ax.plot([0], [truth], marker="o", ms=5.2, mfc=SURFACE, mec=INK, mew=1.0, ls="none", zorder=4)
    ax.plot([1], [est_a], marker="o", ms=4.6, color=ORANGE, ls="none", zorder=4)
    ax.plot([2], [est_b], marker="o", ms=4.6, color=BLUE, ls="none", zorder=4)

    span = max(truth, est_a, est_b) - min(truth, est_a, est_b)
    pad = max(0.12 * max(span, 0.5), 0.18)
    ax.set_ylim(min(truth, est_a, est_b) - 2.8 * pad, max(truth, est_a, est_b) + 3.0 * pad)
    ax.set_yticks(ticks)
    ax.set_ylabel(ylabel, fontsize=7.0)
    ax.set_xticks(
        [0, 1, 2], ["complete\nrecord", "gap A\npeak window", "gap B\nlate autumn"]
    )
    ax.tick_params(axis="x", labelsize=6.0)
    ax.grid(axis="x", visible=False)
    ax.set_xlim(-0.6, 2.6)

    ax.text(0.0, truth + 0.45 * pad, f"{truth:.2f}", fontsize=6.0, color=INK_2, ha="center")
    for x, value, colour in ((1.0, est_a, ORANGE), (2.0, est_b, BLUE)):
        above = value >= truth
        ax.text(
            x,
            value + (0.8 * pad if above else -0.8 * pad),
            f"{value:.2f}\n{_signed(value - truth)} °C",
            fontsize=6.0,
            color=colour,
            ha="center",
            va="bottom" if above else "top",
        )


def _panel_c(ax, sweep: pd.DataFrame, row: dict, gap_a: pd.Series) -> None:
    starts = sweep["gap_start"]
    lo = gap_a.index[gap_a][0] - pd.Timedelta(days=GAP_DAYS - 1)
    hi = gap_a.index[gap_a][-1] + pd.Timedelta(days=GAP_DAYS - 1)
    ax.axvspan(lo, hi, color=ORANGE, alpha=0.10, lw=0, zorder=0)
    ax.axhline(0.0, color=INK_2, lw=0.7, zorder=1)
    ax.plot(starts, sweep["annual_mean_error_c"], color=BLUE, lw=1.1, zorder=2)
    ax.plot(starts, sweep["hottest_30_error_c"], color=ORANGE, lw=1.4, zorder=3)

    for when, colour, label in (
        (row["peak_start"], ORANGE, "A"),
        (f"{row['year']}-{GAP_B_FIRST}", BLUE, "B"),
    ):
        ax.axvline(pd.Timestamp(when), color=colour, ls=(0, (2, 2)), lw=0.9, zorder=1)
        ax.text(
            pd.Timestamp(when),
            Y_TOP,
            label,
            fontsize=6.2,
            color=colour,
            ha="center",
            va="bottom",
        )

    ax.set_ylim(-4.6, Y_TOP)
    ax.set_ylabel("error in the estimate (°C)")
    ax.set_xlabel("first day of the 30-day gap (each point is one gap of the same length)")
    ax.set_title("c  Same gap length, every position", loc="left", pad=6)
    ax.xaxis.set_major_locator(MonthLocator(bymonth=(1, 3, 5, 7, 9, 11)))
    ax.xaxis.set_major_formatter(DateFormatter("%b"))
    ax.grid(axis="x", visible=False)
    ax.set_xlim(starts.iloc[0], starts.iloc[-1])

    ax.text(
        lo + pd.Timedelta(days=3),
        0.62,
        "gaps that reach the peak window",
        fontsize=6.0,
        color=ORANGE,
        ha="left",
        va="bottom",
    )
    handles = [
        plt.Line2D([], [], color=ORANGE, lw=1.4, label="hottest 30-day mean"),
        plt.Line2D([], [], color=BLUE, lw=1.1, label="annual mean"),
    ]
    ax.legend(handles=handles, loc="lower left", fontsize=6.2, handlelength=1.4)


def build_figure(block: pd.Series, row: dict, sweep: pd.DataFrame) -> plt.Figure:
    gap_a, gap_b = _gap_frames(block, row)
    figure = plt.figure(figsize=(COLUMN_INCHES, 5.2))
    grid = figure.add_gridspec(
        3, 2, height_ratios=[1.24, 1.0, 1.0], hspace=0.52, wspace=0.46,
        left=0.105, right=0.985, top=0.955, bottom=0.10,
    )
    ax_a = figure.add_subplot(grid[0, :])
    _panel_a(ax_a, block, row, gap_a, gap_b)

    ax_b1 = figure.add_subplot(grid[1, 0])
    _panel_b(ax_b1, row, which="annual")
    ax_b1.set_title("b  What each gap does to two statistics", loc="left", pad=6)

    ax_b2 = figure.add_subplot(grid[1, 1])
    _panel_b(ax_b2, row, which="hottest")

    ax_c = figure.add_subplot(grid[2, :])
    _panel_c(ax_c, sweep, row, gap_a)
    return figure


# --------------------------------------------------------------------------- #
# caption and side-car metadata, both generated from the computed numbers
# --------------------------------------------------------------------------- #
def caption_text(row: dict, gaps: dict, sweep: pd.DataFrame) -> str:
    ratio = row["err_a_hottest_30_c"] / row["err_b_annual_c"]
    return f"""# Figure 1 - a real annual record, two equal-length gaps, two statistics

**Drop-in caption.** The same station-year, one complete annual water-temperature
record, carries two statistics with different supports: an annual mean, supported
on every day, and a hottest 30-day mean, supported on the single 30-day window
that achieves the maximum. **(a)** The complete daily series of {row['network_id']}
station {row['station_id']}, calendar year {row['year']} (n = 365 days, no missing
day), with two designed gaps of identical length, 30 days, marked in different
positions: gap A over the peak window that achieves the complete-record hottest
30-day mean ({row['peak_start']} to {row['peak_end']}), gap B in late autumn
({row['year']}-{GAP_B_FIRST} to {row['year']}-{GAP_B_LAST}). The daily curve is drawn faint
inside the two bands, where the record exists but the analyst does not see it, and
dark where the gap leaves it observed. The orange line is the 30-day running mean
recomputed with both bands withheld, so it breaks wherever no fully observed
window remains; dotted lines are the two complete-record statistics, and panels
(b) and (c) score each gap separately.
**(b)** Each gap's effect on each statistic, in degrees Celsius. Dots are
estimates from the days the gap leaves; the open dot and dotted line are the
complete-record truth. The two panels use different vertical scales and neither
starts at zero, so the values, not bar lengths, carry the comparison ({row['truth_annual_c']:.2f} °C annual mean,
{row['truth_hottest_30_c']:.2f} °C hottest 30-day mean). A 30-day gap over the
peak window moves the hottest 30-day mean by {row['gap_a_hottest_30_c'] - row['truth_hottest_30_c']:+.2f} °C
while the same length in late autumn leaves it exact ({row['gap_b_hottest_30_c'] - row['truth_hottest_30_c']:+.2f} °C);
the annual mean moves by {row['gap_a_annual_c'] - row['truth_annual_c']:+.2f} °C under gap A and
{row['gap_b_annual_c'] - row['truth_annual_c']:+.2f} °C under gap B. **(c)** The length-matched sweep: every one
of the {len(sweep)} possible 30-day gap starts of the same year, plotting the error each
position induces in the hottest 30-day mean (orange) and in the annual mean (blue);
the shaded band holds the starts whose window reaches the peak window. Position,
not length, decides whether the peak survives.

This figure is an illustration of the mechanism on one real record, not a result:
it reports no model, no estimate of a population quantity and no test. The
station-year belongs to the reserved (retrospective holdout) split of the study
panel, whose recorded prior use is descriptive only, and it enters no fit
reported here.

## Identity and provenance

| item | value |
| --- | --- |
| panel | `{row['panel_path']}` |
| panel root | `{FIRST_PANEL_ROOT.relative_to(ROOT)}` |
| provider / network | {row['provider']} / {row['network_id']} (river group {row['river_group']}) |
| split role | {row['split_role']} (retrospective holdout; prior use `{row['prior_access_bucket']}`) |
| station id | {row['station_id']} |
| calendar year | {row['year']} (365 days, complete; station QC verdict `{row['qc_verdict']}`) |
| network data window | {row['overlap_start']} to {row['overlap_end']} |
| statistic definitions | `src/stream_recoverability/experiments/wrr_revision/thermal.py` (hottest {HOTTEST_WINDOW_DAYS}-day mean = maximum of the {HOTTEST_WINDOW_DAYS}-day rolling mean over fully observed windows; annual mean over the calendar year) |
| units | degrees Celsius |
| gap length | {GAP_DAYS} days each, designed, not observed |
| selection rule | C1-C7 in `scripts/265_wrr_figure1_example.py`; screened over the {row['n_networks_scanned']} network panels of the root ({row['n_complete_station_years']} complete station-years on accepted, reserved-role stations), of which {row['n_rule_survivors']} survive and the ranking picks this one |

## Numbers (degC)

| quantity | complete record (truth) | gap A: over the peak window | gap B: late autumn |
| --- | --- | --- | --- |
| annual mean | {row['truth_annual_c']:.3f} | {row['gap_a_annual_c']:.3f} ({row['gap_a_annual_c'] - row['truth_annual_c']:+.3f}) | {row['gap_b_annual_c']:.3f} ({row['gap_b_annual_c'] - row['truth_annual_c']:+.3f}) |
| hottest 30-day mean | {row['truth_hottest_30_c']:.3f} | {row['gap_a_hottest_30_c']:.3f} ({row['gap_a_hottest_30_c'] - row['truth_hottest_30_c']:+.3f}) | {row['gap_b_hottest_30_c']:.3f} ({row['gap_b_hottest_30_c'] - row['truth_hottest_30_c']:+.3f}) |

Peak window of the complete record: {row['peak_start']} to {row['peak_end']}.
Gap A removes exactly that window; gap B removes {row['year']}-{GAP_B_FIRST} to {row['year']}-{GAP_B_LAST}.
The contrast the figure is built on: the same 30-day length costs
{row['err_a_hottest_30_c']:.2f} °C in the hottest 30-day mean when it covers the peak
and {row['err_b_annual_c']:.2f} °C in the annual mean when it sits in late autumn,
a factor of {ratio:.1f}.
"""


def main() -> int:
    FIGURES.mkdir(parents=True, exist_ok=True)
    row = select_station_year()
    candidates = row.pop("candidates")
    row.update(network_metadata(row["network_id"]))

    panel = ROOT / row["panel_path"]
    frame = pd.read_csv(panel, index_col=0, parse_dates=True)
    series = pd.to_numeric(frame[row["station_id"]], errors="coerce")
    block = reindex_calendar_year(series, row["year"])
    if not calendar_year_is_complete(series, row["year"]):
        raise SystemExit("selected station-year is not a complete calendar year")

    sweep = _sweep(block)
    sweep_out = sweep.assign(gap_start=sweep["gap_start"].dt.strftime("%Y-%m-%d"))
    sweep_out.to_csv(FIGURES / f"{NAME}_sweep.csv", index=False)

    figure = build_figure(block, row, sweep)
    for suffix in ("pdf", "png"):
        figure.savefig(FIGURES / f"{NAME}.{suffix}", dpi=300, bbox_inches="tight",
                       pad_inches=0.06)
    plt.close(figure)

    payload = {
        "figure": f"figures/wrr/{NAME}.pdf",
        "purpose": (
            "Illustration of the mechanism on one real station-year; not a result. "
            "No model, no population estimate, no test."
        ),
        "source": {
            "panel_path": row["panel_path"],
            "panel_root": str(FIRST_PANEL_ROOT.relative_to(ROOT)),
            "network_id": row["network_id"],
            "provider": row["provider"],
            "river_group": row["river_group"],
            "station_id": row["station_id"],
            "year": row["year"],
            "split_role": row["split_role"],
            "prior_access_bucket": row["prior_access_bucket"],
            "qc_verdict": row["qc_verdict"],
            "network_data_window": [row["overlap_start"], row["overlap_end"]],
            "n_days": int(block.notna().sum()),
            "complete_calendar_year": bool(calendar_year_is_complete(series, row["year"])),
        },
        "definitions": {
            "hottest_30_day_mean": (
                "maximum of the 30-day rolling mean over windows that are fully observed "
                "(min_periods = 30)"
            ),
            "annual_mean": "mean of the observed days of the calendar year",
            "window_days": HOTTEST_WINDOW_DAYS,
            "implementation": "src/stream_recoverability/experiments/wrr_revision/thermal.py",
            "units": "degC",
        },
        "truth": {
            "annual_mean_c": row["truth_annual_c"],
            "hottest_30_day_mean_c": row["truth_hottest_30_c"],
            "peak_window_start": row["peak_start"],
            "peak_window_end": row["peak_end"],
        },
        "gaps": {
            "gap_a": {
                "label": "over the peak window",
                "start": row["peak_start"],
                "end": row["peak_end"],
                "length_days": GAP_DAYS,
                "annual_mean_c": row["gap_a_annual_c"],
                "annual_mean_error_c": row["gap_a_annual_c"] - row["truth_annual_c"],
                "hottest_30_day_mean_c": row["gap_a_hottest_30_c"],
                "hottest_30_day_error_c": row["gap_a_hottest_30_c"] - row["truth_hottest_30_c"],
            },
            "gap_b": {
                "label": "late autumn",
                "start": f"{row['year']}-{GAP_B_FIRST}",
                "end": f"{row['year']}-{GAP_B_LAST}",
                "length_days": GAP_DAYS,
                "annual_mean_c": row["gap_b_annual_c"],
                "annual_mean_error_c": row["gap_b_annual_c"] - row["truth_annual_c"],
                "hottest_30_day_mean_c": row["gap_b_hottest_30_c"],
                "hottest_30_day_error_c": row["gap_b_hottest_30_c"] - row["truth_hottest_30_c"],
            },
        },
        "contrast": {
            "hottest_30_error_gap_a_c": row["err_a_hottest_30_c"],
            "annual_mean_error_gap_b_c": row["err_b_annual_c"],
            "ratio": row["err_a_hottest_30_c"] / row["err_b_annual_c"],
        },
        "selection_rule": [
            "C1 primary confirmation daily-QC root of the study panel",
            "C2 station QC verdict accepted, eligible for its network",
            "C3 complete calendar year, no missing day",
            "C4 July mean minus January mean >= 15 degC",
            "C5 truth hottest-30 window wholly inside June-August",
            "C6 reserved (held-out) split role",
            "C7 the 1-30 November gap leaves the hottest 30-day mean exactly unchanged",
            "rank by err(hottest 30-day mean | gap A) - err(annual mean | gap B)",
        ],
        "screening": {
            "n_networks_scanned": row["n_networks_scanned"],
            "n_complete_station_years": row["n_complete_station_years"],
            "n_rule_survivors": row["n_rule_survivors"],
        },
        "sweep": {
            "n_gap_starts": len(sweep),
            "hottest_30_error_min_c": float(sweep["hottest_30_error_c"].min()),
            "hottest_30_error_at_gap_b_c": float(
                sweep.loc[
                    sweep["gap_start"] == pd.Timestamp(f"{row['year']}-{GAP_B_FIRST}"),
                    "hottest_30_error_c",
                ].iloc[0]
            ),
            "annual_mean_error_min_c": float(sweep["annual_mean_error_c"].min()),
            "annual_mean_error_max_c": float(sweep["annual_mean_error_c"].max()),
            "file": f"figures/wrr/{NAME}_sweep.csv",
        },
    }
    (FIGURES / f"{NAME}_data.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (FIGURES / f"{NAME}_caption.md").write_text(caption_text(row, payload["gaps"], sweep), encoding="utf-8")

    print(f"chosen: {row['network_id']} / {row['station_id']} / {row['year']}")
    print(f"  provider {row['provider']}, river group {row['river_group']}, "
          f"split {row['split_role']} (prior use {row['prior_access_bucket']}), "
          f"QC {row['qc_verdict']}")
    print(f"  panel: {row['panel_path']}")
    print(f"  peak window: {row['peak_start']} .. {row['peak_end']}")
    print(f"  n days in year: {int(block.notna().sum())}  (complete: yes)")
    print(f"  truth: annual mean {row['truth_annual_c']:.4f}  hottest 30-day mean {row['truth_hottest_30_c']:.4f}")
    print(f"  gap A ({row['peak_start']}..{row['peak_end']}): annual {row['gap_a_annual_c']:.4f} "
          f"(err {row['gap_a_annual_c'] - row['truth_annual_c']:+.4f}), hottest30 {row['gap_a_hottest_30_c']:.4f} "
          f"(err {row['gap_a_hottest_30_c'] - row['truth_hottest_30_c']:+.4f})")
    print(f"  gap B ({row['year']}-{GAP_B_FIRST}..{GAP_B_LAST}): annual {row['gap_b_annual_c']:.4f} "
          f"(err {row['gap_b_annual_c'] - row['truth_annual_c']:+.4f}), hottest30 {row['gap_b_hottest_30_c']:.4f} "
          f"(err {row['gap_b_hottest_30_c'] - row['truth_hottest_30_c']:+.4f})")
    print(f"  contrast: {row['err_a_hottest_30_c']:.4f} vs {row['err_b_annual_c']:.4f} "
          f"(factor {row['err_a_hottest_30_c'] / row['err_b_annual_c']:.1f})")
    print(f"  screening: {row['n_rule_survivors']} survivors of {row['n_complete_station_years']} "
          f"complete station-years in {row['n_networks_scanned']} networks")
    print(f"  sweep: min hottest-30 error {sweep['hottest_30_error_c'].min():.4f} at "
          f"{sweep.loc[sweep['hottest_30_error_c'].idxmin(), 'gap_start'].date()}; "
          f"annual-mean error in [{sweep['annual_mean_error_c'].min():+.4f}, "
          f"{sweep['annual_mean_error_c'].max():+.4f}]")
    print(f"  runner-up: {candidates.iloc[1]['network_id']} / {candidates.iloc[1]['station_id']} / "
          f"{int(candidates.iloc[1]['year'])} (contrast {candidates.iloc[1]['contrast_c']:.4f})")
    for suffix in ("pdf", "png", "json", "csv", "md"):
        print(f"wrote figures/wrr/{NAME}.{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
