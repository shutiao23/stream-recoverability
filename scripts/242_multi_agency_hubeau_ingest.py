#!/usr/bin/env python3
"""Hub'Eau (France) river-temperature ingest for the pre-registered transport test.

Feeds ``results/wrr_submission_ready/MULTI_AGENCY_TRANSPORT_PROTOCOL.md``
(pre-registered before any transport panel was fetched).  This script only
ingests and QC-labels; it never scores the frozen certificate.

Read-only inputs (never written here)
-------------------------------------
``src/stream_recoverability/data/hubeau_temperature.py`` records that Sandre
qualification code 1 ("Correcte") was absent on the previously audited long
series and that sampled stations (06213500, 06175400, 06151000, 05223000) are
entirely code 4 ("Non qualifie").  That audit was a sample, so this ingest
*measures* the qualification composition instead of assuming it: global counts
for every code, and a per-station count for every candidate station, are
retrieved from the API and written to ``raw_cache/``.

Assurance rule (never mix codes inside one station)
---------------------------------------------------
* code 1 (Correcte) is preferred; a station is ingested as code 1 only when its
  code-1 observation count can support the frozen four-complete-year floor
  (``--min-score-observations``, default 1461 = 4 x 365 + 1);
* otherwise code 4 (Non qualifie) is ingested and the station is labelled
  ``quality = "unqualified (Sandre code 4)"`` in every stations.csv and in
  ingest.json -- a lower-assurance subset that must be reported as such;
* codes 2 (Incorrecte) and 3 (Incertaine) are never ingested;
* a station never receives two codes, so no station silently mixes codes.

Aggregation rule (measurement provenance)
-----------------------------------------
Hub'Eau ``chronique`` rows are instantaneous observations (``date_mesure_temp``
plus ``heure_mesure_temp``).  Daily value = arithmetic mean of the acceptable
observations on that calendar day, using only days with at least
``--min-obs-per-day`` acceptable observations (default 4).  Days with zero
acceptable observations and days below the floor are counted and reported, never
interpolated.  Complete calendar year = every calendar day of that year carries
a daily value (the frozen rule used by
``experiments/wrr_revision/universe.py`` ``full_calendar_year`` and by
``scripts/234_wrr_sealed_confirmation_score.py``); only years that have ended
are considered.

API constraints honoured
------------------------
``page * size`` never exceeds 20,000 and windows are split by date rather than
deep-paged (``HUBEAU_MAX_WINDOW_RECORDS`` / ``hubeau_window_url`` in the shared
module).  Loire last-check site ids are refused, as in the shared module.

Note on the code-4 path: the shared module's download helpers request Sandre
code 1 only, so a code-4 ingest is impossible through them.  This script builds
the window URL itself and asserts byte-equality with the module's
``hubeau_window_url`` for every code-1 request, so the qualified path is exactly
the module's path.

Outputs (all under ``results/wrr_submission_ready/multi_agency_ingest/hubeau/``)
-------------------------------------------------------------------------------
``networks/<network_id>/daily_wide_temperature.csv``  wide, first column
``date``, one column per station id, blank where missing;
``networks/<network_id>/stations.csv`` and ``stations.csv``  per-station
provenance and QC;
``networks/<network_id>/ingest.json`` and ``ingest.json``  retrieval UTC, exact
API URL templates, counts by qualification code, aggregation rule, caveats;
``raw_cache/``  every API response (gzip JSON envelope with url + retrieval
time), the request manifest, station table, span screen, qualification counts.
"""

from __future__ import annotations

import argparse
import calendar
import gzip
import hashlib
import json
import math
import re
import sys
import time
import unicodedata
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.hubeau_temperature import (  # noqa: E402
    HUBEAU_CHRONIQUE,
    HUBEAU_CORRECT_QUALIFICATION,
    HUBEAU_PAGE_SIZE,
    LOIRE_PATTERN,
    cluster_hubeau_rivers,
    hubeau_chronique_rows,
    hubeau_window_url,
)
from stream_recoverability.data.http_json import get_json  # noqa: E402
from stream_recoverability.data.v2_download_policy import last_check_site_ids  # noqa: E402

OUT_ROOT = ROOT / "results" / "wrr_submission_ready" / "multi_agency_ingest" / "hubeau"
RAW = OUT_ROOT / "raw_cache"
NETWORKS = OUT_ROOT / "networks"
STATION_API = "https://hubeau.eaufrance.fr/api/v1/temperature/station"

PROVIDER = "hubeau"
AGENCY = "Hub'Eau / Eaufrance (Office francais de la biodiversite), France"
QUALIFICATION_CODES = ("1", "2", "3", "4")
CODE_LABELS = {
    "1": "Correcte",
    "2": "Incorrecte",
    "3": "Incertaine",
    "4": "Non qualifie",
}
ACCEPTED_CODES = ("1", "4")
PLAUSIBLE_TEMPERATURE_C = (-2.0, 45.0)
MIN_COMPLETE_YEARS = 4
MIN_STATIONS_PER_NETWORK = 2
WATERBODY_RIVER_URI = "MasseDEauRiviere_VEDL2019"
# A water-body label that *is* a standing water body (not a river reach merely
# bounded by a dam) is treated as non-river evidence.
STANDING_WATERBODY_PREFIX = re.compile(
    r"^\s*(lac|lacs|etang|étang|retenue|reservoir|réservoir|plan d'eau|plans d'eau|"
    r"graviere|gravière|lagune|bassin d'arcachon)\b",
    re.IGNORECASE,
)
# Drop rule: evidence that the *station itself* is in the sea or an estuary.
# A river reach label that merely names the sea as its downstream boundary
# ("L'Aude de la Cesse a la mer Mediterranee") is not such evidence and is
# retained (counted separately as a mention).
SEA_ESTUARY_LOCATION = re.compile(
    r"(^\s*(mer|ocean|océan|estuaire|rade|golfe|baie|lagune)\b"
    r"|\b(mer|ocean|océan|estuaire|rade|golfe|baie|lagune)\s+(de|d'|du|des|d’)\b"
    r"|\b(en mer|milieu marin|domaine maritime|marin littoral|milieu estuarien)\b)",
    re.IGNORECASE,
)
SEA_ESTUARY_MENTION = re.compile(
    r"\b(mer|ocean|océan|estuaire|rade|golfe|baie|lagune|littoral|marin|maritime)\b",
    re.IGNORECASE,
)
CANALISED_NAME = re.compile(r"canalis|\bcanal\b|\bbief\b", re.IGNORECASE)

PRIOR_ARTIFACTS = (
    ROOT / "results" / "v17_fitness" / "step1_panel" / "station_roster.csv",
    ROOT / "results" / "wrr_revision" / "step1_universe" / "trusted_river_complete_years.csv",
    ROOT / "results" / "wrr_submission_ready" / "prior_access_ledger_reserved_station_years.csv",
    ROOT / "results" / "wrr_submission_ready" / "confirmation_inputs_manifest.csv",
)
PRIOR_SCAN_DIRS = (
    ROOT / "results" / "v17_fitness" / "step1_panel",
    ROOT / "results" / "wrr_revision" / "step1_universe",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# cached API access
# --------------------------------------------------------------------------- #
class CachedHub:
    """Cached, manifestable Hub'Eau GET. page*size never exceeds 20,000."""

    def __init__(
        self,
        raw: Path,
        *,
        workers: int,
        timeout: int,
        retries: int,
        pause: float,
        outer_retries: int = 3,
    ):
        self.raw = Path(raw)
        self.workers = max(1, int(workers))
        self.timeout = int(timeout)
        self.retries = int(retries)
        self.pause = float(pause)
        self.outer_retries = max(1, int(outer_retries))
        self.failures: list[dict[str, Any]] = []

    def path(self, kind: str, name: str) -> Path:
        return self.raw / kind / f"{name}.json.gz"

    def read(self, kind: str, name: str) -> dict[str, Any] | None:
        dest = self.path(kind, name)
        if not dest.is_file():
            return None
        with gzip.open(dest, "rt", encoding="utf-8") as handle:
            return json.loads(handle.read())

    def get(self, url: str, *, kind: str, name: str, refresh: bool = False) -> dict[str, Any]:
        cached = None if refresh else self.read(kind, name)
        if cached is not None:
            return cached["document"]
        document = None
        last_error: Exception | None = None
        # Hub'Eau sometimes closes a connection without a response
        # (http.client.RemoteDisconnected), which the shared get_json retry policy
        # does not cover; retry the whole request here before giving up loudly.
        for attempt in range(self.outer_retries):
            try:
                document = get_json(url, timeout=self.timeout, retries=self.retries)
                break
            except Exception as error:  # noqa: BLE001
                last_error = error
                time.sleep(min(2.0 * (attempt + 1), 10.0))
        if document is None:
            raise RuntimeError(
                f"Hub'Eau request failed after {self.outer_retries} outer attempts: "
                f"{type(last_error).__name__}: {last_error}"
            ) from last_error
        if self.pause:
            time.sleep(self.pause)
        envelope = {
            "url": url,
            "retrieved_utc": utc_now(),
            "kind": kind,
            "label": name,
            "document": document,
        }
        dest = self.path(kind, name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as handle:
            json.dump(envelope, handle, sort_keys=True, ensure_ascii=False)
        tmp.replace(dest)
        return document

    def get_many(
        self,
        requests: Sequence[tuple[str, str, str]],
        *,
        refresh: bool = False,
        progress: str = "",
    ) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
        """requests: (url, kind, name). Returns (name -> document, failures)."""

        results: dict[str, dict[str, Any]] = {}
        failures: list[dict[str, Any]] = []
        pending = []
        for url, kind, name in requests:
            cached = None if refresh else self.read(kind, name)
            if cached is not None:
                results[name] = cached["document"]
            else:
                pending.append((url, kind, name))
        total = len(requests)
        done = len(results)
        if progress:
            print(f"    {progress}: {done}/{total} cached, {len(pending)} to fetch", flush=True)
        if pending:
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                futures = {
                    pool.submit(self.get, url, kind=kind, name=name, refresh=refresh): (url, kind, name)
                    for url, kind, name in pending
                }
                for future in futures:
                    url, kind, name = futures[future]
                    try:
                        results[name] = future.result()
                    # Every transport failure is retained and reported, not hidden.
                    except Exception as error:  # noqa: BLE001
                        item = {
                            "kind": kind,
                            "name": name,
                            "url": url,
                            "error": f"{type(error).__name__}: {error}",
                        }
                        failures.append(item)
                        self.failures.append(item)
                        print(f"    FAILED {kind} {name}: {item['error']}", flush=True)
                    done += 1
                    if progress and done % 50 == 0:
                        print(f"    {progress}: {done}/{total}", flush=True)
        return results, failures

    def manifest(self) -> pd.DataFrame:
        rows = []
        for path in sorted(self.raw.rglob("*.json.gz")):
            try:
                with gzip.open(path, "rt", encoding="utf-8") as handle:
                    envelope = json.loads(handle.read())
            except (OSError, json.JSONDecodeError) as error:  # pragma: no cover
                rows.append(
                    {
                        "kind": path.parent.name,
                        "label": path.name,
                        "url": None,
                        "retrieved_utc": None,
                        "n_records": None,
                        "api_count": None,
                        "payload_sha256": None,
                        "error": str(error),
                    }
                )
                continue
            if "url" not in envelope:
                rows.append(
                    {
                        "kind": path.parent.name,
                        "label": path.name,
                        "url": None,
                        "retrieved_utc": None,
                        "n_records": None,
                        "api_count": None,
                        "payload_sha256": None,
                        "cache_path": str(path.relative_to(ROOT)),
                        "error": "not a scripts/242 cache envelope (ignored)",
                    }
                )
                continue
            document = envelope.get("document") or {}
            data = document.get("data") or []
            rows.append(
                {
                    "kind": envelope.get("kind"),
                    "label": envelope.get("label"),
                    "url": envelope.get("url"),
                    "retrieved_utc": envelope.get("retrieved_utc"),
                    "n_records": int(len(data)),
                    "api_count": document.get("count"),
                    "payload_sha256": sha256_text(
                        json.dumps(document, sort_keys=True, ensure_ascii=False)
                    ),
                    "cache_path": str(path.relative_to(ROOT)),
                }
            )
        frame = pd.DataFrame(rows)
        if not frame.empty:
            frame = frame.sort_values(["kind", "label"]).reset_index(drop=True)
        return frame


# --------------------------------------------------------------------------- #
# URL construction
# --------------------------------------------------------------------------- #
def _chronique_url(**params: str) -> str:
    return HUBEAU_CHRONIQUE + "?" + urllib.parse.urlencode(params)


def span_url(station_id: str, order: str) -> str:
    return _chronique_url(
        code_station=str(station_id), size="1", page="1", sort=order
    )


def qualification_count_url(station_id: str, code: str) -> str:
    return _chronique_url(
        code_station=str(station_id), code_qualification=str(code), size="1", page="1"
    )


def window_url(station_id: str, start: str, end: str, code: str) -> str:
    """One dated window for one station and one Sandre qualification code.

    The code-1 URL is asserted byte-identical to the shared module's
    ``hubeau_window_url`` so the qualified path is the module's path.
    """

    params = {
        "code_station": str(station_id),
        "date_debut_mesure": str(start),
        "date_fin_mesure": str(end),
        "code_qualification": str(code),
        "size": str(HUBEAU_PAGE_SIZE),
        "page": "1",
        "sort": "asc",
    }
    url = _chronique_url(**params)
    if str(code) == HUBEAU_CORRECT_QUALIFICATION:
        canonical = hubeau_window_url(str(station_id), str(start), str(end))
        if url != canonical:
            raise RuntimeError(
                "code-1 window URL diverges from hubeau_window_url:\n"
                f"  script: {url}\n  module: {canonical}"
            )
    return url


def _window_needs_split(document: dict[str, Any]) -> bool:
    data = document.get("data") or []
    count = int(document.get("count") or 0)
    has_next = bool(document.get("next") or document.get("api_next"))
    return bool(
        has_next or count > HUBEAU_PAGE_SIZE or len(data) >= HUBEAU_PAGE_SIZE
    )


def fetch_window(
    hub: CachedHub,
    station_id: str,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
    code: str,
    *,
    depth: int = 0,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    """Dated window fetch with recursive date splitting (no deep paging)."""

    if depth > 24:
        raise RuntimeError(f"Hub'Eau date split exceeded depth for {station_id} {start_ts}-{end_ts}")
    start = start_ts.strftime("%Y-%m-%d")
    end = end_ts.strftime("%Y-%m-%d")
    name = f"{station_id}_{code}_{start}_{end}"
    document = hub.get(window_url(station_id, start, end, code), kind="chronique", name=name)
    if _window_needs_split(document) and start_ts != end_ts:
        mid = start_ts + (end_ts - start_ts) // 2
        left = fetch_window(hub, station_id, start_ts, mid, code, depth=depth + 1, refresh=refresh)
        right = fetch_window(
            hub, station_id, mid + pd.Timedelta(days=1), end_ts, code, depth=depth + 1, refresh=refresh
        )
        return left + right
    if _window_needs_split(document):
        raise RuntimeError(
            f"single-day window still exceeds {HUBEAU_PAGE_SIZE} records for {station_id} {start}"
        )
    return rows_from_document(document)


def rows_from_document(document: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in document.get("data") or []:
        rows.append(
            {
                "date": item.get("date_mesure_temp"),
                "time": item.get("heure_mesure_temp"),
                "temperature_c": item.get("resultat"),
                "quality_code": item.get("code_qualification"),
                "quality_label": item.get("libelle_qualification"),
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# station table and river classification
# --------------------------------------------------------------------------- #
def build_station_table(document: dict[str, Any], *, dropped: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in document.get("data") or []:
        uri = item.get("uri_masse_eau") or ""
        match = re.search(r"id\.eaufrance\.fr/([^/]+)/", uri)
        waterbody_type = match.group(1) if match else None
        name = str(item.get("libelle_station") or "")
        river = str(item.get("libelle_cours_eau") or "")
        waterbody = str(item.get("libelle_masse_eau") or "")
        localisation = str(item.get("localisation") or "")
        station_id = str(item.get("code_station"))

        reasons = []
        if waterbody_type is None:
            if river.strip():
                waterbody_class = "river_by_name_evidence"
            else:
                waterbody_class = "unknown"
                reasons.append("no_waterbody_class_and_no_river_name")
        elif waterbody_type == WATERBODY_RIVER_URI:
            waterbody_class = "river"
        else:
            waterbody_class = "non_river_waterbody_class"
            reasons.append(f"waterbody_class={waterbody_type}")
        if waterbody_class != "unknown" and STANDING_WATERBODY_PREFIX.search(waterbody):
            reasons.append("standing_waterbody_label")
        if waterbody_class != "unknown" and (
            SEA_ESTUARY_LOCATION.search(name) or SEA_ESTUARY_LOCATION.search(waterbody)
        ):
            reasons.append("sea_or_estuary_station_evidence")
        if waterbody_class == "unknown":
            reasons.append("not_a_river_station")

        river_name = river or waterbody
        if waterbody_class != "unknown" and not str(river_name).strip():
            reasons.append("no_river_name_evidence")
        rows.append(
            {
                "station_id": station_id,
                "station_name": name,
                "river_name": river_name,
                "river_name_source": "libelle_cours_eau" if river else ("libelle_masse_eau" if waterbody else None),
                "code_cours_eau": item.get("code_cours_eau"),
                "waterbody_name": waterbody or None,
                "code_masse_eau": item.get("code_masse_eau"),
                "waterbody_type": waterbody_type,
                "waterbody_class": waterbody_class,
                "in_river_panel": not reasons,
                "drop_reasons": ";".join(reasons),
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
                "bassin": item.get("libelle_bassin"),
                "sous_bassin": item.get("libelle_sous_bassin"),
                "region": item.get("libelle_region"),
                "departement": item.get("libelle_departement"),
                "commune": item.get("libelle_commune"),
                "altitude_m": item.get("altitude"),
                "nature_station": item.get("nature_station"),
                "localisation": localisation or None,
                "date_mise_en_service": item.get("date_mise_en_service"),
                "date_mise_hors_service": item.get("date_mise_hors_service"),
                "canalised_name_flag": bool(CANALISED_NAME.search(name) or CANALISED_NAME.search(river)),
                "sea_estuary_mention_in_waterbody_label": bool(
                    SEA_ESTUARY_MENTION.search(waterbody) or SEA_ESTUARY_MENTION.search(river)
                ),
            }
        )
    frame = pd.DataFrame(rows)
    for row in frame.loc[~frame["in_river_panel"]].itertuples(index=False):
        dropped.append(
            {
                "station_id": row.station_id,
                "station_name": row.station_name,
                "waterbody_class": row.waterbody_class,
                "waterbody_name": row.waterbody_name,
                "river_name": row.river_name,
                "drop_reasons": row.drop_reasons,
            }
        )
    return frame


def normalize_river(name: Any) -> str:
    if name is None or (isinstance(name, float) and math.isnan(name)):
        return ""
    text = unicodedata.normalize("NFKD", str(name).strip())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().strip()
    text = re.sub(r"^(le|la|les|los|las|l'|l’)\s+", "", text)
    text = text.replace("’", "'")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return "" if text in {"nan", "none", "null"} else text


def slugify(name: str) -> str:
    text = normalize_river(name).replace(" ", "_")
    return text or "unnamed"


# --------------------------------------------------------------------------- #
# daily aggregation and complete years
# --------------------------------------------------------------------------- #
def per_day_table(rows: Iterable[dict[str, Any]]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Reduce one window of instantaneous observations to per-day count and sum.

    Keeping the sum (not the mean) makes the reduction exactly composable across
    API windows, so a station downloaded year by year yields the same daily mean
    as a single download.
    """

    frame = pd.DataFrame(list(rows))
    total = int(len(frame))
    if frame.empty:
        return pd.DataFrame(columns=["date", "n_obs", "temp_sum"]), {
            "n_obs_downloaded": 0,
            "n_obs_dropped_qc": 0,
            "n_obs_accepted": 0,
            "dropped_out_of_range": 0,
            "dropped_unparsable": 0,
            "dropped_non_finite": 0,
            "n_time_stamps_present": 0,
        }
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame["temperature_c"] = pd.to_numeric(frame["temperature_c"], errors="coerce")
    unparsable = int(frame["date"].isna().sum())
    non_finite = int(frame["temperature_c"].isna().sum())
    finite = frame.loc[frame["date"].notna() & frame["temperature_c"].notna()]
    low, high = PLAUSIBLE_TEMPERATURE_C
    in_range = finite["temperature_c"].between(low, high)
    out_of_range = int((~in_range).sum())
    accepted = finite.loc[in_range]
    counts = (
        accepted.groupby("date")["temperature_c"]
        .agg(n_obs="size", temp_sum="sum")
        .reset_index()
    )
    qc = {
        "n_obs_downloaded": total,
        "n_obs_dropped_qc": unparsable + non_finite + out_of_range,
        "n_obs_accepted": int(len(accepted)),
        "dropped_out_of_range": out_of_range,
        "dropped_unparsable": unparsable,
        "dropped_non_finite": non_finite,
        "n_time_stamps_present": int(frame["time"].notna().sum()) if "time" in frame.columns else 0,
    }
    return counts, qc


def daily_values(per_day: pd.DataFrame, *, min_obs_per_day: int) -> pd.DataFrame:
    """Daily mean of acceptable observations for days meeting the observation floor."""

    if per_day.empty:
        return pd.DataFrame(columns=["date", "n_obs", "temperature_c"])
    formed = per_day.loc[per_day["n_obs"] >= int(min_obs_per_day)].copy()
    formed["temperature_c"] = formed["temp_sum"] / formed["n_obs"]
    return formed[["date", "n_obs", "temperature_c"]].sort_values("date").reset_index(drop=True)


def per_day_qc(per_day: pd.DataFrame, *, min_obs_per_day: int) -> dict[str, Any]:
    if per_day.empty:
        return {
            "n_days_with_obs": 0,
            "n_days_below_min_obs": 0,
            "n_days_daily_value": 0,
            "median_obs_per_observed_day": float("nan"),
            "max_obs_per_day": 0,
            "min_obs_per_day_observed": 0,
        }
    return {
        "n_days_with_obs": int(len(per_day)),
        "n_days_below_min_obs": int((per_day["n_obs"] < int(min_obs_per_day)).sum()),
        "n_days_daily_value": int((per_day["n_obs"] >= int(min_obs_per_day)).sum()),
        "median_obs_per_observed_day": float(per_day["n_obs"].median()),
        "max_obs_per_day": int(per_day["n_obs"].max()),
        "min_obs_per_day_observed": int(per_day["n_obs"].min()),
    }


def merge_per_day(parts: Sequence[pd.DataFrame]) -> pd.DataFrame:
    frames = [part for part in parts if not part.empty]
    if not frames:
        return pd.DataFrame(columns=["date", "n_obs", "temp_sum"])
    merged = pd.concat(frames, ignore_index=True)
    merged = (
        merged.groupby("date", as_index=False)
        .agg(n_obs=("n_obs", "sum"), temp_sum=("temp_sum", "sum"))
        .sort_values("date")
        .reset_index(drop=True)
    )
    return merged


def year_ended(year: int, as_of: pd.Timestamp) -> bool:
    return pd.Timestamp(year=int(year), month=12, day=31) < pd.Timestamp(as_of).normalize()


def year_coverage(daily: pd.DataFrame, *, as_of: pd.Timestamp) -> pd.DataFrame:
    """Coverage of every calendar year touched by the daily series."""

    if daily.empty:
        return pd.DataFrame(columns=["year", "expected_days", "observed_days", "year_ended", "complete"])
    series = daily.set_index("date")["temperature_c"]
    rows = []
    for year, block in series.groupby(series.index.year):
        expected = 366 if calendar.isleap(int(year)) else 365
        observed = int(block.notna().sum())
        ended = year_ended(int(year), as_of)
        rows.append(
            {
                "year": int(year),
                "expected_days": expected,
                "observed_days": observed,
                "year_ended": bool(ended),
                "complete": bool(ended and observed >= expected),
            }
        )
    return pd.DataFrame(rows)


def complete_years_from_coverage(coverage: pd.DataFrame) -> list[int]:
    if coverage.empty:
        return []
    return [int(y) for y in coverage.loc[coverage["complete"], "year"]]


# --------------------------------------------------------------------------- #
# prior-access check (protocol rule 6)
# --------------------------------------------------------------------------- #
def _station_ids_in(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    try:
        frame = pd.read_csv(path, dtype=str, low_memory=False)
    except (OSError, pd.errors.ParserError, UnicodeDecodeError):
        return set()
    ids: set[str] = set()
    if "station_id" in frame.columns:
        ids |= {str(v).strip() for v in frame["station_id"].dropna() if str(v).strip()}
    for column in ("station_ids_ge4", "site_ids", "station_ids"):
        if column in frame.columns:
            for value in frame[column].dropna():
                ids |= {part.strip() for part in re.split(r"[;,]", str(value)) if part.strip()}
    return ids


def prior_access_ids() -> tuple[dict[str, set[str]], set[str]]:
    by_source: dict[str, set[str]] = {}
    for path in PRIOR_ARTIFACTS:
        ids = _station_ids_in(path)
        if ids:
            by_source[str(path.relative_to(ROOT))] = ids
    for directory in PRIOR_SCAN_DIRS:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.csv")):
            key = str(path.relative_to(ROOT))
            if key in by_source:
                continue
            ids = _station_ids_in(path)
            if ids:
                by_source[key] = ids
    used: set[str] = set()
    for ids in by_source.values():
        used |= ids
    return by_source, used


# --------------------------------------------------------------------------- #
# stages
# --------------------------------------------------------------------------- #
def stage_catalog(hub: CachedHub, *, refresh: bool) -> pd.DataFrame:
    url = STATION_API + "?" + urllib.parse.urlencode({"size": "20000", "page": "1"})
    document = hub.get(url, kind="catalog", name="station_catalog", refresh=refresh)
    count = int(document.get("count") or 0)
    data = document.get("data") or []
    if count != len(data):
        raise RuntimeError(
            f"station catalog is paged ({len(data)} of {count}); refusing partial station table"
        )
    dropped: list[dict[str, Any]] = []
    frame = build_station_table(document, dropped=dropped)
    frame.to_csv(RAW / "station_table.csv", index=False)
    pd.DataFrame(dropped).to_csv(RAW / "stations_dropped_waterbody_filter.csv", index=False)
    n = len(frame)
    n_river = int(frame["in_river_panel"].sum())
    print(
        f"  catalog: {n} stations, {n_river} river stations "
        f"({100.0 * (n - n_river) / max(n, 1):.2f}% dropped on waterbody evidence)",
        flush=True,
    )
    for reason in sorted({r for row in frame["drop_reasons"] for r in str(row).split(";") if r}):
        hits = int(frame["drop_reasons"].str.contains(re.escape(reason)).sum())
        print(f"    dropped reason {reason}: {hits}", flush=True)
    return frame


def stage_spans(hub: CachedHub, stations: pd.DataFrame, *, refresh: bool) -> pd.DataFrame:
    requests = []
    for station_id in stations["station_id"]:
        requests.append((span_url(station_id, "asc"), "spans", f"{station_id}_asc"))
        requests.append((span_url(station_id, "desc"), "spans", f"{station_id}_desc"))
    documents, span_failures = hub.get_many(requests, refresh=refresh, progress="spans")
    unresolved = [
        str(station_id)
        for station_id in stations["station_id"]
        if f"{station_id}_asc" not in documents or f"{station_id}_desc" not in documents
    ]
    for station_id in unresolved:
        hub.failures.append(
            {
                "kind": "spans",
                "name": f"{station_id}_span_screen",
                "url": span_url(station_id, "asc"),
                "error": "span screen unresolved (request failed or was not answered)",
            }
        )
    if unresolved:
        print(
            f"    LOUD: {len(unresolved)} stations have an unresolved span screen and are excluded "
            f"from candidacy: {unresolved[:10]}",
            flush=True,
        )
    rows = []
    for station_id in stations["station_id"]:
        asc = documents.get(f"{station_id}_asc") or {}
        desc = documents.get(f"{station_id}_desc") or {}
        total = int(asc.get("count") or 0)
        first = (asc.get("data") or [{}])[0] if asc.get("data") else {}
        last = (desc.get("data") or [{}])[0] if desc.get("data") else {}
        first_date = first.get("date_mesure_temp")
        last_date = last.get("date_mesure_temp")
        span_days = float("nan")
        if first_date and last_date:
            span_days = float((pd.Timestamp(last_date) - pd.Timestamp(first_date)).days + 1)
        rows.append(
            {
                "station_id": station_id,
                "span_screen_ok": str(station_id) not in set(unresolved),
                "n_obs_total": total,
                "first_obs_date": first_date,
                "last_obs_date": last_date,
                "span_days": span_days,
                "span_years": span_days / 365.25 if math.isfinite(span_days) else float("nan"),
                "asc_url": span_url(station_id, "asc"),
                "desc_url": span_url(station_id, "desc"),
            }
        )
    frame = pd.DataFrame(rows)
    frame.to_csv(RAW / "station_spans.csv", index=False)
    print(
        f"  spans: {int((frame['n_obs_total'] > 0).sum())} stations with >=1 observation, "
        f"{int((frame['span_years'] >= 4).sum())} with >=4 years of span",
        flush=True,
    )
    return frame


def stage_qualification(
    hub: CachedHub,
    stations: pd.DataFrame,
    spans: pd.DataFrame,
    *,
    refresh: bool,
    global_probe: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Counts by Sandre qualification code: globally and per station."""

    global_counts: dict[str, Any] = {"by_code": {}, "labels": {}}
    if global_probe:
        global_requests = [
            (_chronique_url(size="1", page="1"), "qualification_global", "all_codes"),
        ]
        for code in QUALIFICATION_CODES:
            global_requests.append(
                (
                    _chronique_url(code_qualification=code, size="1", page="1"),
                    "qualification_global",
                    f"code_{code}",
                )
            )
        documents, _ = hub.get_many(global_requests, refresh=refresh, progress="global qualification counts")
        for url, _kind, name in global_requests:
            document = documents.get(name) or {}
            global_counts["by_code"][name] = {
                "count": int(document.get("count") or 0),
                "url": url,
            }
        global_counts["labels"] = {
            "all_codes": "all qualification codes",
            **{f"code_{c}": f"Sandre code {c} ({CODE_LABELS[c]})" for c in QUALIFICATION_CODES},
        }

    requests = []
    for station_id in stations["station_id"]:
        for code in QUALIFICATION_CODES:
            requests.append(
                (qualification_count_url(station_id, code), "qualification_station", f"{station_id}_code{code}")
            )
    documents, _ = hub.get_many(requests, refresh=refresh, progress="per-station qualification counts")
    rows = []
    totals = {c: 0 for c in QUALIFICATION_CODES}
    for station_id in stations["station_id"]:
        counts = {
            code: int((documents.get(f"{station_id}_code{code}") or {}).get("count") or 0)
            for code in QUALIFICATION_CODES
        }
        for code, value in counts.items():
            totals[code] += value
        rows.append({"station_id": station_id, **{f"count_code_{c}": counts[c] for c in QUALIFICATION_CODES}})
    frame = pd.DataFrame(rows)
    frame["count_codes_sum"] = frame[[f"count_code_{c}" for c in QUALIFICATION_CODES]].sum(axis=1)
    frame = frame.merge(
        spans[["station_id", "n_obs_total", "first_obs_date", "last_obs_date", "span_years"]],
        on="station_id",
        how="left",
    )
    frame["codes_match_total"] = frame["count_codes_sum"].eq(frame["n_obs_total"])
    frame["codes_1_4_sum"] = frame["count_code_1"] + frame["count_code_4"]
    frame["accepted_code"] = np.where(
        frame["count_code_1"] > 0,
        "1",
        np.where(frame["count_code_4"] > 0, "4", ""),
    )
    frame["accepted_quality_codes"] = frame["accepted_code"]
    frame["quality"] = frame["accepted_code"].map(
        {
            "1": "qualified (Sandre code 1 Correcte)",
            "4": "unqualified (Sandre code 4)",
            "": "no acceptable code",
        }
    )
    frame["quality_assurance"] = frame["accepted_code"].map(
        {
            "1": "quality_checked",
            "4": "provider_published_unqualified",
            "": "no_acceptable_code",
        }
    )
    frame.to_csv(RAW / "qualification_counts.csv", index=False)
    station_totals = {c: int(frame[f"count_code_{c}"].sum()) for c in QUALIFICATION_CODES}
    print(f"  qualification over {len(frame)} audited stations:", flush=True)
    for code in QUALIFICATION_CODES:
        n_stations = int((frame[f"count_code_{code}"] > 0).sum())
        print(
            f"    code {code} ({CODE_LABELS[code]}): {station_totals[code]} obs on {n_stations} stations",
            flush=True,
        )
    n_mismatch = int((~frame["codes_match_total"]).sum())
    print(f"    stations where sum(codes) != unfiltered total: {n_mismatch}", flush=True)
    summary = {
        "global_api_counts": global_counts,
        "n_stations_audited": int(len(frame)),
        "per_station_totals_over_audited": station_totals,
        "per_station_station_counts": {
            code: int((frame[f"count_code_{code}"] > 0).sum()) for code in QUALIFICATION_CODES
        },
        "n_stations_codes_sum_mismatch": n_mismatch,
    }
    return frame, summary


def select_candidates(
    stations: pd.DataFrame,
    spans: pd.DataFrame,
    qualification: pd.DataFrame | None,
    *,
    min_span_years: float,
    min_observations: int,
    min_code1_observations: int,
    max_networks: int = 0,
    network_keys: Sequence[str] = (),
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    list[dict[str, Any]],
    set[str],
    list[dict[str, Any]],
    pd.DataFrame,
    list[dict[str, Any]],
]:
    """River stations with enough span/volume, grouped into >=2-station rivers.

    With ``qualification=None`` the Sandre-code columns are absent and every
    station that could still reach the frozen four-complete-year floor is marked
    a candidate; that preliminary pass defines which rivers need a per-code
    audit before the download.
    """

    river = stations.loc[stations["in_river_panel"]].copy()
    river["river_key"] = river["river_name"].map(normalize_river)
    river = river.loc[river["river_key"].ne("")]
    # Shared module grouping: >= 2 stations per (normalized) river name, Loire excluded.
    clusters = cluster_hubeau_rivers(
        river[["station_id", "river_key"]].rename(
            columns={"station_id": "site_id", "river_key": "river"}
        ),
        min_stations=MIN_STATIONS_PER_NETWORK,
        exclude_loire=True,
    )
    rivers_with_two = set(clusters["river"].astype(str)) if not clusters.empty else set()
    loire_ids = set(
        river.loc[
            river["river_name"]
            .astype(str)
            .str.fullmatch(LOIRE_PATTERN, case=False)
            .fillna(False),
            "station_id",
        ].astype(str)
    )
    blocked = set(map(str, last_check_site_ids()))

    frame = river.merge(spans, on="station_id", how="left")
    if qualification is not None:
        frame = frame.merge(
            qualification[
                [
                    "station_id",
                    "count_code_1",
                    "count_code_2",
                    "count_code_3",
                    "count_code_4",
                    "accepted_code",
                    "accepted_quality_codes",
                    "quality",
                    "quality_assurance",
                    "codes_match_total",
                ]
            ],
            on="station_id",
            how="left",
        )
    frame["is_loire_last_check"] = frame["station_id"].astype(str).isin(loire_ids | blocked)
    codes_per_name = (
        frame.dropna(subset=["code_cours_eau"])
        .groupby("river_key")["code_cours_eau"]
        .nunique()
    )
    ambiguous_names = set(codes_per_name.loc[codes_per_name > 1].index.astype(str))
    frame["ambiguous_river_name"] = frame["river_key"].isin(ambiguous_names)
    frame["river_has_two_stations"] = frame["river_key"].isin(rivers_with_two)
    frame["span_ok"] = (
        frame["span_screen_ok"].fillna(False).astype(bool)
        & (frame["span_years"].fillna(0.0) >= float(min_span_years))
    )
    frame["volume_ok"] = frame["n_obs_total"].fillna(0).astype(int) >= int(min_observations)
    possible = (
        frame["span_ok"]
        & frame["volume_ok"]
        & frame["river_has_two_stations"]
        & ~frame["is_loire_last_check"]
        & ~frame["ambiguous_river_name"]
    )
    if qualification is not None:
        frame["code1_sufficient"] = (
            frame["count_code_1"].fillna(0).astype(int) >= int(min_code1_observations)
        )
        frame["download_code"] = np.where(
            frame["code1_sufficient"],
            "1",
            np.where(frame["count_code_4"].fillna(0).astype(int) > 0, "4", ""),
        )
        possible = possible & frame["download_code"].ne("")
    else:
        frame["code1_sufficient"] = False
        frame["download_code"] = ""
    frame["candidate"] = possible
    candidates = frame.loc[frame["candidate"]].copy()
    network_rows = []
    for river_key, group in candidates.groupby("river_key", sort=False):
        if len(group) < MIN_STATIONS_PER_NETWORK:
            continue
        network_rows.append(
            {
                "network_id": f"{PROVIDER}_{slugify(river_key)}",
                "river_key": river_key,
                "river_name": str(group["river_name"].mode().iat[0]),
                "n_candidate_stations": int(len(group)),
                "station_ids": ";".join(sorted(group["station_id"].astype(str))),
                "n_code1_stations": int((group["download_code"] == "1").sum()),
                "n_code4_stations": int((group["download_code"] == "4").sum()),
            }
        )
    networks = pd.DataFrame(network_rows)
    capped_networks: list[dict[str, Any]] = []
    if max_networks and len(networks) > int(max_networks):
        ranked = networks.assign(
            _obs=networks["station_ids"].map(
                lambda value: int(
                    frame.loc[frame["station_id"].astype(str).isin(str(value).split(";")), "n_obs_total"]
                    .fillna(0)
                    .sum()
                )
            )
        ).sort_values(
            ["n_candidate_stations", "_obs"], ascending=[False, False]
        )
        keep = set(ranked.head(int(max_networks))["network_id"])
        for item in ranked.loc[~ranked["network_id"].isin(keep)].to_dict(orient="records"):
            capped_networks.append(
                {
                    "network_id": item["network_id"],
                    "river_name": item["river_name"],
                    "reason": f"beyond --max-networks {int(max_networks)} cap",
                    "n_candidate_stations": int(item["n_candidate_stations"]),
                    "candidate_observations": int(item["_obs"]),
                    "station_ids": item["station_ids"],
                }
            )
        networks = networks.loc[networks["network_id"].isin(keep)].reset_index(drop=True)
    candidate_networks = set(networks["river_key"]) if not networks.empty else set()
    candidates = candidates.loc[candidates["river_key"].isin(candidate_networks)].copy()
    if not networks.empty:
        candidates = candidates.merge(
            networks[["network_id", "river_key"]], on="river_key", how="left"
        )
    else:
        candidates["network_id"] = pd.Series(dtype=str)
    excluded = []
    for river_key, group in frame.loc[~frame["candidate"]].groupby("river_key", sort=False):
        excluded.append(
            {
                "river_key": river_key,
                "river_name": str(group["river_name"].mode().iat[0]),
                "n_stations_in_catalog": int(len(group)),
                "n_span_ok": int(group["span_ok"].sum()),
                "n_volume_ok": int(group["volume_ok"].sum()),
                "n_loire_last_check": int(group["is_loire_last_check"].sum()),
                "river_has_two_stations": bool(group["river_has_two_stations"].iat[0]),
                "ambiguous_river_name": bool(group["ambiguous_river_name"].iat[0]),
                "n_distinct_watercourse_codes": int(group["code_cours_eau"].dropna().nunique()),
                "station_ids": ";".join(sorted(group["station_id"].astype(str))),
            }
        )
    tranche_dropped: list[dict[str, Any]] = []
    if network_keys:
        wanted = {str(key).strip() for key in network_keys if str(key).strip()}
        keep = {
            str(value)
            for value in set(networks["network_id"]).union(set(networks["river_key"]))
            if str(value) in wanted
        }
        missing = sorted(wanted - keep)
        if missing:
            raise RuntimeError(f"--network-keys not found in the candidate pool: {missing}")
        for item in networks.loc[
            ~networks["network_id"].isin(keep) & ~networks["river_key"].isin(keep)
        ].to_dict(orient="records"):
            tranche_dropped.append(
                {
                    "network_id": item["network_id"],
                    "river_name": item["river_name"],
                    "reason": "--network-keys tranche filter",
                    "n_candidate_stations": int(item["n_candidate_stations"]),
                    "station_ids": item["station_ids"],
                }
            )
        networks = networks.loc[
            networks["network_id"].isin(keep) | networks["river_key"].isin(keep)
        ].reset_index(drop=True)
        candidate_networks = set(networks["river_key"]) if not networks.empty else set()
        candidates = candidates.loc[candidates["river_key"].isin(candidate_networks)].copy()
    return (
        candidates,
        networks,
        excluded,
        loire_ids | blocked,
        capped_networks,
        frame.loc[frame["ambiguous_river_name"]].copy(),
        tranche_dropped,
    )


def stage_download(
    hub: CachedHub,
    candidates: pd.DataFrame,
    *,
    min_obs_per_day: int,
    sensitivity_thresholds: Sequence[int],
    max_stations_per_network: int,
    max_years_per_station: int,
    as_of: pd.Timestamp,
    refresh: bool,
    download_workers: int = 2,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], list[dict[str, Any]]]:
    """Download candidate stations year by year, aggregate daily, apply the frozen year rule."""

    plan = []
    for network_id, group in candidates.groupby("network_id", sort=True):
        ranked = group.sort_values(["download_code", "n_obs_total"], ascending=[True, False])
        chosen = []
        for code in ("1", "4"):
            block = ranked.loc[ranked["download_code"].eq(code)]
            room = max_stations_per_network - len(chosen)
            if room > 0 and not block.empty:
                chosen.append(block.head(room))
        picked = pd.concat(chosen, ignore_index=True) if chosen else ranked.head(0)
        plan.append((str(network_id), picked.sort_values("station_id")))

    thresholds = sorted({int(value) for value in sensitivity_thresholds})
    n_stations = int(sum(len(picked) for _, picked in plan))
    print(
        f"  download: {len(plan)} networks, {n_stations} stations, "
        f"{int(download_workers)} concurrent station downloads",
        flush=True,
    )
    counter = {"done": 0}

    def process(network_id: str, row: Any) -> dict[str, Any]:
        station_id = str(row.station_id)
        code = str(row.download_code)
        first = pd.Timestamp(row.first_obs_date).normalize()
        last = pd.Timestamp(row.last_obs_date).normalize()
        years = list(range(int(first.year), int(last.year) + 1))
        if max_years_per_station and len(years) > max_years_per_station:
            years = years[-int(max_years_per_station) :]
        parts: list[pd.DataFrame] = []
        qc_total = {
            "n_obs_downloaded": 0,
            "n_obs_dropped_qc": 0,
            "n_obs_accepted": 0,
            "dropped_out_of_range": 0,
            "dropped_unparsable": 0,
            "dropped_non_finite": 0,
            "n_time_stamps_present": 0,
        }
        failures: list[dict[str, Any]] = []
        failed_years: list[int] = []
        for year in years:
            try:
                rows = fetch_window(
                    hub,
                    station_id,
                    pd.Timestamp(year=year, month=1, day=1),
                    pd.Timestamp(year=year, month=12, day=31),
                    code,
                    refresh=refresh,
                )
            # Each station-year failure is retained and reported; the station is dropped loudly.
            except Exception as error:  # noqa: BLE001
                failures.append(
                    {
                        "network_id": network_id,
                        "station_id": station_id,
                        "code": code,
                        "year": year,
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
                failed_years.append(year)
                continue
            wrong_code = sorted(
                {
                    str(item.get("quality_code"))
                    for item in rows
                    if str(item.get("quality_code")) != code
                }
            )
            if wrong_code:
                raise RuntimeError(
                    f"API returned unintended Sandre codes {wrong_code} for station "
                    f"{station_id} requested as code {code}; refusing to mix codes"
                )
            part, qc_year = per_day_table(rows)
            for key in qc_total:
                qc_total[key] += int(qc_year.get(key) or 0)
            parts.append(part)
        per_day = merge_per_day(parts)
        counter["done"] += 1
        print(
            f"    [{counter['done']}/{n_stations}] {network_id} {station_id} code {code}: "
            f"{qc_total['n_obs_downloaded']} obs, {len(per_day)} days with data, "
            f"{len(years) - len(failed_years)}/{len(years)} years fetched",
            flush=True,
        )
        result: dict[str, Any] = {
            "network_id": network_id,
            "station_id": station_id,
            "code": code,
            "member": row,
            "per_day": per_day,
            "qc_total": qc_total,
            "failed_years": failed_years,
            "failures": failures,
            "daily": pd.DataFrame(),
            "coverage": pd.DataFrame(),
            "sensitivity": [],
            "qc_row": None,
        }
        if qc_total["n_obs_downloaded"] != qc_total["n_obs_dropped_qc"] + qc_total["n_obs_accepted"]:
            raise RuntimeError(f"observation accounting inconsistent for {station_id}")
        if per_day.empty:
            result["failures"].append(
                {
                    "network_id": network_id,
                    "station_id": station_id,
                    "code": code,
                    "error": "no acceptable observation retrieved",
                }
            )
            return result
        daily = daily_values(per_day, min_obs_per_day=min_obs_per_day)
        if daily.empty:
            result["failures"].append(
                {
                    "network_id": network_id,
                    "station_id": station_id,
                    "code": code,
                    "error": f"no day reached the {min_obs_per_day}-observation floor",
                }
            )
            return result
        qc = {
            **qc_total,
            **per_day_qc(per_day, min_obs_per_day=min_obs_per_day),
            "n_days_in_span": int(
                len(pd.date_range(per_day["date"].min(), per_day["date"].max(), freq="D"))
            ),
        }
        qc["n_days_zero_obs"] = int(qc["n_days_in_span"] - qc["n_days_with_obs"])
        if qc["n_days_in_span"] != qc["n_days_zero_obs"] + qc["n_days_with_obs"]:
            raise RuntimeError(f"day accounting inconsistent for {station_id}")
        if qc["n_days_with_obs"] != qc["n_days_below_min_obs"] + len(daily):
            raise RuntimeError(f"daily-value accounting inconsistent for {station_id}")
        coverage = year_coverage(daily, as_of=as_of)
        sensitivity = []
        for threshold in thresholds:
            alt_daily = daily_values(per_day, min_obs_per_day=threshold)
            alt_cov = year_coverage(alt_daily, as_of=as_of)
            sensitivity.append(
                {
                    "network_id": network_id,
                    "station_id": station_id,
                    "accepted_quality_codes": code,
                    "min_obs_per_day": int(threshold),
                    "n_complete_years": len(complete_years_from_coverage(alt_cov)),
                    "n_days_daily_value": int(len(alt_daily)),
                }
            )
        years_complete = complete_years_from_coverage(coverage)
        result.update({"daily": daily, "coverage": coverage, "sensitivity": sensitivity})
        result["qc_row"] = {
            "network_id": network_id,
            "station_id": station_id,
            "download_code": code,
            "accepted_quality_codes": str(row.accepted_quality_codes),
            "quality": str(row.quality),
            "quality_assurance": str(row.quality_assurance),
            "first_obs_date": str(row.first_obs_date),
            "last_obs_date": str(row.last_obs_date),
            "n_years_downloaded": int(len(years) - len(failed_years)),
            "years_downloaded": ";".join(str(y) for y in years if y not in failed_years),
            "n_complete_years": len(years_complete),
            "complete_years": ";".join(str(y) for y in years_complete),
            "n_failed_years": int(len(failed_years)),
            **qc,
        }
        return result

    jobs = [(network_id, row) for network_id, picked in plan for row in picked.itertuples(index=False)]
    results: list[dict[str, Any]] = []
    if download_workers > 1 and len(jobs) > 1:
        with ThreadPoolExecutor(max_workers=int(download_workers)) as pool:
            futures = [pool.submit(process, network_id, row) for network_id, row in jobs]
            for future in futures:
                results.append(future.result())
    else:
        for network_id, row in jobs:
            results.append(process(network_id, row))

    station_daily: dict[str, pd.DataFrame] = {}
    year_cov: dict[str, pd.DataFrame] = {}
    qc_rows: list[dict[str, Any]] = []
    sensitivity_rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for result in results:
        failures.extend(result["failures"])
        if result["qc_row"] is None:
            continue
        station_daily[result["station_id"]] = result["daily"]
        year_cov[result["station_id"]] = result["coverage"]
        qc_rows.append(result["qc_row"])
        sensitivity_rows.extend(result["sensitivity"])
    qc_frame = pd.DataFrame(qc_rows)
    if not qc_frame.empty:
        qc_frame.to_csv(RAW / "station_qc.csv", index=False)
    if year_cov:
        coverage_frame = pd.concat(
            [frame.assign(station_id=station_id) for station_id, frame in year_cov.items()],
            ignore_index=True,
        )
        coverage_frame.to_csv(RAW / "station_year_coverage.csv", index=False)
    if sensitivity_rows:
        pd.DataFrame(sensitivity_rows).to_csv(RAW / "complete_year_sensitivity.csv", index=False)
    return qc_frame, station_daily, failures


# --------------------------------------------------------------------------- #
# outputs
# --------------------------------------------------------------------------- #
def write_outputs(
    *,
    stations: pd.DataFrame,
    spans: pd.DataFrame,
    qualification: pd.DataFrame,
    candidates: pd.DataFrame,
    networks: pd.DataFrame,
    qc_frame: pd.DataFrame,
    station_daily: dict[str, pd.DataFrame],
    excluded_networks: list[dict[str, Any]],
    dropped_waterbody: list[dict[str, Any]],
    global_counts: dict[str, Any],
    loire_blocked: set[str],
    failures: list[dict[str, Any]],
    args: argparse.Namespace,
    retrieved_utc: str,
    request_manifest: pd.DataFrame,
    prior_conflicts: dict[str, list[str]],
    prior_sources: dict[str, int],
    module_check: dict[str, Any],
    capped_networks: list[dict[str, Any]],
    ambiguous_clusters: pd.DataFrame,
    ambiguous_stations: int,
    tranche_dropped: list[dict[str, Any]],
    resolved_networks: int,
    resolved_stations: int,
    pre_cap_networks_dropped: list[dict[str, Any]],
) -> dict[str, Any]:
    NETWORKS.mkdir(parents=True, exist_ok=True)
    qc_by_station = (
        qc_frame.set_index("station_id").to_dict(orient="index") if not qc_frame.empty else {}
    )
    planned_station_ids = {
        str(station_id) for station_id in station_daily
    } | set(qc_by_station)
    prov = stations.set_index("station_id").to_dict(orient="index")
    span_by = spans.set_index("station_id").to_dict(orient="index")

    network_rows: list[dict[str, Any]] = []
    station_rows: list[dict[str, Any]] = []
    panel_files: list[dict[str, Any]] = []
    dropped_stations: list[dict[str, Any]] = []
    networks_dropped: list[dict[str, Any]] = []
    for row in networks.itertuples(index=False):
        network_id = str(row.network_id)
        members = candidates.loc[candidates["network_id"].astype(str).eq(network_id)]
        kept = []
        for member in members.itertuples(index=False):
            station_id = str(member.station_id)
            qc = qc_by_station.get(station_id)
            if qc is None:
                reason = (
                    "not downloaded (beyond --max-stations-per-network cap for this network)"
                    if station_id not in planned_station_ids
                    else "downloaded but no daily panel built (see ingest.json failures)"
                )
                dropped_stations.append(
                    {"network_id": network_id, "station_id": station_id, "reason": reason}
                )
                continue
            if int(qc["n_complete_years"]) < MIN_COMPLETE_YEARS:
                dropped_stations.append(
                    {
                        "network_id": network_id,
                        "station_id": station_id,
                        "reason": f"only {int(qc['n_complete_years'])} complete calendar years "
                        f"(need {MIN_COMPLETE_YEARS})",
                    }
                )
                continue
            kept.append((station_id, qc, member))
        kept.sort(key=lambda item: item[0])
        if len(kept) < MIN_STATIONS_PER_NETWORK:
            networks_dropped.append(
                {
                    "network_id": network_id,
                    "river_name": str(row.river_name),
                    "reason": f"only {len(kept)} stations with >={MIN_COMPLETE_YEARS} complete years "
                    f"(need {MIN_STATIONS_PER_NETWORK})",
                    "candidate_station_ids": ";".join(sorted(members["station_id"].astype(str))),
                }
            )
            continue
        directory = NETWORKS / network_id
        directory.mkdir(parents=True, exist_ok=True)
        wide = pd.DataFrame(
            {station_id: station_daily[station_id].set_index("date")["temperature_c"] for station_id, _, _ in kept}
        )
        wide = wide.sort_index()
        wide.index.name = "date"
        wide = wide.reindex(pd.date_range(wide.index.min(), wide.index.max(), freq="D"))
        wide.index.name = "date"
        wide_path = directory / "daily_wide_temperature.csv"
        wide.to_csv(wide_path, date_format="%Y-%m-%d")

        network_station_rows = []
        for station_id, qc, member in kept:
            meta = prov.get(station_id, {})
            span = span_by.get(station_id, {})
            created = [
                pd.Timestamp(value).strftime("%Y-%m-%d")
                for value in sorted(station_daily[station_id]["date"])
            ]
            network_station_rows.append(
                {
                    "network_id": network_id,
                    "station_id": station_id,
                    "provider": PROVIDER,
                    "river_name": meta.get("river_name"),
                    "latitude": meta.get("latitude"),
                    "longitude": meta.get("longitude"),
                    "n_complete_years": int(qc["n_complete_years"]),
                    "complete_years": str(qc["complete_years"]),
                    "first_date": created[0],
                    "last_date": created[-1],
                    "n_days": int(len(station_daily[station_id])),
                    "n_dropped_qc": int(qc["n_obs_dropped_qc"]),
                    "accepted_quality_codes": str(qc["accepted_quality_codes"]),
                    "measurement_statistic": (
                        "daily mean water temperature (degC) from sub-daily in-situ "
                        f"observations; mean of >= {int(args.min_obs_per_day)} acceptable "
                        "observations per calendar day"
                    ),
                    "quality": str(qc["quality"]),
                    "quality_assurance": str(qc["quality_assurance"]),
                    "measurement_statistic_quality": str(qc["quality"]),
                    "waterbody_class": meta.get("waterbody_class"),
                    "waterbody_name": meta.get("waterbody_name"),
                    "hubeau_nature_station": meta.get("nature_station"),
                    "canalised_name_flag": bool(meta.get("canalised_name_flag") or False),
                    "latitude_deg": meta.get("latitude"),
                    "longitude_deg": meta.get("longitude"),
                    "hubeau_code_cours_eau": meta.get("code_cours_eau"),
                    "hubeau_code_masse_eau": meta.get("code_masse_eau"),
                    "region": meta.get("region"),
                    "departement": meta.get("departement"),
                    "first_observed_date": span.get("first_obs_date"),
                    "last_observed_date": span.get("last_obs_date"),
                    "span_years_screen": span.get("span_years"),
                    "n_obs_total_screen": span.get("n_obs_total"),
                    "n_obs_downloaded": int(qc["n_obs_downloaded"]),
                    "n_obs_accepted": int(qc["n_obs_accepted"]),
                    "n_obs_dropped_out_of_range": int(qc["dropped_out_of_range"]),
                    "n_obs_dropped_unparsable_or_nonfinite": int(qc["dropped_unparsable"])
                    + int(qc["dropped_non_finite"]),
                    "n_days_in_span": int(qc["n_days_in_span"]),
                    "n_days_with_obs": int(qc["n_days_with_obs"]),
                    "n_days_zero_obs": int(qc["n_days_zero_obs"]),
                    "n_days_below_min_obs": int(qc["n_days_below_min_obs"]),
                    "n_days_daily_value": int(qc["n_days_daily_value"]),
                    "median_obs_per_observed_day": qc["median_obs_per_observed_day"],
                    "min_obs_per_day_rule": int(args.min_obs_per_day),
                    "years_downloaded": str(qc["years_downloaded"]),
                    "n_years_downloaded": int(qc["n_years_downloaded"]),
                    "n_failed_years": int(qc["n_failed_years"]),
                    "download_code": str(qc["download_code"]),
                    "hubeau_sandre_code_labels": ";".join(
                        f"{c}={CODE_LABELS[c]}" for c in QUALIFICATION_CODES
                    ),
                    "hubeau_code1_count": int(member.count_code_1),
                    "hubeau_code2_count": int(member.count_code_2),
                    "hubeau_code3_count": int(member.count_code_3),
                    "hubeau_code4_count": int(member.count_code_4),
                    "hubeau_counts_match_total": bool(member.codes_match_total),
                }
            )
        network_station = pd.DataFrame(network_station_rows)
        network_station.to_csv(directory / "stations.csv", index=False)
        station_rows.extend(network_station_rows)

        digest = sha256_file(wide_path)
        n_station_years = int(network_station["n_complete_years"].sum())
        panel_files.append(
            {
                "network_id": network_id,
                "input_path": str(wide_path.relative_to(ROOT)),
                "sha256": digest,
                "n_stations": int(len(network_station)),
                "n_station_years": n_station_years,
                "station_ids_ge4": ";".join(network_station["station_id"].astype(str)),
                "quality": ";".join(sorted(set(network_station["quality"].astype(str)))),
                "domain": "transport_external",
            }
        )
        network_rows.append(
            {
                "network_id": network_id,
                "provider": PROVIDER,
                "river_name": str(row.river_name),
                "river_key": str(row.river_key),
                "n_stations": int(len(network_station)),
                "n_station_years": n_station_years,
                "complete_year_min": int(network_station["n_complete_years"].min()),
                "complete_year_max": int(network_station["n_complete_years"].max()),
                "station_ids": ";".join(network_station["station_id"].astype(str)),
                "accepted_quality_codes": ";".join(
                    sorted(set(network_station["accepted_quality_codes"].astype(str)))
                ),
                "quality_label": ";".join(sorted(set(network_station["quality"].astype(str)))),
                "quality_assurance": ";".join(
                    sorted(set(network_station["quality_assurance"].astype(str)))
                ),
                "daily_wide_temperature_csv": f"networks/{network_id}/daily_wide_temperature.csv",
                "sha256": digest,
                "panels_include_only_stations_with_ge4_complete_years": True,
            }
        )
        (directory / "README.md").write_text(
            "\n".join(
                [
                    f"# {network_id} (Hub'Eau river-temperature network)",
                    "",
                    f"- provider: `{PROVIDER}` (Hub'Eau / Eaufrance, France)",
                    f"- river: {row.river_name}",
                    f"- retrieved_utc: {retrieved_utc}",
                    f"- stations in panel: {len(network_station)} "
                    f"(all with >= {MIN_COMPLETE_YEARS} complete calendar years)",
                    f"- complete station-years: {n_station_years}",
                    f"- quality_assurance: "
                    f"{';'.join(sorted(set(network_station['quality_assurance'].astype(str))))}",
                    f"- accepted Sandre codes: "
                    f"{';'.join(sorted(set(network_station['accepted_quality_codes'].astype(str))))}",
                    "",
                    "## Files",
                    "",
                    "- `daily_wide_temperature.csv` - wide daily panel, first column `date`, one",
                    "  column per station id, blank where a daily value was not formed.",
                    "- `stations.csv` - per-station provenance, Sandre code counts, QC day counts,",
                    "  complete calendar years, quality labels.",
                    "- `ingest.json` - machine-readable record for this network.",
                    "",
                    "## Measurement provenance",
                    "",
                    "Daily value = arithmetic mean of the station's single accepted Sandre code",
                    f"observations within one calendar day, using only days with >= "
                    f"{int(args.min_obs_per_day)} acceptable observations; days below that floor are",
                    "dropped and counted (never interpolated). Complete calendar year = every calendar",
                    "day of an ended year carries a daily value.",
                    "",
                    "Sandre code 1 = `quality_checked` (Correcte); code 2/3 are never ingested;",
                    "code 4 = `provider_published_unqualified` (Non qualifie) - a lower-assurance",
                    "subset that must be reported as such. No station mixes codes.",
                    "",
                    "No frozen-screen performance was computed on this panel.",
                ]
            )
            + "\n"
        )
        (directory / "ingest.json").write_text(
            json.dumps(
                {
                    "network_id": network_id,
                    "provider": PROVIDER,
                    "river_name": str(row.river_name),
                    "retrieved_utc": retrieved_utc,
                    "stations": network_station_rows,
                    "n_station_years": n_station_years,
                    "daily_wide_temperature_csv_sha256": digest,
                    "quality": ";".join(sorted(set(network_station["quality"].astype(str)))),
                    "quality_assurance": ";".join(
                        sorted(set(network_station["quality_assurance"].astype(str)))
                    ),
                    "aggregation_rule": {
                        "daily_value": "mean of acceptable observations of one Sandre code per day",
                        "min_observations_per_day": int(args.min_obs_per_day),
                        "complete_calendar_year": "all calendar days of an ended year present",
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )

    stations_provider = pd.DataFrame(station_rows)
    if not stations_provider.empty:
        stations_provider = stations_provider.sort_values(["network_id", "station_id"]).reset_index(drop=True)
    stations_provider.to_csv(OUT_ROOT / "stations.csv", index=False)
    if panel_files:
        pd.DataFrame(panel_files).to_csv(RAW / "network_inputs_manifest.csv", index=False)
        pd.DataFrame(network_rows).to_csv(OUT_ROOT / "networks.csv", index=False)
    pd.DataFrame(networks_dropped).to_csv(
        OUT_ROOT / "networks_excluded_after_download.csv", index=False
    )
    pd.DataFrame(dropped_waterbody).to_csv(
        OUT_ROOT / "stations_dropped_waterbody_filter.csv", index=False
    )
    pd.DataFrame(dropped_stations).to_csv(OUT_ROOT / "stations_below_year_floor.csv", index=False)
    if not request_manifest.empty:
        request_manifest.to_csv(RAW / "url_manifest.csv", index=False)

    n_stations_final = int(len(stations_provider))
    n_station_years = int(stations_provider["n_complete_years"].sum()) if n_stations_final else 0
    codes_used = (
        sorted({str(v) for v in stations_provider["accepted_quality_codes"]}) if n_stations_final else []
    )
    assurance = (
        "ALL stations are Sandre code 4 'Non qualifie' (unqualified) - this panel is a "
        "lower-assurance subset and must be reported as such"
        if n_stations_final and codes_used == ["4"]
        else (
            "stations use Sandre code 1 'Correcte' (qualified) only"
            if n_stations_final and codes_used == ["1"]
            else "mixed code 1 / code 4 stations - see per-station quality labels"
        )
    )

    ingest = {
        "provider": PROVIDER,
        "agency": AGENCY,
        "api_root": HUBEAU_CHRONIQUE.rsplit("/", 1)[0],
        "retrieved_utc": retrieved_utc,
        "script": "scripts/242_multi_agency_hubeau_ingest.py",
        "protocol": "results/wrr_submission_ready/MULTI_AGENCY_TRANSPORT_PROTOCOL.md",
        "command": " ".join(sys.argv),
        "frozen_model_touched": False,
        "screening_only_no_frozen_score": True,
        "api_urls": {
            "station_catalog_template": STATION_API + "?size=20000&page=1",
            "span_template": HUBEAU_CHRONIQUE + "?code_station=<id>&size=1&page=1&sort=asc|desc",
            "qualification_count_template": HUBEAU_CHRONIQUE
            + "?code_station=<id>&code_qualification=<1|2|3|4>&size=1&page=1",
            "window_template": HUBEAU_CHRONIQUE
            + "?code_station=<id>&date_debut_mesure=<YYYY-MM-DD>&date_fin_mesure=<YYYY-MM-DD>"
            "&code_qualification=<1|4>&size=20000&page=1&sort=asc",
            "n_requests_logged": int(len(request_manifest)),
            "request_manifest": "raw_cache/url_manifest.csv",
            "page_size_cap": int(HUBEAU_PAGE_SIZE),
            "deep_paging_used": False,
            "conditional_default_code": 1,
        },
        "qualification_counts": {
            "global_api_counts": global_counts,
            "audit_scope": (
                "every station on a river with >= 2 stations that can still reach "
                f"{MIN_COMPLETE_YEARS} complete calendar years (preliminary span/volume screen); "
                "the global probe covers the whole Hub'Eau temperature chronique"
            ),
            "per_station_code_totals_over_audited_rivers": {
                key: value
                for key, value in {
                    "count_code_1": int(qualification["count_code_1"].sum()) if not qualification.empty else 0,
                    "count_code_2": int(qualification["count_code_2"].sum()) if not qualification.empty else 0,
                    "count_code_3": int(qualification["count_code_3"].sum()) if not qualification.empty else 0,
                    "count_code_4": int(qualification["count_code_4"].sum()) if not qualification.empty else 0,
                }.items()
            },
            "n_stations_with_code_1": int((qualification["count_code_1"] > 0).sum())
            if not qualification.empty
            else 0,
            "n_stations_with_code_2": int((qualification["count_code_2"] > 0).sum())
            if not qualification.empty
            else 0,
            "n_stations_with_code_3": int((qualification["count_code_3"] > 0).sum())
            if not qualification.empty
            else 0,
            "n_stations_with_code_4": int((qualification["count_code_4"] > 0).sum())
            if not qualification.empty
            else 0,
            "n_stations_codes_sum_mismatch": int((~qualification["codes_match_total"]).sum())
            if not qualification.empty
            else 0,
            "per_station_table": "raw_cache/qualification_counts.csv",
            "note": (
                "Counts were retrieved from the API count field, per code, over every station in "
                "the Hub'Eau temperature catalog before any series download. A station is ingested "
                "under exactly one code; codes 2 and 3 are never ingested."
            ),
        },
        "waterbody_filter": {
            "catalog_stations": int(len(stations)),
            "river_stations_kept": int(stations["in_river_panel"].sum()),
            "stations_dropped": int((~stations["in_river_panel"]).sum()),
            "fraction_dropped": float((~stations["in_river_panel"]).mean()) if len(stations) else 0.0,
            "dropped_detail_file": "stations_dropped_waterbody_filter.csv",
            "rule": (
                "Hub'Eau temperature stations carry DCE water-body metadata. Every station with a "
                "water-body code is a river water body (MasseDEauRiviere_VEDL2019); the catalog "
                "contains no lake/plan-d'eau, coastal, transitional or groundwater water-body "
                "class, so no station was dropped for those classes. Stations without a "
                "water-body code were kept only with explicit river-name evidence. Stations whose "
                "water-body label is itself a standing water body (lac/etang/retenue/reservoir/"
                "plan d'eau/graviere/lagune) were dropped, and sea/estuary stations were dropped "
                "only on station-name or water-body-class evidence -- a river reach label that "
                "merely names the sea or an estuary as its downstream boundary was retained."
            ),
            "retained_although_label_mentions_sea_or_estuary": int(
                stations["sea_estuary_mention_in_waterbody_label"].sum()
            ),
            "canalised_name_flagged_but_kept": int(stations["canalised_name_flag"].sum()),
        },
        "network_filter": {
            "grouping": "normalized Hub'Eau river name (libelle_cours_eau) via cluster_hubeau_rivers",
            "min_stations_per_network": MIN_STATIONS_PER_NETWORK,
            "min_complete_years_per_station": MIN_COMPLETE_YEARS,
            "loire_last_check_excluded_station_ids": sorted(str(v) for v in loire_blocked),
            "n_candidate_networks_before_year_floor": int(len(networks)),
            "n_networks_final": int(len(network_rows)),
            "n_rivers_excluded_before_download": int(len(excluded_networks)),
            "max_networks_cap": int(args.max_networks),
            "n_rivers_beyond_cap": int(len(capped_networks)),
            "rivers_beyond_cap_file": "raw_cache/networks_beyond_cap.csv",
            "cap_note": (
                "the candidate river pool is capped to the largest --max-networks river groups "
                "(ranked by number of candidate stations, then candidate observations); every "
                "river beyond the cap is listed in raw_cache/networks_beyond_cap.csv and was NOT "
                "downloaded"
            ),
            "n_networks_excluded_after_download": int(len(networks_dropped)),
            "networks_excluded_after_download_file": "networks_excluded_after_download.csv",
            "rivers_excluded_before_download_file": "raw_cache/candidate_rivers_excluded.csv",
            "stations_below_year_floor_file": "stations_below_year_floor.csv",
            "max_stations_per_network_cap": int(args.max_stations_per_network),
            "max_years_per_station_cap": int(args.max_years_per_station),
        },
        "aggregation_rule": {
            "source_rows": "Hub'Eau temperature/chronique instantaneous observations",
            "daily_value": (
                "arithmetic mean of acceptable observations of the station's single accepted "
                "Sandre code within one calendar day"
            ),
            "min_observations_per_day": int(args.min_obs_per_day),
            "days_below_floor": "dropped and counted, never interpolated",
            "plausible_range_c": list(PLAUSIBLE_TEMPERATURE_C),
            "n_dropped_qc_definition": (
                "sub-daily observations removed before aggregation: unparsable date, non-finite "
                "resultat, or resultat outside the plausible range. Observations on days that fail "
                "the min-observations floor are not counted here; those days are reported in "
                "n_days_below_min_obs."
            ),
            "complete_calendar_year": (
                "every calendar day of a year that has ended carries a daily value (frozen rule: "
                "experiments/wrr_revision/universe.py full_calendar_year and "
                "scripts/234_wrr_sealed_confirmation_score.py _complete_years_from_series)"
            ),
            "sensitivity_file": "raw_cache/complete_year_sensitivity.csv",
            "year_coverage_file": "raw_cache/station_year_coverage.csv",
        },
        "assurance": {
            "statement": assurance,
            "codes_used_by_final_stations": codes_used,
            "n_final_stations": n_stations_final,
            "unqualified_stations": int(
                (stations_provider["accepted_quality_codes"].astype(str) == "4").sum()
            )
            if n_stations_final
            else 0,
            "qualified_stations": int(
                (stations_provider["accepted_quality_codes"].astype(str) == "1").sum()
            )
            if n_stations_final
            else 0,
            "measurement_statistic": (
                "daily mean water temperature (degC) from sub-daily in-situ observations"
            ),
            "measurement_statistic_quality": (
                "unqualified (Sandre code 4)" if codes_used == ["4"] else assurance
            ),
        },
        "emitted_vs_resolved": {
            "resolved_river_stations_in_catalog": int(stations["in_river_panel"].sum()),
            "resolved_stations_with_span_ge_4y": int(spans["span_years"].fillna(0).ge(4).sum())
            if "span_years" in spans.columns
            else None,
            "resolved_candidate_stations_before_cap": resolved_stations,
            "resolved_candidate_networks_before_cap": resolved_networks,
            "resolved_candidate_networks_before_cap_note": (
                "resolved_* counts come from the uncapped preliminary screen; the cap then keeps "
                "the largest --max-networks river groups for the Sandre-code audit and download"
            ),
            "cap_applied": {
                "max_networks": int(args.max_networks),
                "max_stations_per_network": int(args.max_stations_per_network),
                "networks_beyond_cap": int(len(pre_cap_networks_dropped)),
                "network_ids_beyond_cap": [
                    str(item.get("network_id")) for item in pre_cap_networks_dropped
                ],
                "stations_per_network_note": (
                    "at most --max-stations-per-network stations per network are downloaded, "
                    "preferring Sandre code 1 stations and then the largest series"
                ),
            },
            "tranche_filter": {
                "network_keys": [k for k in str(args.network_keys).split(",") if k.strip()],
                "networks_withheld_from_this_emission": int(len(tranche_dropped)),
                "file": "raw_cache/networks_withheld_by_tranche_filter.csv",
            },
            "stations_not_downloaded_beyond_network_cap": int(
                sum(
                    1
                    for item in dropped_stations
                    if "beyond --max-stations-per-network cap" in str(item.get("reason"))
                )
            ),
            "stations_downloaded": int(len(station_daily)),
            "emitted_networks": int(len(network_rows)),
            "emitted_stations": n_stations_final,
            "emitted_station_years": n_station_years,
        },
        "days_below_observation_floor": {
            "min_observations_per_day": int(args.min_obs_per_day),
            "n_days_in_span": int(stations_provider["n_days_in_span"].sum()) if n_stations_final else 0,
            "n_days_with_observations": int(stations_provider["n_days_with_obs"].sum())
            if n_stations_final
            else 0,
            "n_days_with_daily_value": int(stations_provider["n_days_daily_value"].sum())
            if n_stations_final
            else 0,
            "n_days_zero_observations": int(stations_provider["n_days_zero_obs"].sum())
            if n_stations_final
            else 0,
            "n_days_below_floor": int(stations_provider["n_days_below_min_obs"].sum())
            if n_stations_final
            else 0,
            "share_of_days_with_obs_below_floor": (
                float(
                    stations_provider["n_days_below_min_obs"].sum()
                    / max(int(stations_provider["n_days_with_obs"].sum()), 1)
                )
                if n_stations_final
                else None
            ),
        },
        "qualification_code_mix_per_emitted_station": {
            str(row.station_id): {
                "network_id": str(row.network_id),
                "accepted_code": str(row.accepted_quality_codes),
                "quality_assurance": str(row.quality_assurance),
                "count_code_1": int(row.hubeau_code1_count),
                "count_code_2": int(row.hubeau_code2_count),
                "count_code_3": int(row.hubeau_code3_count),
                "count_code_4": int(row.hubeau_code4_count),
            }
            for row in stations_provider.itertuples(index=False)
        }
        if n_stations_final
        else {},
        "counts": {
            "n_networks": int(len(network_rows)),
            "n_stations": n_stations_final,
            "n_station_years": n_station_years,
            "n_candidate_stations_screened": int(len(candidates)),
            "n_river_stations_screened": int(stations["in_river_panel"].sum()),
        },
        "networks": network_rows,
        "prior_access": {
            "protocol_rule": "no station in the panel may appear in the v17/v18 study rosters",
            "sources_scanned": prior_sources,
            "conflicts": prior_conflicts,
            "n_conflicting_stations_ingested": sum(len(v) for v in prior_conflicts.values()),
        },
        "ambiguous_river_names": {
            "rule": (
                "one river name that maps to more than one DCE watercourse code (code_cours_eau) "
                "cannot certify a single agency river; every station in such a name cluster is "
                "excluded from the panel rather than guessed into a network"
            ),
            "n_clusters": int(ambiguous_clusters["river_key"].nunique()) if not ambiguous_clusters.empty else 0,
            "n_stations_excluded": int(ambiguous_stations),
            "file": "raw_cache/ambiguous_river_name_clusters.csv",
        },
        "module_consistency_check": module_check,
        "protocol_rule_3_conformance": {
            "rule": (
                "the transport protocol requires a provider daily statistic in degrees C, with the "
                "provider's stated statistic recorded per station"
            ),
            "hubeau_finding": (
                "Hub'Eau temperature/chronique publishes instantaneous sub-daily in-situ "
                "observations (date_mesure_temp + heure_mesure_temp, libelle_parametre "
                "'Temperature de l'Eau'), not an agency-computed daily statistic. The daily "
                "statistic in this panel is DERIVED by scripts/242 with the documented aggregation "
                "rule; measurement_statistic records that derivation, not a provider claim."
            ),
            "verdict": "strict rule-3 non-conformance; ingest is honest and documented, admission is the coordinator's call",
        },
        "caveats": [
            "Hub'Eau temperature chronique values are instantaneous in-situ observations "
            "(probe readings), not agency-computed daily statistics; the daily series here is "
            "derived by this script's documented aggregation rule (protocol rule 3 is therefore "
            "met only by derivation, not by a provider-published daily statistic).",
            "Sandre qualification provenance is per station and is never mixed inside one "
            "station; code 4 stations are unqualified and are a lower-assurance subset.",
            "No frozen-screen performance was computed on this panel; ingest and QC only.",
            "The panel is French metropolitan (plus any overseas) river water temperature and "
            "cannot represent other climate contexts by itself.",
            "Loire last-check sites and the Loire river cluster are excluded, as required by the "
            "shared download policy.",
        ],
        "failures": failures,
    }
    (OUT_ROOT / "ingest.json").write_text(json.dumps(ingest, indent=2, ensure_ascii=False) + "\n")
    print(
        f"  outputs: {len(network_rows)} networks, {n_stations_final} stations, "
        f"{n_station_years} complete station-years",
        flush=True,
    )
    print(f"  assurance: {assurance}", flush=True)
    return ingest


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def module_consistency_check(
    hub: CachedHub, candidates: pd.DataFrame, *, refresh: bool
) -> dict[str, Any]:
    """Compare one cached code-1 year against the shared module's own fetcher."""

    code1 = candidates.loc[candidates["download_code"].eq("1")].sort_values("station_id")
    if code1.empty:
        return {
            "performed": False,
            "reason": "no candidate station has enough Sandre code-1 observations",
        }
    row = code1.iloc[0]
    station_id = str(row.station_id)
    year = int(pd.Timestamp(row.first_obs_date).year)
    start_ts = pd.Timestamp(year=year, month=1, day=1)
    end_ts = pd.Timestamp(year=year, month=12, day=31)
    try:
        module_rows = hubeau_chronique_rows(station_id, start_ts, end_ts)
    # The comparison is optional provenance; a transport failure must be reported, not hidden.
    except Exception as error:  # noqa: BLE001
        return {"performed": False, "reason": f"module fetch failed: {type(error).__name__}: {error}"}
    script_rows = fetch_window(hub, station_id, start_ts, end_ts, "1", refresh=False)

    def key(item: dict[str, Any]) -> tuple[str, float]:
        date = str(item.get("date") or item.get("date_mesure_temp"))
        value = item.get("temperature_c") if "temperature_c" in item else item.get("resultat")
        return (date, round(float(value), 6) if value is not None else float("nan"))

    same = sorted(map(key, module_rows)) == sorted(map(key, script_rows))
    return {
        "performed": True,
        "station_id": station_id,
        "window": f"{start_ts.date()}..{end_ts.date()}",
        "n_module_rows": int(len(module_rows)),
        "n_script_rows": int(len(script_rows)),
        "rows_identical": bool(same),
        "module_rows_carry_time_field": bool(module_rows and "time" in module_rows[0]),
        "note": (
            "scripts/242 code-1 window fetch vs hubeau_chronique_rows on the same window; "
            "compared on (date, resultat) because the module's row dicts carry no heure_mesure_temp"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default="all", choices=("all", "catalog", "spans", "qualify", "download"))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--retries", type=int, default=6)
    parser.add_argument("--pause", type=float, default=0.0)
    parser.add_argument("--refresh", action="store_true", help="ignore cached API responses")
    parser.add_argument("--min-obs-per-day", type=int, default=4)
    parser.add_argument("--sensitivity-thresholds", default="1,4,24")
    parser.add_argument("--min-span-years", type=float, default=4.0)
    parser.add_argument("--min-observations", type=int, default=1461)
    parser.add_argument("--min-code1-observations", type=int, default=1461)
    parser.add_argument("--max-stations-per-network", type=int, default=4)
    parser.add_argument(
        "--network-keys",
        default="",
        help="optional comma list of network ids or river keys to emit only those (tranche filter)",
    )
    parser.add_argument(
        "--max-networks",
        type=int,
        default=15,
        help="keep only the largest N candidate river groups (0 = no cap); the cap is reported",
    )
    parser.add_argument("--download-workers", type=int, default=2)
    parser.add_argument("--outer-retries", type=int, default=3)
    parser.add_argument("--max-years-per-station", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true", help="stop after candidate selection")
    args = parser.parse_args()

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    retrieved_utc = utc_now()
    as_of = pd.Timestamp(retrieved_utc[:10])
    hub = CachedHub(
        RAW,
        workers=args.workers,
        timeout=args.timeout,
        retries=args.retries,
        pause=args.pause,
        outer_retries=args.outer_retries,
    )
    thresholds = [int(value) for value in str(args.sensitivity_thresholds).split(",") if value.strip()]
    if int(args.min_obs_per_day) not in thresholds:
        thresholds.append(int(args.min_obs_per_day))

    print(f"Hub'Eau ingest -> {OUT_ROOT.relative_to(ROOT)}", flush=True)
    print(f"retrieved_utc {retrieved_utc}", flush=True)

    stations = stage_catalog(hub, refresh=args.refresh)
    if args.stage == "catalog":
        return
    spans = stage_spans(hub, stations, refresh=args.refresh)
    if args.stage == "spans":
        return

    # Preliminary pass on span/volume alone decides which rivers need a per-code
    # audit; the Sandre-code audit then covers those rivers' stations only.
    # Uncapped pass: the true resolved pool (for honest "resolved vs emitted" reporting).
    preliminary_all, networks_all, _, _, _, ambiguous_pre, _ = select_candidates(
        stations,
        spans,
        None,
        min_span_years=args.min_span_years,
        min_observations=args.min_observations,
        min_code1_observations=args.min_code1_observations,
        max_networks=0,
    )
    # Capped pass: the pool actually audited and downloaded (bounds API work).
    preliminary, preliminary_networks, _, _, capped_pre, _, _ = select_candidates(
        stations,
        spans,
        None,
        min_span_years=args.min_span_years,
        min_observations=args.min_observations,
        min_code1_observations=args.min_code1_observations,
        max_networks=args.max_networks,
    )
    audit_rivers = set(preliminary_networks["river_key"].astype(str)) if not preliminary_networks.empty else set()
    preliminary.to_csv(RAW / "preliminary_candidate_stations.csv", index=False)
    audit_stations = stations.loc[
        stations["in_river_panel"]
        & stations["river_name"].map(normalize_river).isin(audit_rivers)
    ].copy()
    print(
        f"  preliminary screen (uncapped): {len(preliminary_all)} stations on "
        f"{len(networks_all)} rivers can still reach {MIN_COMPLETE_YEARS} complete years; "
        f"--max-networks {args.max_networks} keeps {len(preliminary)} stations on "
        f"{len(preliminary_networks)} rivers ({len(capped_pre)} rivers beyond the cap); "
        f"{len(audit_stations)} stations enter the Sandre-code audit",
        flush=True,
    )
    qualification, global_counts = stage_qualification(
        hub, audit_stations, spans, refresh=args.refresh
    )
    if args.stage == "qualify":
        return

    (
        candidates,
        networks,
        excluded_rivers,
        loire_blocked,
        capped_networks,
        ambiguous_frame,
        tranche_dropped,
    ) = select_candidates(
        stations,
        spans,
        qualification,
        min_span_years=args.min_span_years,
        min_observations=args.min_observations,
        min_code1_observations=args.min_code1_observations,
        max_networks=args.max_networks,
        network_keys=[key for key in str(args.network_keys).split(",") if key.strip()],
    )
    if capped_networks:
        print(
            f"    --max-networks {args.max_networks}: dropping {len(capped_networks)} smaller river "
            "groups (recorded in raw_cache/networks_beyond_cap.csv)",
            flush=True,
        )
    pd.DataFrame(excluded_rivers).to_csv(RAW / "candidate_rivers_excluded.csv", index=False)
    pd.DataFrame(capped_networks).to_csv(RAW / "networks_beyond_cap.csv", index=False)
    if capped_pre:
        pd.DataFrame(capped_pre).to_csv(OUT_ROOT / "networks_beyond_cap.csv", index=False)
    pd.DataFrame(tranche_dropped).to_csv(RAW / "networks_withheld_by_tranche_filter.csv", index=False)
    ambiguous_station_count = int(len(ambiguous_frame))
    ambiguous = (
        ambiguous_frame
        .groupby("river_key")
        .agg(
            n_stations=("station_id", "size"),
            n_candidate_stations=("candidate", "sum"),
            code_cours_eau=("code_cours_eau", lambda s: ";".join(sorted(set(s.dropna().astype(str))))),
            river_name=("river_name", lambda s: ";".join(sorted(set(s.astype(str))))),
            station_ids=("station_id", lambda s: ";".join(sorted(s.astype(str)))),
        )
        .reset_index()
    )
    ambiguous.to_csv(RAW / "ambiguous_river_name_clusters.csv", index=False)
    candidates.to_csv(RAW / "candidate_stations.csv", index=False)
    print(
        f"  selection: {len(candidates)} candidate stations on {len(networks)} rivers "
        f"(>= {MIN_STATIONS_PER_NETWORK} stations with span >= {args.min_span_years} y and "
        f">= {args.min_observations} observations)",
        flush=True,
    )
    if not candidates.empty:
        print(
            "    download codes: "
            f"code 1 on {int((candidates['download_code'] == '1').sum())} stations, "
            f"code 4 on {int((candidates['download_code'] == '4').sum())} stations",
            flush=True,
        )
    if args.dry_run:
        return

    module_check = module_consistency_check(hub, candidates, refresh=args.refresh)
    qc_frame, station_daily, failures = stage_download(
        hub,
        candidates,
        min_obs_per_day=args.min_obs_per_day,
        sensitivity_thresholds=thresholds,
        max_stations_per_network=args.max_stations_per_network,
        max_years_per_station=args.max_years_per_station,
        as_of=as_of,
        refresh=args.refresh,
        download_workers=args.download_workers,
    )
    failures = list(hub.failures) + list(failures)

    prior_by_source, prior_used = prior_access_ids()
    ingested_ids = set(qc_frame["station_id"].astype(str)) if not qc_frame.empty else set()
    prior_hits = sorted(ingested_ids & prior_used)
    prior_conflicts = {"station_ids": prior_hits} if prior_hits else {}
    if prior_hits:
        print(
            "  LOUD WARNING: ingested stations appear in prior programme artifacts: "
            f"{prior_hits}",
            flush=True,
        )

    request_manifest = hub.manifest()
    dropped_file = RAW / "stations_dropped_waterbody_filter.csv"
    dropped_waterbody = (
        pd.read_csv(dropped_file, dtype=str).to_dict(orient="records") if dropped_file.is_file() else []
    )
    write_outputs(
        stations=stations,
        spans=spans,
        qualification=qualification,
        candidates=candidates,
        networks=networks,
        qc_frame=qc_frame,
        station_daily=station_daily,
        excluded_networks=excluded_rivers,
        dropped_waterbody=dropped_waterbody,
        global_counts=global_counts,
        loire_blocked=loire_blocked,
        failures=failures,
        args=args,
        retrieved_utc=retrieved_utc,
        request_manifest=request_manifest,
        prior_conflicts=prior_conflicts,
        prior_sources={key: len(value) for key, value in prior_by_source.items()},
        module_check=module_check,
        capped_networks=capped_networks,
        tranche_dropped=tranche_dropped,
        resolved_networks=int(networks_all["network_id"].nunique()) if not networks_all.empty else 0,
        resolved_stations=int(len(preliminary_all)),
        pre_cap_networks_dropped=[dict(item) for item in capped_pre],
        ambiguous_clusters=ambiguous,
        ambiguous_stations=ambiguous_station_count,
    )
    if failures:
        print(f"INGEST COMPLETED WITH {len(failures)} FAILURES", flush=True)
        for item in failures[:20]:
            print(f"    {item}", flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
