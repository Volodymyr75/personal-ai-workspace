"""Fixed calculations; no eval, generated code, formulas or network access."""

import csv
import io
import json
import math
from hashlib import sha256
from typing import Any, TypedDict

import pandas as pd
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from paw.domain.analysis import MAX_ARTIFACT_BYTES, AnalysisFailure, AnalysisSpec, Bundle
from paw.domain.files import inspect_csv


class Group(TypedDict):
    group: str | None
    rows: int
    sums: dict[str, float | None]
    ratios: dict[str, dict[str, float | int | bool | None]]


def finite(value: Any) -> float | None:
    if pd.isna(value):
        return None
    result = float(value)
    if not math.isfinite(result):
        raise AnalysisFailure("numeric_overflow")
    return result


def analyze(data: bytes, delimiter: str, spec: AnalysisSpec, source_sha256: str) -> Bundle:
    if sha256(data).hexdigest() != source_sha256:
        raise AnalysisFailure("source_changed")
    info = inspect_csv(data, delimiter)
    rows = list(
        csv.reader(
            io.StringIO(data.decode("utf-8-sig"), newline=""), delimiter=delimiter, strict=True
        )
    )
    columns = rows[0]
    frame = pd.DataFrame(rows[1:], columns=columns)
    missing = {c: int(frame[c].str.strip().eq("").sum()) for c in columns}
    wanted = set(spec.numeric_columns) | ({spec.group_by} if spec.group_by else set())
    if not wanted.issubset(columns):
        raise AnalysisFailure("unknown_column")
    numeric = pd.DataFrame(index=frame.index)
    summaries = {}
    for column in spec.numeric_columns:
        cleaned = frame[column].str.strip().replace("", None)
        try:
            values = pd.to_numeric(cleaned, errors="raise").astype("float64")
        except (ValueError, TypeError, OverflowError):
            raise AnalysisFailure("invalid_numeric") from None
        if any(not math.isfinite(float(v)) for v in values.dropna()):
            raise AnalysisFailure("invalid_numeric")
        # Float64 arithmetic is explicit; bound individual magnitudes and serialized outputs.
        if any(abs(float(v)) > 1e15 for v in values.dropna()):
            raise AnalysisFailure("numeric_overflow")
        numeric[column] = values
        summaries[column] = {
            "count": int(values.count()),
            "missing": missing[column],
            "sum": finite(values.sum(min_count=1)),
            "mean": finite(values.mean()),
            "median": finite(values.median()),
            "min": finite(values.min()),
            "max": finite(values.max()),
        }
    if spec.group_by:
        keys = frame[spec.group_by].map(lambda v: v if v.strip() else None)
        groups = list(keys.groupby(keys, dropna=False, sort=True).groups.items())
    else:
        groups = [("All rows", frame.index)]
    if len(groups) > 100:
        raise AnalysisFailure("too_many_groups")
    aggregates: list[Group] = []
    for key, indices in groups:
        subset = numeric.loc[indices]
        sums = {c: finite(subset[c].sum(min_count=1)) for c in spec.numeric_columns}
        ratios: dict[str, dict[str, float | int | bool | None]] = {}
        for ratio in spec.ratios:
            paired = subset[[ratio.numerator, ratio.denominator]].dropna()
            numerator = finite(paired.iloc[:, 0].sum(min_count=1))
            denominator = finite(paired.iloc[:, 1].sum(min_count=1))
            value = (
                None
                if numerator is None or (denominator is None or denominator == 0)
                else finite(numerator / denominator * ratio.scale)
            )
            ratios[ratio.name] = {
                "value": value,
                "paired_rows": len(paired),
                "excluded_rows": len(subset) - len(paired),
                "undefined": value is None,
            }
        aggregates.append(
            {
                "group": None if pd.isna(key) else str(key),
                "rows": len(indices),
                "sums": sums,
                "ratios": ratios,
            }
        )
    # Deterministic order: group labels ascending; display at most 30, disclose truncation.
    plotted = aggregates[:30]
    labels = ["(missing)" if r["group"] is None else r["group"] for r in plotted]
    heights = [r["sums"][spec.chart_column] for r in plotted]
    fig = Figure(figsize=(10, 6), dpi=120, layout="constrained")
    FigureCanvasAgg(fig)
    ax = fig.subplots()
    positions = list(range(len(labels)))
    ax.bar(positions, [0 if v is None else v for v in heights], color="#2563eb")
    ax.set_xticks(positions, [label[:40] for label in labels], rotation=45, ha="right")
    # Disable mathtext interpretation of user-supplied labels.
    for label in ax.get_xticklabels():
        label.set_parse_math(False)
    ax.set_title("Sum by group", parse_math=False)
    ax.set_ylabel(spec.chart_column, parse_math=False)
    for x, value in zip(positions, heights, strict=True):
        if value is None:
            ax.annotate("N/A", (x, 0))
    stream = io.BytesIO()
    fig.savefig(stream, format="png")
    report = {
        "schema_version": 1,
        "title": "Deterministic CSV analysis",
        "source_sha256": info.sha256,
        "row_count": info.row_count,
        "columns": [
            {
                "name": c,
                "missing": missing[c],
                "type": "numeric" if c in spec.numeric_columns else "text",
            }
            for c in columns
        ],
        "summary": summaries,
        "group_by": spec.group_by,
        "groups": aggregates,
        "chart": {
            "column": spec.chart_column,
            "operation": "sum",
            "kind": "bar",
            "groups_shown": len(plotted),
            "groups_total": len(groups),
            "order": "group label ascending; missing group last",
        },
        "limitations": [
            "No AI interpretation. Only selected numeric columns are converted.",
            "Blank or whitespace-only cells are missing; other numeric tokens must parse.",
            "Statistics exclude missing values; all-missing sums and "
            "zero-denominator ratios are null.",
            "Ratios use only rows with both operands present; they are ratios of sums.",
            "Float64 arithmetic; individual magnitudes limited to 1e15. "
            "Not exact financial accounting.",
            "Chart shows the first 30 groups, with labels shortened to 40 characters; "
            "report retains all groups.",
        ],
    }
    encoded = json.dumps(report, allow_nan=False, ensure_ascii=False).encode()
    chart = stream.getvalue()
    if max(len(encoded), len(chart)) > MAX_ARTIFACT_BYTES:
        raise AnalysisFailure("artifact_too_large")
    return Bundle(encoded, chart)
