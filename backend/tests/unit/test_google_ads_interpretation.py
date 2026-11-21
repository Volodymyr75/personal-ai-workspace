"""Offline model doubles and HTTP transports; tests never download or invoke a model."""

import csv
import io
import json
from datetime import date
from uuid import UUID

import httpx
import pytest

from paw.application.google_ads_interpretation import (
    interpret_one_off,
    interpretation_schema,
    prepare_one_off_analysis,
    validate_interpretation,
)
from paw.application.google_ads_report import render_one_off_report
from paw.domain.files import InputError
from paw.domain.google_ads import GoogleAdsBatchSpec, GoogleAdsCsvSource
from paw.domain.google_ads_interpretation import (
    BusinessContext,
    InterpretationRequest,
    InterpretationResponse,
)
from paw.infrastructure.llm.ollama import MODEL_DIGEST, OllamaProvider

SPEC = GoogleAdsBatchSpec(UUID(int=1), "synthetic-account", date(2026, 11, 1), date(2026, 11, 7))


def source(kind="campaign_summary", *, count=1):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(
        ["Звіт про кампанію" if kind == "campaign_summary" else "Звіт про ключові слова для пошуку"]
    )
    writer.writerow(["1 листопада 2026 р. - 7 листопада 2026 р."])
    headers = [
        "Статус кампанії",
        "Кампанія",
        "Покази",
        "Кліки",
        "Вартість",
        "Код валюти",
        "Примітка",
    ]
    if kind == "search_keywords":
        headers = [
            "Статус ключового слова",
            "Ключове слово",
            "Тип відповідності",
            "Група оголошень",
        ] + headers[1:]
    writer.writerow(headers)
    for i in range(count):
        row = [
            "Увімкнено",
            f"Synthetic campaign {i}",
            "100",
            "10",
            f"{i + 1},00",
            "UAH",
            "PRIVATE RAW NOTE",
        ]
        if kind == "search_keywords":
            row = [
                "Увімкнено",
                f"[synthetic keyword {i}]",
                "Точна відповідність",
                "Synthetic Group",
            ] + row[1:]
        writer.writerow(row)
    return GoogleAdsCsvSource(kind + ".csv", kind, stream.getvalue().encode())


def prepared():
    return prepare_one_off_analysis(SPEC, (source(), source("search_keywords")), BusinessContext())


def response():
    return {
        "title": "Offline test report",
        "summary": "Supplied evidence needs contextual review.",
        "findings": [
            {"explanation": "The source coverage has stated limitations.", "fact_ids": ["F001"]}
        ],
        "recommendations": [
            {
                "action": "Review the supplied campaign context.",
                "rationale": "Business relevance needs owner confirmation.",
                "fact_ids": ["F001"],
                "priority": "medium",
            }
        ],
        "limitations": ["This is a test double, not a live model analysis."],
    }


class FakeProvider:
    def __init__(self, content=None, finish_reason="stop"):
        self.content = content or json.dumps(response()).encode()
        self.finish_reason = finish_reason
        self.calls = []

    def interpret(self, request):
        self.calls.append(request)
        return InterpretationResponse(
            self.content, "test-double", "offline-fixture", finish_reason=self.finish_reason
        )


def test_payload_is_recalculated_bounded_and_omits_raw_cells_and_local_paths():
    p = prepared()
    body = p["payload"]
    serialized = json.dumps(body)
    assert "PRIVATE RAW NOTE" not in serialized and "raw_cells" not in serialized
    assert "/Users/" not in serialized and "row_ids" not in serialized
    assert body["facts"][0]["impressions"]["observed_sum"] == 100
    assert body["facts"][0]["cost"]["observed_sum"] == "1.00"
    assert body["business_context"]["services"] == ()
    assert "F001" in p["provenance"] and p["provenance"]["F001"]["row_ids"]


def test_cost_selection_is_disclosed_and_stable_without_mixing_reports():
    p = prepare_one_off_analysis(
        SPEC,
        (source(), source("search_keywords", count=20)),
        BusinessContext(("Synthetic service",), "Synthetic region"),
    )
    selection = p["payload"]["search_selection"]["search_keywords"]
    assert selection == {
        "available": True,
        "rule": "highest_observed_cost",
        "included": 15,
        "omitted": 5,
    }
    rows = [f for f in p["payload"]["facts"] if f["kind"] == "search_keywords"]
    assert rows[0]["cost"] == "20.00" and rows[-1]["cost"] == "6.00"
    assert p["payload"]["facts"][0]["cost"]["observed_sum"] == "1.00"


def test_exactly_one_generation_call_and_all_schema_ids_are_real():
    p = prepared()
    provider = FakeProvider()
    result = interpret_one_off(p, provider)
    assert len(provider.calls) == 1
    schema = provider.calls[0].output_schema
    allowed = schema["properties"]["findings"]["items"]["properties"]["fact_ids"]["items"]["enum"]
    assert allowed == [f["fact_id"] for f in p["payload"]["facts"]]
    assert result["model"]["provider"] == "test-double"
    assert result["model"]["input_tokens"] is result["model"]["estimated_cost_usd"] is None
    assert result["model"]["duration_seconds"] >= 0
    assert result["payload_sha256"] == p["payload_sha256"]


def test_mutated_payload_and_truncated_response_fail_without_retry():
    p = prepared()
    p["payload"]["currency"] = "USD"
    provider = FakeProvider()
    with pytest.raises(InputError, match="model_payload_changed"):
        interpret_one_off(p, provider)
    assert not provider.calls
    provider = FakeProvider(finish_reason="length")
    with pytest.raises(InputError, match="model_output_truncated"):
        interpret_one_off(prepared(), provider)
    assert len(provider.calls) == 1


@pytest.mark.parametrize(
    "change,code",
    [
        ("unknown_reference", "unknown_model_fact_reference"),
        ("extra_field", "invalid_model_response"),
        ("bad_priority", "invalid_model_response"),
    ],
)
def test_model_prose_and_references_are_validated(change, code):
    r = response()
    if change == "unknown_reference":
        r["findings"][0]["fact_ids"] = ["F999"]
    if change == "extra_field":
        r["shell"] = "arbitrary command"
    if change == "bad_priority":
        r["recommendations"][0]["priority"] = "execute"
    with pytest.raises(InputError, match=code):
        validate_interpretation(json.dumps(r).encode(), {"F001"})


def test_bad_json_and_size_limits_have_safe_errors(monkeypatch):
    with pytest.raises(InputError, match="invalid_model_response"):
        validate_interpretation(b"not-json", {"F001"})
    monkeypatch.setattr("paw.application.google_ads_interpretation.MAX_MODEL_RESPONSE_BYTES", 1)
    with pytest.raises(InputError, match="model_response_too_large"):
        validate_interpretation(json.dumps(response()).encode(), {"F001"})
    monkeypatch.setattr("paw.application.google_ads_interpretation.MAX_MODEL_INPUT_BYTES", 1)
    with pytest.raises(InputError, match="model_input_too_large"):
        prepared()


def test_ambiguous_sources_do_not_trigger_a_model_call():
    a = source()
    b = GoogleAdsCsvSource("copy.csv", a.report_type, a.data.replace(b"100", b"200"))
    with pytest.raises(InputError, match="one_off_campaign_source_required"):
        prepare_one_off_analysis(SPEC, (a, b), BusinessContext())


def test_renderer_escapes_model_markup_and_renders_program_supplied_facts():
    r = response()
    r["title"] = "<script>alert</script> [link](https://invalid.example)"
    provider = FakeProvider(json.dumps(r).encode())
    result = interpret_one_off(prepared(), provider)
    markdown = render_one_off_report(result)
    assert "<script>" not in markdown and "\\[link\\]" in markdown
    assert "[F001](#f001)" in markdown and '"observed_sum": 100' in markdown


def test_numeric_prose_is_preserved_but_not_claimed_as_semantically_verified():
    value = response()
    value["summary"] = "Observed impressions are 100."
    report = interpret_one_off(prepared(), FakeProvider(json.dumps(value).encode()))
    assert report["interpretation"]["summary"] == value["summary"]
    assert report["validation"]["semantic_and_numeric_claims"] == "not_automatically_verified"


def test_changed_installed_model_digest_is_rejected_before_generation():
    mock, calls = transport()

    def handle(req):
        if req.url.path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": "ministral-3:3b", "digest": "b" * 64}]}
            )
        return mock.handle_request(req)

    with pytest.raises(InputError, match="local_model_digest_mismatch"):
        OllamaProvider(transport=httpx.MockTransport(handle)).interpret(request())
    assert not any(r.url.path == "/api/chat" for r in calls)


def request():
    return InterpretationRequest("instructions", b"{}", interpretation_schema(), 1800)


def transport(*, status=200, done_reason="stop", installed=True):
    calls = []

    def handle(req):
        calls.append(req)
        if req.url.path == "/api/version":
            return httpx.Response(200, json={"version": "test-runtime"})
        if req.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [{"name": "ministral-3:3b", "digest": MODEL_DIGEST}]
                    if installed
                    else []
                },
            )
        return httpx.Response(
            status,
            json={
                "model": "ministral-3:3b",
                "done": True,
                "done_reason": done_reason,
                "message": {"role": "assistant", "content": json.dumps(response())},
                "prompt_eval_count": 123,
                "eval_count": 45,
            },
        )

    return httpx.MockTransport(handle), calls


def test_local_adapter_uses_schema_no_cloud_no_tools_and_records_real_metadata():
    mock, calls = transport()
    provider = OllamaProvider(transport=mock)
    result = provider.interpret(request())
    assert len(calls) == 3 and sum(r.url.path == "/api/chat" for r in calls) == 1
    body = json.loads(calls[-1].content)
    assert body["model"] == "ministral-3:3b" and body["stream"] is False
    assert "think" not in body and "tools" not in body and body["keep_alive"] == 0
    assert body["format"]["type"] == "object" and body["options"]["temperature"] == 0
    assert result.input_tokens == 123 and result.output_tokens == 45
    assert result.model_digest == MODEL_DIGEST and result.runtime_version == "test-runtime"


@pytest.mark.parametrize(
    "url",
    [
        "https://api.example.com",
        "http://127.0.0.1.evil.example",
        "http://user:password@127.0.0.1:11434",
        "http://127.0.0.1:11434/path",
        "http://127.0.0.1:11434?redirect=remote",
    ],
)
def test_remote_urls_are_rejected_before_network(url):
    with pytest.raises(InputError, match="local_model_url_required"):
        OllamaProvider(base_url=url)


def test_only_the_chosen_local_model_is_allowlisted():
    with pytest.raises(InputError, match="unsupported_local_model"):
        OllamaProvider(model="cloud-model")
    mock, calls = transport(installed=False)
    with pytest.raises(InputError, match="local_model_not_installed"):
        OllamaProvider(transport=mock).interpret(request())
    assert not any(r.url.path == "/api/chat" for r in calls)


def test_http_errors_and_timeouts_do_not_retry_or_expose_response_text():
    mock, calls = transport(status=500)
    with pytest.raises(InputError, match="local_model_http_error"):
        OllamaProvider(transport=mock).interpret(request())
    assert sum(r.url.path == "/api/chat" for r in calls) == 1

    def timeout(req):
        raise httpx.ReadTimeout("private source body", request=req)

    with pytest.raises(InputError) as error:
        OllamaProvider(transport=httpx.MockTransport(timeout)).interpret(request())
    assert str(error.value) == "local_model_timeout"


def test_redirect_is_not_followed_and_responses_are_bounded(monkeypatch):
    calls = []

    def redirect(req):
        calls.append(req)
        return httpx.Response(307, headers={"location": "https://remote.example"})

    with pytest.raises(InputError, match="local_model_http_error"):
        OllamaProvider(transport=httpx.MockTransport(redirect)).interpret(request())
    assert len(calls) == 1
    mock, _ = transport()
    monkeypatch.setattr("paw.infrastructure.llm.ollama.MAX_OLLAMA_RESPONSE_BYTES", 1)
    with pytest.raises(InputError, match="local_model_response_too_large"):
        OllamaProvider(transport=mock).interpret(request())
