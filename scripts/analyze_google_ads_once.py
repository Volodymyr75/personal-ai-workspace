"""One-off local CSV -> evidence -> Ollama -> cited JSON/Markdown report."""

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from time import monotonic
from typing import cast
from uuid import uuid4

from paw.application.google_ads import MAX_BATCH_SOURCES
from paw.application.google_ads_interpretation import interpret_one_off, prepare_one_off_analysis
from paw.application.google_ads_report import render_one_off_report
from paw.domain.files import MAX_FILE_BYTES, InputError
from paw.domain.google_ads import GoogleAdsBatchSpec, GoogleAdsCsvSource, ReportType
from paw.domain.google_ads_interpretation import (
    BusinessContext,
    InterpretationRequest,
    InterpretationResponse,
)
from paw.infrastructure.llm.ollama import OllamaProvider

KINDS = {"campaign_summary", "campaign_daily", "search_keywords", "search_terms"}


def save(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


class RecordingProvider:
    def __init__(self, provider: OllamaProvider, output: Path):
        self.provider = provider
        self.output = output

    def interpret(self, request: InterpretationRequest) -> InterpretationResponse:
        save(
            self.output / "request.json",
            {
                "instructions": request.instructions,
                "evidence": json.loads(request.evidence_json),
                "output_schema": request.output_schema,
                "max_output_tokens": request.max_output_tokens,
                "call_id": request.call_id,
            },
        )
        started = monotonic()
        response = self.provider.interpret(request)
        duration = monotonic() - started
        with (self.output / "model-response.json").open("xb") as stream:
            stream.write(response.content)
        metadata = asdict(response)
        metadata.pop("content")
        metadata["call_id"] = request.call_id
        metadata["duration_seconds"] = duration
        save(self.output / "response-metadata.json", metadata)
        return response


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-ref", required=True)
    parser.add_argument("--period-start", required=True, type=date.fromisoformat)
    parser.add_argument("--period-end", required=True, type=date.fromisoformat)
    parser.add_argument("--source", required=True, action="append", metavar="TYPE=CSV_PATH")
    parser.add_argument("--delimiter", choices=(",", ";"), default=",")
    parser.add_argument("--service", action="append", default=[])
    parser.add_argument("--geography")
    parser.add_argument("--model", choices=("ministral-3:3b",), default="ministral-3:3b")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--max-output-tokens", type=int, default=1800)
    parser.add_argument("--timeout-seconds", type=float, default=900)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--prepare-only", action="store_true", help="Write the exact input without model invocation"
    )
    args = parser.parse_args()
    output: Path | None = None
    try:
        if not 1 <= len(args.source) <= MAX_BATCH_SOURCES:
            raise InputError("invalid_source_count")
        sources = []
        for value in args.source:
            kind, sep, name = value.partition("=")
            if not sep or kind not in KINDS or not name:
                raise InputError("invalid_source_argument")
            path = Path(name)
            with path.open("rb") as stream:
                data = stream.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES:
                raise InputError("file_too_large")
            sources.append(
                GoogleAdsCsvSource(path.name, cast(ReportType, kind), data, args.delimiter)
            )
        spec = GoogleAdsBatchSpec(uuid4(), args.account_ref, args.period_start, args.period_end)
        prepared = prepare_one_off_analysis(
            spec, tuple(sources), BusinessContext(tuple(args.service), args.geography)
        )
        provider = OllamaProvider(
            base_url=args.ollama_url, model=args.model, timeout_seconds=args.timeout_seconds
        )
        output = args.output_dir or Path("artifacts") / "one-off" / str(spec.batch_id)
        output.mkdir(parents=True, exist_ok=False)
        save(output / "prepared.json", prepared)
        if args.prepare_only:
            print(f"Prepared local evidence: {output}; no model call.")
            return 0
        report = interpret_one_off(
            prepared, RecordingProvider(provider, output), max_output_tokens=args.max_output_tokens
        )
        save(output / "report.json", report)
        with (output / "report.md").open("x", encoding="utf-8") as stream:
            stream.write(render_one_off_report(report))
        print(f"Local model report saved: {output / 'report.md'}")
        return 0
    except InputError as error:
        if output is not None and output.exists() and not (output / "failure.json").exists():
            save(output / "failure.json", {"status": "failed", "code": error.code})
        print(f"Failed: {error.code}", file=sys.stderr)
        return 1
    except FileExistsError:
        print("Failed: output_exists", file=sys.stderr)
        return 1
    except OSError:
        print("Failed: local_file_error", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
