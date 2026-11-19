# Optional n8n runtime configuration

The inactive `automation` Compose profile reserves an independent n8n service for M3. It does not register an integration, execute a workflow or access PAW tables. M0 does not require starting it or creating an n8n account.

The configuration targets a separate logical PostgreSQL database `n8n` and user `n8n`, plus its own state volume and encryption key. M3 must provision that database/user, set a private `N8N_DB_PASSWORD`, preserve the encryption key, and validate the actual workflow before enabling the profile. Those database resources are deliberately not created by the M0 PAW migrations. Do not enable the profile yet; configuration alone does not constitute a working integration.

The future local admin URL is `http://127.0.0.1:5678`. Online exposure requires the separate deployment gate. PAW must never query n8n internal tables.

M3 will add an authenticated, bounded, idempotent API integration and an exportable sanitized scheduled workflow. Until then `workflows/` contains no fabricated workflow. n8n is a separate third-party product with its own license; PAW's MIT license does not relicense it.
