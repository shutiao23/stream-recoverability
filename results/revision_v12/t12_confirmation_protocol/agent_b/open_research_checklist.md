# Open-Research Checklist for the v3 External-Confirmation Panel (agent b)

Companion to `protocol_v3.md` (same namespace). Everything here concerns the
**release and preregistration workflow**, not the science protocol. All
repository paths are relative to the repo root.

## 0. Governing constraints from existing records

- `DATA_RIGHTS.md` (repo root) is the conservative rights record. Key
  restrictions it establishes:
  - `WTEMP`/`WLEVEL`/`FLOW` (China yearbook hydrology): `redistribution_allowed=false`.
  - `RHMEAN`/`DH` (CMA V3.0 member-service columns): `redistribution_allowed=false`.
  - `TEMP`/`WDSP`/`PRCP` (WMO/CMA series, matched to NOAA GSOD only as a
    provenance check): `contested_wmo_res40`, `redistribution_allowed=false`.
  - Processed tables and `data_versions/` inherit these restrictions.
  - The public GitHub tree is a development host, not an archival repository.
- `.zenodo.json` and `CITATION.cff` currently have **no minted DOI** and
  must not be given invented placeholders.
- `paper/development_v11/package_manifest.json` → `open_research` block:
  `software_doi: null`, `archive_status: "pending_deposit"`,
  `provider_daily_values: "omit_unless_redistribution_terms_explicitly_allow"`.
- `paper/development_v11/submission_checklist.md` ("External items that
  cannot be fabricated in-repository") already lists the DOI, permissions,
  and author-identity items.

## 1. External preregistration workflow (protocol v3, Section 11)

Order of operations — each gate must be true before the next step:

1. **Freeze locally**: finalize `protocol_v3.md`, QC rules, model roster,
   endpoint definitions, success margins (§12), analysis pipeline, and the
   power-analysis tables (`power_analysis.csv`, `power_analysis_summary.json`).
2. **Assemble the frozen archive** (Section 3 below) and compute its
   SHA-256 manifest.
3. **Register externally** (choose one):
   - *OSF preregistration*: create an OSF project, fill the preregistration
     form with the frozen artifacts (or a link + manifest), and submit;
     record the permanent URL and timestamp. OSF provides version-stamped
     file history, which strengthens the audit trail.
   - *Zenodo preregistration-style deposit*: upload the frozen archive as a
     restricted (embargoed) record first, or as an open record, and mint the
     DOI at this step. A Zenodo record created **before** outcome scoring
     with a `preregistration` relation is the strongest archival option.
   - *Separate public commit*: commit exactly the frozen artifacts, push to
     the public remote as its own commit, record SHA-256 and commit
     timestamp; the outcome-scoring commit must be a later, distinct commit
     whose manifest binds the frozen-commit SHA-256.
4. **Gate**: verify the registration record (DOI/URL, timestamp) is publicly
   retrievable **before** the first v3 outcome value is computed or viewed.
5. **Score outcomes** with the frozen pipeline; bind the registration record
   into the output manifest.
6. **Deposit results** (Section 4) as a *new* version of the Zenodo record,
   or a second record with `relation: isSupplementTo` the registration.

Nothing in this repository can substitute for steps 3–4; the v2 lesson is
that internal hash-binding in the same commit as the outcomes is not
externally verifiable.

## 2. Zenodo/OSF deposit steps (software + results record)

1. Create account; confirm ORCID linkage and affiliation for all authors.
2. New deposit: upload_type `software` (matches `.zenodo.json`), or
   `dataset` if a results-only record is preferred.
3. Metadata to fill:
   - title: "Stream-Temperature Gap Recoverability and Monitoring-Network
     Evaluation" (keep consistent with `.zenodo.json`);
   - creators: full author list (this is the author-identity gate);
   - license: MIT (software only — see Section 5 for data);
   - version: bump from current `1.1.0` for the v3 release;
   - related identifiers: GitHub URL `relation: isSupplementTo`;
     preregistration record `relation: isNewVersionOf`/`isSupplementTo`;
   - description: keep the "software only; restricted observations
     excluded" wording from `.zenodo.json`.
4. Publish → minted DOI (10.5281/zenodo.XXXXXXX).

## 3. What must be deposited (frozen archive + results)

Deposit (all paths relative to repo root):

- `results/revision_v12/t12_confirmation_protocol/agent_b/protocol_v3.md`
  (the frozen protocol, including margins);
- `results/revision_v12/t12_confirmation_protocol/agent_b/open_research_checklist.md`;
- `scripts/rev_v12_t12_protocol_b.py` (power analysis, reproducible);
- `results/revision_v12/t12_confirmation_protocol/agent_b/power_analysis.csv`,
  `panel_effect_distribution.csv`, `power_analysis_summary.json`,
  `power_curve.png`;
- the frozen configs: `configs/route_a_second_confirmation_protocol.yaml`,
  `configs/route_a_second_confirmation_amendment_v2.yaml` (historical
  records referenced by v3);
- `paper/development_v11/manuscript.md`, `supporting_information.md`,
  `figure_captions.md`, `cover_letter.md`, `claim_matrix.md`,
  `submission_checklist.md`, `package_manifest.json`;
- result tables and figures already declared primary artifacts in
  `package_manifest.json` (`results/development_v11/reviewer_completion/*`
  and the `second_confirmation` block);
- `CITATION.cff`, `.zenodo.json`, `LICENSE`, `README.md`, `Makefile`,
  `pyproject.toml`, `environment.yml`, `constraints.txt`, `Dockerfile`;
- the registration record itself (DOI/URL + timestamp + SHA-256 manifest).

**Excluded from the public deposit** (see Section 5): `data/raw/`,
`data/processed/`, `data_versions/`, `data_versions_pre_rs/`, `private/`,
`checkpoints/`, and any provider-restricted daily values. Placement-level
predictions already marked "regenerable" in `package_manifest.json` are
regenerated by `make development-v11-reviewer-completion` and need not be
deposited.

## 4. DOI insertion points (after the mint)

1. `paper/development_v11/package_manifest.json`:
   - `open_research.software_doi`: replace `null` with the minted DOI;
   - `open_research.archive_status`: `pending_deposit` → `deposited_<DOI>`;
   - add the v3 registration DOI under `second_confirmation`-style block or
     a new `revision_v12_confirmation_panel_v3` block (registration
     identifier, timestamp, SHA-256);
   - update `external_todos` items 3 and 4 to `[x]` only after the action is
     actually performed.
2. `paper/development_v11/manuscript.md`: Open Research / Data Availability
   statement — insert the software DOI, the preregistration DOI, and the
   archive DOI (distinct identifiers: registration ≠ software release).
3. `.zenodo.json`: `related_identifiers` — add the preregistration record
   with `relation: "isSupplementTo"` (or the appropriate relation), and the
   software DOI is auto-minted by Zenodo; keep `version` in sync.
4. `CITATION.cff`: the `doi:` field is intentionally unset; set it to the
   minted software DOI **only** once the deposit exists (the file itself
   forbids placeholders).
5. `README.md`: replace any "DOI pending" text with the DOI and badge.
6. Submission portal metadata: DOI, references, ORCIDs, CRediT.

## 5. Controlled-access plan for provider-restricted data

1. **Default**: omit restricted daily values from the public deposit. The
   deposit contains code, configs, protocol, aggregates, and derived
   result tables that do not republish restricted daily series
   (`DATA_RIGHTS.md` allows derived aggregates and journal figures as the
   normal publication path).
2. **If a provider grants redistribution**: attach the permission document
   (letter or terms excerpt) to the deposit and add the provider to a
   `provider_redistribution_allowed` list in `metadata/data_rights.csv`
   (with date and permission scope). Only then may that provider's values
   be archived — ideally as a separate restricted Zenodo record.
3. **If redistribution is allowed with conditions** (e.g., research-only):
   use a Zenodo **restricted-access** record (access request workflow) for
   those values, or a controlled-access repository; the Data Availability
   statement must describe the application path and never describe the data
   as openly available.
4. **Data availability statement template** (to adapt):
   "Analysis code and derived aggregate tables are archived at [DOI].
   Daily observational values are third-party provider data; redistribution
   terms are documented in DATA_RIGHTS.md. Values not covered by an
   explicit redistribution grant are omitted from the archive and can be
   obtained from the provider; the code documents the ingestion path."
5. Review `README.md` and `DATA_RIGHTS.md` before deposit for the
   "presence of restricted columns in the public tree" defect that
   `DATA_RIGHTS.md` already flags as unresolved for the GitHub host; the
   archival deposit must not repeat it.

## 6. Final verification checklist (run before submission)

- [ ] Registration record publicly retrievable, timestamp precedes first
      v3 outcome computation (protocol v3 §11 gate).
- [ ] Minted DOI inserted in `package_manifest.json`, `CITATION.cff`,
      `.zenodo.json` (related identifiers), manuscript Open Research
      statement, README, and submission portal.
- [ ] Deposit manifest (SHA-256) matches the frozen archive and the
      registration record.
- [ ] No restricted daily values in the deposit; permissions attached where
      values are included; controlled-access path described for conditional
      data.
- [ ] `submission_checklist.md` external items either completed or left
      unchecked with a reason (no silent completion by code generation).
- [ ] All URLs, DOIs, reference keys, figure callouts, and SI callouts
      resolve in the rendered submission files.
- [ ] Author identity items (names, affiliations, ORCIDs, CRediT, funding,
      conflicts, corresponding author) confirmed by authors, not by tooling.
