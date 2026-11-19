# Local development security boundary

M0 is for one owner on a trusted local machine. API and web ports bind to `127.0.0.1`. PostgreSQL has no published port and uses an internal Docker network. There is no production authentication: do not expose these services to the Internet or a shared network.

Generate private local credentials with `python3 scripts/init_local_env.py`. It creates a mode-0600 `.env` once without printing or overwriting values. `.env.example` contains placeholders only. Environment files, local tool installations, datasets, artifacts and database/n8n storage are ignored by Git. Do not paste resolved Compose configuration or credentials into issues or logs.

PAW logs fixed structured event names, not database exception contents or private payloads. Uvicorn access logging is disabled. Registry metadata has a small key-and-value allowlist. Bootstrap is a local CLI operation; no model-generated code execution or file processing exists in M0.

The optional n8n profile is local-only and requires its own encryption key; browser secure-cookie enforcement is disabled solely for local HTTP. It is not an integrated workflow yet. Its configuration must be reviewed before online use.

CI runs one Gitleaks scan over Git history. It detects recognizable credential patterns, not every possible secret or personal document. It does not scan ignored local files or replace human review. A confirmed exposed credential is a blocker: revoke/rotate it, identify exposure, remove it from current files and coordinate history cleanup if necessary. Do not disable the entire scanner for a false positive; document a narrow exception.

Before online deployment, add owner authentication, HTTPS, rate limits, restricted CORS and admin/database access, backup/restore verification, and a targeted dependency/container review. No current local run establishes production readiness. Additional security infrastructure is deferred until there is a concrete need.
