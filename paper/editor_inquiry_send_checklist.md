# WRR editor inquiry — send checklist

This is the only **externally delayed** submission blocker. A human must send
the packet. Do not submit the manuscript before written editor or AGU DataHelp
acceptance. Building a local GEMS bundle or a public archive candidate does
**not** close this blocker.

**Status now:** `date_sent` is OPEN. `metadata/editor_data_exception_approval.json`
has `accepted: false`. Keep it false until a written response says the plan is
accepted.

## 1. Send this first

Send before author-metadata fill, GEMS manuscript upload, or Zenodo minting.
Those other three blockers are local or post-acceptance work. This one waits
on an editor.

Do not treat a GEMS account, a pre-submission draft, or a cover-letter sentence
as acceptance.

## 2. Where to send (public addresses only)

Use the public journal office and AGU data desk. Do not invent a private
editor name or a personal inbox.

| Route | Public address or URL | Use |
| --- | --- | --- |
| WRR editorial office (primary) | `wrr@agu.org` | Pre-submission confirmation of the restricted-data plan. This is the public Editors' Assistant address on the [WRR editorial-board page](https://agupubs.onlinelibrary.wiley.com/hub/journal/19447973/editorial-board/editorial-board). |
| AGU DataHelp (copy or follow-up) | `DataHelp@agu.org` | Policy questions on AGU data and software exceptions. Listed on [Data and Software for Authors](https://www.agu.org/publications/authors/journals/data-software-for-authors). |
| WRR GEMS (later submission only) | https://wrr-submit.agu.org/ and https://wrr-submit.agu.org/cgi-bin/main.plex | Manuscript submission **after** written acceptance. Upload confidential files there as `Data File(s) for Peer Review (will not publish)`. |
| AGU data-policy page | https://www.agu.org/publications/authors/journals/data-software-for-authors | Official wording for restricted-access exceptions and the GEMS file type. |
| AGU author data page (same policy) | https://www.agu.org/publish-with-agu/publish/author-resources/data-and-software-for-authors | Alternate public URL for the same guidance. |

If GEMS shows a correspondence or inquiry form after login, you may file the
same packet there **in addition** to email. Email to `wrr@agu.org` is the
send-now path. Do not open a full Research Article submission until the
written exception exists.

## 3. Suggested email

**To:** `wrr@agu.org`  
**Cc:** `DataHelp@agu.org`  
**Subject:** Pre-submission confirmation of restricted third-party data plan — WRR manuscript on stream-temperature recoverability

Paste `paper/editor_data_exception_request.md` as the body (replace only the
corresponding-author placeholders with the real legal name, affiliation, email,
and ORCID). If you must send a short cover note, include the public-versus-restricted
paragraph below in the email itself.

## 4. Attachments (exact)

Attach these four items. Do not attach `data/raw/*.csv` or any other restricted
observation file to this inquiry.

1. `paper/editor_data_exception_request.md`
2. `DATA_RIGHTS.md`
3. `metadata/data_rights.csv`
4. The public-versus-restricted paragraph (in the letter and/or pasted below)

Optional and public only: `metadata/data_dictionary.csv` and
`metadata/station_metadata.csv` if the office asks for variable or station
definitions. Do not attach the confidential GEMS bundle to this inquiry.

## 5. Public-versus-restricted paragraph (paste)

NASA POWER, USGS Water Data, and GAGES-II products used in this study are
public US-government sources and may be archived with the code. Jinsha
yearbook hydrology (`WTEMP` / `WLEVEL` / `FLOW`), CMA surface-climate fields
(`RHMEAN` / `DH`), and the WMO/CMA series independently matching GSOD
(`TEMP` / `WDSP` / `PRCP`) are restricted and cannot be placed in a public
repository or described as available upon request. All original code is MIT
and is 100% public after the restricted-history rewrite. Editors and reviewers
receive the full restricted working tree through AGU GEMS as
`Data File(s) for Peer Review (will not publish)`.

## 6. After you send — record only the send, not acceptance

Fill the send fields. Do **not** set `accepted=true`.

In `paper/editor_data_exception_request.md`:

- `Date sent:` the calendar date you sent the email (not OPEN)
- `Recipient/address:` for example `wrr@agu.org; cc DataHelp@agu.org`
- Leave `Written response received`, `Exception accepted`, and `Conditions`
  as **OPEN** / **OPEN / BLOCKING**

In `metadata/editor_data_exception_approval.json`:

- set `date_sent` to that same date string
- set `recipient` to the same address string
- keep `"accepted": false`
- keep `"complete": false`
- keep `"status": "open"`
- leave `date_received`, `written_response_archive`, and `conditions` null
  until a written reply exists

Save the sent message (EML or PDF) outside git if it contains a personal
mailbox. Only after a written yes, an authorized person may set `accepted`
to true and point `written_response_archive` at a retained copy.

## 7. Do not do these things

- Do not submit the manuscript in GEMS before written acceptance
- Do not mark `accepted=true` from silence, a phone call, or a verbal chat
- Do not invent an editor's personal name or email
- Do not attach restricted CSVs, parquets, or the private GEMS bundle to this inquiry
- Do not mint a Zenodo DOI in order to "look ready" for this email
