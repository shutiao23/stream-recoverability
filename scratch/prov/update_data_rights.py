"""One-off: update metadata/data_rights.csv rows verified against live sources.

Only the seven v11 rows whose terms were re-verified on 2026-10-12 are touched
(ARSO, CHMI, GKD Bayern, LUBW, RWS, FOEN, SYKE).  Every other row is left
byte-identical.  Run from the repository root:

    python3 scratch/prov/update_data_rights.py
"""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "metadata/data_rights.csv"

D = "2026-10-12"
UPDATES: dict[str, dict[str, str]] = {
    "v11 ARSO confirmation temperature": {
        "license": "ARSO_terms_of_use_no_named_licence_citation_required",
        "redistribution_allowed": (
            "conditional_publication_distribution_permitted_with_mandatory_ARSO_citation"
        ),
        "derived_output_allowed": "true_with_mandatory_ARSO_citation",
        "required_citation": "Agencija Republike Slovenije za okolje (ARSO)",
        "reviewer_access_route": (
            "official_provider_redownload; archive_contains_only_request_metadata_qc_and_"
            "aggregate_losses; evidence 2026-10-12 https://vode.arso.gov.si/hidarhiv/ : "
            '"Pri objavi, distribuciji ali uporabi podatkov v kakr\u0161nekoli namene je '
            'potrebno citirati vir podatkov: Agencije Republike Slovenije za okolje '
            '(ali skraj\u0161ano: ARSO)."'
        ),
    },
    "v11 CHMI confirmation temperature": {
        "license": "CC-BY-4.0",
        "redistribution_allowed": "true",
        "derived_output_allowed": "true",
        "required_citation": (
            "CHMI (\u010cesk\u00fd hydrometeorologick\u00fd \u00fastav); Creative Commons BY 4.0"
        ),
        "reviewer_access_route": (
            "official_provider_redownload; archive_contains_only_request_metadata_qc_and_"
            "aggregate_losses; evidence 2026-10-12 "
            "https://www.chmi.cz/-/jak-mohu-pou%C5%BE%C3%ADvat-otev%C5%99en%C3%A1-data-"
            "%C4%8Dhm%C3%BA- : \"Otev\u0159en\u00e1 data \u010cHM\u00da m\u016f\u017eete vyu\u017e\u00edvat "
            "bezplatn\u011b p\u0159i respektov\u00e1n\u00ed licence Creative Commons BY 4.0.\""
        ),
    },
    "v11 GKD Bayern confirmation temperature": {
        "license": "CC-BY-4.0",
        "redistribution_allowed": "true",
        "derived_output_allowed": "true",
        "required_citation": (
            "Datenquelle: Bayerisches Landesamt f\u00fcr Umwelt, www.lfu.bayern.de"
        ),
        "reviewer_access_route": (
            "official_provider_redownload; archive_contains_only_request_metadata_qc_and_"
            "aggregate_losses; evidence 2026-10-12 https://www.gkd.bayern.de/de/impressum "
            ': "Die Download-Daten im GKD wurden von der Fachseite her mit der '
            '\\"Namensnennung 4.0 International (CC BY 4.0)\\" lizensiert."'
        ),
    },
    "v11 LUBW confirmation temperature": {
        "license": "lubw_copyright_reuse_and_redistribution_require_LUBW_consent",
        "redistribution_allowed": "false",
        "derived_output_allowed": "false",
        "required_citation": (
            "LUBW as source; processing date where possible (Als Quelle ist die LUBW "
            "zu nennen)"
        ),
        "reviewer_access_route": (
            "recreate_official_session; no_opaque_session_token_persisted; "
            "aggregate_losses_only; evidence 2026-10-12 "
            "https://www.lubw.baden-wuerttemberg.de/impressum : \"Alle auf dieser "
            "Internetseite ver\u00f6ffentlichten Beitr\u00e4ge, Abbildungen und Daten sind "
            "urheberrechtlich gesch\u00fctzt. Sie d\u00fcrfen nur mit Zustimmung der LUBW "
            "ver\u00e4ndert, vervielf\u00e4ltigt, in Vervielf\u00e4ltigungen an Dritte abgegeben "
            "oder zu \u00f6ffentlichen Wiedergaben verwendet werden.\""
        ),
    },
    "v11 RWS confirmation temperature": {
        "license": (
            "rijkswaterstaat_open_data_no_named_licence_source_and_retrieval_date_required"
        ),
        "redistribution_allowed": "true",
        "derived_output_allowed": "true",
        "required_citation": (
            "Rijkswaterstaat as source site, with the date the information was taken"
        ),
        "reviewer_access_route": (
            "official_provider_redownload; archive_contains_only_request_metadata_qc_and_"
            "aggregate_losses; evidence 2026-10-12 "
            "https://www.rijkswaterstaat.nl/zakelijk/open-data : \"Rijkswaterstaat stelt "
            "zijn data als open data beschikbaar. Iedereen is vrij om data van "
            "Rijkswaterstaat in te zien en te hergebruiken.\" and "
            "https://rijkswaterstaatdata.nl/vaste-onderdelen/verantwoording/ : \"U mag "
            "informatie van deze site overnemen onder twee voorwaarden: U vermeldt deze "
            "website als bron. U vermeldt op welke datum u de informatie heeft "
            "overgenomen\""
        ),
    },
    "v11 FOEN confirmation temperature": {
        "license": "opendata.swiss_open_use_must_provide_the_source_terms_by",
        "redistribution_allowed": "true",
        "derived_output_allowed": "true",
        "required_citation": (
            "FOEN/BAFU hydrological observations, data.bafu.admin.ch; provide author, "
            "title and link to the dataset"
        ),
        "reviewer_access_route": (
            "official_provider_redownload; archive_contains_only_request_metadata_qc_and_"
            "aggregate_losses; evidence 2026-10-12 "
            "https://api.data-platform.cloud.bafu.admin.ch/en/lizenz-und-quelle : "
            '"The data provided through the platform is published under the \\"Open use. '
            'Must provide the source.\\" licence of the Swiss open-government-data '
            'portal opendata.swiss"'
        ),
    },
    "v11 SYKE candidate temperature": {
        "license": "CC-BY-4.0",
        "redistribution_allowed": "true",
        "derived_output_allowed": "true",
        "required_citation": (
            "Finnish Environment Institute (Syke) with the dataset name "
            "(e.g. Surface water temperature)"
        ),
        "reviewer_access_route": (
            "source_qc_only_no_network_qualified; evidence 2026-10-12 "
            "https://www.syke.fi/en/environmental-data/use-license-and-responsibilities "
            ': "Open data distributed by the Finnish Environment Institute (Syke) is '
            'licenced under Creative Commons Attribution 4.0 International licence."'
        ),
    },
}


def main() -> None:
    with PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        rows = list(reader)
    if fieldnames is None:
        raise SystemExit("data_rights.csv has no header")
    changed = []
    matched = set()
    for row in rows:
        update = UPDATES.get(row["artifact"])
        if update is None:
            continue
        matched.add(row["artifact"])
        for key, value in update.items():
            if key not in fieldnames:
                raise SystemExit(f"{key} is not a column of data_rights.csv")
            if row[key] != value:
                changed.append((row["artifact"], key, row[key], value))
            row[key] = value
    missing = sorted(set(UPDATES) - matched)
    if missing:
        raise SystemExit(f"artifact rows not found: {missing}")
    with PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"rows updated: {len(matched)}; fields changed: {len(changed)}")
    for artifact, key, old, new in changed:
        print(f"  {artifact} :: {key}\n      - {old}\n      + {new}")


if __name__ == "__main__":
    main()
