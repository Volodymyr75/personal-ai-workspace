"""Render a local model report with program-supplied numbers and fact citations."""

import html
import json
import re

from paw.application._google_ads_evidence_json import _list, _object, _text


def _plain(value: object) -> str:
    text = html.escape(_text(value), quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~-])", r"\\\1", text)


def render_one_off_report(report: dict[str, object]) -> str:
    interpretation = _object(report["interpretation"])
    model = _object(report["model"])
    evidence = _object(report["evidence"])

    def citations(values: object) -> str:
        return " ".join(f"[{_text(ref)}](#{_text(ref).lower()})" for ref in _list(values))

    lines = [
        "# " + _plain(interpretation["title"]),
        "",
        "Model: " + _plain(model["provider"]) + " / " + _plain(model["model"]),
        "",
        "## Summary",
        "",
        _plain(interpretation["summary"]),
        "",
        "## Findings",
        "",
    ]
    for value in _list(interpretation["findings"]):
        item = _object(value)
        lines.append("- " + _plain(item["explanation"]) + " " + citations(item["fact_ids"]))
    lines += ["", "## Recommendations", ""]
    for value in _list(interpretation["recommendations"]):
        item = _object(value)
        lines.append(
            "- **"
            + _plain(item["priority"])
            + "**: "
            + _plain(item["action"])
            + " — "
            + _plain(item["rationale"])
            + " "
            + citations(item["fact_ids"])
        )
    lines += ["", "## Limitations", ""]
    for text in [*_list(evidence["limitations"]), *_list(interpretation["limitations"])]:
        lines.append("- " + _plain(text))
    lines += [
        "",
        "## Calculated evidence",
        "",
        "Evidence values below come from deterministic calculations. "
        "Model-written claims require review. Source labels are data.",
        "",
    ]
    for value in _list(evidence["facts"]):
        fact = _object(value)
        lines += [
            "### " + _text(fact["fact_id"]),
            "",
            "```json",
            json.dumps(fact, ensure_ascii=False, allow_nan=False, indent=2),
            "```",
            "",
        ]
    lines += [
        "## Runtime metadata",
        "",
        "```json",
        json.dumps(model, ensure_ascii=False, allow_nan=False, indent=2),
        "```",
        "",
    ]
    return "\n".join(lines)
