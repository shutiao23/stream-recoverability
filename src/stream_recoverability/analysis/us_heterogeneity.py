"""US multi-phase heterogeneity panel and mixed calibration-slope models.

The panel combines open-development leave-one-network-out predictions with the
US portions of the first and second outcome panels.  Climate bands use the
frozen HUC2 mapping and regulation uses the public GAGES-II 2009 major-dam
field.  These are descriptive modifiers, not causal reservoir labels.
"""

from __future__ import annotations

import io
import re
import warnings
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

HUC_CLIMATE = {
    "01": "humid_continental",
    "02": "humid_continental",
    "03": "humid_subtropical",
    "04": "humid_continental",
    "05": "humid_continental",
    "06": "humid_subtropical",
    "07": "humid_continental",
    "10": "cold_semiarid",
    "11": "humid_subtropical",
    "12": "subtropical_semiarid",
    "13": "cold_arid_highland",
    "14": "cold_arid_highland",
    "15": "hot_arid",
    "16": "cold_semiarid",
    "17": "marine_west_coast",
    "18": "mediterranean",
    "19": "subarctic",
    "20": "humid_continental",
}


def split_site_ids(value: object) -> list[str]:
    """Split both pipe- and comma-delimited provider station lists."""

    return [
        item.strip()
        for item in re.split(r"[|,]", str(value or ""))
        if item.strip() and item.strip().lower() != "nan"
    ]


def infer_huc2(network_id: object) -> str | None:
    """Recover the HUC2 prefix from the frozen US network identifiers."""

    text = str(network_id)
    match = re.search(r"huc(?:2|4|6|8)_?(\d+)$", text)
    if match is None:
        match = re.search(r"_huc(\d+)$", text)
    if match is None:
        return None
    return match.group(1)[:2].zfill(2)


def climate_band(huc2: object) -> str:
    return HUC_CLIMATE.get(str(huc2 or ""), "unspecified")


def collapse_climate_band(value: object) -> str:
    text = str(value)
    if text in {"humid_continental", "humid_subtropical"}:
        return "humid"
    if text in {
        "cold_semiarid",
        "subtropical_semiarid",
        "hot_arid",
        "cold_arid_highland",
    }:
        return "arid_semiarid"
    if text in {"marine_west_coast", "mediterranean"}:
        return "maritime"
    return "other"


def _staid_key(value: object) -> str:
    digits = re.sub(r"\D", "", str(value))
    if not digits:
        return ""
    return digits.zfill(8) if len(digits) <= 8 else digits


def load_gages_major_dams(archive: Path) -> pd.DataFrame:
    """Read the public GAGES-II major-dam field from its nested archive."""

    if not archive.is_file():
        raise FileNotFoundError(f"GAGES-II archive is required: {archive}")
    with zipfile.ZipFile(archive) as outer:
        nested = outer.read("spreadsheets-in-csv-format.zip")
    with zipfile.ZipFile(io.BytesIO(nested)) as inner:
        pieces = []
        for prefix in ("conterm", "AKHIPR"):
            frame = pd.read_csv(
                inner.open(f"{prefix}_hydromod_dams.txt"),
                dtype={"STAID": str},
                encoding="cp1252",
            )
            pieces.append(frame[["STAID", "MAJ_NDAMS_2009"]])
    result = pd.concat(pieces, ignore_index=True)
    result["STAID"] = result["STAID"].map(_staid_key)
    return result.drop_duplicates("STAID")


def regulation_stratum(site_ids: object, gages: pd.DataFrame) -> str:
    keys = {_staid_key(item) for item in split_site_ids(site_ids)}
    keys.discard("")
    matched = gages.loc[gages["STAID"].isin(keys)]
    if matched.empty:
        return "unmatched_gages"
    major = pd.to_numeric(matched["MAJ_NDAMS_2009"], errors="coerce")
    return "regulated" if major.ge(1).any() else "unregulated"


def _candidate_metadata(
    candidates: pd.DataFrame,
    scored_networks: set[str],
    gages: pd.DataFrame,
) -> pd.DataFrame:
    selected = candidates.loc[
        candidates["domain"].eq("united_states")
        & candidates["network_id"].astype(str).isin(scored_networks)
    ].copy()
    selected["huc2"] = selected["network_id"].map(infer_huc2)
    selected["climate_band"] = selected["huc2"].map(climate_band)
    selected["climate_group"] = selected["climate_band"].map(
        collapse_climate_band
    )
    selected["regulation_stratum"] = selected["site_ids"].map(
        lambda value: regulation_stratum(value, gages)
    )
    selected["n_stations"] = selected["site_ids"].map(
        lambda value: len(split_site_ids(value))
    )
    return selected[
        [
            "network_id",
            "huc2",
            "climate_band",
            "climate_group",
            "regulation_stratum",
            "n_stations",
        ]
    ].drop_duplicates("network_id")


def _station_gap_empirical(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"network_id": str, "station_id": str})
    if "placement" not in frame.columns:
        return frame.rename(
            columns={"empirical_transfer_prediction": "predicted_loss"}
        )[
            [
                "network_id",
                "station_id",
                "gap_length",
                "predicted_loss",
                "observed_recovery_loss",
            ]
        ]
    return (
        frame.groupby(["network_id", "station_id", "gap_length"], as_index=False)
        .agg(
            predicted_loss=("empirical_transfer_prediction", "mean"),
            observed_recovery_loss=("observed_recovery_loss", "mean"),
        )
    )


def build_us_heterogeneity_panel(root: Path, *, gages_archive: Path) -> pd.DataFrame:
    """Build simple and empirical prediction panels over 100+ US networks."""

    gages = load_gages_major_dams(gages_archive)
    inventory = pd.read_csv(
        root / "results/development_v11/network_inventory.csv",
        dtype={"network_id": str},
    )
    development_simple = pd.read_csv(
        root / "results/development_v11/nested_lono_predictions.csv",
        dtype={"network_id": str, "station_id": str},
    ).rename(columns={"simple_prediction": "predicted_loss"})
    development_empirical = _station_gap_empirical(
        root
        / "results/development_v11/reviewer_completion"
        / "development_empirical_predictions.csv"
    )
    development_metadata = inventory[
        [
            "network_id",
            "climate_band",
            "regulation_stratum",
            "n_stations",
        ]
    ].copy()
    development_metadata["huc2"] = development_metadata["network_id"].map(
        infer_huc2
    )
    development_metadata["climate_group"] = development_metadata[
        "climate_band"
    ].map(collapse_climate_band)

    parts: list[pd.DataFrame] = []
    for risk_model, frame in (
        ("simple_descriptors", development_simple),
        ("fitting_period_empirical", development_empirical),
    ):
        parts.append(
            frame.merge(
                development_metadata,
                on="network_id",
                how="inner",
                validate="many_to_one",
            ).assign(phase="development", risk_model=risk_model)
        )

    phase_inputs = (
        (
            "first",
            root / "results/development_v11/route_a_confirmation/predictions.csv",
            root
            / "results/development_v11/reviewer_completion"
            / "confirmation_empirical_predictions.csv",
            root / "results/development_v11/confirmation_candidates.csv",
        ),
        (
            "second",
            root
            / "results/development_v11/second_confirmation/scoring"
            / "simple_predictions.csv",
            root
            / "results/development_v11/second_confirmation/scoring"
            / "empirical_predictions.csv",
            root
            / "results/development_v11/second_confirmation/readiness_roster.csv",
        ),
    )
    for phase, simple_path, empirical_path, candidate_path in phase_inputs:
        simple = pd.read_csv(
            simple_path, dtype={"network_id": str, "station_id": str}
        )
        empirical = _station_gap_empirical(empirical_path)
        candidates = pd.read_csv(candidate_path, dtype=str)
        scored_networks = set(simple["network_id"].astype(str))
        metadata = _candidate_metadata(candidates, scored_networks, gages)
        for risk_model, frame in (
            ("simple_descriptors", simple),
            ("fitting_period_empirical", empirical),
        ):
            parts.append(
                frame.merge(
                    metadata,
                    on="network_id",
                    how="inner",
                    validate="many_to_one",
                ).assign(phase=phase, risk_model=risk_model)
            )

    panel = pd.concat(parts, ignore_index=True, sort=False)
    keep = [
        "risk_model",
        "phase",
        "network_id",
        "station_id",
        "gap_length",
        "predicted_loss",
        "observed_recovery_loss",
        "huc2",
        "climate_band",
        "climate_group",
        "regulation_stratum",
        "n_stations",
    ]
    panel = panel[keep].copy()
    panel["network_uid"] = panel["phase"] + "::" + panel["network_id"]
    for column in (
        "gap_length",
        "predicted_loss",
        "observed_recovery_loss",
        "n_stations",
    ):
        panel[column] = pd.to_numeric(panel[column], errors="coerce")
    panel = panel.dropna(
        subset=["predicted_loss", "observed_recovery_loss", "n_stations"]
    )
    panel["log_network_size"] = np.log1p(panel["n_stations"])
    panel["network_weight"] = 1.0 / panel.groupby(
        ["risk_model", "network_uid"]
    )["network_uid"].transform("size")
    return panel.sort_values(
        ["risk_model", "phase", "network_id", "station_id", "gap_length"]
    ).reset_index(drop=True)


def _interaction_name(moderator: str, level: str) -> str:
    return f"predicted_loss:C({moderator})[T.{level}]"


def fit_mixed_calibration(
    panel: pd.DataFrame, *, risk_model: str, moderator: str
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Fit a random-intercept/random-slope calibration model by network."""

    data = panel.loc[panel["risk_model"].eq(risk_model)].copy()
    data[moderator] = pd.Categorical(data[moderator])
    formula = (
        "observed_recovery_loss ~ "
        f"predicted_loss * C({moderator}) + predicted_loss * C(phase)"
    )
    with warnings.catch_warnings(record=True) as caught:
        result = smf.mixedlm(
            formula,
            data,
            groups=data["network_uid"],
            re_formula="~predicted_loss",
        ).fit(reml=False, method="lbfgs", maxiter=1000, disp=False)
    coefficients = pd.DataFrame(
        {
            "term": result.params.index,
            "estimate": result.params.to_numpy(dtype=float),
            "std_error": result.bse.reindex(result.params.index).to_numpy(dtype=float),
            "p_value": result.pvalues.reindex(result.params.index).to_numpy(dtype=float),
        }
    )
    coefficients["ci_lower"] = coefficients["estimate"] - 1.96 * coefficients[
        "std_error"
    ]
    coefficients["ci_upper"] = coefficients["estimate"] + 1.96 * coefficients[
        "std_error"
    ]
    coefficients.insert(0, "moderator", moderator)
    coefficients.insert(0, "risk_model", risk_model)

    levels = sorted(data[moderator].astype(str).unique())
    params = result.params
    covariance = result.cov_params()
    base = levels[0]
    slope_rows = []
    for level in levels:
        contrast = pd.Series(0.0, index=params.index)
        contrast["predicted_loss"] = 1.0
        term = _interaction_name(moderator, level)
        if level != base and term in contrast.index:
            contrast[term] = 1.0
        estimate = float(contrast @ params)
        variance = float(contrast @ covariance.loc[params.index, params.index] @ contrast)
        std_error = float(np.sqrt(max(variance, 0.0)))
        slope_rows.append(
            {
                "risk_model": risk_model,
                "moderator": moderator,
                "level": level,
                "reference_phase": "development",
                "adjusted_calibration_slope": estimate,
                "std_error": std_error,
                "ci_lower": estimate - 1.96 * std_error,
                "ci_upper": estimate + 1.96 * std_error,
                "n_networks": int(
                    data.loc[data[moderator].astype(str).eq(level), "network_uid"].nunique()
                ),
                "n_station_gaps": len(data.loc[data[moderator].astype(str).eq(level)]),
            }
        )
    diagnostics = {
        "risk_model": risk_model,
        "moderator": moderator,
        "formula": formula,
        "converged": bool(result.converged),
        "warnings": [str(item.message) for item in caught],
        "log_likelihood": float(result.llf),
        "residual_variance": float(result.scale),
        "random_intercept_variance": float(result.cov_re.iloc[0, 0]),
        "random_slope_variance": float(result.cov_re.iloc[1, 1]),
        "random_intercept_slope_covariance": float(result.cov_re.iloc[0, 1]),
        "n_networks": int(data["network_uid"].nunique()),
        "n_station_gaps": len(data),
        "reference_level": base,
        "level_slopes": slope_rows,
    }
    return coefficients, diagnostics


__all__ = [
    "build_us_heterogeneity_panel",
    "climate_band",
    "collapse_climate_band",
    "fit_mixed_calibration",
    "infer_huc2",
    "load_gages_major_dams",
    "regulation_stratum",
    "split_site_ids",
]
