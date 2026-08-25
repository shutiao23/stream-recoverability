# Zenodo archival software DOI runbook

This is a human runbook. It does not mint a DOI. No DOI exists today.

## Honest status

- `CITATION.cff` leaves `doi` unset on purpose
- `.zenodo.json` is software metadata only and must not contain a `doi` field
- The manuscript Open Research section must not cite a fabricated `10.5281/zenodo....` identifier
- GitHub (`https://github.com/shutiao23/stream-recoverability`) is a development host, not the AGU archive
- `scripts/40_build_public_archive_candidate.py` builds a local rights-filtered tarball. That candidate is not a minted record

Do **not** invent a DOI, reserve a fake one, or paste a placeholder into
citation or manuscript files.

## Sequencing warning — do not mint yet

**Do not mint until the scientific BL-011 diagnosis and the corresponding
manuscript text are committed.** Minting now would pin a pre-diagnosis
artifact as the archival software version.

Enabling the GitHub–Zenodo integration does not mint a DOI by itself. Creating
or publishing a GitHub release after the integration is enabled **does** mint.
Do not publish a release until the science freeze.

There may already be a development tag `v1.0.0`. Do not turn that current tag
into a Zenodo-enabled GitHub release.

## Tag to use after the science freeze

After BL-011 and the manuscript text are committed, and the public tree is
still code-only:

```text
v1.0.0-wrr-submission
```

Create that annotated tag on the frozen commit only.

## Minting steps (after freeze only)

Official integration pages:

- GitHub: https://docs.github.com/en/repositories/archiving-a-github-repository/referencing-and-citing-content
- Zenodo GitHub settings: https://zenodo.org/account/settings/github/
- Zenodo enable-repository guide: https://help.zenodo.org/docs/github/enable-repository/
- Zenodo login: https://zenodo.org/login

1. Confirm the frozen commit contains the BL-011 diagnosis, the manuscript
   text, the current paper title in `.zenodo.json`, and no restricted paths
   (`python scripts/26_audit_restricted_hosting.py --fail-if-present`).
2. Log in to Zenodo with GitHub for account `shutiao23`.
3. Open https://zenodo.org/account/settings/github/ and enable
   `shutiao23/stream-recoverability`.
4. From that frozen commit, create a **code-only** GitHub release tagged
   `v1.0.0-wrr-submission`. The release archive must be the public repository
   (MIT code, public metadata, permitted aggregates). It must not include
   `data/raw/`, `data/processed/`, restricted `data_versions/`, Jinsha masks,
   or `private/gems_reviewer_bundle/`.
5. Wait for Zenodo to ingest the release. Zenodo mints a **concept DOI**
   (all versions) and a **version DOI** (this release).
6. Copy the real **version DOI** only after it exists on the Zenodo record.
   Never guess the number.
7. Write that version DOI into `CITATION.cff` as `doi:`.
8. Write the same version DOI into the manuscript Open Research / software
   availability sentence. Do not edit those manuscript files until the DOI
   is real.
9. Confirm `.zenodo.json` `title` still matches the paper title:
   “Reservoir-Associated Thermal Structure Predicts Stream-Temperature
   Recoverability in the Jinsha and Chattahoochee Rivers”.
10. Re-run the submission gate. The archival-DOI blocker should clear only
    after `CITATION.cff` contains the minted `doi`.

## What not to do

- Do not type `10.5281/zenodo.` followed by an invented number
- Do not set a DOI in `.zenodo.json` (Zenodo ignores that field for GitHub
  releases; putting one there is still a fake identifier in this repo)
- Do not mint from a worktree that still has an uncommitted scientific
  diagnosis
- Do not upload restricted Jinsha files to Zenodo
- Do not treat the local `dist/` archive candidate as a DOI record
