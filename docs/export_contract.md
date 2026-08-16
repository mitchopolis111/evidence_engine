# Export Endpoint Contract

This document defines the Evidence Engine export endpoint, including its
filesystem authorization boundary and ZIP invariants.

## Endpoint

- Method: `GET`
- Path: `/api/evidence/export`
- Query parameter: `folder` (optional URL-encoded absolute path)

If `folder` is omitted, the endpoint uses `EVIDENCE_SOURCE_FOLDER`. If that is
also unset, it uses the canonical `parenting_evidence/text_logs` folder.

Example:

```bash
curl -G --output output.zip \
  --data-urlencode "folder=/Users/mitchelwatson/Projects/Mitchopolis/parenting_evidence/text_logs" \
  http://localhost:8000/api/evidence/export
```

## Approved source roots

The resolved source path must be equal to or below one of these roots:

1. The canonical `parenting_evidence` folder beside the repository.
2. `EVIDENCE_SOURCE_FOLDER`, when configured.
3. Each absolute path in `EVIDENCE_EXPORT_ALLOWED_ROOTS`, separated by the
   platform path separator (`:` on macOS).

Configured roots must be absolute and cannot be the filesystem root. A request
path is resolved before authorization, so `..` traversal and a requested
symlink that escapes an approved root are rejected. Authentication of callers
remains a deployment responsibility; the allowlist limits filesystem scope but
does not replace API authentication.

## Successful response

- HTTP status: `200 OK`
- Content-Type: `application/zip`
- Body: raw ZIP bytes
- Server-side output: `Mitchopolis/exports/<source-name>_export.zip`

Archive entries use paths relative to the selected source folder. Absolute ZIP
entry paths are never written. Files and directories are traversed in stable
sorted order, and archive timestamps and file modes are normalized. The same
filenames and file contents therefore produce the same ZIP bytes.

The server writes to a temporary file and atomically replaces the named output
after successful packaging, so a failed request does not leave a partial final
archive.

## Source restrictions

Only regular files are packaged. A symbolic link or special filesystem entry
anywhere in the source causes the request to fail rather than following or
silently omitting that entry. The export destination must also remain outside
the selected source folder.

## Error responses

| Status | Meaning |
|---|---|
| `400 Bad Request` | Relative path, non-directory source, invalid path, or unsafe source entry |
| `403 Forbidden` | Resolved source is outside every approved evidence root |
| `404 Not Found` | Approved source folder does not exist or disappears before packaging |
| `500 Internal Server Error` | Invalid server configuration or unexpected archive failure |

All errors use FastAPI's JSON error response shape with a concise `detail`
message. Internal filesystem paths are not returned for unexpected failures.

## Compatibility invariants

- `folder` remains optional.
- The archive name remains `<source-name>_export.zip`.
- Nested source structure is preserved with relative POSIX-style entry names.
- `generate_evidence_zip()` remains the router-facing compatibility function.
