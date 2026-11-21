"""Local-only Ollama chat adapter using bounded HTTP and structured JSON output."""

import json
import re
from urllib.parse import urlsplit

import httpx

from paw.domain.files import InputError
from paw.domain.google_ads_interpretation import InterpretationRequest, InterpretationResponse

MAX_OLLAMA_RESPONSE_BYTES = 128 * 1024
MODEL_DIGEST = "f04aa1c738f64e13c625b82ae92504fc0260fa6723b509ed1ece0fa188179b1d"


class OllamaProvider:
    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "ministral-3:3b",
        timeout_seconds: float = 600,
        transport: httpx.BaseTransport | None = None,
    ):
        url = urlsplit(base_url)
        if (
            url.scheme != "http"
            or url.hostname not in ("127.0.0.1", "localhost", "::1")
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in ("", "/")
        ):
            raise InputError("local_model_url_required")
        if model != "ministral-3:3b":
            raise InputError("unsupported_local_model")
        if not 1 <= timeout_seconds <= 1800:
            raise InputError("invalid_local_model_timeout")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def _request(
        self, client: httpx.Client, method: str, path: str, body: dict[str, object] | None = None
    ) -> dict[str, object]:
        with client.stream(method, path, json=body) as response:
            if response.status_code != 200:
                raise InputError("local_model_http_error")
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > MAX_OLLAMA_RESPONSE_BYTES:
                    raise InputError("local_model_response_too_large")
        try:
            value: object = json.loads(data)
        except (ValueError, UnicodeDecodeError, RecursionError):
            raise InputError("invalid_local_model_response") from None
        if not isinstance(value, dict):
            raise InputError("invalid_local_model_response")
        return value

    def interpret(self, request: InterpretationRequest) -> InterpretationResponse:
        # No redirects/proxies/cloud endpoints or automatic retries. The Compose
        # runtime also sets OLLAMA_NO_CLOUD=1; only installed allowlisted models run.
        try:
            with httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                trust_env=False,
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                version = self._request(client, "GET", "/api/version").get("version")
                tags = self._request(client, "GET", "/api/tags").get("models")
                if not isinstance(tags, list):
                    raise InputError("invalid_local_model_response")
                found = [
                    item
                    for item in tags
                    if isinstance(item, dict) and item.get("name") == self.model
                ]
                if len(found) != 1:
                    raise InputError("local_model_not_installed")
                digest = found[0].get("digest")
                if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                    raise InputError("invalid_local_model_response")
                if digest != MODEL_DIGEST:
                    raise InputError("local_model_digest_mismatch")
                data = self._request(
                    client,
                    "POST",
                    "/api/chat",
                    {
                        "model": self.model,
                        "stream": False,
                        "keep_alive": 0,
                        "format": request.output_schema,
                        "messages": [
                            {"role": "system", "content": request.instructions},
                            {
                                "role": "user",
                                "content": request.evidence_json.decode("utf-8")
                                + "\nReturn JSON matching this schema:\n"
                                + json.dumps(request.output_schema),
                            },
                        ],
                        "options": {
                            "temperature": 0,
                            "seed": 42,
                            "num_ctx": 16384,
                            "num_predict": request.max_output_tokens,
                            "num_thread": 6,
                        },
                    },
                )
        except httpx.TimeoutException:
            raise InputError("local_model_timeout") from None
        except httpx.HTTPError:
            raise InputError("local_model_unavailable") from None
        message = data.get("message")
        if (
            data.get("done") is not True
            or data.get("model") != self.model
            or not isinstance(message, dict)
        ):
            raise InputError("invalid_local_model_response")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise InputError("empty_local_model_response")

        def tokens(name: str) -> int | None:
            value = data.get(name)
            if value is not None and (type(value) is not int or value < 0):
                raise InputError("invalid_local_model_response")
            return value

        return InterpretationResponse(
            content.encode("utf-8"),
            "ollama-local",
            self.model,
            tokens("prompt_eval_count"),
            tokens("eval_count"),
            model_digest=digest,
            runtime_version=version if isinstance(version, str) else None,
            finish_reason=str(data["done_reason"]) if data.get("done_reason") is not None else None,
        )
