# ADR-021 — One-off local interpretation before historical/automation integration

Status: Accepted, 2026-11-21. Scope: owner-authorized offline M1.5 experiment.

## Decision

The owner chose a one-off CSV -> evidence -> local model -> saved report experiment
before historical imports or automation. No paid API budget; no external model service.
Use Ministral 3 3B through an optional, separately launched Ollama Docker service.
This is a fixed interpretation pass, not the full Data Analyst agent/API/Worker slice.
It does not replace the planned explicit agent registration/restricted tools or mark
M1 complete. No database writes, lifecycle events, history merge or scheduled triggers.

Reuse existing CSV/evidence functions in memory. Require exactly one campaign source,
at most one keyword and one search-term source; aggregated search periods must match.
All campaigns (maximum twenty) and up to fifteen highest-observed-cost rows of each
search profile enter the model package, with included/omitted counts. Full-report
coverage facts are computed before this selection. Omitted data remains local and
must not be represented as complete query visibility. Business context is explicit;
unknown services/geography do not authorize irrelevant-query/negative-keyword claims.

The provider receives bounded calculated facts (maximum 80 KiB) with local fact IDs,
business context, warnings and selection limitations. Original CSV/raw cells/notes,
filesystem paths and full row-reference arrays are omitted. The local manifest maps
fact IDs back to source rows. Store exact payload hash, prompt version, batch/call IDs,
raw model answer, available usage, measured duration, model digest/runtime version and
JSON/Markdown report in a new local output directory (default under ignored artifacts).
Preserve failed responses and metadata; never silently replace or automatically retry
a generation. Unavailable billing values remain null; no electricity-cost claim is made.

## Runtime and trust boundaries

Pin the Ollama image by digest and the allowed installed Ministral model digest.
Expose only `127.0.0.1:11434`; disable cloud features (`OLLAMA_NO_CLOUD=1`). The adapter
accepts only loopback HTTP endpoints, disables proxies/redirects, allows only the chosen
installed model, bounds response bytes and provides no model tools. Network access is
needed for image/weight downloads, not external inference. No advertising file mount
is provided to the container. Docker CPU/RAM limits are explicit; macOS Docker has no
Metal GPU acceleration. The model unloads after each request; weights persist separately
from PAW's private DB/file/artifact volumes.

Use Ollama JSON-schema output plus local validation of required fields, list/prose
limits and known fact references. Escape model prose in Markdown. Model-written
numeric and semantic claims are **not automatically verified** merely because a cited
fact exists; show calculated evidence and review recommendations. Rejecting all digits
in prose distorted a real trial's output, so the current prompt permits accurate numbers
and instead makes review/grounding limits explicit. It forbids interpreting undisclosed
queries as missed traffic or assigning global coverage to individual campaigns.

## Alternatives and next boundary

Paid cloud interpretation was not selected. A normalized historical warehouse is not
required for this experiment. Direct raw CSV prompting would discard verified arithmetic
and provenance. A fully integrated autonomous agent/tool loop would expand the scope
before judging whether local interpretation is useful. The minimal typed provider port
keeps a later agent adapter possible without bringing provider dependencies into domain.

Native Metal inference, larger models, full-row model input, durable API/run integration
and automated collection remain separately scoped decisions. Comparison with an assistant
baseline on one identical payload is an exploratory quality check, not a general benchmark.

Sources: [Ministral 3 3B](https://docs.mistral.ai/models/ministral-3b-latest),
[Ollama model/digest](https://ollama.com/library/ministral-3:3b),
[local/cloud settings and macOS limitations](https://docs.ollama.com/faq),
[structured outputs](https://docs.ollama.com/capabilities/structured-outputs).
