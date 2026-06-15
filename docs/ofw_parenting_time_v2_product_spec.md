# OFW Parenting-Time Communication Pipeline V2 Product Spec

## Purpose

Build a deterministic, reusable pipeline for OurFamilyWizard (OFW) message exports that identifies parenting-time-related communication and surfaces extracted-export evidence of missing or delayed replies that may affect parenting-time coordination.

This spec is a product and implementation contract. It is not legal advice, and generated summaries must stay neutral, factual, and grounded only in parsed source text.

## Canonical Paths

- Workspace root: `/Users/mitchelwatson/Projects/Mitchopolis`
- Evidence Engine repo: `/Users/mitchelwatson/Projects/Mitchopolis/evidence_engine`
- Input inbox: `/Users/mitchelwatson/Projects/Mitchopolis/parenting_evidence/inbox`
- Processed output: `/Users/mitchelwatson/Projects/Mitchopolis/parenting_evidence/processed`
- Timeline output: `/Users/mitchelwatson/Projects/Mitchopolis/parenting_evidence/timelines`
- Utility code: `/Users/mitchelwatson/Projects/Mitchopolis/evidence_engine/src/utils`

Do not use home-directory shadow workspace paths; use the canonical paths above.

## Goals

- Extract OFW messages from PDF exports into structured message records.
- Parse messages as blocks, not individual lines.
- Identify parenting-time logistics and coordination messages.
- Detect whether the other party replied after a message.
- Classify response status as `responded`, `delayed`, or `no_response_found`.
- Produce court-review-ready CSV, JSON, Markdown, and timeline outputs.
- Preserve source text snippets exactly as extracted, with provenance and review flags.

## Non-Goals

- Do not infer replies that are not present in the extracted OFW export.
- Do not decide legal conclusions.
- Do not modify or move original OFW PDFs.
- Do not silently install system dependencies during normal pipeline runs.
- Do not use unstated messages from email, memory, or prior exports to fill gaps in a PDF-specific run.

## Dependency Contract

Required local dependency:

- `pdftotext` from Poppler, used with layout preservation.

Setup check:

```bash
command -v pdftotext
```

If missing, the pipeline should stop with a clear setup message:

```bash
brew install poppler
```

The pipeline should not run Homebrew automatically.

## Recommended Implementation Shape

The original prompt proposed a Node.js parser. For this repository, the preferred implementation is Python unless a later task explicitly requires Node:

- Parser module: `src/utils/ofw_parser.py`
- CLI/pipeline module: `src/utils/ofw_pipeline.py`
- Optional shell wrapper: `src/utils/ofw_pipeline.sh`
- Tests: `tests/test_ofw_parser.py` and `tests/test_ofw_pipeline.py`

The shell wrapper may exist for convenience, but parsing and classification logic should live in tested Python code.

## Input Selection

The pipeline must accept an explicit PDF path.

Optional convenience mode may select the newest PDF in the canonical inbox. If this mode is used, the selected PDF path must be printed and stored in output metadata.

## PDF Text Extraction

Convert PDF to raw text with layout preservation:

```bash
pdftotext -layout "$INPUT_PDF" "$RAW_TEXT_OUTPUT"
```

Raw extracted text should be saved beside other processed outputs for auditability when practical.

## Message Block Parsing

Parsing must split the export into message blocks. A block begins at a line containing `Sent:`.

For each block, extract:

- `message_id`
- `sent_datetime`
- `date`
- `sent_time`
- `from`
- `to`
- `first_viewed`
- `subject`
- `body`
- `raw_block`
- `parse_confidence`
- `parse_warnings`

Normalization rules:

- Trim field labels and surrounding whitespace.
- Preserve body text and snippets exactly as extracted except for outer whitespace trimming.
- Normalize dates internally to ISO-like values when parseable, while retaining original text fields.
- Generate stable `message_id` values from source file hash, sent datetime, sender, recipient, subject, and raw block hash.
- If a required field cannot be parsed, keep the message and add a review warning.

## Thread Grouping

Group messages by:

- normalized subject, when available; otherwise
- chronological proximity and sender alternation.

Subject normalization should remove common prefixes such as `Re:`, `RE:`, and `Fwd:` and collapse repeated whitespace.

Proximity grouping is a fallback only and must be marked with lower confidence.

## Parenting-Time Classification

Classify each message using deterministic keyword and phrase rules. Initial keywords:

- `pickup`
- `drop`
- `drop-off`
- `schedule`
- `time`
- `call`
- `facetime`
- `visit`
- `see her`
- `have her`
- `available`
- `parenting time`
- `exchange`
- `overnight`

Category:

- `parenting_time`: direct parenting-time logistics or access coordination.
- `communication`: general communication not directly tied to parenting time.
- `ignore`: low relevance to this pipeline.

Relevance:

- `HIGH`: direct logistics about seeing the child, exchanges, visits, pickup/drop-off, calls, FaceTime, or scheduling parenting time.
- `MEDIUM`: coordination language that may affect parenting time but is less direct.
- `LOW`: not included in filtered outputs.

Classification must be explainable by matched terms or rules.

## Response Matching

For each parenting-time message:

- Sort all messages chronologically.
- Identify the next later message in the same thread or fallback proximity group from the other party.
- Compute `response_time` and `delay_hours` when a candidate reply exists.
- Classify:
  - `responded`: reply found within 24 hours.
  - `delayed`: reply found after more than 24 hours.
  - `no_response_found`: no later reply found in the extracted OFW export.

Do not mark an item as simply `no_response` without explaining that the finding is limited to the parsed export.

If the parser is uncertain about thread grouping, keep the response match but add `review_required: true`.

## Filtered Output Rule

Filtered court-review outputs include only messages where:

- `category = parenting_time`
- and `status` is `no_response_found` or `delayed`

The full JSON audit output may include all parsed messages for debugging and review.

## Required Outputs

### CSV

Path:

`/Users/mitchelwatson/Projects/Mitchopolis/parenting_evidence/processed/parenting_time_log.csv`

Fields:

- `date`
- `from`
- `to`
- `sent_time`
- `first_viewed`
- `response_time`
- `delay_hours`
- `status`
- `relevance`
- `subject`
- `snippet`
- `source_pdf`
- `message_id`
- `review_required`

### JSON

Path:

`/Users/mitchelwatson/Projects/Mitchopolis/parenting_evidence/processed/parenting_time_log.json`

Each record:

```json
{
  "message_id": "",
  "date": "",
  "from": "",
  "to": "",
  "category": "parenting_time",
  "status": "no_response_found",
  "delay_hours": null,
  "snippet": "",
  "source_pdf": "",
  "review_required": false
}
```

### Markdown Summary

Path:

`/Users/mitchelwatson/Projects/Mitchopolis/parenting_evidence/processed/parenting_time_summary.md`

Required sections:

- `# Parenting Time Communication Analysis`
- `## Source`
- `## Metrics`
- `## Pattern Summary`
- `## Review Flags`
- `## Court Statement Draft`

Metrics:

- total parsed messages
- total parenting-time messages
- total non-responses found in parsed export
- total delayed responses
- total review-required records

Court statement draft must use neutral language such as:

> The parsed OFW export contains repeated parenting-time coordination messages where no later response was found in the export or where the next identified response occurred after more than 24 hours. These records may be relevant to reviewing whether communication delays affected parenting-time coordination.

### Timeline

Path:

`/Users/mitchelwatson/Projects/Mitchopolis/parenting_evidence/timelines/ofw_timeline_YYYY-MM-DD.md`

Entry format:

```text
[DATE]
Event: Parenting communication sent
Outcome: No later response found in parsed export / delayed response
Impact: Parenting-time coordination may have been affected
Source: <source_pdf>#<message_id>
```

## Terminal Summary

On completion, print:

```text
Summary:
- parsed messages: X
- parenting-time matches: X
- no-response-found count: X
- delayed count: X
- review-required count: X
- output directory: /Users/mitchelwatson/Projects/Mitchopolis/parenting_evidence/processed
```

Exit non-zero only for setup errors, unreadable input, parse failure with zero message blocks, or output-write failure.

## Safety Rules

- Preserve original PDFs.
- Preserve extracted snippets exactly.
- Do not hallucinate responses.
- Do not assume a reply if no parsed reply exists.
- Use `no_response_found` to make the evidence boundary explicit.
- Add review flags for low-confidence parsing, fallback thread grouping, missing date fields, or ambiguous sender names.
- Store enough provenance to reproduce every output row from the source PDF.

## Test Requirements

Tests should cover:

- block parsing from representative OFW text.
- missing `first_viewed` fields.
- multi-line subjects and bodies.
- subject-based thread grouping.
- fallback proximity grouping with review flags.
- response time under 24 hours.
- delayed response over 24 hours.
- no later reply found.
- exact snippet preservation.
- CSV/JSON/Markdown output schema.

Fixtures should be synthetic or sanitized. Do not commit private OFW exports.

## Implementation Milestones

1. Add parser fixtures and parser tests.
2. Implement message block parser.
3. Implement deterministic classification.
4. Implement thread grouping and response matching.
5. Implement output writers.
6. Add CLI and optional shell wrapper.
7. Run focused tests, then full Evidence Engine tests.
