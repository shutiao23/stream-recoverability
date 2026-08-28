# Pre-submission request: restricted-data plan

> Historical AGU/WRR inquiry template. The canonical v4 case study currently
> targets *Journal of Hydrology*, and v9 is not submittable. Do not send this
> packet without first confirming the target journal and replacing the route
> with that journal's official confidential-review mechanism.

**To:** Water Resources Research editorial office / AGU DataHelp
**Subject:** Pre-submission confirmation of restricted third-party data plan

Dear Editors,

We are preparing the manuscript “A Case-Study Covariance Heuristic for Stream-Temperature Recoverability in Two Regulated River Networks.” Before submission, we request confirmation that the following restricted-data plan is acceptable under AGU's Data and Software Policy.

The study uses daily Jinsha River temperature, discharge, and water-level records attributed to the *Annual Hydrological Report of the People's Republic of China, Volume VI*, together with WMO/CMA meteorological fields. The files were supplied to the project, but permission to redistribute their daily values publicly was not established. We therefore cannot lawfully place those exact records in a public repository or state that they are “available upon request.”

Public versus restricted split: NASA POWER, USGS Water Data, and GAGES-II products used here are public US-government sources and may be archived with the code. Jinsha yearbook hydrology, CMA surface-climate fields, and the WMO/CMA series independently matching GSOD are restricted. All original code is MIT and is public after the history rewrite. Editors and reviewers receive the full restricted working tree through GEMS as “Data File(s) for Peer Review (will not publish).”

At peer review we propose to:

1. upload the exact analysis inputs and provenance manifests through GEMS using “Data File(s) for Peer Review (will not publish)”;
2. provide editors and reviewers with the complete rights matrix and source documentation;
3. publicly archive all original code, environments, masks that do not expose restricted dates/values, aggregate result tables, figure source data permitted for release, and public USGS/NASA inputs with a versioned DOI;
4. cite the upstream publications and data products and state the access restrictions explicitly in the Open Research section; and
5. retain a private immutable reproduction bundle so that editorial questions can be checked without placing restricted bytes in public history.

The public repository has undergone a full-history rights audit and contains no path identified as restricted. The manuscript's conclusions do not depend on a claim that the restricted records are open.

Would WRR consider this an acceptable restricted third-party data exception if the confidential files are available to editors and reviewers? If additional documentation or a different access mechanism is required, please let us know before we submit.

Sincerely,

**[Corresponding author name]**

**[Affiliation]**
**[Email and ORCID]**

## Required record before submission

- Date sent: **OPEN**
- Recipient/address: **OPEN**
- Written response received: **OPEN**
- Exception accepted: **OPEN / BLOCKING**
- Conditions imposed by editor: **OPEN**

Send instructions for a human are in `paper/editor_inquiry_send_checklist.md`.
After sending, fill only Date sent and Recipient/address. Do not change
Exception accepted until a written editor or AGU reply exists.

## Packet contents

1. This letter (`paper/editor_data_exception_request.md`)
2. `DATA_RIGHTS.md`
3. `metadata/data_rights.csv`
4. The public-versus-restricted paragraph in the letter body

Do not attach restricted observation files to this inquiry. Reviewer access
uses a later confidential GEMS upload, not this pre-submission email.
