# ADR-015 — Projects and bounded CSV storage

Status: Accepted, 2026-11-19. Scope: M1.1 only.

## Decision

Create one internal workspace, projects and file metadata through migration 0002. A file belongs to a project and derives its workspace through that relationship. The API owns writes; no runs, Worker, agents or frontend workflow are introduced here.

Preserve uploaded bytes in a dedicated local volume through a framework-independent storage port. Generate UUID storage keys on the server, retain the original filename only as metadata, and return no disk paths. Store SHA-256, byte size, CSV dimensions, delimiter and server timestamp. Repeated uploads are separate files; hashes do not implement deduplication.

Accept UTF-8 (including BOM), a header and at least one data row, comma or explicitly selected semicolon. Limits: 10 MiB, 100,000 data rows, 200 columns, 256 characters per header and 32,768 characters per cell. Reject blank/duplicate trimmed headers, malformed quoting, inconsistent row widths, unsafe filenames and unsupported encodings. No type inference, formula evaluation or automatic delimiter guessing.

Bound incoming POST bytes before multipart parsing, including requests without trustworthy Content-Length. Upload envelopes have 64 KiB overhead allowance; other POST bodies have a 64 KiB limit. Two requests may buffer/process at once per API process, with a 30-second body-read timeout. These local controls do not replace the online deployment gate.

## Persistence and recovery

Under a PostgreSQL transaction advisory lock, reconcile unreferenced UUID files, write a temporary blob, fsync, rename and fsync the directory, then insert metadata and commit. This serializes uploads for a small personal installation. Registry operations use their own lock.

The filesystem and PostgreSQL do not share an atomic transaction. On failure, reacquire the lock and inspect committed metadata before removing unreferenced blobs. Never blindly delete after an ambiguous commit failure. When the database is unavailable, defer cleanup until startup or the next upload. Abrupt interruption may leave an invisible orphan until reconciliation succeeds. Unknown filenames are left alone.

Use a dedicated volume per installation/database. Back up and restore the database and file volume together while writes are stopped. Reconciliation does not recover externally deleted files. Shared object storage, parallel upload scaling and a backup implementation are later work.

## Alternatives and consequences

Storing blobs in PostgreSQL would simplify atomicity but couples future large materials to database storage. Object storage would add unnecessary infrastructure now. The local adapter keeps the first slice small and replaceable; full-volume reconciliation on each upload is acceptable initially and should be revisited with measured growth.

Projects and uploads are application data, not architecture changes. They do not append `system_events` or fabricate component registrations. Future execution uses `runs` and `run_events` in M1.2.
