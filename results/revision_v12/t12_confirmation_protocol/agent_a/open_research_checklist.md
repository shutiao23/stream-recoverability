# Open Research and external preregistration checklist — route A third-panel confirmation (v3)

Status: plan. This checklist converts the v2 same-commit internal freeze
(`results/development_v11/second_confirmation/amendment_registration_record.json`)
into an externally verifiable preregistration and deposit workflow. Cross-refs:
`paper/development_v11/submission_checklist.md`, `package_manifest.json`,
`DATA_RIGHTS.md`, `metadata/data_rights.csv`, SI Text S17.

---

## 1. External preregistration workflow (must precede outcome scoring)

The v3 protocol (`protocol_v3.md`, Section 8) requires a separate pre-outcome
commit and an external registration before any third-panel outcome is opened.
Steps, in order:

1. [ ] **Freeze commit (commit #1)**: create the separate public commit containing
   - `configs/route_a_second_confirmation_protocol.yaml` (v1) and `...amendment_v2.yaml` (v2) as read-only references,
   - `protocol_v3.md` (this namespace),
   - `frozen_scoring_roster_v3.csv` (exact per-domain roster) and its sha256,
   - the power analysis artifacts (power_table.csv, power_curve.png, observed_effects.json, effect_bootstrap_distribution.csv, recommended_sample_size.json, per_network_observed_deltas.csv) and `scripts/rev_v12_t12_protocol_a.py`,
   - `registration_record_v3.json` (template only, filled in step 3).
   No outcome-derived file may be in this commit. Push to the public remote and
   record the commit hash.
2. [ ] **Create the registration record**: `registration_record_v3.json` with
   fields `separate_pre_outcome_commit: true`,
   `externally_verifiable_preregistration: true`, registry, DOI, registration
   URL, registration UTC timestamp, registered commit hash, sha256 of the
   registered files (mirror the v2 record structure, opposite field values).
3. [ ] **Register at OSF or Zenodo**:
   - OSF: create project → "Preregistration" add-on → upload commit #1 files
     (protocol, roster, power analysis, hashes) → submit for registration;
     capture the registration DOI/handle.
   - Zenodo alternative: create a restricted/embargoed deposit of the same
     files, mint the concept DOI, and record it; embargo end date must be
     after the anticipated outcome commit.
4. [ ] **Authorization gate**: `readiness.json` for the third panel sets
   `external_registration_verified: true` only when the registration record
   exists and file hashes match commit #1.
5. [ ] **Outcome commit (commit #2)**: scoring and results, referencing the
   registration DOI in the manuscript and in the package manifest.
6. [ ] **Amendment path**: any change to roster, margins, or endpoints requires
   a new amendment file and a new external registration before scoring; no
   post-outcome amendments.

## 2. Deposit and DOI minting (Zenodo/OSF artifact deposit)

1. [ ] Build the permitted archival package (Section 4) from the public repo at
   the outcome commit.
2. [ ] Deposit in Zenodo (or OSF with DOI) with the AGU-recommended metadata:
   title, authors with ORCIDs, license MIT (software), version, related repo
   URL, and the registration DOI from step 3 above as a related identifier.
3. [ ] Minted DOI must replace `pending` in:
   - [ ] `.zenodo.json` (`software_doi` / deposit fields),
   - [ ] `CITATION.cff`,
   - [ ] `paper/development_v11/package_manifest.json` (`open_research.archive_status` → `deposited`, `open_research.software_doi`),
   - [ ] manuscript Open Research section ("The archival release and DOI have
     not yet been created" sentence must be replaced),
   - [ ] submission-portal metadata.
4. [ ] No placeholder DOI may be cited as an archived record
   (`submission_checklist.md` external item).

## 3. DOI insertion points (manuscript + package manifest)

| File | Field/location | Action |
| --- | --- | --- |
| `paper/development_v11/manuscript.md` | Open Research section | insert software DOI + preregistration DOI + data-availability DOI |
| `paper/development_v11/package_manifest.json` | `open_research.archive_status`, `open_research.software_doi`, `second_confirmation.amendment_status` | set deposited/DOI; add `third_confirmation.registration_doi` |
| `paper/development_v11/supporting_information.md` | Text S17 | replace "same commit … not externally verifiable preregistration" with the v3 registration DOI statement |
| `.zenodo.json` | deposit metadata | set DOI + related identifiers |
| `CITATION.cff` | preferred-citation | set DOI + version |

## 4. Artifacts that must be deposited

Deposit (public, license-permitting):
- Source code, `configs/` protocol files, `scripts/rev_v12_t12_protocol_a.py`, registration record, readiness records.
- Power analysis and protocol v3 artifacts (this namespace).
- Derived station-gap losses and all result tables referenced by the package
  manifest's `primary_result_artifacts`.
- Provider request metadata and source-QC summaries.
- Figure inputs and regenerable-output generation targets
  (`package_manifest.json` `regenerable_local_outputs` stays regenerable,
  not required in the archival primary artifacts).

Do not deposit without permission:
- Provider daily values (see Section 5).
- `data/raw/`, `data/processed/` parquets, `data_versions/` (per DATA_RIGHTS.md).

## 5. DATA_RIGHTS.md review and controlled-access plan

Review `DATA_RIGHTS.md` and `metadata/data_rights.csv` (a conservative rights
record, not a claim of openness):

- [ ] No repository statement may describe restricted columns as open;
  mixed-column files take the most restrictive reading.
- [ ] Provider rows in SI Text S17 govern third-panel acquisition:
  - USGS: releasable (request metadata, derived aggregates); NASA POWER:
    forcing retained with day-boundary disclosure; NVE: NLOD open-data
    license (10 second-panel networks); ARSO/CHMI/GKD/LUBW/RWS/FOEN: raw
    values omitted pending explicit redistribution statements; ECCC/eHYD/SYKE:
    source-QC metadata only; Canadian Coast Guard: excluded (unvalidated).
- [ ] **Controlled-access plan for provider-restricted data**: raw daily values
  stay out of the public tree; the Data Availability statement must give (a)
  official retrieval routes (per provider), (b) hashes of any raw files held,
  (c) a named contact and journal data-sharing channel for reviewer access to
  derived-but-restricted aggregates, and (d) any provider permission letter as
  a deposited attachment. Temperature values needed for endpoint (d) follow
  the same plan.
- [ ] `.zenodo.json` deposit must include a data-rights note pointing to
  `metadata/data_rights.csv`; no MIT claim over third-party observations.

## 6. Submission-checklist integration

- [ ] Mirror the unchecked external items of
  `paper/development_v11/submission_checklist.md`: author identity (names,
  ORCIDs, CRediT, corresponding author), conflicts/funding, provider
  permissions, portal checks (word count, formats, references, figure/SI
  callouts).
- [ ] Update `package_manifest.json` `submission_status` and
  `second_confirmation` block after the third-panel outcome commit; add a
  `third_confirmation` block including the registration DOI.
