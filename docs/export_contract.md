# Export Endpoint Contract

This document specifies the observed and intended contract for the Evidence Engine export endpoint.
It captures purpose, inputs, outputs, side-effects, error behavior, and invariants.

## Purpose

Provide a way to export a filesystem folder as a ZIP archive. The endpoint returns the ZIP file contents
and — as an implementation-side-effect — writes a copy of the archive under the configured `EXPORT_ROOT`.

## Endpoint

- Method: GET
- Path: `/api/evidence/export`
- Query parameter: `folder` (URL-encoded absolute or relative filesystem path)

Example request (URL-encoded):

```
GET /api/evidence/export?folder=/full/path/to/folder
```

## Inputs

- `folder` (required): filesystem path to the folder to be exported. The path is interpreted by the
  server process (tilde expansion is performed by the exporter implementation).
- Authentication/authorization: out of scope for this document (handled by higher-level middleware if present).

Preconditions:
- The path points to an existing directory readable by the server process.

## Outputs

On success the server returns a binary ZIP archive representing the contents of `folder`.

- HTTP status: `200 OK`
- Content-Type: `application/zip` (or a content-type that contains `zip`)
- Body: raw ZIP bytes

Side-effect (observed behavior):
- The server also writes a file to `EXPORT_ROOT` named `{folder.name}_export.zip` (where `folder.name` is
  the final path component of the input folder). The function returns the full path to this file internally.

Returned ZIP contents:
- The archive contains the files discovered under `folder` with archive names computed as relative
  paths to `folder` (i.e., the ZIP entries preserve the folder-relative paths `a.txt`, `sub/b.txt`, ...).

Invariants the implementation preserves:
- Archive filename pattern: `<folder.name>_export.zip` under configured `EXPORT_ROOT`.
- Archive entries are relative to the provided folder (no absolute paths inside the ZIP).

## Error behavior (current observed)

- If the provided `folder` does not exist the exporter raises `FileNotFoundError` and the endpoint returns an
  internal error (500) as currently observed in tests/run. (Recommendation: translate this into a `404 Not Found`.)
- Filesystem/permission errors are propagated from the underlying stdlib calls and surface as 5xx errors.

## Recommended contract clarifications (optional)

To stabilize the contract across clients and implementations, consider the following authoritative rules:

- Successful responses MUST be `200` with `Content-Type: application/zip` and the raw ZIP bytes.
- If the input folder does not exist, the server SHOULD return `404 Not Found` with a JSON error body.
- If the server is unable to write the archive to `EXPORT_ROOT`, the server SHOULD return `503 Service Unavailable`
  or `500 Internal Server Error` depending on transient vs permanent conditions.
- The exporter MUST NOT include absolute paths in ZIP entries and MUST preserve relative structure rooted at the
  provided `folder`.

## Examples

Observed success example (curl):

```
curl -G --output output.zip --data-urlencode "folder=/full/path/to/source" \
  http://localhost:8000/api/evidence/export
```

After this request the server will:
- Write `EXPORT_ROOT/<source>_export.zip` on disk (implementation side-effect).
- Return the ZIP bytes that can be saved locally (as in `output.zip`).

## Notes

- The behavior documented above reflects the current implementation's behavior and the tests used during stabilization.
- This file is intended for documentation only and does not change runtime behavior.
