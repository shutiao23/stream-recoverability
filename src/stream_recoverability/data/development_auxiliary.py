"""Plain parallel meteorology and hydraulics acquisition for open networks.

The input roster comes from the completed development and validation QC
directories.  Every run downloads the selected sources again and overwrites
the two materialized tables in each selected network directory.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import numpy as np
import pandas as pd

POWER_START = "1981-01-01"
POWER_ENDPOINT = "https://power.larc.nasa.gov/api/temporal/daily/point"
NWIS_ENDPOINT = "https://waterservices.usgs.gov/nwis/dv/"
POWER_VARIABLES = {
    "Ta": ("T2M", "C", "degC"),
    "P": ("PRECTOTCORR", "mm/day", "mm/day"),
    "W": ("WS2M", "m/s", "m/s"),
    "RH": ("RH2M", "%", "%"),
    "Rs": ("ALLSKY_SFC_SW_DWN", "MJ/m^2/day", "MJ/m^2/day"),
}
NWIS_VARIABLES = {
    "00060": ("F", "ft^3/s", "m3/s", 0.028316846592),
    "00065": ("L", "ft", "m", 0.3048),
}
OUTPUT_COLUMNS = (
    "date",
    "site_id",
    "station_id",
    "variable",
    "raw_name",
    "source",
    "raw_text",
    "source_value_original",
    "raw_value",
    "value",
    "raw_unit",
    "unit",
    "conversion_factor",
    "unit_conversion",
    "natural_observed",
    "quality_approved",
    "approval_status",
    "qualifier_json",
    "estimated_qualifier",
    "qc_status",
    "time_series_id",
    "source_feature_id",
    "source_last_modified",
    "source_longitude",
    "source_latitude",
    "interpretation",
    "quality_basis",
)


@dataclass(frozen=True)
class Site:
    site_id: str
    start: str
    end: str
    longitude: float
    latitude: float


@dataclass(frozen=True)
class Network:
    network_id: str
    role: str
    sites: tuple[Site, ...]


@dataclass(frozen=True)
class Request:
    network_id: str
    kind: str
    site_id: str | None
    url: str


def _site_id(value: object) -> str:
    return str(value).strip().zfill(8)


def discover_networks(repository_root: str | Path) -> tuple[Network, ...]:
    """Read the current completed open-role QC roster and public coordinates."""

    root = Path(repository_root)
    qc_root = root / "data_versions/global_network_corpus_v1/open_role_qc/failure_closure6"
    locations = pd.read_csv(
        root / "results/framework/public_catalog/usgs_long_temperature_locations.csv",
        dtype={"site_id": "string"},
    )
    locations["site_id"] = locations["site_id"].map(_site_id)
    locations = locations.set_index("site_id")
    networks: list[Network] = []
    for role in ("development", "validation"):
        network_root = qc_root / role / "networks"
        for manifest_path in sorted(network_root.glob("*/network_qc_manifest.json")):
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest["overlap"]["complete_enough"] is not True:
                continue
            network_dir = manifest_path.parent
            columns = pd.read_csv(network_dir / "daily_wide_qc.csv", nrows=0).columns
            station_ids = tuple(sorted(_site_id(value) for value in columns[1:]))
            dates = pd.read_csv(
                network_dir / "daily_long_qc.csv",
                usecols=["site_id", "date"],
                dtype={"site_id": "string", "date": "string"},
            )
            dates["site_id"] = dates["site_id"].map(_site_id)
            dates = dates.loc[dates["site_id"].isin(station_ids)]
            windows = dates.groupby("site_id")["date"].agg(["min", "max"])
            sites = tuple(
                Site(
                    site_id=station_id,
                    start=str(windows.loc[station_id, "min"]),
                    end=str(windows.loc[station_id, "max"]),
                    longitude=float(locations.loc[station_id, "longitude"]),
                    latitude=float(locations.loc[station_id, "latitude"]),
                )
                for station_id in station_ids
            )
            networks.append(Network(manifest_path.parent.name, role, sites))
    return tuple(sorted(networks, key=lambda value: (value.role, value.network_id)))


def power_url(site: Site) -> str:
    start = max(site.start, POWER_START).replace("-", "")
    end = site.end.replace("-", "")
    query = urllib.parse.urlencode(
        {
            "parameters": ",".join(value[0] for value in POWER_VARIABLES.values()),
            "community": "AG",
            "longitude": site.longitude,
            "latitude": site.latitude,
            "start": start,
            "end": end,
            "format": "JSON",
            "time-standard": "UTC",
        }
    )
    return f"{POWER_ENDPOINT}?{query}"


def nwis_url(network: Network) -> str:
    query = urllib.parse.urlencode(
        {
            "format": "rdb",
            "sites": ",".join(site.site_id for site in network.sites),
            "startDT": min(site.start for site in network.sites),
            "endDT": max(site.end for site in network.sites),
            "parameterCd": "00060,00065",
            "statCd": "00003",
            "siteStatus": "all",
        }
    )
    return f"{NWIS_ENDPOINT}?{query}"


def requests_for(network: Network) -> tuple[Request, ...]:
    return (
        Request(network.network_id, "nwis", None, nwis_url(network)),
        *(
            Request(network.network_id, "power", site.site_id, power_url(site))
            for site in network.sites
        ),
    )


def download(url: str, timeout: int = 180) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json,text/plain",
            "User-Agent": "stream-recoverability-development/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def parse_power(payload: bytes, site: Site) -> pd.DataFrame:
    document = json.loads(payload)
    fill_value = float(document["header"]["fill_value"])
    parameters = document["properties"]["parameter"]
    coordinates = document["geometry"]["coordinates"]
    frames = []
    for variable, (code, raw_unit, unit) in POWER_VARIABLES.items():
        values = parameters[code]
        numeric = np.asarray(tuple(values.values()), dtype=float)
        observed = numeric != fill_value
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(tuple(values), format="%Y%m%d"),
                "raw_text": tuple(str(value) for value in values.values()),
                "source_value_original": numeric,
                "raw_value": numeric,
                "value": np.where(observed, numeric, np.nan),
                "natural_observed": observed,
                "quality_approved": observed,
                "qc_status": np.where(
                    observed, "provider_value", "provider_fill_value"
                ),
            }
        )
        frame["site_id"] = site.site_id
        frame["station_id"] = site.site_id
        frame["variable"] = variable
        frame["raw_name"] = code
        frame["source"] = "nasa_power_daily_point"
        frame["raw_unit"] = raw_unit
        frame["unit"] = unit
        frame["conversion_factor"] = 1.0
        frame["unit_conversion"] = "identity"
        frame["approval_status"] = "NotApplicable"
        frame["qualifier_json"] = "[]"
        frame["estimated_qualifier"] = False
        frame["time_series_id"] = None
        frame["source_feature_id"] = None
        frame["source_last_modified"] = None
        frame["source_longitude"] = float(coordinates[0])
        frame["source_latitude"] = float(coordinates[1])
        frame["interpretation"] = {
            "Ta": "daily_air_temperature_at_2_m",
            "P": "daily_corrected_precipitation",
            "W": "daily_wind_speed_at_2_m",
            "RH": "daily_relative_humidity_at_2_m",
            "Rs": "daily_all_sky_surface_shortwave_radiation",
        }[variable]
        frame["quality_basis"] = "NASA POWER finite non-fill-value screen"
        frames.append(frame.loc[:, OUTPUT_COLUMNS])
    return pd.concat(frames, ignore_index=True)


def parse_nwis(payload: bytes) -> pd.DataFrame:
    lines = payload.decode("utf-8").splitlines()
    tables = []
    position = 0
    while position < len(lines):
        if not lines[position].startswith("agency_cd\tsite_no\tdatetime"):
            position += 1
            continue
        columns = lines[position].split("\t")
        position += 2
        records = []
        while position < len(lines) and not lines[position].startswith(
            "agency_cd\tsite_no\tdatetime"
        ):
            line = lines[position]
            position += 1
            if line and not line.startswith("#"):
                records.append(line.split("\t"))
        if records:
            tables.append(pd.DataFrame(records, columns=columns))
    if not tables:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    frames = []
    for table in tables:
        for column in table.columns:
            match = re.fullmatch(r"(.+)_(00060|00065)_00003", column)
            if match is None:
                continue
            code = match.group(2)
            variable, raw_unit, unit, factor = NWIS_VARIABLES[code]
            qualifier_column = f"{column}_cd"
            selected = table.loc[
                table[column].notna() & table[column].str.strip().ne(""),
                ["site_no", "datetime", column, qualifier_column],
            ].copy()
            if selected.empty:
                continue
            raw_text = selected[column].str.strip()
            numeric = pd.to_numeric(raw_text, errors="coerce")
            finite = np.isfinite(numeric)
            qualifiers = selected[qualifier_column].fillna("").str.strip()
            approved = finite & qualifiers.str.match(
                r"^A(?:$|:)", case=False, na=False
            )
            estimated = qualifiers.str.lower().str.split(":").map(
                lambda parts: "e" in parts
            )
            frame = pd.DataFrame(
                {
                    "date": pd.to_datetime(selected["datetime"]),
                    "site_id": selected["site_no"].map(_site_id),
                    "station_id": selected["site_no"].map(_site_id),
                    "raw_text": raw_text,
                    "source_value_original": numeric.where(finite),
                    "raw_value": numeric.where(finite),
                    "value": (numeric * factor).where(approved),
                    "natural_observed": finite,
                    "quality_approved": approved,
                    "approval_status": np.where(approved, "Approved", "Provisional"),
                    "qualifier_json": qualifiers.map(lambda value: json.dumps([value])),
                    "estimated_qualifier": estimated,
                    "qc_status": np.where(
                        approved & estimated,
                        "approved_estimated",
                        np.where(
                            approved,
                            "approved",
                            np.where(
                                finite,
                                "excluded_provisional",
                                "excluded_non_numeric_provider_code",
                            ),
                        ),
                    ),
                }
            )
            frame["variable"] = variable
            frame["raw_name"] = code
            frame["source"] = "usgs_legacy_nwis_dv_rdb"
            frame["raw_unit"] = raw_unit
            frame["unit"] = unit
            frame["conversion_factor"] = factor
            frame["unit_conversion"] = (
                "m3_per_s = ft3_per_s * 0.028316846592"
                if variable == "F"
                else "m = ft * 0.3048"
            )
            frame["time_series_id"] = match.group(1)
            frame["source_feature_id"] = None
            frame["source_last_modified"] = None
            frame["source_longitude"] = np.nan
            frame["source_latitude"] = np.nan
            frame["interpretation"] = (
                "daily_mean_discharge"
                if variable == "F"
                else "daily_mean_gage_height"
            )
            frame["quality_basis"] = "legacy NWIS RDB qualifier prefix A only"
            frames.append(frame.loc[:, OUTPUT_COLUMNS])
    if not frames:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    return pd.concat(frames, ignore_index=True)


def coverage(network: Network, daily: pd.DataFrame) -> pd.DataFrame:
    counts = daily.groupby(["site_id", "variable"])["quality_approved"].agg(
        n_provider_rows="size",
        n_provider_eligible_rows="sum",
    )
    rows = []
    for site in network.sites:
        for variable in (*POWER_VARIABLES, "F", "L"):
            request_start = max(site.start, POWER_START) if variable in POWER_VARIABLES else site.start
            expected = len(pd.date_range(request_start, site.end, freq="D"))
            key = (site.site_id, variable)
            if key in counts.index:
                provider_rows = int(counts.loc[key, "n_provider_rows"])
                eligible = int(counts.loc[key, "n_provider_eligible_rows"])
            else:
                provider_rows = 0
                eligible = 0
            rows.append(
                {
                    "network_id": network.network_id,
                    "role": network.role,
                    "site_id": site.site_id,
                    "variable": variable,
                    "information_group": "M" if variable in POWER_VARIABLES else "H",
                    "target_start": site.start,
                    "request_start": request_start,
                    "request_end": site.end,
                    "n_target_calendar_days": len(pd.date_range(site.start, site.end, freq="D")),
                    "n_expected_provider_days": expected,
                    "n_provider_rows": provider_rows,
                    "n_provider_eligible_rows": eligible,
                    "provider_row_coverage": provider_rows / expected,
                    "eligible_coverage": eligible / expected,
                    "pre_power_archive_days": (
                        len(pd.date_range(site.start, POWER_START, freq="D")) - 1
                        if variable in POWER_VARIABLES and site.start < POWER_START
                        else 0
                    ),
                    "source_status": "materialized" if provider_rows else "unavailable",
                }
            )
    return pd.DataFrame(rows)


def _materialize(
    network: Network,
    responses: dict[tuple[str, str, str | None], bytes],
    output_root: Path,
) -> dict[str, object]:
    frames = [parse_nwis(responses[(network.network_id, "nwis", None)])]
    frames.extend(
        parse_power(
            responses[(network.network_id, "power", site.site_id)],
            site,
        )
        for site in network.sites
    )
    daily = pd.concat([frame for frame in frames if not frame.empty], ignore_index=True)
    windows = {
        site.site_id: (pd.Timestamp(site.start), pd.Timestamp(site.end))
        for site in network.sites
    }
    dates = pd.to_datetime(daily["date"])
    starts = daily["site_id"].map({key: value[0] for key, value in windows.items()})
    ends = daily["site_id"].map({key: value[1] for key, value in windows.items()})
    keep = starts.notna() & dates.ge(starts) & dates.le(ends)
    daily = daily.loc[keep].sort_values(["site_id", "date", "variable"])
    daily["date"] = pd.to_datetime(daily["date"]).dt.strftime("%Y-%m-%d")
    network_output = output_root / network.role / "networks" / network.network_id
    network_output.mkdir(parents=True, exist_ok=True)
    daily_path = network_output / "daily_long_auxiliary.parquet"
    coverage_path = network_output / "coverage.csv"
    daily.to_parquet(daily_path, index=False)
    coverage_table = coverage(network, daily)
    coverage_table.to_csv(coverage_path, index=False)
    return {
        "network_id": network.network_id,
        "role": network.role,
        "n_sites": len(network.sites),
        "n_rows": len(daily),
        "n_available_site_variables": int(coverage_table["n_provider_rows"].gt(0).sum()),
        "n_site_variables": len(coverage_table),
        "daily_long_auxiliary": str(daily_path),
        "coverage": str(coverage_path),
    }


def acquire_network(
    network: Network,
    output_root: str | Path,
    fetcher: Callable[[str], bytes] = download,
) -> dict[str, object]:
    responses = {}
    for request in requests_for(network):
        responses[(request.network_id, request.kind, request.site_id)] = fetcher(
            request.url
        )
    return _materialize(network, responses, Path(output_root))


def run_acquisition(
    repository_root: str | Path,
    output_root: str | Path,
    *,
    network_ids: Sequence[str] = (),
    roles: Sequence[str] = ("development", "validation"),
    max_networks: int | None = None,
    workers: int = 8,
    fetcher: Callable[[str], bytes] = download,
) -> dict[str, object]:
    """Download selected requests concurrently and overwrite network outputs."""

    selected = [
        network
        for network in discover_networks(repository_root)
        if network.role in roles
        and (not network_ids or network.network_id in set(network_ids))
    ]
    if max_networks is not None:
        selected = selected[:max_networks]
    n_requests = sum(len(requests_for(network)) for network in selected)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        network_results = list(
            executor.map(
                lambda network: acquire_network(network, output_root, fetcher),
                selected,
            )
        )
    return {
        "output_root": str(output_root),
        "n_networks": len(selected),
        "n_sites": sum(len(network.sites) for network in selected),
        "n_requests": n_requests,
        "workers": workers,
        "networks": network_results,
    }


__all__ = [
    "Network",
    "Request",
    "Site",
    "acquire_network",
    "coverage",
    "discover_networks",
    "download",
    "nwis_url",
    "parse_nwis",
    "parse_power",
    "power_url",
    "requests_for",
    "run_acquisition",
]
