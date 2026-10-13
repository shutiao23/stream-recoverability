# SMHI multi-agency ingest: QC/eligibility failure

Retrieval: 2026-10-12T09:55:14Z

Stations downloaded: 176 of 176 catalogued.
Rows parsed: 1063746. Accepted under the fixed QC gate (G, Y): 0. Dropped: 1063746 (1.0000 of parsed rows).

## Observed quality-code distribution (parsed rows)

- `O`: 1063746

## Why there is no panel

- Stations with >= 1 accepted (G/Y) day: 0 of 176
- Stations with >= 4 complete calendar years after QC: 0
- Eligible networks (>= 2 such stations): 0
- Complete station-years: 0

Every parameter-4 station is catalogued `measuringStations = ADDITIONAL` ('Övriga stationer' = outside SMHI's own station network) and the corrected-archive series carry only quality code `O`. SMHI documents `O` as uncontrolled values, so the fixed gate accepts none of them.

No proxy rule was substituted. Accepting `O` would be a QC-rule change on never-scored data and requires an explicit coordinator decision recorded in the seal chain.

PRIOR-USE CHECK: 0 of 176 SMHI station ids appear in the v17/v18 rosters.

Verbatim legend and full counts: `ingest.json` (retrieval 2026-10-12T09:55:14Z).
