"""Build a local CSV batch JSON; no network, API writes or AI processing."""

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from paw.application.google_ads import MAX_BATCH_SOURCES, build_google_ads_batch
from paw.domain.files import MAX_FILE_BYTES, InputError
from paw.domain.google_ads import GoogleAdsBatchSpec, GoogleAdsCsvSource, ReportType

KINDS = {"campaign_summary", "campaign_daily", "search_keywords", "search_terms"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-ref", required=True, help="Local owner-asserted account label")
    parser.add_argument("--period-start", required=True, type=date.fromisoformat)
    parser.add_argument("--period-end", required=True, type=date.fromisoformat)
    parser.add_argument("--batch-id", type=UUID, default=None)
    parser.add_argument("--source", action="append", required=True, metavar="TYPE=CSV_PATH")
    parser.add_argument("--delimiter", choices=(",", ";"), default=",")
    parser.add_argument(
        "--output", required=True, type=Path, help="New output file; never overwritten"
    )
    args = parser.parse_args()
    try:
        if len(args.source) > MAX_BATCH_SOURCES:
            raise InputError("invalid_source_count")
        sources = []
        for item in args.source:
            kind, sep, path = item.partition("=")
            if not sep or kind not in KINDS or not path:
                raise InputError("invalid_source_argument")
            source_path = Path(path)
            with source_path.open("rb") as stream:
                data = stream.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES:
                raise InputError("file_too_large")
            sources.append(
                GoogleAdsCsvSource(source_path.name, cast(ReportType, kind), data, args.delimiter)
            )
        spec = GoogleAdsBatchSpec(
            args.batch_id or uuid4(),
            args.account_ref,
            args.period_start,
            args.period_end,
        )
        result = build_google_ads_batch(spec, tuple(sources))
        with args.output.open("xb") as output:
            output.write(result)
    except InputError as error:
        print(f"Failed: {error.code}", file=sys.stderr)
        return 1
    except FileExistsError:
        print("Failed: output_exists", file=sys.stderr)
        return 1
    except OSError:
        print("Failed: local_file_error", file=sys.stderr)
        return 1
    print(f"Created JSON batch: {len(sources)} reports, {len(result)} bytes; no AI call.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
