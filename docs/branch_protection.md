# Branch protection and signed releases

The review snapshot `main@7ea38ae00ad341bc8cb2c59fe6d03aedaee6e3d3` had no
GitHub branch protection and no signed commits. This file records the required
governance setting. Enabling it needs repository-admin access and is not
performed by rewriting git history.

Required `main` settings:

- no direct pushes; pull requests only
- required status check: CI Python 3.10/3.11
- no force push
- no deletion
- signed commits preferred for release tags

Release tags must be annotated and must point at a single SHA:

```text
git tag -a audit/p0-v3 -m "P0 protocol freeze at <sha>"
```

Do not invent a software DOI. `CITATION.cff` keeps `doi` unset until a real
Zenodo or HydroShare deposit exists.
