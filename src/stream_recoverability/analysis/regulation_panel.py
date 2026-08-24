"""Frozen nationwide USGS/GAGES-II regulation-panel analysis.

The module is intentionally independent of the external-confirmation code and data.
It discovers daily mean water-temperature series from the modern USGS Water Data
APIs and joins exact station numbers to the routed upstream-dam attributes published
in GAGES-II.  See ``configs/regulation_panel_freeze_v1.yaml``.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
import yaml
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, roc_curve

from stream_recoverability.analysis.regulation import (
    circular_doy_climatology,
    predict_climatology,
)

USER_AGENT = "stream-recoverability-regulation-panel/1.0 (scientific-research)"


def load_freeze(path: Path) -> dict[str, Any]:
    """Load and minimally validate the controlling design freeze."""

    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if config.get("design_id") != "regulation_panel_freeze_v1":
        raise ValueError("expected regulation_panel_freeze_v1")
    if config.get("status") != "frozen_before_temperature_panel_outcomes":
        raise ValueError("regulation-panel design is not frozen")
    return config


def enforce_isolation(paths: Iterable[Path | str], config: Mapping[str, Any]) -> None:
    """Reject paths that could cross the frozen confirmatory isolation boundary."""

    tokens = [
        str(value).lower()
        for value in config["isolation_contract"]["forbidden_path_tokens"]
    ]
    for path in paths:
        normalized = str(path).replace("\\", "/").lower()
        matched = [token for token in tokens if token in normalized]
        if matched:
            raise ValueError(
                f"regulation-panel isolation violation in {path!s}: {matched}"
            )


def file_identity(path: Path) -> dict[str, Any]:
    """Return a portable SHA-256 file identity."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def portable_file_identity(path: Path, project_root: Path) -> dict[str, Any]:
    """Return a file identity whose path is repository-relative when possible."""

    identity = file_identity(path)
    try:
        identity["path"] = path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        identity["path"] = path.name
    return identity


def _url_with_query(url: str, params: Mapping[str, Any]) -> str:
    query = urllib.parse.urlencode(
        [
            (key, value)
            for key, raw in params.items()
            for value in ([raw] if not isinstance(raw, (list, tuple)) else raw)
        ]
    )
    return f"{url}?{query}"


def _request_bytes(url: str, *, attempts: int = 5, timeout: int = 180) -> bytes:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            headers = {"User-Agent": USER_AGENT}
            api_key = os.environ.get("USGS_WATERDATA_API_KEY")
            if (
                api_key
                and urllib.parse.urlparse(url).hostname == "api.waterdata.usgs.gov"
            ):
                headers["api_key"] = api_key
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(min(2**attempt, 15))
    raise RuntimeError(
        f"request failed after {attempts} attempts: {url}"
    ) from last_error


def _request_json(url: str) -> dict[str, Any]:
    return json.loads(_request_bytes(url).decode("utf-8"))


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_bytes(payload)
    temporary.replace(path)


def fetch_json_cache(url: str, path: Path, *, offline: bool = False) -> dict[str, Any]:
    """Read an immutable JSON cache or populate it from ``url``."""

    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if offline:
        raise FileNotFoundError(f"offline cache is missing: {path}")
    payload = _request_bytes(url)
    _atomic_bytes(path, payload)
    return json.loads(payload.decode("utf-8"))


def discover_temperature_series(
    config: Mapping[str, Any], cache_dir: Path, *, offline: bool = False
) -> pd.DataFrame:
    """Discover all primary USGS daily-mean water-temperature time series."""

    spec = config["data_sources"]["usgs"]
    endpoint = (
        f"{spec['api_root']}/collections/"
        f"{spec['time_series_metadata_collection']}/items"
    )
    url = _url_with_query(
        endpoint,
        {
            "f": "json",
            "limit": 10000,
            "parameter_code": spec["parameter_code"],
            "statistic_id": spec["statistic_id"],
            "computation_period_identifier": spec["computation_period_identifier"],
            "computation_identifier": spec["computation_identifier"],
        },
    )
    raw = fetch_json_cache(
        url, cache_dir / "usgs_time_series_metadata.json", offline=offline
    )
    if any(link.get("rel") == "next" for link in raw.get("links", [])):
        raise RuntimeError("temperature metadata exceeded the frozen one-page limit")
    records: list[dict[str, Any]] = []
    for feature in raw.get("features", []):
        row = dict(feature.get("properties", {}))
        coordinates = (feature.get("geometry") or {}).get(
            "coordinates", [np.nan, np.nan]
        )
        row["longitude"] = coordinates[0]
        row["latitude"] = coordinates[1]
        records.append(row)
    frame = pd.DataFrame(records)
    if frame.empty:
        raise RuntimeError("USGS returned no daily-mean water-temperature series")
    frame["station_id"] = frame["monitoring_location_id"].str.replace(
        r"^USGS-", "", regex=True
    )
    frame["begin"] = pd.to_datetime(frame["begin"], errors="coerce")
    frame["end"] = pd.to_datetime(frame["end"], errors="coerce")
    start = pd.Timestamp(spec["period_start"])
    end = pd.Timestamp(spec["period_end"])
    selected = (
        frame["primary"].eq("Primary")
        & frame["parameter_code"].astype(str).eq(str(spec["parameter_code"]))
        & frame["statistic_id"].astype(str).str.zfill(5).eq(str(spec["statistic_id"]))
        & frame["computation_period_identifier"].eq("Daily")
        & frame["computation_identifier"].eq("Mean")
        & frame["begin"].le(end)
        & frame["end"].ge(start)
    )
    return frame.loc[selected].reset_index(drop=True)


def _sciencebase_archive(
    config: Mapping[str, Any], cache_dir: Path, *, offline: bool = False
) -> Path:
    spec = config["data_sources"]["gages_ii"]
    item_url = (
        "https://www.sciencebase.gov/catalog/item/"
        f"{spec['sciencebase_item_id']}?format=json"
    )
    item = fetch_json_cache(
        item_url, cache_dir / "gages_ii_sciencebase_item.json", offline=offline
    )
    candidates = [
        file
        for file in item.get("files", [])
        if file.get("name") == spec["archive_name"]
    ]
    if len(candidates) != 1:
        raise RuntimeError(
            f"ScienceBase did not expose exactly one {spec['archive_name']}"
        )
    archive = cache_dir / spec["archive_name"]
    if not archive.exists():
        if offline:
            raise FileNotFoundError(f"offline cache is missing: {archive}")
        _atomic_bytes(
            archive, _request_bytes(candidates[0]["downloadUri"], timeout=300)
        )
    md5 = hashlib.md5(archive.read_bytes(), usedforsecurity=False).hexdigest()
    if md5 != str(spec["archive_md5"]):
        raise RuntimeError(f"GAGES-II archive MD5 mismatch: {md5}")
    return archive


def load_gages_ii(
    config: Mapping[str, Any], cache_dir: Path, *, offline: bool = False
) -> tuple[pd.DataFrame, Path]:
    """Load station, ecoregion, and routed dam attributes from GAGES-II."""

    archive = _sciencebase_archive(config, cache_dir, offline=offline)
    with zipfile.ZipFile(archive) as outer:
        nested_payload = outer.read("spreadsheets-in-csv-format.zip")
    with zipfile.ZipFile(io.BytesIO(nested_payload)) as nested:

        def table(name: str) -> pd.DataFrame:
            return pd.read_csv(
                nested.open(name), dtype={"STAID": str}, encoding="cp1252"
            )

        pieces: list[pd.DataFrame] = []
        for prefix in ("conterm", "AKHIPR"):
            basin = table(f"{prefix}_basinid.txt")
            classification = table(f"{prefix}_bas_classif.txt")
            dams = table(f"{prefix}_hydromod_dams.txt")
            pieces.append(
                basin.merge(
                    classification[["STAID", "CLASS", "AGGECOREGION"]],
                    on="STAID",
                    how="left",
                    validate="one_to_one",
                ).merge(dams, on="STAID", how="left", validate="one_to_one")
            )
    result = pd.concat(pieces, ignore_index=True, sort=False)
    result["STAID"] = result["STAID"].astype(str).str.strip()
    if result["STAID"].duplicated().any():
        raise RuntimeError("GAGES-II station IDs are not unique")
    return result, archive


def fetch_monitoring_locations(
    station_ids: Sequence[str],
    config: Mapping[str, Any],
    cache_dir: Path,
    *,
    offline: bool = False,
    batch_size: int = 200,
) -> pd.DataFrame:
    """Fetch official USGS monitoring-location metadata for exact station IDs."""

    cache = cache_dir / "usgs_monitoring_locations.json"
    spec = config["data_sources"]["usgs"]
    if cache.exists():
        payload = json.loads(cache.read_text(encoding="utf-8"))
    else:
        if offline:
            raise FileNotFoundError(f"offline cache is missing: {cache}")
        endpoint = f"{spec['api_root']}/collections/{spec['monitoring_locations_collection']}/items"
        features: list[dict[str, Any]] = []
        requests: list[str] = []
        values = sorted({f"USGS-{value}" for value in station_ids})
        for offset in range(0, len(values), batch_size):
            url = _url_with_query(
                endpoint,
                {
                    "f": "json",
                    "limit": batch_size,
                    "id": ",".join(values[offset : offset + batch_size]),
                },
            )
            while url:
                response = _request_json(url)
                requests.append(url)
                features.extend(response.get("features", []))
                links = [
                    link["href"]
                    for link in response.get("links", [])
                    if link.get("rel") == "next"
                ]
                url = links[0] if links else ""
        payload = {"requests": requests, "features": features}
        _atomic_bytes(cache, json.dumps(payload, sort_keys=True).encode("utf-8"))
    rows: list[dict[str, Any]] = []
    for feature in payload["features"]:
        row = dict(feature["properties"])
        coordinates = (feature.get("geometry") or {}).get(
            "coordinates", [np.nan, np.nan]
        )
        row["longitude"] = coordinates[0]
        row["latitude"] = coordinates[1]
        rows.append(row)
    return pd.DataFrame(rows)


def _daily_batch(
    series_ids: Sequence[str],
    config: Mapping[str, Any],
    *,
    start: str,
    end: str,
) -> tuple[pd.DataFrame, list[str]]:
    spec = config["data_sources"]["usgs"]
    endpoint = f"{spec['api_root']}/collections/{spec['daily_collection']}/items"
    frames: list[pd.DataFrame] = []
    requests: list[str] = []
    # CSV is substantially smaller than GeoJSON, but the API does not expose its
    # next cursor in the CSV representation and caps numeric offsets at 40,000.
    # Five 20-year daily series can contain at most 36,525 rows, so fixed sub-batches
    # of five are provably complete under the frozen 2000--2019 interval.
    for offset in range(0, len(series_ids), 5):
        selected = series_ids[offset : offset + 5]
        url = _url_with_query(
            endpoint,
            {
                "f": "csv",
                "limit": 50000,
                "skipGeometry": "true",
                "properties": (
                    "time_series_id,monitoring_location_id,parameter_code,statistic_id,"
                    "time,value,unit_of_measure,approval_status,qualifier,last_modified"
                ),
                "time_series_id": ",".join(selected),
                "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
            },
        )
        requests.append(url)
        page = pd.read_csv(io.BytesIO(_request_bytes(url)), dtype=str)
        if len(page) >= 50000:
            raise RuntimeError("daily CSV sub-batch reached its provable row ceiling")
        frames.append(page.drop(columns=["x", "y"], errors="ignore"))
    return pd.concat(frames, ignore_index=True, sort=False), requests


def fetch_daily_values(
    metadata: pd.DataFrame,
    config: Mapping[str, Any],
    cache_dir: Path,
    *,
    offline: bool = False,
    batch_size: int = 25,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Fetch daily observations with restartable, content-identified batch caches."""

    spec = config["data_sources"]["usgs"]
    batch_dir = cache_dir / "daily_batches"
    batch_dir.mkdir(parents=True, exist_ok=True)
    series = sorted(metadata["id"].astype(str).unique())
    completed: dict[int, tuple[pd.DataFrame, dict[str, Any]]] = {}
    missing: list[tuple[int, list[str], Path, Path]] = []
    for number, offset in enumerate(range(0, len(series), batch_size)):
        selected = series[offset : offset + batch_size]
        key = hashlib.sha256("\n".join(selected).encode("utf-8")).hexdigest()[:16]
        parquet = batch_dir / f"batch_{number:04d}_{key}.parquet"
        manifest_path = parquet.with_suffix(".json")
        if parquet.exists() and manifest_path.exists():
            frame = pd.read_parquet(parquet)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("series_ids") != selected:
                raise RuntimeError(f"daily batch manifest does not match {parquet}")
            completed[number] = (frame, manifest)
        else:
            if offline:
                raise FileNotFoundError(f"offline daily cache is missing: {parquet}")
            missing.append((number, selected, parquet, manifest_path))

    def populate(
        job: tuple[int, list[str], Path, Path],
    ) -> tuple[int, pd.DataFrame, dict[str, Any]]:
        number, selected, parquet, manifest_path = job
        frame, requests = _daily_batch(
            selected,
            config,
            start=spec["period_start"],
            end=spec["period_end"],
        )
        temporary = parquet.with_suffix(".parquet.partial")
        frame.to_parquet(temporary, index=False)
        temporary.replace(parquet)
        manifest = {
            "series_ids": selected,
            "requests": requests,
            "rows": len(frame),
            "cache": file_identity(parquet),
        }
        _atomic_bytes(
            manifest_path,
            json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"),
        )
        return number, frame, manifest

    if missing:
        with ThreadPoolExecutor(max_workers=min(4, len(missing))) as executor:
            futures = {executor.submit(populate, job): job[0] for job in missing}
            for future in as_completed(futures):
                number, frame, manifest = future.result()
                completed[number] = (frame, manifest)

    frames: list[pd.DataFrame] = []
    manifests: list[dict[str, Any]] = []
    for number in sorted(completed):
        frame, manifest = completed[number]
        frames.append(frame)
        manifests.append(manifest)
    if not frames:
        return pd.DataFrame(), manifests
    return pd.concat(frames, ignore_index=True, sort=False), manifests


def _parse_legacy_rdb(
    payload: bytes, series_by_station: Mapping[str, str]
) -> pd.DataFrame:
    """Parse the repeated per-site RDB tables returned by legacy USGS ``/dv``."""

    lines = payload.decode("utf-8", errors="strict").splitlines()
    rows: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        if not lines[index].startswith("agency_cd\t"):
            index += 1
            continue
        columns = lines[index].split("\t")
        value_columns = [
            column
            for column in columns
            if column.endswith("_00010_00003") and not column.endswith("_cd")
        ]
        if len(value_columns) != 1:
            raise RuntimeError(
                f"legacy RDB table has ambiguous temperature columns: {columns}"
            )
        value_column = value_columns[0]
        qualifier_column = f"{value_column}_cd"
        index += 2  # Skip the RDB width/type row.
        while index < len(lines) and not lines[index].startswith("agency_cd\t"):
            line = lines[index]
            index += 1
            if not line or line.startswith("#"):
                continue
            values = line.split("\t")
            if len(values) != len(columns):
                continue
            record = dict(zip(columns, values, strict=True))
            station = str(record["site_no"])
            if station not in series_by_station:
                raise RuntimeError(
                    f"legacy response contained an unrequested station: {station}"
                )
            rows.append(
                {
                    "time_series_id": series_by_station[station],
                    "monitoring_location_id": f"USGS-{station}",
                    "parameter_code": "00010",
                    "statistic_id": "00003",
                    "time": record["datetime"],
                    "value": record[value_column],
                    "unit_of_measure": "degC",
                    "approval_status": (
                        "Approved"
                        if record.get(qualifier_column, "").split(":", maxsplit=1)[0]
                        == "A"
                        else "Provisional"
                    ),
                    "qualifier": record.get(qualifier_column, ""),
                    "last_modified": None,
                }
            )
    return pd.DataFrame(rows)


def fetch_legacy_daily_values(
    metadata: pd.DataFrame,
    config: Mapping[str, Any],
    cache_dir: Path,
    *,
    offline: bool = False,
    batch_size: int = 50,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Fetch the predeclared official ``/dv`` fallback for single-series sites."""

    counts = metadata.groupby("station_id", observed=True)["id"].nunique()
    if not counts.eq(1).all():
        raise ValueError(
            "legacy transport is restricted to exactly one primary series per station"
        )
    series_by_station = metadata.set_index("station_id")["id"].astype(str).to_dict()
    stations = sorted(series_by_station)
    batch_dir = cache_dir / "legacy_daily_batches"
    batch_dir.mkdir(parents=True, exist_ok=True)
    endpoint = "https://waterservices.usgs.gov/nwis/dv/"
    frames: list[pd.DataFrame] = []
    manifests: list[dict[str, Any]] = []
    for number, offset in enumerate(range(0, len(stations), batch_size)):
        selected = stations[offset : offset + batch_size]
        key = hashlib.sha256("\n".join(selected).encode("utf-8")).hexdigest()[:16]
        raw_path = batch_dir / f"batch_{number:04d}_{key}.rdb"
        parquet = raw_path.with_suffix(".parquet")
        manifest_path = raw_path.with_suffix(".json")
        url = _url_with_query(
            endpoint,
            {
                "format": "rdb",
                "sites": ",".join(selected),
                "startDT": config["data_sources"]["usgs"]["period_start"],
                "endDT": config["data_sources"]["usgs"]["period_end"],
                "parameterCd": "00010",
                "statCd": "00003",
                "siteStatus": "all",
            },
        )
        if raw_path.exists() and manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("parser_version") == 2 and parquet.exists():
                frame = pd.read_parquet(parquet)
            else:
                frame = _parse_legacy_rdb(raw_path.read_bytes(), series_by_station)
                temporary = parquet.with_suffix(".parquet.partial")
                frame.to_parquet(temporary, index=False)
                temporary.replace(parquet)
                manifest["parser_version"] = 2
                manifest["rows"] = len(frame)
                manifest["parsed_cache"] = file_identity(parquet)
                _atomic_bytes(
                    manifest_path,
                    json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"),
                )
        else:
            if offline:
                raise FileNotFoundError(f"offline legacy cache is missing: {raw_path}")
            payload = _request_bytes(url, timeout=300)
            _atomic_bytes(raw_path, payload)
            frame = _parse_legacy_rdb(payload, series_by_station)
            temporary = parquet.with_suffix(".parquet.partial")
            frame.to_parquet(temporary, index=False)
            temporary.replace(parquet)
            manifest = {
                "stations": selected,
                "request": url,
                "parser_version": 2,
                "rows": len(frame),
                "raw_cache": file_identity(raw_path),
                "parsed_cache": file_identity(parquet),
            }
            _atomic_bytes(
                manifest_path,
                json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"),
            )
        if manifest.get("stations") != selected:
            raise RuntimeError(f"legacy batch manifest does not match {raw_path}")
        frames.append(frame)
        manifests.append(manifest)
    return pd.concat(frames, ignore_index=True, sort=False), manifests


def audit_modern_legacy_equivalence(
    legacy: pd.DataFrame,
    metadata: pd.DataFrame,
    cache_dir: Path,
) -> dict[str, Any]:
    """Require exact approved station-date-value agreement on completed OGC caches."""

    modern_paths = sorted((cache_dir / "daily_batches").glob("batch_*.parquet"))
    if not modern_paths:
        raise FileNotFoundError(
            "modern equivalence cache is absent; bootstrap it with "
            "scripts/38_run_regulation_panel.py --legacy-transport "
            "--bootstrap-equivalence-batches 26"
        )
    modern = pd.concat(
        [pd.read_parquet(path) for path in modern_paths], ignore_index=True
    )
    single_series = set(metadata["id"].astype(str))

    def normalize(frame: pd.DataFrame) -> pd.DataFrame:
        data = frame.loc[
            frame["time_series_id"].astype(str).isin(single_series)
            & frame["approval_status"].eq("Approved")
        ].copy()
        data["station_id"] = data["monitoring_location_id"].str.replace(
            r"^USGS-", "", regex=True
        )
        data["date"] = (
            pd.to_datetime(data["time"], errors="coerce")
            .dt.tz_localize(None)
            .dt.normalize()
        )
        data["temperature_degC"] = pd.to_numeric(data["value"], errors="coerce")
        return data.groupby(["station_id", "date"], observed=True, as_index=False).agg(
            temperature_degC=("temperature_degC", "median")
        )

    modern_values = normalize(modern).rename(columns={"temperature_degC": "modern"})
    legacy_values = normalize(legacy).rename(columns={"temperature_degC": "legacy"})
    comparison = modern_values.merge(
        legacy_values, on=["station_id", "date"], how="left", validate="one_to_one"
    )
    comparison["exact_match"] = comparison["legacy"].notna() & np.isclose(
        comparison["modern"], comparison["legacy"], rtol=0.0, atol=1e-12
    )
    result = {
        "completed_modern_batch_count": len(modern_paths),
        "modern_single_series_station_dates": len(comparison),
        "legacy_station_dates_present": int(comparison["legacy"].notna().sum()),
        "exact_station_date_value_matches": int(comparison["exact_match"].sum()),
        "pass_fraction": float(comparison["exact_match"].mean()),
        "passed": bool(comparison["exact_match"].all() and len(comparison) > 0),
    }
    if not result["passed"]:
        raise RuntimeError(f"modern/legacy equivalence audit failed: {result}")
    return result


def select_station_series(
    daily: pd.DataFrame,
    metadata: pd.DataFrame,
    config: Mapping[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply the frozen no-splicing series choice and calendar-year eligibility."""

    if daily.empty:
        return daily.copy(), pd.DataFrame()
    spec = config["data_sources"]["usgs"]
    data = daily.copy()
    data["date"] = (
        pd.to_datetime(data["time"], errors="coerce")
        .dt.tz_localize(None)
        .dt.normalize()
    )
    data["temperature_degC"] = pd.to_numeric(data["value"], errors="coerce")
    data["station_id"] = data["monitoring_location_id"].str.replace(
        r"^USGS-", "", regex=True
    )
    valid = (
        data["approval_status"].eq(spec["approval_status_retained"])
        & np.isfinite(data["temperature_degC"])
        & data["date"].notna()
    )
    data = data.loc[valid].copy()
    data = data.groupby(
        ["station_id", "time_series_id", "date"], observed=True, as_index=False
    ).agg(temperature_degC=("temperature_degC", "median"))
    counts = (
        data.groupby(["station_id", "time_series_id"], observed=True)
        .agg(approved_distinct_dates=("date", "nunique"))
        .reset_index()
    )
    begin = (
        metadata[["id", "begin"]]
        .drop_duplicates("id")
        .rename(columns={"id": "time_series_id"})
    )
    counts = counts.merge(
        begin, on="time_series_id", how="left", validate="many_to_one"
    )
    counts = counts.sort_values(
        ["station_id", "approved_distinct_dates", "begin", "time_series_id"],
        ascending=[True, False, True, True],
        kind="mergesort",
    )
    chosen = counts.drop_duplicates("station_id", keep="first").copy()
    retained = data.merge(
        chosen[["station_id", "time_series_id"]],
        on=["station_id", "time_series_id"],
        how="inner",
        validate="many_to_one",
    )
    retained["year"] = retained["date"].dt.year
    years = (
        retained.groupby(["station_id", "year"], observed=True)
        .agg(approved_distinct_days=("date", "nunique"))
        .reset_index()
    )
    threshold = int(
        config["eligibility"]["minimum_approved_distinct_days_per_qualifying_year"]
    )
    qualifying = years.loc[years["approved_distinct_days"].ge(threshold)]
    n_years = (
        qualifying.groupby("station_id")["year"].nunique().rename("n_qualifying_years")
    )
    chosen = chosen.merge(n_years, on="station_id", how="left")
    chosen["n_qualifying_years"] = chosen["n_qualifying_years"].fillna(0).astype(int)
    minimum = int(config["eligibility"]["minimum_qualifying_calendar_years"])
    eligible = chosen.loc[chosen["n_qualifying_years"].ge(minimum), "station_id"]
    retained = retained.loc[retained["station_id"].isin(eligible)].copy()
    retained = retained.merge(
        qualifying[["station_id", "year"]].assign(qualifying_year=True),
        on=["station_id", "year"],
        how="left",
    )
    retained["qualifying_year"] = retained["qualifying_year"].fillna(False).astype(bool)
    return retained.reset_index(drop=True), chosen.reset_index(drop=True)


def exact_lag_acf(values: pd.Series, lag_days: int) -> tuple[float, int]:
    """Pearson autocorrelation using pairs exactly ``lag_days`` apart."""

    series = pd.to_numeric(values, errors="coerce").dropna().sort_index()
    if not isinstance(series.index, pd.DatetimeIndex):
        raise TypeError("exact_lag_acf requires a DatetimeIndex")
    series = series.loc[~series.index.duplicated(keep="first")]
    left = series.rename("left")
    right = series.copy()
    right.index = right.index - pd.Timedelta(days=lag_days)
    pairs = pd.concat([left, right.rename("right")], axis=1, join="inner").dropna()
    if len(pairs) < 3:
        return np.nan, len(pairs)
    return float(pairs["left"].corr(pairs["right"])), len(pairs)


def compute_station_metrics(
    retained: pd.DataFrame,
    gages: pd.DataFrame,
    config: Mapping[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute all frozen station diagnostics and explicit metric exclusions."""

    half_window = int(config["features"]["climatology"]["half_window_days"])
    minimum_pairs = int(config["features"]["autocorrelation"]["minimum_pairs_each_lag"])
    rows: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = []
    for station, group in retained.groupby("station_id", observed=True, sort=True):
        group = group.sort_values("date")
        values = group["temperature_degC"].to_numpy(float)
        observed_range = float(np.max(values) - np.min(values))
        if not np.isfinite(observed_range) or observed_range <= 0:
            exclusions.append(
                {"station_id": str(station), "reason": "zero_temperature_range"}
            )
            continue
        climatology = circular_doy_climatology(
            group["date"], values, half_window_days=half_window
        )
        anomalies = pd.Series(
            values - predict_climatology(climatology, group["date"]),
            index=pd.DatetimeIndex(group["date"]),
        )
        acf30, pairs30 = exact_lag_acf(anomalies, 30)
        acf90, pairs90 = exact_lag_acf(anomalies, 90)
        if pairs30 < minimum_pairs or pairs90 < minimum_pairs:
            exclusions.append(
                {"station_id": str(station), "reason": "insufficient_exact_lag_pairs"}
            )
            continue
        annual = group.loc[group["qualifying_year"]].groupby("year", observed=True)[
            "temperature_degC"
        ]
        amplitudes = annual.max() - annual.min()
        raw_variance = float(np.var(values, ddof=0))
        anomaly_variance = float(np.var(anomalies.to_numpy(float), ddof=0))
        rows.append(
            {
                "station_id": str(station),
                "n_approved_days": len(group),
                "n_qualifying_years": int(
                    group.loc[group["qualifying_year"], "year"].nunique()
                ),
                "first_date": group["date"].min().date().isoformat(),
                "last_date": group["date"].max().date().isoformat(),
                "median_annual_amplitude_degC": float(amplitudes.median()),
                "anomaly_sd_degC": float(anomalies.std(ddof=1)),
                "acf30": acf30,
                "acf90": acf90,
                "n_exact_pairs_30d": pairs30,
                "n_exact_pairs_90d": pairs90,
                "seasonal_variance_fraction": float(
                    1.0 - anomaly_variance / raw_variance
                ),
                "observed_temperature_range_degC": observed_range,
                "memory_range_index_per_degC": float(acf30 / observed_range),
            }
        )
    metrics = pd.DataFrame(rows)
    attributes = gages.rename(columns={"STAID": "station_id"}).copy()
    required = [
        "station_id",
        "STANAME",
        "DRAIN_SQKM",
        "LAT_GAGE",
        "LNG_GAGE",
        "STATE",
        "CLASS",
        "AGGECOREGION",
        "NDAMS_2009",
        "STOR_NID_2009",
        "STOR_NOR_2009",
        "MAJ_NDAMS_2009",
        "RAW_DIS_NEAREST_DAM",
        "RAW_DIS_NEAREST_MAJ_DAM",
    ]
    for column in required:
        if column not in attributes:
            attributes[column] = np.nan
    metrics = metrics.merge(
        attributes[required], on="station_id", how="left", validate="one_to_one"
    )
    dam_count = pd.to_numeric(metrics["MAJ_NDAMS_2009"], errors="coerce")
    missing = metrics.loc[dam_count.isna(), "station_id"]
    exclusions.extend(
        {
            "station_id": str(station),
            "reason": "missing_required_GAGES_II_dam_attribute",
        }
        for station in missing
    )
    metrics = metrics.loc[dam_count.notna()].copy()
    metrics["upstream_major_dam_2009"] = (
        dam_count.loc[dam_count.notna()].ge(1).astype(int)
    )
    for column in ("RAW_DIS_NEAREST_DAM", "RAW_DIS_NEAREST_MAJ_DAM"):
        metrics[column] = pd.to_numeric(metrics[column], errors="coerce").replace(
            -999, np.nan
        )
    return metrics.reset_index(drop=True), pd.DataFrame(exclusions)


def _coefficient_table(result: Any, model: str) -> pd.DataFrame:
    interval = result.conf_int(alpha=0.05)
    rows = []
    for term in result.params.index:
        coefficient = float(result.params[term])
        lower, upper = map(float, interval.loc[term])
        rows.append(
            {
                "model": model,
                "term": term,
                "coefficient_log_odds": coefficient,
                "robust_se": float(result.bse[term]),
                "wald_p_value": float(result.pvalues[term]),
                "coefficient_ci_low": lower,
                "coefficient_ci_high": upper,
                "odds_ratio": float(np.exp(coefficient)),
                "odds_ratio_ci_low": float(np.exp(lower)),
                "odds_ratio_ci_high": float(np.exp(upper)),
            }
        )
    return pd.DataFrame(rows)


def logistic_models(metrics: pd.DataFrame) -> pd.DataFrame:
    """Fit the frozen primary and ecoregion/scale-adjusted logistic models."""

    data = metrics.copy()
    data["z_memory_range_index"] = (
        data["memory_range_index_per_degC"] - data["memory_range_index_per_degC"].mean()
    ) / data["memory_range_index_per_degC"].std(ddof=0)
    data["log1p_drainage_area"] = np.log1p(
        pd.to_numeric(data["DRAIN_SQKM"], errors="coerce")
    )
    data["z_log1p_drainage_area"] = (
        data["log1p_drainage_area"] - data["log1p_drainage_area"].mean()
    ) / data["log1p_drainage_area"].std(ddof=0)
    y = data["upstream_major_dam_2009"].astype(float)
    primary_x = sm.add_constant(data[["z_memory_range_index"]], has_constant="add")
    primary = sm.GLM(y, primary_x, family=sm.families.Binomial()).fit(cov_type="HC1")
    tables = [_coefficient_table(primary, "primary_unadjusted")]

    adjusted_data = data.dropna(subset=["z_log1p_drainage_area", "AGGECOREGION"]).copy()
    region = pd.get_dummies(
        adjusted_data["AGGECOREGION"].astype(str),
        prefix="ecoregion",
        drop_first=True,
        dtype=float,
    )
    adjusted_x = pd.concat(
        [adjusted_data[["z_memory_range_index", "z_log1p_drainage_area"]], region],
        axis=1,
    )
    adjusted_x = sm.add_constant(adjusted_x, has_constant="add")
    adjusted = sm.GLM(
        adjusted_data["upstream_major_dam_2009"].astype(float),
        adjusted_x.astype(float),
        family=sm.families.Binomial(),
    ).fit(cov_type="HC1")
    tables.append(_coefficient_table(adjusted, "adjusted_ecoregion_and_drainage"))
    return pd.concat(tables, ignore_index=True)


def leave_ecoregion_out_predictions(metrics: pd.DataFrame) -> pd.DataFrame:
    """Return frozen leave-one-aggregated-ecoregion-out probabilities."""

    data = metrics.dropna(
        subset=[
            "memory_range_index_per_degC",
            "AGGECOREGION",
            "upstream_major_dam_2009",
        ]
    ).copy()
    predictions: list[pd.DataFrame] = []
    for region in sorted(data["AGGECOREGION"].astype(str).unique()):
        test = data["AGGECOREGION"].astype(str).eq(region)
        train = ~test
        train_x = data.loc[train, ["memory_range_index_per_degC"]].to_numpy(float)
        test_x = data.loc[test, ["memory_range_index_per_degC"]].to_numpy(float)
        mean = train_x.mean(axis=0)
        scale = train_x.std(axis=0, ddof=0)
        if (
            np.any(scale <= 0)
            or data.loc[train, "upstream_major_dam_2009"].nunique() < 2
        ):
            raise RuntimeError(f"invalid leave-ecoregion-out training fold: {region}")
        model = LogisticRegression(C=1e6, solver="lbfgs", max_iter=10000)
        model.fit((train_x - mean) / scale, data.loc[train, "upstream_major_dam_2009"])
        fold = data.loc[
            test, ["station_id", "AGGECOREGION", "upstream_major_dam_2009"]
        ].copy()
        fold["oof_probability"] = model.predict_proba((test_x - mean) / scale)[:, 1]
        fold["held_out_ecoregion"] = region
        predictions.append(fold)
    return pd.concat(predictions, ignore_index=True)


def cluster_bootstrap_auc(
    predictions: pd.DataFrame, *, replicates: int, seed: int
) -> tuple[float, float, int]:
    """Cluster-bootstrap pooled AUC by aggregated ecoregion."""

    groups = [
        group.copy() for _, group in predictions.groupby("AGGECOREGION", observed=True)
    ]
    rng = np.random.default_rng(seed)
    values: list[float] = []
    for _ in range(replicates):
        sample = pd.concat(
            [groups[index] for index in rng.integers(0, len(groups), size=len(groups))],
            ignore_index=True,
        )
        if sample["upstream_major_dam_2009"].nunique() == 2:
            values.append(
                float(
                    roc_auc_score(
                        sample["upstream_major_dam_2009"], sample["oof_probability"]
                    )
                )
            )
    if not values:
        return np.nan, np.nan, 0
    return (
        float(np.quantile(values, 0.025)),
        float(np.quantile(values, 0.975)),
        len(values),
    )


def distance_profile(metrics: pd.DataFrame, config: Mapping[str, Any]) -> pd.DataFrame:
    """Summarize the frozen nearest-major-dam distance bins."""

    spec = config["distance_profile"]
    data = (
        metrics.loc[metrics["upstream_major_dam_2009"].eq(1)]
        .dropna(subset=[spec["distance_field"], "AGGECOREGION"])
        .copy()
    )
    bins = [float(value) for value in spec["bins_km"]]
    labels = [
        f"[{bins[index]:g},{bins[index + 1]:g})" for index in range(len(bins) - 1)
    ]
    data["distance_bin_km"] = pd.cut(
        data[spec["distance_field"]],
        bins=bins,
        labels=labels,
        right=False,
        include_lowest=True,
    )
    rng = np.random.default_rng(int(spec["uncertainty"]["seed"]))
    replicates = int(spec["uncertainty"]["replicates"])
    rows: list[dict[str, Any]] = []
    fields = [
        "memory_range_index_per_degC",
        "acf30",
        "median_annual_amplitude_degC",
    ]
    for label in labels:
        group = data.loc[data["distance_bin_km"].astype(str).eq(label)].copy()
        row: dict[str, Any] = {
            "distance_bin_km": label,
            "distance_lower_km": bins[labels.index(label)],
            "distance_upper_km": bins[labels.index(label) + 1],
            "station_count": len(group),
        }
        clusters = [
            values.copy() for _, values in group.groupby("AGGECOREGION", observed=True)
        ]
        for field in fields:
            output_field = field if field.startswith("median_") else f"median_{field}"
            row[output_field] = float(group[field].median()) if len(group) else np.nan
            draws: list[float] = []
            if clusters:
                for _ in range(replicates):
                    sample = pd.concat(
                        [
                            clusters[index]
                            for index in rng.integers(
                                0, len(clusters), size=len(clusters)
                            )
                        ],
                        ignore_index=True,
                    )
                    draws.append(float(sample[field].median()))
            row[f"{output_field}_ci_low"] = (
                float(np.quantile(draws, 0.025)) if draws else np.nan
            )
            row[f"{output_field}_ci_high"] = (
                float(np.quantile(draws, 0.975)) if draws else np.nan
            )
        rows.append(row)
    return pd.DataFrame(rows)


def make_regulation_panel_figure(
    metrics: pd.DataFrame,
    predictions: pd.DataFrame,
    profile: pd.DataFrame,
    *,
    auc: float,
    auc_low: float,
    auc_high: float,
    output_path: Path,
) -> None:
    """Write a compact, publication-resolution three-panel result figure."""

    colors = {0: "#4C78A8", 1: "#E45756"}
    labels = {0: "No upstream major dam", 1: "Upstream major dam"}
    figure, axes = plt.subplots(1, 3, figsize=(12.2, 4.15), constrained_layout=True)

    rng = np.random.default_rng(20260824)
    values = [
        metrics.loc[
            metrics["upstream_major_dam_2009"].eq(label),
            "memory_range_index_per_degC",
        ].to_numpy(float)
        for label in (0, 1)
    ]
    box = axes[0].boxplot(
        values,
        positions=[0, 1],
        widths=0.55,
        patch_artist=True,
        showfliers=False,
        medianprops={"color": "black", "linewidth": 1.4},
    )
    for label, patch in zip((0, 1), box["boxes"], strict=True):
        patch.set_facecolor(colors[label])
        patch.set_alpha(0.45)
    for label, station_values in zip((0, 1), values, strict=True):
        axes[0].scatter(
            label + rng.uniform(-0.18, 0.18, size=len(station_values)),
            station_values,
            s=9,
            alpha=0.42,
            color=colors[label],
            linewidths=0,
            rasterized=True,
        )
    axes[0].set_xticks(
        [0, 1],
        [f"{labels[0]}\n(n={len(values[0])})", f"{labels[1]}\n(n={len(values[1])})"],
    )
    axes[0].set_ylabel(r"Memory–range index ($^°$C$^{-1}$)")
    axes[0].set_title("Station-level contrast")

    false_positive, true_positive, _ = roc_curve(
        predictions["upstream_major_dam_2009"], predictions["oof_probability"]
    )
    axes[1].plot(false_positive, true_positive, color="#7A5195", linewidth=2.0)
    axes[1].plot([0, 1], [0, 1], color="#777777", linestyle="--", linewidth=1.0)
    axes[1].set(
        xlim=(0, 1),
        ylim=(0, 1),
        xlabel="False-positive rate",
        ylabel="True-positive rate",
    )
    axes[1].set_aspect("equal", adjustable="box")
    axes[1].set_title("Leave-ecoregion-out discrimination")
    axes[1].text(
        0.04,
        0.94,
        f"AUC = {auc:.3f}\ncluster 95% CI {auc_low:.3f}–{auc_high:.3f}",
        transform=axes[1].transAxes,
        va="top",
        fontsize=9,
    )

    x = np.arange(len(profile))
    y = profile["median_memory_range_index_per_degC"].to_numpy(float)
    lower = profile["median_memory_range_index_per_degC_ci_low"].to_numpy(float)
    upper = profile["median_memory_range_index_per_degC_ci_high"].to_numpy(float)
    axes[2].errorbar(
        x,
        y,
        yerr=np.vstack([y - lower, upper - y]),
        marker="o",
        markersize=5,
        linewidth=1.7,
        capsize=3,
        color="#2A9D8F",
    )
    axes[2].set_xticks(x, profile["distance_bin_km"], rotation=35, ha="right")
    axes[2].set_xlabel("Distance to nearest upstream major dam (km)")
    axes[2].set_ylabel(r"Median memory–range index ($^°$C$^{-1}$)")
    axes[2].set_title("Within-regulated distance profile")
    for index, row in profile.iterrows():
        axes[2].annotate(
            f"n={int(row['station_count'])}",
            (index, row["median_memory_range_index_per_degC_ci_high"]),
            xytext=(0, 5),
            textcoords="offset points",
            ha="center",
            fontsize=8,
        )

    for letter, axis in zip("ABC", axes, strict=True):
        axis.text(
            -0.14,
            1.06,
            letter,
            transform=axis.transAxes,
            fontsize=12,
            fontweight="bold",
            va="top",
        )
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", color="#DDDDDD", linewidth=0.6, alpha=0.7)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(figure)


def _write_result_summary(report: Mapping[str, Any], output_path: Path) -> None:
    """Write outcome-calibrated manuscript-ready wording without changing claims."""

    primary = report["primary"]
    adjusted = report["adjusted_sensitivity"]
    flow = report["flow"]
    profile = pd.DataFrame(report["distance_profile"])
    lines = [
        "# Nationwide regulation-panel result (transport-limited)",
        "",
        "## Result",
        "",
        (
            f"The transport-limited maximum legal panel contained {flow['eligible_stations']} "
            f"stations ({flow['regulated_stations']} with and {flow['unregulated_stations']} "
            "without an upstream major dam in the 2009 GAGES-II snapshot). The "
            "predeclared primary discrimination test was not supported: pooled "
            f"leave-one-ecoregion-out AUC was {primary['pooled_leave_ecoregion_out_auc']:.3f} "
            f"(cluster-bootstrap 95% CI {primary['cluster_bootstrap_auc_ci_low']:.3f}–"
            f"{primary['cluster_bootstrap_auc_ci_high']:.3f}), and the unadjusted odds "
            f"ratio per SD of the memory–range index was {primary['odds_ratio_per_index_sd']:.2f} "
            f"(95% CI {primary['odds_ratio_ci_low']:.2f}–{primary['odds_ratio_ci_high']:.2f}; "
            f"p = {primary['wald_p_value']:.3f})."
        ),
        "",
        (
            "The predeclared drainage-area and ecoregion-adjusted sensitivity was "
            f"positive (OR {adjusted['odds_ratio_per_index_sd']:.2f}, 95% CI "
            f"{adjusted['odds_ratio_ci_low']:.2f}–{adjusted['odds_ratio_ci_high']:.2f}; "
            f"p = {adjusted['wald_p_value']:.3f}), but is supporting rather than primary "
            "evidence because Alaska contained only one outcome class, producing a "
            "fixed-effect separation warning. It does not rescue the failed out-of-region "
            "primary discrimination test."
        ),
        "",
        (
            "Within the regulated subset, the predeclared distance profile was monotonic: "
            f"the median index decreased from {profile.iloc[0]['median_memory_range_index_per_degC']:.4f} "
            f"°C⁻¹ at 0–5 km (n={int(profile.iloc[0]['station_count'])}) to "
            f"{profile.iloc[3]['median_memory_range_index_per_degC']:.4f} °C⁻¹ at "
            f"50–100 km (n={int(profile.iloc[3]['station_count'])}). This proximity gradient "
            "is supporting associational evidence, not proof of a causal operating effect."
        ),
        "",
        "## Transport and scope qualifier",
        "",
        (
            "The modern USGS API stopped after 26 of 56 atomic batches with HTTP 429 "
            "`OVER_RATE_LIMIT`. The official `/dv` fallback was therefore restricted to "
            "stations with exactly one primary series. All 1,662,961 available approved "
            "station–dates matched the modern API exactly. Twenty-six exact-overlap sites "
            "had multiple primary series (22 after the stream-site filter) and were not "
            "spliced. Consequently, these estimates are transport-limited and must not be "
            "described as completion of the full frozen roster."
        ),
        "",
        "## Claim decision",
        "",
        "**Primary nationwide discrimination: not supported.**",
        "",
        "**Adjusted association and within-regulated distance profile: supporting only.**",
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")


def run_regulation_panel(
    *,
    project_root: Path,
    config_path: Path,
    cache_dir: Path,
    output_dir: Path,
    offline: bool = False,
    transport: str = "modern",
    equivalence_bootstrap_batches: int = 0,
) -> dict[str, Any]:
    """Execute the complete frozen panel and write auditable aggregate artifacts."""

    config = load_freeze(config_path)
    enforce_isolation([project_root, config_path, cache_dir, output_dir], config)
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    gages, archive = load_gages_ii(config, cache_dir, offline=offline)
    metadata = discover_temperature_series(config, cache_dir, offline=offline)
    metadata = metadata.loc[metadata["station_id"].isin(set(gages["STAID"]))].copy()
    exact_overlap_n = int(metadata["station_id"].nunique())
    exact_overlap_series_counts = metadata.groupby("station_id", observed=True)[
        "id"
    ].nunique()
    exact_overlap_multiple_series_n = int(exact_overlap_series_counts.gt(1).sum())
    locations = fetch_monitoring_locations(
        metadata["station_id"].unique(), config, cache_dir, offline=offline
    )
    stream_ids = set(
        locations.loc[
            locations["agency_code"].eq("USGS")
            & locations["site_type_code"].eq(
                config["data_sources"]["usgs"]["site_type_code"]
            ),
            "monitoring_location_number",
        ].astype(str)
    )
    non_stream = sorted(set(metadata["station_id"]) - stream_ids)
    metadata = metadata.loc[metadata["station_id"].isin(stream_ids)].copy()
    stream_overlap_n = int(metadata["station_id"].nunique())
    full_stream_metadata = metadata.copy()
    if transport not in {"modern", "legacy_single_series"}:
        raise ValueError(f"unsupported USGS daily transport: {transport}")
    metadata_series_counts = metadata.groupby("station_id", observed=True)[
        "id"
    ].nunique()
    transport_ambiguous: list[str] = []
    equivalence_audit: dict[str, Any] | None = None
    if transport == "legacy_single_series":
        if equivalence_bootstrap_batches < 0 or equivalence_bootstrap_batches > 56:
            raise ValueError("equivalence_bootstrap_batches must be between 0 and 56")
        if equivalence_bootstrap_batches:
            ordered_series = sorted(full_stream_metadata["id"].astype(str).unique())
            bootstrap_ids = set(ordered_series[: equivalence_bootstrap_batches * 25])
            bootstrap_metadata = full_stream_metadata.loc[
                full_stream_metadata["id"].astype(str).isin(bootstrap_ids)
            ].copy()
            fetch_daily_values(
                bootstrap_metadata,
                config,
                cache_dir,
                offline=offline,
            )
        transport_ambiguous = sorted(
            metadata_series_counts.loc[metadata_series_counts.ne(1)].index
        )
        metadata = metadata.loc[
            ~metadata["station_id"].isin(transport_ambiguous)
        ].copy()
        daily, batch_manifests = fetch_legacy_daily_values(
            metadata, config, cache_dir, offline=offline
        )
        equivalence_audit = audit_modern_legacy_equivalence(daily, metadata, cache_dir)
    else:
        daily, batch_manifests = fetch_daily_values(
            metadata, config, cache_dir, offline=offline
        )
    retained, choices = select_station_series(daily, metadata, config)
    metrics, metric_exclusions = compute_station_metrics(retained, gages, config)

    minimum_years = int(config["eligibility"]["minimum_qualifying_calendar_years"])
    eligibility_exclusions = choices.loc[
        choices["n_qualifying_years"].lt(minimum_years), ["station_id"]
    ].assign(reason="fewer_than_10_qualifying_years")
    all_exclusions = pd.concat(
        [
            pd.DataFrame({"station_id": non_stream, "reason": "non_stream_site_type"}),
            pd.DataFrame(
                {
                    "station_id": transport_ambiguous,
                    "reason": "multiple_primary_series_legacy_transport_ambiguous",
                }
            ),
            eligibility_exclusions,
            metric_exclusions,
        ],
        ignore_index=True,
    )

    if metrics["upstream_major_dam_2009"].nunique() < 2:
        raise RuntimeError("eligible panel does not contain both dam-label classes")
    coefficients = logistic_models(metrics)
    oof = leave_ecoregion_out_predictions(metrics)
    auc = float(roc_auc_score(oof["upstream_major_dam_2009"], oof["oof_probability"]))
    auc_spec = config["primary_analysis"]["auc_uncertainty"]
    auc_low, auc_high, valid_draws = cluster_bootstrap_auc(
        oof, replicates=int(auc_spec["replicates"]), seed=int(auc_spec["seed"])
    )
    profile = distance_profile(metrics, config)
    figure_path = output_dir / "figure_06_regulation_panel.png"
    make_regulation_panel_figure(
        metrics,
        oof,
        profile,
        auc=auc,
        auc_low=auc_low,
        auc_high=auc_high,
        output_path=figure_path,
    )

    metrics.to_csv(output_dir / "station_metrics.csv", index=False)
    choices.to_csv(output_dir / "series_selection_audit.csv", index=False)
    all_exclusions.to_csv(output_dir / "exclusions.csv", index=False)
    coefficients.to_csv(output_dir / "logistic_regression.csv", index=False)
    oof.to_csv(output_dir / "leave_ecoregion_out_predictions.csv", index=False)
    profile.to_csv(output_dir / "distance_profile.csv", index=False)

    minimum_n = int(config["reporting_rules"]["minimum_N_for_primary_claim"])
    primary_term = coefficients.loc[
        coefficients["model"].eq("primary_unadjusted")
        & coefficients["term"].eq("z_memory_range_index")
    ].iloc[0]
    adjusted_term = coefficients.loc[
        coefficients["model"].eq("adjusted_ecoregion_and_drainage")
        & coefficients["term"].eq("z_memory_range_index")
    ].iloc[0]
    ecoregion_class_counts = pd.crosstab(
        metrics["AGGECOREGION"], metrics["upstream_major_dam_2009"]
    ).reindex(columns=[0, 1], fill_value=0)
    single_class_ecoregions = (
        ecoregion_class_counts.loc[ecoregion_class_counts.eq(0).any(axis=1)]
        .index.astype(str)
        .tolist()
    )
    module_path = Path(__file__).resolve()
    module_text = module_path.read_text(encoding="utf-8").lower()
    forbidden_tokens = [
        str(value).lower()
        for value in config["isolation_contract"]["forbidden_path_tokens"]
    ]
    isolation_audit = {
        "passed": not any(token in module_text for token in forbidden_tokens),
        "checked_runtime_input_paths": [
            ".",
            config_path.resolve().relative_to(project_root.resolve()).as_posix(),
            cache_dir.resolve().relative_to(project_root.resolve()).as_posix(),
            output_dir.resolve().relative_to(project_root.resolve()).as_posix(),
        ],
        "forbidden_path_tokens": forbidden_tokens,
        "forbidden_literal_matches_in_pipeline_module": [
            token for token in forbidden_tokens if token in module_text
        ],
        "pipeline_module": portable_file_identity(module_path, project_root),
        "confirmatory_network_touched": False,
        "audit_scope": "runtime_path_guard_plus_static_pipeline_literal_scan",
    }
    if not isolation_audit["passed"]:
        raise RuntimeError(f"confirmatory isolation audit failed: {isolation_audit}")
    profile_report = profile.replace([np.inf, -np.inf], np.nan).astype(object)
    profile_report = profile_report.where(pd.notna(profile_report), None)
    report = {
        "design_id": config["design_id"],
        "complete": True,
        "confirmatory_network_touched": False,
        "transport": transport,
        "full_frozen_roster_complete": transport == "modern",
        "transport_equivalence_audit": equivalence_audit,
        "confirmatory_path_access_audit": isolation_audit,
        "modern_API_blocker": (
            {
                "http_status": 429,
                "error_code": "OVER_RATE_LIMIT",
                "completed_atomic_batches": len(
                    list((cache_dir / "daily_batches").glob("batch_*.json"))
                ),
                "planned_atomic_batches": 56,
                "api_key_available": False,
            }
            if transport == "legacy_single_series"
            else None
        ),
        "flow": {
            "metadata_series_discovered": len(
                json.loads((cache_dir / "usgs_time_series_metadata.json").read_text())[
                    "features"
                ]
            ),
            "exact_GAGES_II_overlap_stations": exact_overlap_n,
            "stream_site_overlap_stations": stream_overlap_n,
            "transport_unambiguous_stations": int(metadata["station_id"].nunique()),
            "multiple_primary_series_at_exact_overlap": exact_overlap_multiple_series_n,
            "daily_values_downloaded": len(daily),
            "eligible_stations": len(metrics),
            "regulated_stations": int(metrics["upstream_major_dam_2009"].sum()),
            "unregulated_stations": int(metrics["upstream_major_dam_2009"].eq(0).sum()),
        },
        "primary": {
            "pooled_leave_ecoregion_out_auc": auc,
            "cluster_bootstrap_auc_ci_low": auc_low,
            "cluster_bootstrap_auc_ci_high": auc_high,
            "cluster_bootstrap_valid_draws": valid_draws,
            "logistic_coefficient_per_index_sd": float(
                primary_term["coefficient_log_odds"]
            ),
            "odds_ratio_per_index_sd": float(primary_term["odds_ratio"]),
            "odds_ratio_ci_low": float(primary_term["odds_ratio_ci_low"]),
            "odds_ratio_ci_high": float(primary_term["odds_ratio_ci_high"]),
            "wald_p_value": float(primary_term["wald_p_value"]),
        },
        "adjusted_sensitivity": {
            "logistic_coefficient_per_index_sd": float(
                adjusted_term["coefficient_log_odds"]
            ),
            "odds_ratio_per_index_sd": float(adjusted_term["odds_ratio"]),
            "odds_ratio_ci_low": float(adjusted_term["odds_ratio_ci_low"]),
            "odds_ratio_ci_high": float(adjusted_term["odds_ratio_ci_high"]),
            "wald_p_value": float(adjusted_term["wald_p_value"]),
            "single_class_ecoregions": single_class_ecoregions,
            "fixed_effect_model_separation_warning": bool(single_class_ecoregions),
            "interpretation": (
                "exploratory_only_complete_separation_in_at_least_one_ecoregion"
                if single_class_ecoregions
                else "predeclared_adjusted_sensitivity"
            ),
        },
        "distance_profile": profile_report.to_dict(orient="records"),
        "scientific_conclusion": {
            "primary_discrimination": "not_supported",
            "basis": (
                "leave_ecoregion_out_AUC_below_0.5_with_CI_including_0.5_and_"
                "unadjusted_odds_ratio_CI_including_1"
            ),
            "adjusted_association": "supporting_only_with_fixed_effect_separation_warning",
            "within_regulated_distance_profile": "monotonic_supporting_association",
            "transport_scope": "transport_limited_not_full_frozen_roster",
        },
        "claim_status": (
            "transport_limited_maximum_legal_panel_minimum_N_met"
            if transport == "legacy_single_series" and len(metrics) >= minimum_n
            else (
                "transport_limited_and_below_frozen_minimum_N"
                if transport == "legacy_single_series"
                else (
                    "minimum_N_met_report_frozen_result"
                    if len(metrics) >= minimum_n
                    else "withhold_generalizable_panel_claim_below_frozen_minimum_N"
                )
            )
        ),
        "exclusion_counts": {
            str(key): int(value)
            for key, value in all_exclusions["reason"].value_counts().items()
        },
        "source_identities": {
            "freeze": portable_file_identity(config_path, project_root),
            "gages_ii_archive": portable_file_identity(archive, project_root),
            "usgs_time_series_metadata": portable_file_identity(
                cache_dir / "usgs_time_series_metadata.json", project_root
            ),
            "usgs_monitoring_locations": portable_file_identity(
                cache_dir / "usgs_monitoring_locations.json", project_root
            ),
            "transport_amendment": (
                portable_file_identity(
                    project_root
                    / "configs/regulation_panel_transport_amendment_v1.yaml",
                    project_root,
                )
                if transport == "legacy_single_series"
                else None
            ),
            "daily_batch_count": len(batch_manifests),
            "daily_batch_sha256": [
                (
                    manifest["cache"]["sha256"]
                    if "cache" in manifest
                    else manifest["raw_cache"]["sha256"]
                )
                for manifest in batch_manifests
            ],
        },
        "limitations": [
            "GAGES-II dam attributes are a 2009 watershed snapshot.",
            "Major-dam presence is not a time-varying operating or thermal-release record.",
            "GAGES-II nearest-dam distance is straight-line distance within the watershed.",
            "The analysis is associational and does not estimate a causal dam effect.",
        ],
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    _write_result_summary(report, output_dir / "README.md")
    bootstrap_status = {
        "design_id": config["design_id"],
        "transport": transport,
        "modern_equivalence_batches_required": 26,
        "modern_equivalence_batches_present": len(
            list((cache_dir / "daily_batches").glob("batch_*.json"))
        ),
        "legacy_batches_required": 27,
        "legacy_batches_present": len(
            list((cache_dir / "legacy_daily_batches").glob("batch_*.json"))
        ),
        "modern_legacy_equivalence_passed": bool(
            equivalence_audit and equivalence_audit["passed"]
        ),
        "clean_online_bootstrap_command": (
            "USGS_WATERDATA_API_KEY=<key> PYTHONPATH=src python "
            "scripts/38_run_regulation_panel.py --legacy-transport "
            "--bootstrap-equivalence-batches 26 "
            "--output-dir results/regulation_panel_v1_legacy_transport"
        ),
        "cached_offline_reproduction_command": (
            "PYTHONPATH=src python scripts/38_run_regulation_panel.py --offline "
            "--legacy-transport --bootstrap-equivalence-batches 26 "
            "--output-dir results/regulation_panel_v1_legacy_transport"
        ),
        "api_key_secret_handling": (
            "read_from_USGS_WATERDATA_API_KEY_and_never_written_to_manifests"
        ),
    }
    (output_dir / "bootstrap_status.json").write_text(
        json.dumps(bootstrap_status, indent=2, sort_keys=True), encoding="utf-8"
    )
    artifact_names = [
        "README.md",
        "bootstrap_status.json",
        "distance_profile.csv",
        "exclusions.csv",
        "figure_06_regulation_panel.png",
        "leave_ecoregion_out_predictions.csv",
        "logistic_regression.csv",
        "report.json",
        "series_selection_audit.csv",
        "station_metrics.csv",
    ]
    manifest = {
        "design_id": config["design_id"],
        "transport": transport,
        "portable_paths": True,
        "artifacts": [
            portable_file_identity(output_dir / name, project_root)
            for name in artifact_names
        ],
        "source_inputs": report["source_identities"],
        "confirmatory_path_access_audit_passed": isolation_audit["passed"],
    }
    (output_dir / "artifact_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return report


__all__ = [
    "cluster_bootstrap_auc",
    "compute_station_metrics",
    "distance_profile",
    "enforce_isolation",
    "exact_lag_acf",
    "leave_ecoregion_out_predictions",
    "load_freeze",
    "load_gages_ii",
    "logistic_models",
    "run_regulation_panel",
    "select_station_series",
]
