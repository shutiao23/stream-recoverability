"""Evaluation universe and complete-year thermal-truth roster for the WRR revision.

Step 1 of the 2026-09-07 review: classify waterbodies, record station-year
coverage and donor availability, and freeze a trusted reference panel. The
reference series is never imputed. Incomplete calendar years are not annual
thermal-peak truth. Non-river objects are listed separately and are not
averaged into the river main experiment.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pandas as pd

from stream_recoverability.analysis.us_heterogeneity import (
    load_gages_major_dams,
    regulation_stratum,
)
from stream_recoverability.data.rws_temperature import RIVER_NETWORKS
from stream_recoverability.experiments.development_recovery import read_temperature_panel
from stream_recoverability.experiments.wrr_revision.paths import (
    CANDIDATES,
    DEVELOPMENT_INVENTORY,
    FIRST_PANEL_ROOT,
    FIRST_PLACEMENTS,
    GAGES_II_ARCHIVE,
    JJA_MONTHS,
    P0_SECOND,
    QC_SUMMARY,
    RESULTS_ROOT,
    SECOND_PANEL_ROOT,
    SECOND_PLACEMENTS,
    STEP1_UNIVERSE,
    UNIVERSE_AS_OF,
    WARM_SEASON_MONTHS,
)
from stream_recoverability.experiments.wrr_revision.thermal import (
    annual_hottest_consecutive_mean,
    calendar_year_index,
    seasonal_hottest_consecutive_mean,
)

RIVER_FAMILY = "river"
NON_RIVER_FAMILY = "non_river"

# Explicit waterbody classes. These decide the study population; name heuristics
# are a fallback only when a network is absent from this map.
EXPLICIT_WATERBODY: dict[str, str] = {
    "rws_noordzee": "sea",
    "rws_waddenzee": "sea",
    "rws_ijsselmeer_markermeer": "lake",
    "rws_grevelingen": "lake",
    "rws_volkerak_krammer": "lake",
    "rws_haringvliet": "estuary",
    "rws_westerschelde": "estuary",
    "rws_oosterschelde": "estuary",
    "rws_rijn_maas_delta": "estuary_delta",
    "rws_amsterdam_rijnkanaal": "canal",
    "rws_twentekanalen": "canal",
    "rws_maas": "river",
    "rws_rijn_lek_nederrijn": "river",
    "ehyd_neusiedler_see": "lake",
    "eccc_automated_great_lakes": "lake",
    "eccc_automated_maritime_coastal": "coastal",
    "ccg_st_lawrence_ship_channel": "canal",
}

NON_RIVER_CLASSES = frozenset(
    {"sea", "lake", "estuary", "estuary_delta", "canal", "coastal", "other_non_river"}
)

_NAME_RULES: tuple[tuple[str, str], ...] = (
    ("ship_channel", "canal"),
    ("kanaal", "canal"),
    ("kanalen", "canal"),
    ("canal", "canal"),
    ("noordzee", "sea"),
    ("waddenzee", "sea"),
    ("_zee", "sea"),
    ("great_lakes", "lake"),
    ("_lake", "lake"),
    ("lakes", "lake"),
    ("_meer", "lake"),
    ("neusiedler", "lake"),
    ("delta", "estuary_delta"),
    ("estuar", "estuary"),
    ("coastal", "coastal"),
    ("harbour", "coastal"),
    ("harbor", "coastal"),
)


def classify_waterbody(
    network_id: str,
    *,
    river_group: str | None = None,
    qc_status: str | None = None,
) -> dict[str, str]:
    """Return waterbody class, family, and the rule that assigned them."""

    nid = str(network_id)
    if nid in EXPLICIT_WATERBODY:
        waterbody = EXPLICIT_WATERBODY[nid]
        rule = "explicit_network_map"
    else:
        haystack = f"{nid} {river_group or ''}".lower()
        waterbody = "river"
        rule = "default_river"
        for token, klass in _NAME_RULES:
            if token in haystack:
                waterbody = klass
                rule = f"name_token:{token}"
                break
        if waterbody == "river" and str(qc_status) == "non_river_domain_excluded":
            waterbody = "other_non_river"
            rule = "legacy_qc_non_river_domain_excluded"

    if nid in RIVER_NETWORKS:
        waterbody = "river"
        rule = "rws_river_allowlist"

    family = RIVER_FAMILY if waterbody == "river" else NON_RIVER_FAMILY
    return {
        "network_id": nid,
        "waterbody_class": waterbody,
        "waterbody_family": family,
        "classification_rule": rule,
    }


def year_has_ended(year: int, as_of: str = UNIVERSE_AS_OF) -> bool:
    as_of_ts = pd.Timestamp(as_of)
    return int(year) < int(as_of_ts.year) or (
        int(year) == int(as_of_ts.year) and as_of_ts >= pd.Timestamp(f"{int(year)}-12-31")
    )


def _id_set(path: Path, column: str = "network_id") -> set[str]:
    if not path.exists():
        return set()
    frame = pd.read_csv(path, usecols=[column])
    return set(frame[column].astype(str))


def _load_optional_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _regulation_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}
    inventory = _load_optional_csv(DEVELOPMENT_INVENTORY)
    if not inventory.empty and {"network_id", "regulation_stratum"}.issubset(inventory.columns):
        for row in inventory.itertuples(index=False):
            lookup[str(row.network_id)] = str(row.regulation_stratum)
    candidates = _load_optional_csv(CANDIDATES)
    archive = GAGES_II_ARCHIVE
    if candidates.empty or not archive.is_file() or "site_ids" not in candidates.columns:
        return lookup
    try:
        gages = load_gages_major_dams(archive)
    except (OSError, ValueError, KeyError):
        return lookup
    for row in candidates.itertuples(index=False):
        network_id = str(row.network_id)
        if network_id in lookup and lookup[network_id] not in {"", "nan", "unmatched_gages"}:
            continue
        lookup[network_id] = regulation_stratum(row.site_ids, gages)
    return lookup


def v16_design_role(
    network_id: str,
    *,
    first_ids: set[str],
    second_ids: set[str],
    confirmation_scored_ids: set[str],
    has_temperature: bool,
) -> str:
    nid = str(network_id)
    if nid in first_ids:
        return "first_panel_development"
    if nid in second_ids:
        return "second_panel_descriptive"
    if nid in confirmation_scored_ids:
        return "v16_confirmation_scored"
    if has_temperature:
        return "unscored_available"
    return "no_temperature"


def evidence_use(v16_role: str, eligible_annual_truth: bool) -> str:
    if not eligible_annual_truth:
        return "excluded_from_annual_main"
    if v16_role == "first_panel_development":
        return "design_development"
    if v16_role == "second_panel_descriptive":
        return "descriptive_second"
    if v16_role == "v16_confirmation_scored":
        return "retrospective_opened"
    if v16_role == "unscored_available":
        return "candidate_unseen"
    return "excluded_from_annual_main"


def exclusion_reason(
    *,
    has_temperature: bool,
    waterbody_family: str,
    observed_days: int,
    full_calendar_year: bool,
    year_ended: bool,
) -> str:
    if not has_temperature:
        return "no_temperature"
    if observed_days <= 0:
        return "no_observed_days"
    if waterbody_family != RIVER_FAMILY:
        return "non_river_waterbody"
    if not year_ended:
        return "year_not_ended"
    if not full_calendar_year:
        return "incomplete_calendar_year"
    return ""


def station_year_coverage(
    panel: pd.DataFrame,
    network_id: str,
    *,
    as_of: str = UNIVERSE_AS_OF,
) -> pd.DataFrame:
    """One row per station-year. Missing calendar days remain missing."""

    if panel is None or panel.empty or panel.shape[1] == 0:
        return pd.DataFrame()
    daily = panel.copy().sort_index()
    daily.columns = daily.columns.astype(str)
    numeric = daily.apply(pd.to_numeric, errors="coerce")
    observed = numeric.notna()
    start_year = int(observed.index.min().year)
    end_year = int(observed.index.max().year)
    stations = list(observed.columns)
    rows: list[dict[str, object]] = []
    for year in range(start_year, end_year + 1):
        calendar = calendar_year_index(year)
        year_obs = observed.reindex(calendar).fillna(False).astype(bool)
        jja = year_obs.index.month.isin(JJA_MONTHS)
        warm = year_obs.index.month.isin(WARM_SEASON_MONTHS)
        ended = year_has_ended(year, as_of=as_of)
        for station in stations:
            target = year_obs[station]
            donors = [name for name in stations if name != station]
            if donors:
                donor_obs = year_obs[donors]
                n_donors_any = int((donor_obs.sum(axis=0) > 0).sum())
                n_donors_full = int((donor_obs.all(axis=0)).sum())
                days_with_donor = int(donor_obs.any(axis=1).sum())
            else:
                n_donors_any = 0
                n_donors_full = 0
                days_with_donor = 0
            values = numeric[station]
            annual_peak = annual_hottest_consecutive_mean(values, year)
            warm_peak = seasonal_hottest_consecutive_mean(values, year, months=WARM_SEASON_MONTHS)
            peaks_agree = (
                np.isfinite(annual_peak)
                and np.isfinite(warm_peak)
                and abs(float(annual_peak) - float(warm_peak)) < 1e-9
            )
            observed_days = int(target.sum())
            full_year = bool(target.all())
            rows.append(
                {
                    "network_id": str(network_id),
                    "station_id": str(station),
                    "year": int(year),
                    "expected_days": int(len(calendar)),
                    "observed_days": observed_days,
                    "missing_days": int(len(calendar) - observed_days),
                    "full_calendar_year": full_year,
                    "year_ended": bool(ended),
                    "jja_expected_days": int(jja.sum()),
                    "jja_observed_days": int(target.loc[jja].sum()),
                    "jja_complete": bool(target.loc[jja].all()) if int(jja.sum()) else False,
                    "warm_season_expected_days": int(warm.sum()),
                    "warm_season_observed_days": int(target.loc[warm].sum()),
                    "warm_season_complete": bool(target.loc[warm].all()) if int(warm.sum()) else False,
                    "n_network_stations": int(len(stations)),
                    "n_donors_any": n_donors_any,
                    "n_donors_full_year": n_donors_full,
                    "days_with_any_donor": days_with_donor,
                    "annual_hottest_30": annual_peak,
                    "warm_season_hottest_30": warm_peak,
                    "warm_season_equals_annual_peak": bool(peaks_agree),
                }
            )
    return pd.DataFrame(rows)


def _network_qc_row(directory: Path) -> dict[str, object]:
    summary_path = directory / "network_qc_summary.csv"
    if not summary_path.exists():
        return {}
    frame = pd.read_csv(summary_path)
    if frame.empty:
        return {}
    return {str(k): v for k, v in frame.iloc[0].to_dict().items()}


def iter_network_directories() -> list[tuple[str, Path, str]]:
    """Yield (network_id, directory, source_root). First-panel path wins on overlap."""

    found: dict[str, tuple[Path, str]] = {}
    for root, label in ((FIRST_PANEL_ROOT, "first"), (SECOND_PANEL_ROOT, "second")):
        if not root.exists():
            continue
        for path in sorted(root.iterdir()):
            if not path.is_dir():
                continue
            network_id = path.name
            if network_id in found:
                previous, previous_label = found[network_id]
                found[network_id] = (previous, f"{previous_label}+{label}")
            else:
                found[network_id] = (path, label)
    return [(nid, directory, source) for nid, (directory, source) in sorted(found.items())]


def _temperature_panel(directory: Path) -> pd.DataFrame:
    path = directory / "daily_wide_temperature.csv"
    if not path.exists():
        return pd.DataFrame()
    raw = pd.read_csv(path)
    if raw.empty or "date" not in raw.columns or raw.shape[1] < 2:
        return pd.DataFrame()
    if raw["date"].isna().all():
        return pd.DataFrame()
    return read_temperature_panel(str(path))


def confirmation_scored_ids() -> set[str]:
    path = RESULTS_ROOT / "step8_frozen_replay" / "station_year_replay.csv"
    return _id_set(path)


def build_universe(*, as_of: str = UNIVERSE_AS_OF) -> dict[str, pd.DataFrame | dict]:
    """Scan available daily panels and freeze the station-year roster."""

    first_ids = _id_set(FIRST_PLACEMENTS)
    second_ids = _id_set(P0_SECOND) | _id_set(SECOND_PLACEMENTS)
    scored_ids = confirmation_scored_ids()
    qc = _load_optional_csv(QC_SUMMARY)
    qc_by_id = {}
    if not qc.empty:
        qc_by_id = {str(row.network_id): row for row in qc.itertuples(index=False)}
    regulation = _regulation_lookup()

    network_rows: list[dict[str, object]] = []
    station_frames: list[pd.DataFrame] = []
    for network_id, directory, source in iter_network_directories():
        panel = _temperature_panel(directory)
        qc_row = _network_qc_row(directory)
        river_group = None
        qc_status = None
        provider = None
        if network_id in qc_by_id:
            meta = qc_by_id[network_id]
            river_group = getattr(meta, "river_group", None)
            qc_status = getattr(meta, "qc_status", None)
            provider = getattr(meta, "provider", None)
        if river_group is None:
            river_group = qc_row.get("river_group")
        if qc_status is None:
            qc_status = qc_row.get("qc_status")
        if provider is None:
            provider = qc_row.get("provider")
        classified = classify_waterbody(
            network_id, river_group=None if river_group is None else str(river_group), qc_status=None if qc_status is None else str(qc_status)
        )
        has_temperature = not panel.empty
        role = v16_design_role(
            network_id,
            first_ids=first_ids,
            second_ids=second_ids,
            confirmation_scored_ids=scored_ids,
            has_temperature=has_temperature,
        )
        coverage = station_year_coverage(panel, network_id, as_of=as_of) if has_temperature else pd.DataFrame()
        if not coverage.empty:
            coverage = coverage.copy()
            coverage["waterbody_class"] = classified["waterbody_class"]
            coverage["waterbody_family"] = classified["waterbody_family"]
            coverage["v16_role"] = role
            coverage["source_root"] = source
            coverage["legacy_qc_status"] = str(qc_status) if qc_status is not None else ""
            coverage["regulation_status"] = regulation.get(network_id, "unknown")
            coverage["eligible_annual_truth"] = (
                coverage["waterbody_family"].eq(RIVER_FAMILY)
                & coverage["full_calendar_year"]
                & coverage["year_ended"]
            )
            coverage["eligible_warm_season_truth"] = (
                coverage["waterbody_family"].eq(RIVER_FAMILY)
                & coverage["warm_season_complete"]
                & coverage["year_ended"]
            )
            coverage["exclusion_reason"] = [
                exclusion_reason(
                    has_temperature=True,
                    waterbody_family=str(row.waterbody_family),
                    observed_days=int(row.observed_days),
                    full_calendar_year=bool(row.full_calendar_year),
                    year_ended=bool(row.year_ended),
                )
                for row in coverage.itertuples(index=False)
            ]
            coverage["evidence_use"] = [
                evidence_use(str(row.v16_role), bool(row.eligible_annual_truth))
                for row in coverage.itertuples(index=False)
            ]
            coverage["opened_in_review_20260907"] = (
                coverage["v16_role"].eq("v16_confirmation_scored")
                & coverage["eligible_annual_truth"]
            )
            station_frames.append(coverage)

        n_complete = int(coverage["eligible_annual_truth"].sum()) if not coverage.empty else 0
        n_years = int(coverage["year"].nunique()) if not coverage.empty else 0
        network_rows.append(
            {
                "network_id": network_id,
                "provider": None if provider is None else str(provider),
                "river_group": None if river_group is None else str(river_group),
                "legacy_qc_status": None if qc_status is None else str(qc_status),
                "source_root": source,
                "v16_role": role,
                "waterbody_class": classified["waterbody_class"],
                "waterbody_family": classified["waterbody_family"],
                "classification_rule": classified["classification_rule"],
                "regulation_status": regulation.get(network_id, "unknown"),
                "has_temperature": has_temperature,
                "n_stations": 0 if panel.empty else int(panel.shape[1]),
                "n_days": 0 if panel.empty else int(len(panel)),
                "start": None if panel.empty else str(panel.index.min().date()),
                "end": None if panel.empty else str(panel.index.max().date()),
                "n_station_years": 0 if coverage.empty else int(len(coverage)),
                "n_eligible_annual_station_years": n_complete,
                "n_calendar_years_present": n_years,
                "in_river_main": classified["waterbody_family"] == RIVER_FAMILY,
            }
        )

    networks = pd.DataFrame(network_rows)
    station_years = pd.concat(station_frames, ignore_index=True) if station_frames else pd.DataFrame()
    exclusions = _exclusion_counts(networks, station_years)
    warm_agreement = _warm_season_agreement(station_years)
    summary = summarize_universe(networks, station_years, exclusions, warm_agreement, as_of=as_of)
    return {
        "networks": networks,
        "station_years": station_years,
        "exclusions": exclusions,
        "warm_season_agreement": warm_agreement,
        "summary": summary,
    }


def _exclusion_counts(networks: pd.DataFrame, station_years: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if not networks.empty:
        for reason, count in networks["waterbody_class"].value_counts().items():
            rows.append(
                {
                    "level": "network",
                    "reason": f"waterbody_class={reason}",
                    "n": int(count),
                }
            )
        for reason, count in networks["v16_role"].value_counts().items():
            rows.append({"level": "network", "reason": f"v16_role={reason}", "n": int(count)})
    if not station_years.empty:
        for reason, count in station_years["exclusion_reason"].value_counts().items():
            rows.append({"level": "station_year", "reason": str(reason) or "eligible", "n": int(count)})
        for reason, count in station_years["evidence_use"].value_counts().items():
            rows.append({"level": "station_year", "reason": f"evidence_use={reason}", "n": int(count)})
    return pd.DataFrame(rows)


def _warm_season_agreement(station_years: pd.DataFrame) -> pd.DataFrame:
    if station_years.empty:
        return pd.DataFrame()
    eligible = station_years.loc[station_years["eligible_annual_truth"]].copy()
    if eligible.empty:
        return pd.DataFrame()
    grouped = (
        eligible.groupby(["evidence_use", "waterbody_class"], dropna=False)
        .agg(
            n_station_years=("year", "size"),
            n_networks=("network_id", "nunique"),
            n_stations=("station_id", "nunique"),
            warm_equals_annual_rate=("warm_season_equals_annual_peak", "mean"),
            n_warm_complete=("warm_season_complete", "sum"),
        )
        .reset_index()
    )
    return grouped


def summarize_universe(
    networks: pd.DataFrame,
    station_years: pd.DataFrame,
    exclusions: pd.DataFrame,
    warm_season_agreement: pd.DataFrame,
    *,
    as_of: str,
) -> dict:
    river = networks.loc[networks["in_river_main"]] if not networks.empty else networks
    eligible = (
        station_years.loc[station_years["eligible_annual_truth"]]
        if not station_years.empty
        else station_years
    )
    opened = (
        eligible.loc[eligible["opened_in_review_20260907"]]
        if not eligible.empty
        else eligible
    )
    unseen = (
        eligible.loc[eligible["evidence_use"].eq("candidate_unseen")]
        if not eligible.empty
        else eligible
    )
    non_river_scored = []
    if not networks.empty:
        non_river_scored = networks.loc[
            networks["v16_role"].eq("v16_confirmation_scored")
            & ~networks["in_river_main"],
            "network_id",
        ].astype(str).tolist()
    return {
        "as_of": as_of,
        "do_not_impute_reference": True,
        "main_truth_endpoint": "hottest_30_on_complete_calendar_year",
        "warm_season_months": list(WARM_SEASON_MONTHS),
        "n_networks_scanned": int(len(networks)),
        "n_river_networks": int(len(river)),
        "n_non_river_networks": int((~networks["in_river_main"]).sum()) if not networks.empty else 0,
        "n_station_years": int(len(station_years)),
        "n_eligible_annual_station_years": int(len(eligible)),
        "n_eligible_annual_networks": int(eligible["network_id"].nunique()) if not eligible.empty else 0,
        "n_eligible_annual_stations": int(eligible["station_id"].nunique()) if not eligible.empty else 0,
        "n_opened_confirmation_eligible_station_years": int(len(opened)),
        "n_candidate_unseen_station_years": int(len(unseen)),
        "n_candidate_unseen_networks": int(unseen["network_id"].nunique()) if not unseen.empty else 0,
        "v16_non_river_confirmation_network_ids": non_river_scored,
        "opened_confirmation_cannot_be_unseen": True,
        "846_case_subset_is_development_only": True,
        "exclusion_rows": int(len(exclusions)),
        "warm_season_equals_annual_on_complete_years": (
            None
            if warm_season_agreement.empty
            else float(warm_season_agreement["warm_equals_annual_rate"].mean())
        ),
    }


def write_universe(bundle: Mapping[str, pd.DataFrame | dict], directory: Path = STEP1_UNIVERSE) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    networks = bundle["networks"]
    station_years = bundle["station_years"]
    exclusions = bundle["exclusions"]
    warm = bundle["warm_season_agreement"]
    summary = bundle["summary"]
    assert isinstance(networks, pd.DataFrame)
    assert isinstance(station_years, pd.DataFrame)
    assert isinstance(exclusions, pd.DataFrame)
    assert isinstance(warm, pd.DataFrame)
    assert isinstance(summary, dict)
    networks.to_csv(directory / "network_roster.csv", index=False)
    station_years.to_csv(directory / "station_year_roster.csv", index=False)
    exclusions.to_csv(directory / "exclusion_counts.csv", index=False)
    warm.to_csv(directory / "warm_season_agreement.csv", index=False)
    eligible = station_years.loc[station_years["eligible_annual_truth"]] if not station_years.empty else station_years
    if not eligible.empty:
        eligible.to_csv(directory / "trusted_river_complete_years.csv", index=False)
    (directory / "summary.json").write_text(json.dumps(summary, indent=2))
    (directory / "REPORT.md").write_text(_report_markdown(summary, networks, station_years, exclusions, warm))
    return directory


def _report_markdown(
    summary: dict,
    networks: pd.DataFrame,
    station_years: pd.DataFrame,
    exclusions: pd.DataFrame,
    warm: pd.DataFrame,
) -> str:
    lines = [
        "# Step 1 — evaluation universe and complete-year thermal truth",
        "",
        f"As of `{summary.get('as_of')}`. Reference series are not imputed.",
        "The main hottest-30 endpoint is defined only on fully observed calendar years",
        "of river objects. Non-river objects are a transfer population, not part of",
        "the river confirmation average.",
        "",
        "## Frozen denominator",
        "",
        f"- Networks scanned: **{summary.get('n_networks_scanned')}**",
        f"- River networks: **{summary.get('n_river_networks')}**",
        f"- Non-river networks: **{summary.get('n_non_river_networks')}**",
        f"- Eligible river complete station-years: **{summary.get('n_eligible_annual_station_years')}**",
        f"- Eligible networks / stations: **{summary.get('n_eligible_annual_networks')}** / **{summary.get('n_eligible_annual_stations')}**",
        f"- Opened v16 confirmation station-years (development/retrospective only): **{summary.get('n_opened_confirmation_eligible_station_years')}**",
        f"- Candidate unseen complete river station-years: **{summary.get('n_candidate_unseen_station_years')}** "
        f"on **{summary.get('n_candidate_unseen_networks')}** networks",
        "",
        "The 846-case river+complete-year confirmation subset already read in the",
        "2026-09-07 review remains development diagnostics. It is not a new unseen",
        "confirmation set.",
        "",
        "## v16 confirmation networks previously flagged non-river",
        "",
    ]
    ids = summary.get("v16_non_river_confirmation_network_ids") or []
    if ids:
        lines.append(", ".join(f"`{item}`" for item in ids))
    else:
        lines.append("(none)")
    lines.extend(["", "## Warm-season vs annual peak on complete years", ""])
    if warm.empty:
        lines.append("No complete river years were available to test the May–September endpoint.")
    else:
        lines.append(warm.to_string(index=False))
        lines.append("")
        lines.append(
            "A warm-season-only year may be used later only if this agreement rate is "
            "high on complete years and the endpoint is frozen in advance."
        )
    lines.extend(["", "## Exclusion counts", ""])
    if exclusions.empty:
        lines.append("(none)")
    else:
        lines.append(exclusions.to_string(index=False))
    river_classes = (
        networks.loc[~networks["in_river_main"], ["network_id", "waterbody_class", "v16_role"]]
        if not networks.empty
        else networks
    )
    lines.extend(["", "## Non-river objects (transfer list, not river main)", ""])
    if river_classes.empty:
        lines.append("(none)")
    else:
        lines.append(river_classes.to_string(index=False))
    if not station_years.empty:
        uses = (
            station_years.loc[station_years["eligible_annual_truth"]]
            .groupby("evidence_use")
            .agg(
                n_networks=("network_id", "nunique"),
                n_stations=("station_id", "nunique"),
                n_station_years=("year", "size"),
            )
            .reset_index()
        )
        lines.extend(["", "## Eligible river complete years by evidence use", "", uses.to_string(index=False)])
    lines.append("")
    return "\n".join(lines)
