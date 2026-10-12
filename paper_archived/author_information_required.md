# Author-supplied information required before submission

The repository does not contain enough verified personal information to create
a truthful journal title page. Do not infer these fields from the GitHub alias.

The current repo alias is `shutiao23` / `chestnutlee23@163.com`. That alias is
**not** sufficient for a WRR title page, cover letter, or GEMS author list.

`metadata/submission_author_metadata.json` remains blocking:

- `complete`: false
- `approved_by_all_authors`: false
- `authors`: []
- `affiliations`: []

Do not set `complete=true` and do not invent legal names, ORCID values,
funding lines, or COI text.

## Blocking checklist → JSON keys

Fill every row. Leave the JSON incomplete until a human supplies the real
values and every author approves them.

| Blocking item | JSON key | How to fill | Status |
| --- | --- | --- | --- |
| Full legal publication name and preferred initials for every author | `authors[]` objects, suggested keys `full_legal_name`, `preferred_initials` | Exact title-page spelling. Not a GitHub handle. | **BLOCKING** |
| Author order | `authors[]` key `author_order` (1-based) | Final agreed order. | **BLOCKING** |
| Corresponding-author designation | `authors[]` key `corresponding` (boolean); exactly one true | Must match GEMS and the cover letter. | **BLOCKING** |
| Connected ORCID for the corresponding author | top-level `corresponding_author_orcid` | Full `https://orcid.org/0000-...` or the 16-digit ORCID. Not blank. | **BLOCKING** |
| Corresponding-author email | `authors[]` key `email` on the corresponding object | Institutional or professional address that will appear in GEMS. The repo alias mailbox is not enough by itself. | **BLOCKING** |
| Institutional affiliation(s) at the time of the work | `affiliations[]` plus `authors[]` key `affiliation_ids` | Suggested affiliation keys: `id`, `institution`, `department`, `city`, `country`. | **BLOCKING** |
| Current address where applicable | `authors[]` key `current_address` | Use null only when it is the same as the affiliation. | **BLOCKING** until confirmed |
| Funding bodies, grant identifiers, and in-kind support | `funding[]` | Suggested keys: `funder`, `award_number`, `award_title`, `in_kind`. Use an empty list only after every author confirms there was no funding. | **BLOCKING** |
| CRediT contribution statement approved by every author | `credit_contributions[]` | Suggested keys: `full_legal_name`, `roles` (CRediT taxonomy). | **BLOCKING** |
| Conflict-of-interest declaration approved by every author | `conflict_of_interest_statement` | One approved sentence or short paragraph. Do not draft a fake “no conflicts” line. | **BLOCKING** |
| Acknowledged contributors and permission to name them | `acknowledgments` | Null only if there are no acknowledgments. Named people need permission. | **BLOCKING** until confirmed |
| Confirmation the manuscript is not submitted elsewhere | `exclusive_submission_confirmed` | Set true only after every author confirms. | **BLOCKING** (`false` now) |
| All-author approval of the package | `approved_by_all_authors` | Set true only after every author signs off. | **BLOCKING** (`false` now) |
| Optional suggested and opposed reviewers | not stored in this JSON | Collect outside git if needed. Affiliations must be non-conflicting. | Optional |

Suggested empty author object (do not commit invented values):

```json
{
  "full_legal_name": "",
  "preferred_initials": "",
  "author_order": 1,
  "corresponding": true,
  "orcid": "",
  "email": "",
  "affiliation_ids": [],
  "current_address": null
}
```

Suggested empty affiliation object:

```json
{
  "id": "aff1",
  "institution": "",
  "department": "",
  "city": "",
  "country": ""
}
```

## Finalization rule

The AGU manuscript and cover letter may contain bracketed placeholders in the
local draft, but the submission gate must fail until all blocking fields are
supplied and the final rendered PDF contains no placeholder.

Set `complete` to true only after:

1. every blocking key above is populated with approved facts;
2. `authors` and `affiliations` are non-empty;
3. `corresponding_author_orcid` is present;
4. `conflict_of_interest_statement` is present;
5. `approved_by_all_authors` is true;
6. title-page, cover letter, and GEMS names match this file.

Until then the gate blocker remains: “submission author metadata is incomplete
or unapproved.”
