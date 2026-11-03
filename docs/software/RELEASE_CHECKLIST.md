# Release checklist

Package: `stream-recoverability` / `gapbench`
Version under preparation: `1.3.0`
Checklist date: 2026-11-02

This checklist distinguishes three states that are often conflated:

| State | What exists | What it proves | What it does not prove |
|---|---|---|---|
| Local package | Working tree and editable install at version `1.3.0` | The files describe version `1.3.0` and the local smoke checks pass | No archived release, no DOI, no independent reviewer access |
| GitHub release | A pushed tag and a GitHub release page | A citable code snapshot on GitHub | No archival DOI, no guarantee of long-term preservation |
| Zenodo deposit | A minted DOI and an archived record | An archival, version-specific software citation | Data rights are still governed by each provider; no restricted data are opened |

Current facts:

- `pyproject.toml` and `CITATION.cff` both declare `1.3.0`.
- The latest git tag is `v1.0.0`, which is historical and does not describe `1.3.0`.
- No `v1.3.0` git tag exists.
- No GitHub release for `1.3.0` exists.
- No Zenodo DOI has been minted; the `doi` field is intentionally unset.
- Reviewer access to restricted material is not established.
- `.zenodo.json` still records `1.1.0` and is outside this metadata task's edit scope; it must be updated before any deposit.

## 1. Version and metadata

- [x] `pyproject.toml` version is `1.3.0`.
- [x] `pyproject.toml` description is "Leakage-safe benchmarking of gap handling for annual heat extremes and river-temperature trends."
- [x] `CITATION.cff` version and preferred-citation version are `1.3.0`.
- [x] `CITATION.cff` date is `2026-11-02` and the title/abstract use the EMS software framing.
- [x] `CITATION.cff` has no invented DOI.
- [x] `LICENSE` preamble names the relevant providers (FOEN, GKD Bayern, USGS, NASA POWER, LUBW, other providers) and keeps the MIT body unchanged.
- [x] Version consistency check passes locally:
  `python scripts/check_version_consistency.py`
- [ ] Confirm `.zenodo.json` version, title, and description match `1.3.0` before any deposit `[待完成]`
- [ ] Confirm package metadata build (`python -m build` or equivalent) reports `1.3.0` `[待完成]`

## 2. Local package checks

- [ ] Clean virtual environment install with `pip install -e ".[review,dev]"` `[待完成]`
- [ ] LightGBM import check inside that environment `[待完成]`
- [ ] `gapbench` quickstart completes within 30 minutes `[待完成]`
- [ ] Docker image builds and the default command runs the quickstart `[待完成]`
- [ ] Full test suite result recorded for this version `[待完成]`

A local editable install is not a release. Passing local checks does not create a tag, a GitHub release, or a DOI.

## 3. Git tag and GitHub release

- [ ] Review the working tree and stage only intended files `[待完成]`
- [ ] Commit the `1.3.0` metadata and software changes `[待完成]`
- [ ] Push the commit to the public repository `[待完成]`
- [ ] Create an annotated tag `v1.3.0` on the reviewed commit `[待完成]`
- [ ] Push the tag `v1.3.0` `[待完成]`
- [ ] Create the GitHub release from `v1.3.0` with release notes and the package hash `[待完成]`
- [ ] Re-run `python scripts/check_version_consistency.py` after tagging; the historical-tag warning should disappear `[待完成]`

Do not describe `v1.0.0` as the current release. It predates the `1.3.0` metadata and software work.

## 4. Zenodo DOI

- [ ] Enable the repository in Zenodo and confirm the deposit metadata `[待完成]`
- [ ] Update `.zenodo.json` to version `1.3.0` and the current title/description `[待完成]`
- [ ] Create the GitHub release or deposit the archive, then let Zenodo mint the DOI `[待完成]`
- [ ] Record the DOI in `CITATION.cff` (`doi` and preferred-citation) only after it resolves `[待完成]`
- [ ] Record the DOI in the GitHub release notes `[待完成]`
- [ ] Record the DOI in the README and the Software and Data Availability statement `[待完成]`
- [ ] Verify the DOI resolves to the `1.3.0` record `[待完成]`

Never insert a placeholder or invented DOI. Until this section is complete, the software has no archival DOI.

## 5. Reviewer access and data rights

- [ ] Provide reviewers with a code-only archive and installation instructions `[待完成]`
- [ ] Provide a documented access route for restricted LUBW and other provider material, if the journal requires it `[待完成]`
- [ ] Confirm that no restricted observations are redistributed in the code archive, Docker image, or GitHub release `[待完成]`
- [ ] Confirm the data statement names FOEN, GKD Bayern, USGS, NASA POWER, LUBW, and other providers under their own terms `[待完成]`
- [ ] Record the reviewer-access route and any credentials procedure outside the public repository `[待完成]`

## 6. Sign-off

- [ ] Version, tag, GitHub release, and DOI agree `[待完成]`
- [ ] Clean-install and Docker smoke records are attached to the release `[待完成]`
- [ ] Reviewer access and data-rights statements are approved by the authors `[待完成]`
- [ ] Public wording does not claim that restricted data are redistributable `[待完成]`

Release is complete only when every `[待完成]` item that applies to the chosen route (local, GitHub, or Zenodo) is closed with evidence.
