"""Basin characteristics for the United States stations, from GAGES-II.

The screening mechanism established elsewhere in this study is a property of
estimators and estimands, not of rivers. This module supplies the catchment
physics needed to ask the hydrological question instead: which rivers are hard,
and does the answer follow groundwater contribution, regulation, size or
elevation. Johnson et al. (2021) report that filling can harm
groundwater-influenced sites; `BFI_AVE` is the variable that claim is about.
"""

from __future__ import annotations

import io
import zipfile
from functools import lru_cache

import pandas as pd

from stream_recoverability.experiments.v17_fitness.paths import REPO_ROOT

GAGES_ARCHIVE = REPO_ROOT / "data" / "cache" / "regulation_panel_v1" / "basinchar_and_report_sept_2011.zip"
INNER = "spreadsheets-in-csv-format.zip"

TABLES = {
    "conterm_basinid.txt": ["DRAIN_SQKM", "LAT_GAGE", "LNG_GAGE", "STATE", "HCDN-2009"],
    "conterm_hydro.txt": ["BFI_AVE", "CONTACT", "TOPWET", "RUNAVE7100", "PCT_1ST_ORDER"],
    "conterm_topo.txt": ["ELEV_SITE_M", "ELEV_MEAN_M_BASIN", "SLOPE_PCT"],
    "conterm_hydromod_dams.txt": ["NDAMS_2009", "STOR_NID_2009", "MAJ_NDAMS_2009", "DDENS_2009"],
    "conterm_climate.txt": ["PPTAVG_BASIN", "T_AVG_BASIN", "T_MAX_BASIN"],
    "conterm_bas_classif.txt": ["CLASS", "AGGECOREGION", "HYDRO_DISTURB_INDX"],
}

# Pre-stated direction of each effect on donor synchrony, written before the
# regressions were run. A hypothesis with no declared sign cannot be wrong.
EXPECTED_SIGNS = {
    "BFI_AVE": "negative: groundwater damps the shared atmospheric signal donors carry",
    "CONTACT": "negative: longer subsurface contact time decouples the stream from weather",
    "STOR_NID_2009": "negative: upstream storage imposes a release regime donors do not share",
    "DRAIN_SQKM": "positive: thermal inertia makes large rivers track regional rather than local forcing",
    "ELEV_SITE_M": "none declared",
    "SLOPE_PCT": "none declared",
}


@lru_cache(maxsize=1)
def gages_attributes() -> pd.DataFrame:
    """One row per GAGES-II gauge, carrying the attributes this study uses."""

    if not GAGES_ARCHIVE.exists():
        return pd.DataFrame()
    outer = zipfile.ZipFile(GAGES_ARCHIVE)
    inner = zipfile.ZipFile(io.BytesIO(outer.read(INNER)))
    frame: pd.DataFrame | None = None
    for name, columns in TABLES.items():
        table = pd.read_csv(
            io.BytesIO(inner.read(name)), dtype={"STAID": str}, encoding="latin-1", low_memory=False
        )
        table["STAID"] = table["STAID"].astype(str).str.strip().str.zfill(8)
        keep = ["STAID"] + [c for c in columns if c in table.columns]
        table = table[keep].drop_duplicates("STAID")
        frame = table if frame is None else frame.merge(table, on="STAID", how="outer")
    if frame is None:
        return pd.DataFrame()
    frame = frame.rename(columns={"STAID": "gages_id"})
    numeric = [c for c in frame.columns if c not in ("gages_id", "STATE", "CLASS", "AGGECOREGION")]
    for column in numeric:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    # Storage and area are extremely skewed; the log transform is declared
    # here rather than chosen after seeing a scatter plot.
    import numpy as np

    frame["log_storage"] = np.log10(frame["STOR_NID_2009"].clip(lower=0).fillna(0.0) + 1.0)
    frame["log_area"] = np.log10(frame["DRAIN_SQKM"].clip(lower=1e-3))
    return frame


def match_stations(station_roster: pd.DataFrame) -> pd.DataFrame:
    """Join eligible United States stations to their GAGES-II attributes."""

    attributes = gages_attributes()
    if attributes.empty:
        return pd.DataFrame()
    roster = station_roster.loc[station_roster["provider"].astype(str).eq("usgs")].copy()
    roster["gages_id"] = roster["station_id"].astype(str).str.strip().str.zfill(8)
    merged = roster.merge(attributes, on="gages_id", how="inner")
    return merged
