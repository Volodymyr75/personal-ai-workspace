"""Build keyword/query evidence from explicitly selected batch sources; no AI calls."""

import argparse
import sys
from datetime import date
from pathlib import Path

from paw.application.google_ads import MAX_BATCH_JSON_BYTES
from paw.application.google_ads_search_evidence import build_search_evidence
from paw.domain.files import InputError
from paw.domain.google_ads_evidence import SearchEvidenceSpec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--keyword-source-id")
    parser.add_argument("--search-term-source-id")
    parser.add_argument("--period-start", required=True, type=date.fromisoformat)
    parser.add_argument("--period-end", required=True, type=date.fromisoformat)
    parser.add_argument(
        "--output", required=True, type=Path, help="New output file; never overwritten"
    )
    args = parser.parse_args()
    try:
        with args.input.open("rb") as source:
            data = source.read(MAX_BATCH_JSON_BYTES + 1)
        spec = SearchEvidenceSpec(
            args.period_start, args.period_end, args.keyword_source_id, args.search_term_source_id
        )
        result = build_search_evidence(data, spec)
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
    print(f"Created search evidence: {len(result)} bytes; no AI call.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
