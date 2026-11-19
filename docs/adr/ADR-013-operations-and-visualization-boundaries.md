# ADR-013: Operations, traceability and visualization boundaries

- Status: Accepted for planning; not implemented
- Date: 2026-11-19
- Scope: Clarification of Blueprint v1.4; no expansion of M0

## Context

The future workspace needs a unified view of components, executions and operations. Existing contracts already separate registry identity, lifecycle history, run events and observed health. Ambiguous references to platform events could nevertheless put frequent monitoring activity into permanent architecture history. Historical topology and historical activity also require different source data.

## Decision

1. Keep the Service Registry authoritative for component identity and topology. A future Operations view joins information through these stable identities; it does not introduce another registry or microservice.
2. Reserve `system_events` for component/link lifecycle changes and explicit milestones. Use `runs`/`run_events` for agent execution from M1. Store health checks, routine deployment attempts and backup outcomes separately only when needed. An operation causing a topology change can produce a distinct lifecycle event; its detailed execution remains in its own context.
3. In M1, correlate runs, attempts and model/tool activity with stable identifiers and optional correlation IDs. Keep correlation distinct from retry deduplication. Expose available provider/model, token counts, measured duration and explicitly estimated cost with a pricing basis. Missing usage is unavailable, not zero; no Gateway is needed.
4. Expose renderer-neutral nodes, typed relationships, states and events. React Flow is the first renderer; layout and engine-specific fields stay outside the domain. A future 3D renderer may reuse contracts, but is not implemented now.
5. Distinguish Live System Map, Project Evolution, Historical Activity Replay and isolated Portfolio Demo. Replay uses retained execution/operational observations, not only topology history or latest heartbeats. Define retention with each feature and display missing coverage honestly.
6. n8n remains responsible for triggers and integration workflows. PAW owns accepted application state and observations. Future notifications, rollback and self-healing are separate capabilities, not implicit permissions.

## Alternatives and consequences

One universal event table would simplify initial ingestion but mix immutable topology with high-volume activity and incompatible retention needs. A new monitoring platform or broker would add infrastructure before there is a demonstrated requirement. Neither is justified.

M0 remains the existing three-table foundation with liveness/readiness endpoints, verified bootstrap, a minimal UI shell and checks. It does not persist every probe or create unused execution/telemetry schemas. M1 introduces traceable execution and usage; M3 adds only the observations required by the n8n health workflow; M4 adds deployment and backup evidence. Full operations dashboards, animated replay, 3D and automatic remediation remain deferred.

This clarifies existing architecture rather than replacing ADR-012 or restarting a milestone. Prioritize functioning M0 and the first complete Data Analyst workflow.
