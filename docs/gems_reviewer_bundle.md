# GEMS confidential reviewer bundle

This bundle is **confidential**. It is not a public archive and it is not the
rights-filtered candidate built by `scripts/40_build_public_archive_candidate.py`.

AGU file type to use at upload:

**Data File(s) for Peer Review (will not publish)**

Policy page:
https://www.agu.org/publications/authors/journals/data-software-for-authors

## What the local bundle is

`scripts/42_build_gems_reviewer_bundle.py` copies restricted working files that
already exist on this machine into:

```text
private/gems_reviewer_bundle/
```

That directory is gitignored. Do not add it, zip it, or its CSVs/parquets to
git. The tracked, values-free inventory is

```text
metadata/gems_reviewer_bundle_inventory.json
```

The inventory lists expected logical paths and whether each was found. It does
not contain observation values.

`metadata/gems_reviewer_data_upload.json` stays `uploaded: false` until a human
finishes the GEMS upload. Running the build script is not an upload.

## Build

From the repository root, with the local restricted working tree present:

```bash
python scripts/42_build_gems_reviewer_bundle.py
```

The script skips missing published or sensitivity trees instead of failing.
Re-run it after the working files change. Confirm `git status` does not list
`data/raw/*.csv` or `private/gems_reviewer_bundle/` as files to commit.

## Upload later in GEMS (after written editor acceptance)

1. Do not upload until `paper/editor_data_exception_request.md` has a written
   acceptance and the manuscript is ready to submit.
2. Zip `private/gems_reviewer_bundle/` locally. Keep the zip outside git.
3. In WRR GEMS (https://wrr-submit.agu.org/), upload the zip as
   `Data File(s) for Peer Review (will not publish)`.
4. Only then fill `metadata/gems_reviewer_data_upload.json`:
   - `uploaded: true`
   - `gems_manuscript_id`
   - `upload_date`
   - `file_inventory` (logical paths, not observation values)
   - `uploader_confirmation_archive` if you retain a screenshot or receipt
5. Do not also deposit this bundle in Zenodo, Figshare, or the public GitHub
   tree.

## What reviewers should see

The bundle README states fields, units, the 2006-01-01 to 2020-12-31 range,
mixed-column restrictions, and the confidential GEMS file type. Rights and
dictionary files are copied next to the observations.

Public USGS / NASA / GAGES-II inputs are not this bundle. They belong in the
public software archive after a real DOI exists.
