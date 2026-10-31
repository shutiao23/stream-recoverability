#!/usr/bin/env python3
"""Prepare provider-level scope and unsent source-access drafts."""
from __future__ import annotations
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/wrr_review_response_20261027/source_rights"
PAPER = ROOT / "paper/wrr_tr"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cases = pd.read_parquet(ROOT / "results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet",
                            columns=["provider", "station_key", "year"]).drop_duplicates()
    scope = cases.groupby(["provider", "station_key"]).year.agg(["min", "max", "nunique"]).reset_index()
    scope.rename(columns={"min":"first_complete_year", "max":"last_complete_year", "nunique":"n_complete_years"}, inplace=True)
    scope.to_csv(OUT / "provider_station_scope.csv", index=False)
    counts = scope.groupby("provider").agg(stations=("station_key", "nunique"),
                                             complete_station_years=("n_complete_years", "sum")).reset_index()
    counts.to_csv(OUT / "provider_counts.csv", index=False)
    providers = {
        "arso": ("https://vode.arso.gov.si/hidarhiv/", "v11 ARSO confirmation temperature"),
        "chmi": ("https://opendata.chmi.cz/hydrology/historical/data/measured_temperature", "v11 CHMI confirmation temperature"),
        "foen": ("https://data.bafu.admin.ch/api", "v11 FOEN confirmation temperature"),
        "gkd_bayern": ("https://www.gkd.bayern.de/de/fluesse/wassertemperatur/tabellen", "v11 GKD Bayern confirmation temperature"),
        "hubeau": ("https://hubeau.eaufrance.fr/api/v1/temperature/chronique", "v11 Hub'Eau confirmation temperature"),
        "lubw": ("https://umweltdaten.lubw.baden-wuerttemberg.de/w/online-messstationen", "v11 LUBW confirmation temperature"),
        "nve_hydapi": ("https://hydapi.nve.no/api/v1", "v11 NVE second-confirmation temperature"),
        "rws_waterwebservices": ("https://rijkswaterstaatdata.nl/waterdata/", "v11 RWS confirmation temperature"),
        "syke": ("https://rajapinnat.ymparisto.fi/api/Hydrologiarajapinta/1.2/odata", "v11 SYKE candidate temperature"),
        "usgs": ("https://api.waterdata.usgs.gov/ogcapi/v1/collections/daily", "USGS national regulation panel"),
    }
    rights = pd.read_csv(ROOT / "metadata/data_rights.csv").set_index("artifact")
    rows = []
    for row in counts.itertuples(index=False):
        url, key = providers[row.provider]
        entry = rights.loc[key]
        rows.append(dict(provider=row.provider, stations=row.stations,
                         complete_station_years=row.complete_station_years,
                         source_url=url, recorded_licence=entry["license"],
                         recorded_redistribution=entry.redistribution_allowed,
                         required_citation=entry.required_citation,
                         scope="provider-level source locator and recorded terms; dataset-specific permissions require author confirmation"))
    pd.DataFrame(rows).to_csv(OUT / "provider_source_inventory.csv", index=False)
    lubw = scope.loc[scope.provider.eq("lubw")]
    lubw.to_csv(OUT / "lubw_station_year_scope.csv", index=False)
    ids = ", ".join(lubw.station_key.str.removeprefix("lubw|"))
    (PAPER / "lubw_permission_request_draft.txt").write_text(f"""UNSENT DRAFT — sender identity and external sending require author confirmation.

Proposed recipient: udo@lubw.bwl.de (the UDO service contact; not sent).

Subject: Applicability of UIS terms to temperature exports and reviewer access

Dear LUBW data team,

We are preparing a research article on incomplete river-temperature records.
Our analysis uses reported daily observations from these LUBW station identifiers:
{ids}.
The attached station-year scope records complete years used in model evaluation;
other visible years can also contribute to local historical model fitting. First
and last evaluation years do not imply continuous coverage.
The whole-archive source models also used LUBW cases in estimator training and,
for some target regions, interval calibration. We seek clarification for trained
models, calibration parameters, per-case predictions and evaluation summaries,
in addition to the underlying daily observations.

The official measurement metadata record
https://rips-metadaten.lubw.de/trefferanzeige?docuuid=fff497a2-4fbf-41c1-b871-22f23f3a3a77
and our acquisition landing
https://umweltdaten.lubw.baden-wuerttemberg.de/w/online-messstationen
both link to the UIS usage agreement:
https://www.lubw.baden-wuerttemberg.de/umweltinformationssystem/nutzungsvereinbarung
We found an indexed version describing attributed reuse, but could not retrieve
the complete live agreement in our environment. Please confirm whether these
terms apply to the archived exports for the station identifiers above, and
whether any separate conditions apply to the acquisition vintage or products.
We do not assume that the general website copyright notice alone determines
the source-specific conditions.

Please clarify the conditions for (1) using and processing the records in the
study, (2) providing the original or derived daily values and masked case tables
confidentially to journal reviewers, and (3) preserving and redistributing any
permitted inputs or outputs through a trusted research repository. If public
redistribution is not permitted, please identify an authorised access route for
reviewers and readers. We will cite LUBW and the relevant processing date and
will follow any additional attribution or licence requirements you specify.

No data or commitments are enclosed in this unsent draft. The corresponding
author's name, affiliation, contact information and the journal manuscript
details must be completed before a real request can be considered.

Sincerely,
[Corresponding author]
[Affiliation and email]
""")
    (PAPER / "editor_data_access_draft.txt").write_text("""UNSENT DRAFT — complete only after the authors confirm source rights and reviewer-access arrangements.

Dear Editor,

The manuscript combines data from multiple agencies. The authors identified
source-specific UIS terms linked from the LUBW observation metadata and download
landing, and are confirming their applicability to archived observations,
trained models and derived case-level tables.
We will identify every underlying dataset, its provider, access conditions and
the exact materials available to reviewers. If permission for any necessary
material is restricted, we request guidance on a compliant confidential-review
route or an editorial exception, with the relevant provider's conditions attached.

The software and permitted data will be archived in a trusted repository and
cited once the authors arrange the deposit. This draft does not assert that an
exception has been requested or accepted.

[Corresponding author, affiliation and email]
""")
    print(counts.to_string(index=False), flush=True)
    print(f"Prepared an unsent LUBW request for {len(lubw)} source stations.", flush=True)


if __name__ == "__main__":
    main()
