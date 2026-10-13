# --------------------------------------------------------------------------- #
# C. the WAC 7-DADMax regulatory endpoint
# --------------------------------------------------------------------------- #

NWIS_DV = "https://waterservices.usgs.gov/nwis/dv/"
NWIS_SITE = "https://waterservices.usgs.gov/nwis/site/"
NWIS_USER_AGENT = (
    "stream-recoverability-research/1.0 (WRR submission reproducibility check; "
    "contact: repository maintainer)"
)
WAC_CITATION = (
    "WAC 173-201A-020 (definition of 7-DADMax) and WAC 173-201A-200(1)(c) Table 200(1)(c) "
    "(aquatic life temperature criteria, column 'Highest 7-DADMax')"
)
WAC_DEFINITION = (
    "'7-DADMax' or '7-day average of the daily maximum temperatures' is the arithmetic average "
    "of seven consecutive measures of daily maximum temperatures. The 7-DADMax for any individual "
    "day is calculated by averaging that day's daily maximum temperature with the daily maximum "
    "temperatures of the three days prior and the three days after that date."
)
# The criteria table's own column header is "Highest 7-DADMax", so the annual statistic is the
# maximum over the year of the rolling seven-day average of daily maxima.
DADMAX_THRESHOLDS_C = (16.0, 18.0, 20.0)
MIN_VALID_DAYS_PER_YEAR = 330


def _read_rdb(text: str) -> pd.DataFrame:
    """Parse a USGS RDB table (comment lines, header, format line, data)."""

    lines = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
    if len(lines) < 2:
        return pd.DataFrame()
    header = lines[0].split("\t")
    body = lines[2:] if len(lines) > 2 else []
    rows = [line.split("\t") for line in body if len(line.split("\t")) == len(header)]
    return pd.DataFrame(rows, columns=header)


def _fetch_text(url: str, cache_path: Path, *, refresh: bool = False, pause: float = 0.35) -> tuple[str, str]:
    """Download once, cache on disk, and return (text, sha256)."""

    if cache_path.exists() and not refresh:
        text = cache_path.read_text(encoding="utf-8", errors="replace")
        return text, _sha256(cache_path)
    request = urllib.request.Request(url, headers={"User-Agent": NWIS_USER_AGENT, "Accept": "text/plain"})
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                text = response.read().decode("utf-8", errors="replace")
            break
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as error:  # pragma: no cover
            last_error = error
            time.sleep(2.0 * (attempt + 1))
    else:  # pragma: no cover
        raise RuntimeError(f"failed to fetch {url}: {last_error}")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(text, encoding="utf-8")
    time.sleep(pause)
    return text, _sha256(cache_path)


def confirmation_station_ids() -> list[str]:
    manifest = pd.read_csv(CONFIRMATION_MANIFEST)
    stations: set[str] = set()
    for value in manifest["station_ids_ge4"].astype(str):
        stations.update(part for part in value.split(";") if part)
    return sorted(stations)


def verify_daily_max_availability(stations: list[str], cache_dir: Path) -> pd.DataFrame:
    """Ask the NWIS site service which of the 91 stations publish daily-max temperature."""

    rows: list[pd.DataFrame] = []
    for start in range(0, len(stations), 20):
        chunk = stations[start : start + 20]
        url = (
            NWIS_SITE
            + "?"
            + urllib.parse.urlencode(
                {
                    "format": "rdb",
                    "sites": ",".join(chunk),
                    "seriesCatalogOutput": "true",
                    "parameterCd": "00010",
                    "siteStatus": "all",
                }
            )
        )
        text, digest = _fetch_text(url, cache_dir / f"series_catalog_{start:03d}.rdb", pause=0.4)
        table = _read_rdb(text)
        if table.empty:
            continue
        table["_catalog_sha256"] = digest
        rows.append(table)
    if not rows:
        return pd.DataFrame()
    catalog = pd.concat(rows, ignore_index=True)
    keep = [
        column
        for column in (
            "site_no",
            "station_nm",
            "parm_cd",
            "stat_cd",
            "begin_date",
            "end_date",
            "count_nu",
            "access_cd",
            "_catalog_sha256",
        )
        if column in catalog.columns
    ]
    return catalog[keep]


def download_daily_values(
    stations: list[str], stat_cd: str, cache_dir: Path, *, refresh: bool = False
) -> tuple[pd.DataFrame, list[dict]]:
    """Long daily water-temperature table for one USGS statistic code."""

    frames: list[pd.DataFrame] = []
    manifest: list[dict] = []
    for index, station in enumerate(stations, start=1):
        url = (
            NWIS_DV
            + "?"
            + urllib.parse.urlencode(
                {
                    "format": "rdb",
                    "sites": station,
                    "parameterCd": "00010",
                    "statCd": stat_cd,
                    "siteStatus": "all",
                }
            )
        )
        cache_path = cache_dir / f"{station}_{stat_cd}.rdb"
        text, digest = _fetch_text(url, cache_path, refresh=refresh)
        table = _read_rdb(text)
        value_columns = [column for column in table.columns if column.endswith(f"_{stat_cd}")] if not table.empty else []
        n_values = 0
        if value_columns:
            value_column = value_columns[0]
            code_column = f"{value_column}_cd"
            frame = pd.DataFrame(
                {
                    "site_id": table["site_no"].astype(str),
                    "date": pd.to_datetime(table["datetime"], errors="coerce"),
                    "temperature_c": pd.to_numeric(table[value_column], errors="coerce"),
                    "qualifier": table[code_column].astype(str) if code_column in table.columns else "",
                }
            )
            frame = frame.dropna(subset=["date"])
            n_values = int(frame["temperature_c"].notna().sum())
            frames.append(frame)
        manifest.append(
            {
                "station_id": station,
                "stat_cd": stat_cd,
                "value_description": "Maximum" if stat_cd == "00001" else "Mean",
                "url": url,
                "cache_path": str(cache_path.relative_to(ROOT)),
                "bytes": int(cache_path.stat().st_size),
                "sha256": digest,
                "n_rows": int(len(table)),
                "n_numeric_values": n_values,
            }
        )
        if index % 20 == 0:
            print(f"  [dadmax] stat {stat_cd}: {index}/{len(stations)} stations", flush=True)
    long = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=["site_id", "date", "temperature_c", "qualifier"])
    )
    return long, manifest


def qc_long_values(long: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the repository's own confirmation QC so both statistics are treated identically."""

    from stream_recoverability.data.ingest_qc import clean_long_frame, qc_long_frame

    if long.empty:
        return long, pd.DataFrame()
    report = qc_long_frame(long)
    clean = clean_long_frame(long, report=report, min_qualified_years=0)
    return clean, report


def station_year_statistics(values: pd.Series, *, window: int = 7) -> pd.DataFrame:
    """Annual extremes of a daily series, per calendar year.

    ``hottest_window_mean`` is the maximum over the year of the window-day rolling mean; on daily
    maxima with window 7 that is the WAC "highest 7-DADMax". ``single_day_max`` is the 1-DMax.
    """

    frame = pd.DataFrame({"value": pd.to_numeric(values, errors="coerce")}).dropna()
    if frame.empty:
        return pd.DataFrame()
    frame["year"] = frame.index.year
    rows = []
    for year, block in frame.groupby("year", sort=True):
        series = block["value"]
        n_days_in_year = days_in_year(int(year))
        rolling = series.rolling(window, min_periods=window).mean()
        rows.append(
            {
                "year": int(year),
                "n_valid_days": int(series.notna().sum()),
                "coverage": float(series.notna().sum() / n_days_in_year),
                "hottest_window_mean": float(rolling.max()) if rolling.notna().any() else float("nan"),
                "peak_day": series.index[int(np.nanargmax(rolling.to_numpy(dtype=float)))]
                if rolling.notna().any()
                else pd.NaT,
                "single_day_max": float(series.max()),
            }
        )
    return pd.DataFrame(rows)


def _annual_stats_by_station(clean: pd.DataFrame, renames: dict[str, str]) -> pd.DataFrame:
    rows = []
    if clean.empty:
        return pd.DataFrame()
    for site_id, group in clean.groupby("site_id", sort=True):
        block = group.set_index("date").sort_index()
        stats = station_year_statistics(block["temperature_c"])
        if stats.empty:
            continue
        stats["site_id"] = str(site_id)
        rows.append(stats.rename(columns=renames))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def run_dadmax(workers: int) -> int:
    del workers  # the endpoint is one sequential download plus one comparison
    OUT_REG.mkdir(parents=True, exist_ok=True)
    cache_dir = OUT_REG / "raw_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    stations = confirmation_station_ids()
    print(f"[dadmax] sealed confirmation panel stations: {len(stations)}", flush=True)

    catalog = verify_daily_max_availability(stations, cache_dir)
    if not catalog.empty:
        catalog.to_csv(OUT_REG / "daily_max_availability.csv", index=False)
        stat = catalog["stat_cd"].astype(str).str.zfill(5)
        max_rows = catalog.loc[stat.eq("00001")]
        mean_rows = catalog.loc[stat.eq("00003")]
        availability = {
            "n_stations_requested": int(len(stations)),
            "n_stations_in_catalog": int(catalog["site_no"].nunique()),
            "n_stations_with_daily_max_00001": int(max_rows["site_no"].nunique()),
            "n_stations_with_daily_mean_00003": int(mean_rows["site_no"].nunique()),
            "n_stations_with_max_but_no_mean": sorted(set(max_rows["site_no"]) - set(mean_rows["site_no"])),
            "n_stations_with_mean_but_no_max": sorted(set(mean_rows["site_no"]) - set(max_rows["site_no"])),
            "stations_missing_from_catalog": sorted(set(stations) - set(catalog["site_no"])),
            "catalog_sha256": sorted(
                {str(value) for value in catalog.get("_catalog_sha256", []) if isinstance(value, str)}
            ),
        }
    else:  # pragma: no cover
        availability = {"n_stations_requested": int(len(stations)), "catalog_empty": True}
    _write_json(OUT_REG / "daily_max_availability_summary.json", availability)

    max_long, max_manifest = download_daily_values(stations, "00001", cache_dir)
    mean_long, mean_manifest = download_daily_values(stations, "00003", cache_dir)
    pd.DataFrame(max_manifest + mean_manifest).to_csv(OUT_REG / "raw_cache_manifest.csv", index=False)
    max_long.to_parquet(OUT_REG / "daily_max_long_raw.parquet", index=False)
    mean_long.to_parquet(OUT_REG / "daily_mean_long_raw.parquet", index=False)

    max_clean, max_qc = qc_long_values(max_long)
    mean_clean, mean_qc = qc_long_values(mean_long)
    if len(max_qc):
        max_qc.to_csv(OUT_REG / "daily_max_qc_report.csv", index=False)
    if len(mean_qc):
        mean_qc.to_csv(OUT_REG / "daily_mean_qc_report.csv", index=False)
    max_clean.to_parquet(OUT_REG / "daily_max_long_clean.parquet", index=False)
    mean_clean.to_parquet(OUT_REG / "daily_mean_long_clean.parquet", index=False)

    max_stats = _annual_stats_by_station(
        max_clean,
        {
            "hottest_window_mean": "dadmax7",
            "single_day_max": "one_day_max",
            "peak_day": "dadmax_peak_day",
            "n_valid_days": "n_valid_days_max",
            "coverage": "coverage_max",
        },
    )
    mean_stats = _annual_stats_by_station(
        mean_clean,
        {
            "hottest_window_mean": "hottest7_mean",
            "single_day_max": "one_day_max_mean_series",
            "peak_day": "hottest7_peak_day",
            "n_valid_days": "n_valid_days_mean",
            "coverage": "coverage_mean",
        },
    )

    # The sealed panel's station-years, read for context only (never re-scored).
    sealed_years: set[tuple[str, int]] = set()
    sealed_path = (
        ROOT / "results" / "wrr_submission_ready" / "p0_07_sealed_confirmation" / "sealed_cases.parquet"
    )
    if sealed_path.exists():
        sealed = pd.read_parquet(sealed_path, columns=["station_id", "year"])
        sealed_years = {(str(site), int(year)) for site, year in zip(sealed["station_id"], sealed["year"])}

    paired = max_stats.merge(mean_stats, on=["site_id", "year"], how="inner", suffixes=("", "_mean"))
    paired["difference_dadmax_minus_hottest7_mean"] = paired["dadmax7"] - paired["hottest7_mean"]
    paired["peak_window_shift_days"] = (paired["dadmax_peak_day"] - paired["hottest7_peak_day"]).dt.days
    paired["in_sealed_panel"] = [
        (str(site), int(year)) in sealed_years for site, year in zip(paired["site_id"], paired["year"])
    ]
    paired["max_below_mean"] = paired["difference_dadmax_minus_hottest7_mean"] < 0
    paired.to_parquet(OUT_REG / "station_year_pairs.parquet", index=False)

    comparison = paired.loc[
        paired["n_valid_days_max"].ge(MIN_VALID_DAYS_PER_YEAR)
        & paired["n_valid_days_mean"].ge(MIN_VALID_DAYS_PER_YEAR)
    ].reset_index(drop=True)
    comparison.to_csv(OUT_REG / "dadmax_comparison.csv", index=False)
    complete_both = paired.loc[
        paired["n_valid_days_max"].ge(paired["year"].map(days_in_year))
        & paired["n_valid_days_mean"].ge(paired["year"].map(days_in_year))
    ].reset_index(drop=True)

    threshold_rows = []
    sweep_grid = list(DADMAX_THRESHOLDS_C) + [14.0, 17.0, 19.0, 21.0, 22.0, 24.0]
    for threshold in sweep_grid:
        exceeds_mean = comparison["hottest7_mean"].to_numpy(dtype=float) > threshold
        exceeds_max = comparison["dadmax7"].to_numpy(dtype=float) > threshold
        agreement = float((exceeds_mean == exceeds_max).mean())
        expected = float(exceeds_max.mean()) * float(exceeds_mean.mean()) + float(
            (~exceeds_max).mean()
        ) * float((~exceeds_mean).mean())
        threshold_rows.append(
            {
                "threshold_c": threshold,
                "n": int(len(comparison)),
                "n_exceed_dadmax": int(exceeds_max.sum()),
                "n_exceed_hottest7_mean": int(exceeds_mean.sum()),
                "n_agree": int((exceeds_mean == exceeds_max).sum()),
                "agreement_rate": agreement,
                "n_mean_only": int((exceeds_mean & ~exceeds_max).sum()),
                "n_dadmax_only": int((~exceeds_mean & exceeds_max).sum()),
                "class_change_rate": float((exceeds_mean != exceeds_max).mean()),
                "base_rate_dadmax": float(exceeds_max.mean()),
                "base_rate_hottest7_mean": float(exceeds_mean.mean()),
                "cohen_kappa": float((agreement - expected) / (1 - expected)) if expected < 1 else float("nan"),
                "in_manuscript_grid": threshold in DADMAX_THRESHOLDS_C,
            }
        )
    threshold_table = pd.DataFrame(threshold_rows).sort_values("threshold_c").reset_index(drop=True)
    threshold_table.to_csv(OUT_REG / "threshold_class_change.csv", index=False)

    differences = comparison["difference_dadmax_minus_hottest7_mean"].to_numpy(dtype=float)
    valid = comparison.dropna(subset=["hottest7_mean", "difference_dadmax_minus_hottest7_mean"])
    slope, intercept = np.polyfit(
        valid["hottest7_mean"].to_numpy(dtype=float),
        valid["difference_dadmax_minus_hottest7_mean"].to_numpy(dtype=float),
        1,
    )
    pooled = {
        "n_station_years_paired": int(len(paired)),
        "n_station_years_analysis": int(len(comparison)),
        "n_station_years_fully_complete_both": int(len(complete_both)),
        "n_stations_analysis": int(comparison["site_id"].nunique()),
        "year_min": int(comparison["year"].min()),
        "year_max": int(comparison["year"].max()),
        "n_station_years_also_in_sealed_panel": int(comparison["in_sealed_panel"].sum()),
        "min_valid_days_per_year_rule": MIN_VALID_DAYS_PER_YEAR,
        "difference_c": {
            "mean": float(np.nanmean(differences)),
            "sd": float(np.nanstd(differences, ddof=1)),
            "median": float(np.nanmedian(differences)),
            "q05": float(np.nanquantile(differences, 0.05)),
            "q25": float(np.nanquantile(differences, 0.25)),
            "q75": float(np.nanquantile(differences, 0.75)),
            "q95": float(np.nanquantile(differences, 0.95)),
            "min": float(np.nanmin(differences)),
            "max": float(np.nanmax(differences)),
            "share_positive": float(np.nanmean(differences > 0)),
            "share_zero": float(np.nanmean(differences == 0)),
            "share_negative": float(np.nanmean(differences < 0)),
        },
        "difference_c_fully_complete_subset": {
            "n": int(len(complete_both)),
            "mean": float(complete_both["difference_dadmax_minus_hottest7_mean"].mean()),
            "median": float(complete_both["difference_dadmax_minus_hottest7_mean"].median()),
            "sd": float(complete_both["difference_dadmax_minus_hottest7_mean"].std(ddof=1)),
        },
        "peak_window_shift_days": {
            "median": float(comparison["peak_window_shift_days"].median()),
            "share_same_day": float((comparison["peak_window_shift_days"] == 0).mean()),
            "share_abs_le_7": float((comparison["peak_window_shift_days"].abs() <= 7).mean()),
        },
        "sanity_max_below_mean_station_years": int(paired["max_below_mean"].sum()),
        "difference_vs_level_regression": {
            "slope_c_per_c": float(slope),
            "intercept_c": float(intercept),
            "pearson_r": float(
                pd.Series(valid["hottest7_mean"]).corr(
                    pd.Series(valid["difference_dadmax_minus_hottest7_mean"])
                )
            ),
            "note": (
                "a constant offset could in principle be absorbed by moving the threshold; a level-dependent "
                "difference cannot, because the required shift varies by station-year"
            ),
        },
    }

    summary = {
        "question": (
            "F17: the manuscript's regulatory illustration uses the hottest seven-day mean of daily MEAN "
            "water temperature, while WAC 173-201A-200(1)(c) is written against the highest 7-DADMax, the "
            "seven-day average of consecutive daily MAXIMA. How large is the endpoint mismatch?"
        ),
        "endpoint_compared_against": "highest 7-DADMax (WAC 173-201A-200(1)(c) Table 200(1)(c))",
        "wac_citation": WAC_CITATION,
        "wac_definition": WAC_DEFINITION,
        "statistics_used": {
            "dadmax7": "annual maximum of the 7-day rolling mean of USGS daily maxima (00010/00001)",
            "hottest7_mean": "annual maximum of the 7-day rolling mean of USGS daily means (00010/00003)",
        },
        "qc": "the repository's own confirmation QC (ingest_qc.qc_long_frame / clean_long_frame) applied to both statistics",
        "stations": {
            "requested": int(len(stations)),
            "with_daily_max_after_qc": int(max_clean["site_id"].nunique()) if len(max_clean) else 0,
            "with_daily_mean_after_qc": int(mean_clean["site_id"].nunique()) if len(mean_clean) else 0,
        },
        "availability": availability,
        "raw_cache": {
            "files": int(len(max_manifest) + len(mean_manifest)),
            "bytes": int(sum(row["bytes"] for row in max_manifest + mean_manifest)),
            "manifest": "results/wrr_submission_ready/amendments/regulatory_daily_max/raw_cache_manifest.csv",
        },
        "paired": pooled,
        "threshold_table": threshold_table.to_dict(orient="records"),
        "manuscript_reference": {
            "artifact": "results/v17_fitness/step22_robustness/threshold_sweep.csv",
            "note": "the 16/18/20 C grid is the manuscript's own",
            "step22_grid": sorted(
                float(value) for value in pd.read_csv(STEP22 / "threshold_sweep.csv")["threshold_c"].unique()
            ),
        },
    }
    _write_json(OUT_REG / "summary.json", summary)
    write_dadmax_report(threshold_table, pooled, summary)
    print(threshold_table.round(4).to_string(index=False))
    print(json.dumps(pooled["difference_c"], indent=2))
    return 0


def write_dadmax_report(threshold_table: pd.DataFrame, pooled: dict, summary: dict) -> None:
    diff = pooled["difference_c"]
    grid = threshold_table.loc[threshold_table["in_manuscript_grid"]].sort_values("threshold_c")
    grid_changes = [float(value) for value in grid["class_change_rate"]]
    twenty = [
        float(row.class_change_rate)
        for row in threshold_table.itertuples(index=False)
        if row.threshold_c == 20.0
    ][0]
    lines: list[str] = []
    lines.append("# F17 - the regulatory illustration uses daily means, but the criterion is 7-DADMax")
    lines.append("")
    lines.append(
        "Artifacts: `dadmax_comparison.csv`, `threshold_class_change.csv`, `summary.json`, "
        "`daily_max_availability.csv`, `raw_cache/` (hashes in `raw_cache_manifest.csv`). "
        "Script: `scripts/251_wrr_winter_regulatory_endpoints.py dadmax`."
    )
    lines.append("")
    lines.append("## The definition used")
    lines.append("")
    lines.append(f"{summary['wac_citation']}:")
    lines.append("")
    lines.append(f"> {summary['wac_definition']}")
    lines.append("")
    lines.append(
        "The criteria table's column header is **Highest 7-DADMax**, so the annual statistic is the "
        "maximum over the year of the rolling seven-day average of daily maxima. This report computes "
        "exactly that from USGS daily values with `parameterCd=00010`, `statCd=00001` (Maximum), and "
        "compares it, station-year by station-year, with the manuscript's statistic: the maximum of the "
        "rolling seven-day average of `statCd=00003` (daily Mean). Both series pass through the "
        "repository's own confirmation QC (`ingest_qc.qc_long_frame` / `clean_long_frame`), so the "
        "comparison is not contaminated by different treatment of provisional or out-of-range values."
    )
    lines.append("")
    lines.append("## Availability of daily maxima at the 91 confirmation stations")
    lines.append("")
    availability = summary["availability"]
    lines.append(
        "* stations requested: {n_stations_requested}; with a daily-maximum time series in the NWIS "
        "series catalog: **{n_stations_with_daily_max_00001}**; with a daily-mean series: "
        "{n_stations_with_daily_mean_00003}.".format(**availability)
    )
    lines.append(
        "* stations with a daily mean but no daily maximum: {}; with a daily maximum but no daily mean: "
        "{}.".format(
            availability.get("n_stations_with_mean_but_no_max") or "none",
            availability.get("n_stations_with_max_but_no_mean") or "none",
        )
    )
    lines.append(
        "* after QC, {} stations contribute a daily-maximum series and {} a daily-mean series.".format(
            summary["stations"]["with_daily_max_after_qc"], summary["stations"]["with_daily_mean_after_qc"]
        )
    )
    lines.append(
        "* raw responses and hashes: {files} files, {bytes:,} bytes, in `raw_cache/`.".format(
            **summary["raw_cache"]
        )
    )
    lines.append("")
    lines.append("## The comparison")
    lines.append("")
    lines.append(
        "Station-years with at least {} valid days in **both** series: **n = {:,}** station-years at {} "
        "stations, {}-{}. A further {:,} station-years have both series complete day-for-day and tell the "
        "same story (median difference {:+.3f} C against {:+.3f} C on the coverage-filtered set). {:,} of "
        "the analysed station-years are also in the sealed USGS confirmation panel; the sealed panel "
        "itself was not re-scored.".format(
            pooled["min_valid_days_per_year_rule"],
            pooled["n_station_years_analysis"],
            pooled["n_stations_analysis"],
            pooled["year_min"],
            pooled["year_max"],
            pooled["n_station_years_fully_complete_both"],
            pooled["difference_c_fully_complete_subset"]["median"],
            diff["median"],
            pooled["n_station_years_also_in_sealed_panel"],
        )
    )
    lines.append("")
    lines.append("Distribution of `7-DADMax - hottest-7 daily mean` over the same station-years:")
    lines.append("")
    lines.append("| statistic | value (C) |")
    lines.append("| --- | --- |")
    for label, key in (
        ("mean", "mean"),
        ("standard deviation", "sd"),
        ("median", "median"),
        ("5th percentile", "q05"),
        ("25th percentile", "q25"),
        ("75th percentile", "q75"),
        ("95th percentile", "q95"),
        ("minimum", "min"),
        ("maximum", "max"),
    ):
        lines.append("| {} | {:+.3f} |".format(label, diff[key]))
    lines.append("| share where 7-DADMax > hottest-7 mean | {:.1%} |".format(diff["share_positive"]))
    lines.append("| share exactly equal | {:.1%} |".format(diff["share_zero"]))
    lines.append("| share where 7-DADMax < hottest-7 mean | {:.2%} |".format(diff["share_negative"]))
    lines.append("")
    lines.append(
        "The difference is not a constant offset that a shifted threshold could absorb: regressing it on "
        "the daily-mean level gives a slope of {:+.3f} C per C (Pearson r = {:+.3f}), so the required shift "
        "varies station-year by station-year. The seven-day peak also moves: the two statistics select the "
        "same peak day in {:.1%} of station-years and within a week in {:.1%} (median absolute shift "
        "{:.0f} days).".format(
            pooled["difference_vs_level_regression"]["slope_c_per_c"],
            pooled["difference_vs_level_regression"]["pearson_r"],
            pooled["peak_window_shift_days"]["share_same_day"],
            pooled["peak_window_shift_days"]["share_abs_le_7"],
            abs(pooled["peak_window_shift_days"]["median"]),
        )
    )
    lines.append("")
    lines.append("## Would the threshold decision change?")
    lines.append("")
    lines.append(
        "The 16/18/20 C grid is the manuscript's own (`step22_robustness/threshold_sweep.csv`). "
        "\"mean only\" means the daily-mean statistic calls an exceedance that the 7-DADMax does not; "
        "\"7-DADMax only\" is the reverse."
    )
    lines.append("")
    lines.append(
        "| threshold (C) | n | exceed: 7-DADMax | exceed: hottest-7 mean | agree | mean only | "
        "7-DADMax only | class-change rate | Cohen's kappa |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for row in grid.itertuples(index=False):
        lines.append(
            "| {:.0f} | {:,} | {:,} | {:,} | {:,} | **{:,}** | **{:,}** | {:.2%} | {:.3f} |".format(
                row.threshold_c, row.n, row.n_exceed_dadmax, row.n_exceed_hottest7_mean, row.n_agree,
                row.n_mean_only, row.n_dadmax_only, row.class_change_rate, row.cohen_kappa,
            )
        )
    lines.append("")
    lines.append("The same over the whole swept grid:")
    lines.append("")
    lines.append("| threshold (C) | exceed: 7-DADMax | exceed: hottest-7 mean | class-change rate | mean only | 7-DADMax only |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for row in threshold_table.itertuples(index=False):
        lines.append(
            "| {:.0f} | {:,} | {:,} | {:.2%} | {:,} | {:,} |".format(
                row.threshold_c, row.n_exceed_dadmax, row.n_exceed_hottest7_mean,
                row.class_change_rate, row.n_mean_only, row.n_dadmax_only,
            )
        )
    lines.append("")
    lines.append(
        "Recorded rather than assumed: 7-DADMax falls below the hottest-7 daily mean in {:,} of {:,} "
        "station-years ({:.2%}). That is possible only through the annual maximisation selecting different "
        "peak windows (and, in a few cases, through QC dropping different days from the two series), not "
        "through a daily violation of max >= mean.".format(
            pooled["sanity_max_below_mean_station_years"],
            pooled["n_station_years_analysis"],
            pooled["sanity_max_below_mean_station_years"] / max(1, pooled["n_station_years_analysis"]),
        )
    )
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    lines.append(
        "**No - the current hottest-7 daily-mean illustration cannot stand as a regulatory-aligned "
        "example.** It substitutes a different input statistic ({:+.2f} C at the median, {:+.2f} C on "
        "average, with a 5th-95th percentile spread of {:.2f} C), it moves the date of the seven-day peak "
        "in {:.1%} of station-years, and on the manuscript's own 16/18/20 C grid it changes the exceedance "
        "classification in {:.2%} / {:.2%} / {:.2%} of station-years. Sweeping the threshold cannot repair "
        "this: the difference is level-dependent (slope {:+.3f} C per C), so no single shifted threshold "
        "reproduces the 7-DADMax calls, and the sign is not uniform, so there is no conservative direction "
        "to retreat to either.".format(
            diff["median"], diff["mean"], diff["q95"] - diff["q05"],
            1 - pooled["peak_window_shift_days"]["share_same_day"],
            grid_changes[0], grid_changes[1], grid_changes[2],
            pooled["difference_vs_level_regression"]["slope_c_per_c"],
        )
    )
    lines.append("")
    lines.append("**Corrected statement.** Replace the illustration with one of two claims:")
    lines.append("")
    lines.append(
        "1. *Preferred, and now computable.* Where an archive is screening a WAC-style criterion, the "
        "endpoint must be the highest 7-DADMax built from daily maxima, and the screening results reported "
        "for the hottest-7 daily mean should be recomputed on that endpoint. This amendment supplies the "
        "daily-maximum input and the station-year join for the 91 confirmation stations "
        "(`dadmax_comparison.csv`), so the recomputation is a re-run of the existing screen against a "
        "different target column, not a new data campaign."
    )
    lines.append(
        "2. *If the illustration is kept.* Relabel it as a daily-mean illustration of a seven-day "
        "endpoint, stating explicitly that the WAC 7-DADMax criterion is built from daily maxima, that the "
        "daily-mean surrogate is biased low by a median of {:+.2f} C (5th-95th percentile {:+.2f} to "
        "{:+.2f} C), that the classification changes in {:.2%} of station-years at 20 C, and that the "
        "manuscript's misclassification numbers are therefore not compliance numbers for WAC "
        "173-201A-200.".format(diff["median"], diff["q05"], diff["q95"], twenty)
    )
    lines.append("")
    lines.append(
        "Nothing here contradicts the mechanism claim: the screen's advantage over gap length is a "
        "property of the estimator and the gap geometry, not of the units. The finding is narrower and "
        "harder to argue with - the endpoint must match the regulation before the numbers may be called "
        "regulatory."
    )
    lines.append("")
    (OUT_REG / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
