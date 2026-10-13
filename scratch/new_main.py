def _load_catalog_with_metadata(api_key: str, *, refresh: bool, record: dict) -> pd.DataFrame:
    """Series catalog + station metadata + per-station keep/drop decision."""

    print("[stage] catalog", flush=True)
    catalog = fetch_catalog(api_key, refresh=refresh, record=record)
    print(f"  parameter {PARAMETER} daily series rows: {len(catalog)}", flush=True)

    catalog["is_river"] = catalog["observation_place"].astype(str).str.startswith(
        ACCEPT_OBSERVATION_PLACES
    )
    catalog["is_measured"] = (
        catalog["measured_or_derived"].astype(str).str.strip().isin(ACCEPT_MEASURED_OR_DERIVED)
    )
    catalog["is_mean"] = catalog["aggregation_method"].astype(str).isin(ACCEPT_AGGREGATION)
    catalog["in_v17_roster"] = catalog["station_id"].isin(V17_STATION_IDS)

    print("[stage] station metadata", flush=True)
    metadata = fetch_station_metadata(
        api_key, sorted(catalog["station_id"]), refresh=refresh, record=record
    )
    catalog = catalog.merge(metadata, on="station_id", how="left")
    catalog["metadata_available"] = catalog["metadata_available"].fillna(False).astype(bool)
    if "drop_reason" not in catalog.columns:
        catalog["drop_reason"] = np.nan
    catalog["basin_number"] = catalog["station_id"].map(basin_number)
    regine_prefix = (
        catalog["regine_no"].fillna("").astype(str).str.split(".").str[0].str.zfill(3)
    )
    catalog["regine_basin_number"] = regine_prefix.where(catalog["regine_no"].notna())
    catalog["basin_prefix_mismatch"] = catalog["regine_basin_number"].notna() & catalog[
        "regine_basin_number"
    ].ne(catalog["basin_number"])
    catalog["network_id"] = "nve_basin_" + catalog["basin_number"]
    catalog["network_name"] = catalog["hierarchy"].fillna("").astype(str)
    missing_name = catalog["network_name"].eq("")
    catalog.loc[missing_name, "network_name"] = catalog.loc[missing_name, "river_name"].fillna("")
    catalog["network_name"] = catalog["network_name"].replace({"": np.nan})
    catalog["is_svalbard"] = catalog["basin_number"].eq(SVALBARD_BASIN_NUMBER) | catalog[
        "station_id"
    ].astype(str).str.startswith("400.")
    catalog["in_coastal_catchment"] = (
        catalog["river_name"].fillna("").astype(str).str.upper().str.contains("KYSTFELT")
    ) | (
        catalog["hierarchy"].fillna("").astype(str).str.upper().str.contains("KYSTFELT|FJORD")
    )

    catalog.loc[~catalog["is_river"], "drop_reason"] = "observation_place_not_river"
    catalog.loc[catalog["is_river"] & ~catalog["is_measured"], "drop_reason"] = "not_measured"
    catalog.loc[
        catalog["is_river"] & catalog["is_measured"] & ~catalog["is_mean"], "drop_reason"
    ] = "daily_resolution_aggregation_not_mean"
    catalog.loc[catalog["in_v17_roster"], "drop_reason"] = "in_v17_station_roster"
    catalog.loc[catalog["is_svalbard"], "drop_reason"] = "svalbard_non_mainland"
    # a dtype=str metadata merge can render an unset marker as the string "nan"
    catalog["drop_reason"] = catalog["drop_reason"].replace({"nan": np.nan, "": np.nan})
    candidates = catalog[catalog["drop_reason"].isna()].copy()

    place_counts = catalog["observation_place"].value_counts().to_dict()
    record["catalog_counts"] = {
        "parameter_1003_daily_series_rows": int(len(catalog)),
        "duplicate_version_series_rows_collapsed": int(removed := catalog.attrs.get(
            "duplicate_series_rows_removed", 0
        )),
        "unique_stations": int(catalog["station_id"].nunique()),
        "observation_place_counts": {str(k): int(v) for k, v in place_counts.items()},
        "measured_or_derived_counts": {
            str(k): int(v) for k, v in catalog["measured_or_derived"].value_counts().items()
        },
        "aggregation_method_counts": {
            str(k): int(v) for k, v in catalog["aggregation_method"].value_counts().items()
        },
        "unit_counts": {str(k): int(v) for k, v in catalog["unit"].value_counts().items()},
        "river_measured_mean_rows": int(
            (catalog["is_river"] & catalog["is_measured"] & catalog["is_mean"]).sum()
        ),
        "dropped_observation_place_not_river": int((~catalog["is_river"]).sum()),
        "dropped_not_measured": int((catalog["is_river"] & ~catalog["is_measured"]).sum()),
        "dropped_daily_resolution_aggregation_not_mean": int(
            (catalog["is_river"] & catalog["is_measured"] & ~catalog["is_mean"]).sum()
        ),
        "dropped_v17_roster_stations": int(
            catalog["drop_reason"].eq("in_v17_station_roster").sum()
        ),
        "dropped_svalbard_non_mainland": int(
            catalog["drop_reason"].eq("svalbard_non_mainland").sum()
        ),
        "candidate_stations": int(len(candidates)),
    }
    catalog.to_csv(RAW / "station_decisions.csv", index=False)
    candidates.to_csv(OUT_ROOT / "candidate_stations.csv", index=False)

    record["candidate_counts"] = {
        "candidate_stations": int(len(candidates)),
        "candidate_basins": int(candidates["network_id"].nunique()),
        "metadata_available": int(candidates["metadata_available"].sum()),
        "stations_missing_metadata": int((~candidates["metadata_available"]).sum()),
        "basins_without_metadata_name": int(
            candidates.loc[candidates["network_name"].isna(), "network_id"].nunique()
        ),
        "basins_without_regine_number": int(
            candidates.loc[candidates["regine_basin_number"].isna(), "network_id"].nunique()
        ),
        "regine_prefix_mismatch_stations": int(candidates["basin_prefix_mismatch"].sum()),
        "regulated_stations": int(
            candidates["catchment_regulation_type"]
            .fillna("")
            .astype(str)
            .str.contains("regulert")
            .sum()
        ),
        "coastal_catchment_river_stations": int(candidates["in_coastal_catchment"].sum()),
    }
    return candidates


def _run_observations(
    api_key: str,
    candidates: pd.DataFrame,
    *,
    refresh: bool,
    record: dict,
) -> pd.DataFrame:
    print(f"[stage] observations for {len(candidates)} candidate stations", flush=True)
    raw = fetch_observations(api_key, candidates, refresh=refresh, record=record)
    print(f"  raw observation rows: {len(raw)}", flush=True)
    return raw


def _assemble(
    raw: pd.DataFrame, candidates: pd.DataFrame, record: dict, *, dev_limited: bool
) -> None:
    print("[stage] assemble", flush=True)
    accepted = candidates.dropna(subset=["network_id"]).copy()
    accepted["station_latitude"] = accepted["metadata_latitude"].fillna(accepted["latitude"])
    accepted["station_longitude"] = accepted["metadata_longitude"].fillna(accepted["longitude"])
    accepted["measurement_statistic"] = (
        "daily_mean_1440min_" + accepted["aggregation_method"].astype(str).str.lower()
    )

    daily, ledger = qc_observations(raw, accepted)
    daily.to_parquet(OUT_ROOT / "daily_long_qc.parquet", index=False)
    ledger.to_csv(OUT_ROOT / "qc_ledger.csv", index=False)

    record["qc_counts"] = {
        "raw_observation_rows": int(len(raw)),
        "stations_requested": int(raw["station_id"].nunique()),
        "qc_passing_station_days": int(len(daily)),
        "rows_dropped_total": int(ledger["n_values_dropped_total"].sum()),
        "drop_reason_totals": {
            column.replace("dropped_", ""): int(ledger[column].sum())
            for column in ledger.columns
            if column.startswith("dropped_") and column != "dropped_total"
        },
        "drop_reason_note": (
            "reasons are assigned in a fixed precedence order (place/aggregation "
            "screen first, then quality, correction, range, then missing null); a "
            "row failing several checks is counted under the first one, so the "
            "totals are disjoint and sum to rows_dropped_total"
        ),
        "stations_with_accepted_values": int(daily["station_id"].nunique()),
        "accepted_quality_code_counts": {
            str(int(k)): int(v)
            for k, v in daily["provider_quality_code"].value_counts().items()
        },
        "accepted_correction_code_counts": {
            str(int(k)): int(v)
            for k, v in daily["provider_correction_code"].value_counts().items()
        },
        "duplicate_station_days": int((daily["n_duplicate_extra"] > 0).sum()),
    }

    # complete-year screen (structural eligibility only; no scoring)
    year_rows = []
    for station_id, block in daily.groupby("station_id"):
        for year in complete_years_from_series(block.set_index("date")["temperature_c"]):
            year_rows.append({"station_id": station_id, "year": int(year)})
    year_frame = pd.DataFrame(year_rows, columns=["station_id", "year"])
    if len(year_frame):
        year_frame = year_frame.merge(
            accepted[["station_id", "network_id"]], on="station_id", how="left"
        )
        year_frame.to_csv(OUT_ROOT / "complete_station_years.csv", index=False)
    record["complete_year_counts"] = {
        "stations_with_complete_years": int(year_frame["station_id"].nunique())
        if len(year_frame)
        else 0,
        "complete_station_years": int(len(year_frame)),
        "stations_with_ge4_complete_years": int(
            year_frame.groupby("station_id").size().ge(MIN_COMPLETE_YEARS).sum()
        )
        if len(year_frame)
        else 0,
    }

    wide = daily.pivot_table(
        index="date", columns="station_id", values="temperature_c", aggfunc="mean"
    ).sort_index()
    wide.index.name = "date"

    ledger_map = {row.station_id: row for row in ledger.itertuples()}
    stations_rows = []
    for row in accepted.sort_values("station_id").itertuples():
        station_id = str(row.station_id)
        if station_id not in wide.columns:
            continue
        series = pd.to_numeric(wide[station_id], errors="coerce")
        years = complete_years_from_series(series)
        present = series.dropna()
        entry = ledger_map.get(station_id)
        stations_rows.append(
            {
                "network_id": row.network_id,
                "network_name": row.network_name,
                "station_id": station_id,
                "provider": PROVIDER,
                "river_name": row.river_name,
                "latitude": row.station_latitude,
                "longitude": row.station_longitude,
                "basin_number": row.basin_number,
                "regine_no": row.regine_no,
                "n_complete_years": len(years),
                "complete_years": ";".join(str(year) for year in years),
                "first_date": present.index.min().date().isoformat() if len(present) else "",
                "last_date": present.index.max().date().isoformat() if len(present) else "",
                "n_days": int(len(present)),
                "n_dropped_qc": int(entry.n_values_dropped_total) if entry is not None else 0,
                "accepted_quality_codes": str(entry.accepted_quality_codes)
                if entry is not None
                else "",
                "measurement_statistic": row.measurement_statistic,
                "catchment_regulation_type": row.catchment_regulation_type,
                "first_year_regulation": row.first_year_regulation,
                "in_coastal_catchment": bool(row.in_coastal_catchment),
            }
        )
    stations_frame = pd.DataFrame(stations_rows)
    if stations_frame.empty:
        record["failures"].append(
            "no station produced a QC-passing daily value; no network was written"
        )
        (OUT_ROOT / "ingest.json").write_text(
            json.dumps(record, indent=1, ensure_ascii=False, default=str)
        )
        print("FAILURE: no station has QC-passing values", flush=True)
        return

    eligible_mask = stations_frame["n_complete_years"] >= MIN_COMPLETE_YEARS
    eligible_pairs = (
        stations_frame[eligible_mask].groupby("network_id")["station_id"].nunique()
    )
    kept_networks = sorted(eligible_pairs[eligible_pairs >= MIN_STATIONS_PER_NETWORK].index)

    # only the stations that satisfy the structural eligibility rule enter the
    # written panel (a network may hold extra short-record stations that are
    # irrelevant to the frozen fit/donor design)
    stations_out = stations_frame[
        stations_frame["network_id"].isin(kept_networks) & eligible_mask
    ].copy()
    stations_out.sort_values(["network_id", "station_id"]).to_csv(
        OUT_ROOT / "stations.csv", index=False
    )
    year_frame = (
        year_frame[year_frame["station_id"].isin(set(stations_out["station_id"]))]
        if len(year_frame)
        else year_frame
    )
    if len(year_frame):
        year_frame.to_csv(OUT_ROOT / "complete_station_years.csv", index=False)

    print("[stage] writing networks", flush=True)
    manifest_rows = write_networks(wide, stations_out, record)

    record["final_counts"] = {
        "candidate_basins_scanned": int(candidates["network_id"].nunique()),
        "candidate_stations": int(len(candidates)),
        "networks_kept": int(len(manifest_rows)),
        "stations_in_kept_networks": int(len(stations_out)),
        "stations_ge4_complete_years_in_kept_networks": int(
            (stations_out["n_complete_years"] >= MIN_COMPLETE_YEARS).sum()
        ),
        "complete_station_years_in_kept_networks": int(stations_out["n_complete_years"].sum()),
        "basins_dropped_below_minimum_stations_or_years": int(
            candidates["network_id"].nunique() - len(kept_networks)
        ),
    }
    record["kept_networks_detail"] = [
        {
            "network_id": row["network_id"],
            "network_name": row["network_name"],
            "n_stations": int(row["n_stations"]),
            "n_complete_station_years": int(row["n_complete_station_years"]),
            "first_date": row["first_date"],
            "last_date": row["last_date"],
        }
        for _, row in pd.DataFrame(manifest_rows).iterrows()
    ]
    record["qc_ledger_totals"] = {
        "stations_in_qc_ledger": int(len(ledger)),
        "stations_with_zero_accepted_values": int(ledger["n_values_accepted"].eq(0).sum()),
    }
    record["caveats"] = build_caveats(record, stations_out, candidates)
    if dev_limited:
        record["caveats"].insert(
            0,
            "DEVELOPMENT RUN with --dev-limit-stations: counts above cover only a "
            "truncated station list and must not be reported.",
        )
    write_record(record)
    print(json.dumps(record["final_counts"], indent=1), flush=True)


def write_record(record: dict) -> None:
    record["inputs_sha256"] = {
        str(V17_ROSTER.relative_to(ROOT)): sha256_file(V17_ROSTER),
        str(PROTOCOL.relative_to(ROOT)): sha256_file(PROTOCOL),
        str(Path(__file__).relative_to(ROOT)): sha256_file(Path(__file__)),
    }
    (OUT_ROOT / "ingest.json").write_text(
        json.dumps(record, indent=1, ensure_ascii=False, default=str)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        default="all",
        choices=("all", "catalog", "metadata", "observations", "assemble"),
    )
    parser.add_argument("--refresh", action="store_true", help="ignore cached raw responses")
    parser.add_argument(
        "--dev-limit-stations",
        type=int,
        default=0,
        help="development smoke test: ingest at most N candidate stations",
    )
    args = parser.parse_args(argv)

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    NETWORKS.mkdir(parents=True, exist_ok=True)

    record: dict = {
        "provider": PROVIDER,
        "protocol": str(PROTOCOL.relative_to(ROOT)),
        "generated_utc": utc_stamp(),
        "run_scope": (
            f"stage={args.stage}"
            + (f", dev_limit_stations={args.dev_limit_stations}" if args.dev_limit_stations else "")
            + (", refresh_cache" if args.refresh else "")
        ),
        "script": str(Path(__file__).relative_to(ROOT)),
        "api": {
            "base": HYDAPI,
            "parameter": PARAMETER,
            "parameter_name": PARAMETER_NAME,
            "resolution_time_minutes": RESOLUTION_TIME,
            "aggregation_method_accepted": list(ACCEPT_AGGREGATION),
            "day_definition": (
                "HydAPI 1440-minute series: daily statistic for the calendar day in "
                "Norwegian normal time (UTC+1), timestamped 11:00Z; aggregation method "
                "reported per series in the Observations response 'method' field"
            ),
            "quality_codes": {
                "accepted": list(ACCEPT_QUALITY),
                "meaning": {
                    "0": "Unknown",
                    "1": "Uncontrolled",
                    "2": "PrimaryControlled",
                    "3": "SecondaryControlled",
                },
            },
            "correction_codes_accepted": list(ACCEPT_CORRECTION),
            "observation_places_accepted_prefix": list(ACCEPT_OBSERVATION_PLACES),
            "measured_or_derived_accepted": list(ACCEPT_MEASURED_OR_DERIVED),
            "plausible_range_c": list(PLAUSIBLE_TEMPERATURE_C),
        },
        "rules": {
            "min_stations_per_network": MIN_STATIONS_PER_NETWORK,
            "min_complete_years_per_station": MIN_COMPLETE_YEARS,
            "complete_year_definition": ">=365 QC-passing days (366 in leap years)",
            "v17_roster_exclusion": str(V17_ROSTER.relative_to(ROOT)),
        },
        "requests": [],
        "stations_absent_from_api_response": [],
        "caveats": [],
        "failures": [],
    }

    api_key = discover_public_hydapi_key()
    roster = pd.read_csv(V17_ROSTER, dtype=str)
    global V17_STATION_IDS
    V17_STATION_IDS = set(roster["station_id"].astype(str))
    print(f"v17 roster stations excluded: {len(V17_STATION_IDS)}", flush=True)

    candidates = _load_catalog_with_metadata(api_key, refresh=args.refresh, record=record)
    if args.stage in ("catalog", "metadata"):
        write_record(record)
        print("catalog + metadata stages complete", flush=True)
        return 0

    candidates_for_run = candidates
    if args.dev_limit_stations:
        candidates_for_run = candidates.head(args.dev_limit_stations).copy()

    if args.stage == "assemble":
        raw_path = RAW / "observations_raw.parquet"
        if not raw_path.is_file():
            raise RuntimeError(
                f"stage=assemble needs {raw_path.relative_to(ROOT)}; run the observations stage first"
            )
        raw = pd.read_parquet(raw_path)
        print(f"  loaded cached raw observations: {len(raw)} rows", flush=True)
    else:
        raw = _run_observations(
            api_key,
            candidates_for_run,
            refresh=args.refresh,
            record=record,
        )
        if args.stage == "observations":
            print("observations stage complete", flush=True)
            return 0

    _assemble(raw, candidates_for_run, record, dev_limited=bool(args.dev_limit_stations))
    return 0

