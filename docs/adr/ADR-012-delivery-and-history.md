# ADR-012: Owner workflows and history-first delivery

- Status: Accepted for planning; not implemented
- Date: 2026-11-19
- Context: Owner discussion refining Blueprint v1.3

## Context

PAW is a learning project and a useful single-owner workspace. CSV analysis is a manageable first workflow; later tasks will include images, documents and language learning. The owner uses an iPhone and MacBook and intends to run the system privately online. Visualization can wait, but its underlying history must be collected from the beginning.

## Decision

Keep the modular monolith, separate API and Worker processes, PostgreSQL, API ownership and independent n8n service. Develop locally first; private online deployment has a separate M4 gate. Do not choose hosting or a recurring budget before understanding the working stack.

M0 records verified nodes and logical links using minimal `service_nodes`, `service_edges` and append-only `system_events` tables. Bootstrap verifies the running API and its database readiness before registering `service:api`, `storage:postgres` and their `persists_to` link. Stable identities, sanitized after-state events and atomic projection/event writes prevent retries or later renames from inventing growth. A logical link is not evidence of measured traffic or permanent health.

Move System Map, historical APIs, Project Evolution charts and isolated synthetic portfolio mode out of core MVP acceptance into a separate post-MVP visualization slice. M2 delivers the usable responsive workflow UI; M3 delivers authenticated n8n automation. Preserve events for future replay without building replay infrastructure now.

Future web and Telegram capture channels use shared platform state. Treat incoming material, execution and saved results as distinct concepts, introducing their models only with the relevant feature. Preserve source-to-result provenance separately from non-sensitive system evolution history.

Use English for UI and general reports, Ukrainian for explanations/translations of Estonian and English learning material. A later language workflow extracts all readable text, flags uncertainty and prepares editable drafts for owner selection. Preserve originals and distinguish source text from generated examples.

## Alternatives and tradeoffs

- Keeping visualization in M2 would delay everyday utility. Deferral preserves its value while reducing core MVP UI scope.
- Deferring link collection until visualization would lose early topology. Three minimal history tables cost slightly more than the former two-table M0, but preserve actual relationships without a generic event-sourcing platform.
- Recording only link events in M0 would defer a table but require separate mutation/idempotency handling. A small current projection keeps node/link rules consistent.
- Separate per-channel databases would fragment results and history. Shared API ownership supports adding channels incrementally.
- Full offline AI and native mobile applications are not requirements. External providers are permitted; provider selection, spending limits and device shortcuts remain later decisions.

## Consequences

This supersedes the v1.3 requirement for map UI in M2, portfolio readiness in M3 and node-only M0 history. It does not authorize application implementation, server provisioning, external-project connections or building language/Telegram modules during M0.

Future validation must cover event/projection rollback, append-only enforcement, repeated and concurrent bootstrap, historical identities and safe metadata. M0 checks these on an isolated PostgreSQL test database as well as through unit/API tests. Historical read APIs and visual replay tests arrive with visualization.
