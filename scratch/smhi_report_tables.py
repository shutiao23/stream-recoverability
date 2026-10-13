"""Report tables for the SMHI ingest (reads artifacts only; writes scratch/)."""
from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/wrr_submission_ready/multi_agency_ingest/smhi"
s = pd.read_csv(OUT / "stations_all.csv", dtype={"station_id": str})
cat = pd.read_csv(OUT / "station_catalog.csv", dtype={"id": str})
ing = json.loads((OUT / "ingest.json").read_text())

tbl = (
    s.groupby(["network_id", "catchment_name"], dropna=False)
    .agg(n_stations=("station_id", "size"),
         n_rows=("n_days_any_quality", "sum"),
         first=("first_date_any_quality", "min"),
         last=("last_date_any_quality", "max"),
         lat_median=("latitude", "median"))
    .reset_index()
    .sort_values("n_stations", ascending=False)
)
tbl.to_csv(ROOT / "scratch/smhi_report_networks.csv", index=False)
print("=== downloaded stations per catchment (all ineligible: 0 accepted days) ===")
print(tbl.to_string(index=False))
print()
print("catalog stations:", len(cat), "| downloaded:", ing["n_downloaded"], "| failures:", ing["n_download_failures"])
print("catalog catchmentNumber groups:", cat["catchmentNumber"].nunique(),
      "| groups with >=2 catalog stations:", int((cat.groupby("catchmentNumber").size() >= 2).sum()))
print("quality codes:", ing["qc"]["quality_code_distribution_rows_parsed"], "| accepted rows:", ing["qc"]["n_rows_accepted"])
print("stations with >=4 complete years after QC:", ing["n_stations"])
print("networks:", ing["n_networks"], "| complete station-years:", ing["n_station_years_complete"])
print("grid:", ing["panel_character"]["coverage_note"])
