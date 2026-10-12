# F22 author metadata — failure收口

`metadata/submission_author_metadata.json` is still empty (`complete: false`).

**Cannot be closed by the agent.** Legal names, affiliations, ORCID, funding,
CRediT, COI and exclusive-submission confirmation must be supplied by the
authors. Inventing values from the git alias `shutiao23` is forbidden
(`paper_archived/author_information_required.md`).

## Gate behavior

- AGU build correctly reports `NOT submission-ready` while placeholders remain.
- Manuscript may keep `AUTHOR` / `AFFILIATION PENDING` locally.
- Do not set `complete=true` until humans approve the JSON checklist.

## What is ready without authors

Science/code/evidence-identity package under `results/wrr_submission_ready/` and
`paper/wrr/` desk checks (except author block).
