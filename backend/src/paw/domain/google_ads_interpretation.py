"""One-off interpretation contracts, independent of HTTP/provider SDKs."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class BusinessContext:
    services: tuple[str, ...] = ()
    geography: str | None = None
    objective: str = "Review traffic quality and suggest evidence-backed improvements."


@dataclass(frozen=True)
class InterpretationRequest:
    instructions: str
    evidence_json: bytes
    output_schema: dict[str, object]
    max_output_tokens: int
    call_id: str | None = None


@dataclass(frozen=True)
class InterpretationResponse:
    content: bytes
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider_request_id: str | None = None
    model_digest: str | None = None
    runtime_version: str | None = None
    finish_reason: str | None = None


class InterpretationProvider(Protocol):
    def interpret(self, request: InterpretationRequest) -> InterpretationResponse: ...
