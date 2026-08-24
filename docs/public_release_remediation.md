# Public-release remediation record

The public history remediation described below was completed after the scientific
revision. A verified private bundle and old-to-new commit map were created before
the force-push. The sanitized public history contains no path flagged by the
restricted-hosting audit. The private bundle remains outside the public repository.

## Preferred option: new code-only archival repository

1. Preserve an institutional private mirror of the current repository and its
   complete history.
2. Create a new empty public repository with no ancestry from the development
   remote.
3. Export only project-authored code/configuration/documentation plus permitted
   aggregate figures and tables. Exclude every path reported by
   `results/audits/restricted_hosting_audit.json`, all ignored internal data,
   daily predictions, checkpoints, and date-bearing restricted masks.
4. Run `scripts/35_validate_review_revision.py` against the archive candidate,
   using confidential or local evidence inputs only for validation.
5. Deposit the sanitized release in an archival service, mint the DOI, and add
   that real DOI to `CITATION.cff` and the manuscript.
6. Re-run `scripts/26_audit_restricted_hosting.py --fail-if-present` and the
   explicit submission gate on the public archive candidate.

This option avoids rewriting a public history that other users may already
have cloned.

## Alternative: coordinated history rewrite

Only the repository owner should perform this option. After a verified private
mirror and collaborator notification, use `git filter-repo` with an explicit
path list generated from the rights audit. At minimum it must remove:

- `data/raw/` and `data/processed/`;
- restricted internal `data_versions/`;
- `masks/test/` and `masks/validation/`;
- restricted date/value-bearing anchor and event catalogs identified by the
  audit.

Then expire the old public objects according to the hosting provider's
procedure, force-push all rewritten refs, rotate release tags, and require
fresh clones. Deleting files only from the current tip is insufficient.

## Non-negotiable checks

- The public audit must report `public_hosting_defect=false`.
- The archive DOI must resolve; placeholders are forbidden.
- Restricted reviewer files remain in AGU GEMS confidential review storage and
  are never copied into the public archive.
- Public USGS/NASA external inputs and aggregates retain request/provenance and
  provider citations.
