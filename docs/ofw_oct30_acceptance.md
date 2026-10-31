# October 30 OFW acceptance workflow

The compact report contains 1,174 numbered messages on 498 pages. Its table
layout differs from the October 16 report (622 messages / 643 pages). It has no
report timezone, selected date range or generation-time cover declaration.
PDF creation metadata is not a declaration of the message display timezone.

## Preserve the source

Keep both original PDFs, extracted text, renders and database files outside Git.
Keep original filenames. Record acquisition URL/time and compute SHA-256 before
and after testing. The fixture checks the original bytes against its pinned hash;
the hash establishes byte identity, not authenticity or legal effect. Attachment
references do not establish the contents of the attachment files.

The parser reads the original bytes. Its normalized message records and test
database are derivatives. Each source occurrence retains document ID, SHA-256,
PDF page range, message number/total, raw sent/viewed timestamp strings, timezone
and its basis, extracted subject/body, and attachment references/raw filenames.
Native extraction has no claimed accuracy score (`confidence` remains null).

## Timezone and source metadata

The compact format requires `parse_ofw_message_report(...,
report_timezone="America/Vancouver")`, or the actual confirmed IANA display
timezone. There is no implicit fallback. `metadata.timezone_basis` and
`message.source_timezone_basis` are `supplied`; a declared legacy report timezone
is `report`. Supplying a contradictory timezone for a legacy report fails.
The compact date range comes from message timestamps and is marked
`date_range_basis="messages"`; it is not described as report-declared metadata.

The source owner confirmed America/Vancouver as the account setting used when
the October 30 report was generated.
All 622 overlapping messages' displayed timestamps also agree with the older
report's declared timezone. The compact report's timezone basis remains
`supplied`: user confirmation is distinct from a declaration inside the PDF.
For other exports, passing a timezone explicitly does not independently verify
it. Tests run with an assumption must be reported as conditional on that assumption.

Physical location when sending/reading is separate from a report's display
timezone. Do not infer per-message timezone changes from travel or work schedules.
Preserve a timezone explicitly written in message text as message content; it is
not the header's timezone. Other sources (device screenshots or call reports)
need their own timezone basis before comparison. Normalize known instants to UTC
for identity while retaining each source's raw timestamp and timezone. The
synthetic suite verifies that equivalent Vancouver/Edmonton exports keep their
message IDs; reinterpreting unchanged PDF timestamps in a different timezone is
instead rejected. Call-report timestamp behavior has not been tested here.

## Identity version 2 and old databases

The original parser inserted spaces when a PDF line wrapped within a token.
Across these two exports this produced 23 different fingerprints for matching
messages. Version 2 removes those introduced spaces **only at physical line
boundaries** inside contraction suffixes, hyphenated/underscored tokens, numeric
times, URLs and conventional slash-separated alternatives. Ordinary word wrapping
after a colon or a possessive apostrophe keeps its separator. It does not remove
ordinary within-line whitespace, fuzzy-match text, or match by timestamp alone.
The extracted body and raw attachment names remain available in their source
occurrences, and the original PDFs remain authoritative.

Version 2 identifiers use `ofw_v2_` and messages carry `identity_version=2`.
This is an intentional identifier-contract change. The importer rejects incoming
v1 records and any collection containing v1/missing-version records for the case,
before message writes. Existing IDs cannot be reliably migrated from stored body
text alone because v1 discarded the PDF line boundaries.

Do not rename, delete, overwrite or silently migrate the existing collection.
Reparse every original source report into a **new, separately named collection**,
verify counts/provenance against the old collection and original files, and review
dependent references before an application cutover. This workflow does not perform
that cutover or repair external links to v1 identifiers. Old binaries must not write
to a v2 collection. The guard protects this importer; it is not database-wide
access control against other writers or direct message API calls.

A unique database index also binds `(case_id, source_record_key)` to one canonical
message. The source record key uses PDF SHA-256, source type and record locator,
excluding acquisition ID. Importing identical PDF records under a conflicting
timezone therefore raises a conflict, including under concurrent imports. Separate
acquisitions remain distinct occurrences on the same canonical message. Correcting
a supplied timezone requires a fresh rebuild; reimport is not a correction API.

## Reproduce locally

Use the existing Python environment supporting Python 3.10 or later and the pinned
requirements. Do not use an older Python 3.9 environment. Place all private files
outside the checkout. Supply the confirmed display timezone (or clearly label a
hypothesis run):

```bash
python -m pytest -q --tb=short \
  --ofw-oct16-export="/absolute/private/OFW_Messages_Report_2026-10-16_17-50-15.pdf" \
  --ofw-oct30-export="/absolute/private/OFW_Messages_Report_2026-10-30_07-35-16.pdf" \
  --ofw-oct30-timezone="America/Vancouver" \
  --ofw-mongod="/absolute/path/to/mongod" \
  --ofw-mongo-work-dir="/absolute/private/disposable-work"
```

The parent work directory must exist outside Git. The database fixture creates a
new loopback-only server, random port and private data directory, then tears them
down. It never uses a production database URL. The two report options enable
both individual acceptance and cross-report tests; `--ofw-mongod` enables real
database tests. Omitting optional fixtures/runtime produces explicit skips;
an invalid explicit path or missing explicit compact timezone fails.

The compact oracle uses sorted PDF text independently of the production
coordinate reader. It checks all primary fields, source pages, body text, read
receipts and attachment references. The older oracle uses coordinates
independently of the legacy text parser. Both operate on the pinned private bytes.
Comparisons normalize layout whitespace; they do not certify every rendered glyph.
Private failures withhold values and tracebacks, including under `--showlocals`.

## Expected overlapping-report results

With the confirmed Vancouver setting, all 622 older messages match the newer report:

| Operation | Canonical messages inserted | Source occurrences added |
| --- | ---: | ---: |
| October 16 into empty collection | 622 | 622 |
| October 30 after October 16 | 552 | 1,174 |
| Replay either report | 0 | 0 |
| October 30 into empty collection | 1,174 | 1,174 |
| October 16 after October 30 | 0 | 622 |
| Eight simultaneous imports, four of each report | 1,174 total | 1,796 total |

The final collection has 622 messages with two source occurrences and 552 with one.
Receipt reconciliation selects the earliest known viewed time for each recipient
while preserving each report's receipt observations. Six compact-report receipt
observations are unviewed; 1,176 receipt observations span 1,174 messages. There
are 295 attachment references across 81 messages. Under Vancouver, 774 sent
timestamps have UTC-07 and 400 have UTC-08 offsets.

These expectations are checked by both BSON-round-trip tests and live MongoDB
tests. A test's presence is not proof that it ran. Record command, code revision,
runtime versions, exit status and skip reasons for each execution.

## Executed validation: October 31, 2026

The reviewed changes following PR head
`a51836f5fae1e39998d63a502748ce9687622235` were revalidated before publication:

| Execution | Result |
| --- | --- |
| Full suite, both private PDFs and disposable MongoDB | **73 passed, 1 skipped** in 71.64 seconds |
| Full suite without optional private fixtures/runtime | **52 passed, 22 skipped** |
| Real MongoDB tests included in the full acceptance run | **16 passed** |
| Python 3.10 syntax check of changed/new Python files | **16 files passed** |
| Patch whitespace validation | Passed |

The single full-suite skip is the unavailable July export. Five existing
PyMuPDF/SWIG deprecation warnings remain. Runtime: Python 3.14.6, pytest 8.4.2,
PyMuPDF 1.26.5, Pydantic 2.12.4, PyMongo 4.15.4 and MongoDB Community 8.0.34.
Local flake8 was unavailable; GitHub lint and test results are recorded separately
in the PR, without private fixtures. Python 3.10 was syntax-checked locally;
the executed local suite used Python 3.14.6.

Both sequential import orders and eight synchronized overlapping imports produced
1,174 canonical messages and 1,796 source occurrences. Sequential and concurrent
replays added nothing. Original PDF hashes remained unchanged. The fixture's
loopback-only server and temporary database directories were removed after testing.
Non-loopback networking was denied during the test run. **All acceptance imports
used the fixture-owned disposable server; the existing application database was
not imported into, changed or migrated.**

Independent read-only review found two edge cases in ordinary punctuation wrapping
and conflicting supplied timezones; regressions were added and both fixes were
re-reviewed. No remaining blocker was found within the reviewed scope. The PR
remains **draft**; these results do not authorize a merge, deployment or database
cutover.

## Limits

This is native-text parsing of the two observed formats, not OCR or general OFW
format support. Message IDs are derived; the PDFs do not expose OFW UUIDs. They
cannot distinguish truly identical messages sent in the same displayed minute;
within-report duplicate IDs fail closed. Punctuation wrap normalization relies
on the physical line boundary, and original PDFs remain available for ambiguity
review. Local standalone database tests do not establish replica-set failover,
sharding, network partition handling, crash recovery or restart durability.
Imports are atomic per message/occurrence, not whole-report transactions.
The older July fixture remains unavailable, and its v2 identifier digest has not
been independently established. OFW calls and actual attachment files are outside
these acceptance checks. No private fixtures should be uploaded to CI.
