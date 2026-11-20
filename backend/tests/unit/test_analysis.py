import json
from hashlib import sha256

import pytest

from paw.domain.analysis import AnalysisFailure, AnalysisSpec, Ratio
from paw.tools.csv_analysis import analyze

CSV = b"campaign,impressions,clicks,cost\nSearch,1000,50,25\nSocial,2000,60,18\nSearch,500,20,10\n"
SPEC = AnalysisSpec(
    ("impressions", "clicks", "cost"),
    "cost",
    "campaign",
    (Ratio("CTR", "clicks", "impressions", 100), Ratio("CPC", "cost", "clicks")),
)


def report(data=CSV, spec=SPEC):
    bundle = analyze(data, ",", spec, sha256(data).hexdigest())
    assert bundle.chart.startswith(b"\x89PNG\r\n\x1a\n")
    return json.loads(bundle.report)


def test_campaign_statistics_are_ratio_of_sums():
    result = report()
    assert result["summary"]["impressions"]["sum"] == 3500
    assert result["summary"]["clicks"]["sum"] == 130
    assert result["summary"]["cost"]["sum"] == 53
    assert result["summary"]["cost"]["median"] == 18
    search, social = result["groups"]
    assert search["group"] == "Search" and search["sums"]["cost"] == 35
    assert search["ratios"]["CTR"]["value"] == pytest.approx(70 / 1500 * 100)
    assert search["ratios"]["CPC"]["value"] == 0.5
    assert social["ratios"]["CPC"]["value"] == 0.3


def test_missing_group_and_all_missing_numeric_zero_denominator():
    data = b"g,a,b\nx,,0\nx, ,0\n,5,0\n"
    result = report(data, AnalysisSpec(("a", "b"), "a", "g", (Ratio("r", "a", "b"),)))
    assert result["summary"]["a"]["missing"] == 2
    assert len(result["groups"]) == 2
    x = next(g for g in result["groups"] if g["group"] == "x")
    assert x["sums"]["a"] is None
    assert x["ratios"]["r"]["value"] is None
    missing = next(g for g in result["groups"] if g["group"] is None)
    assert missing["ratios"]["r"]["value"] is None
    assert missing["ratios"]["r"]["paired_rows"] == 1


def test_ratios_use_paired_rows_instead_of_mismatched_sums():
    result = report(
        b"a,b\n10,2\n100,\n,1000\n", AnalysisSpec(("a", "b"), "a", ratios=(Ratio("r", "a", "b"),))
    )
    r = result["groups"][0]["ratios"]["r"]
    assert r["value"] == 5 and r["paired_rows"] == 1 and r["excluded_rows"] == 2


@pytest.mark.parametrize("value", ["oops", "NaN", "Infinity", "1e100", "=1+2"])
def test_invalid_numeric_is_not_silently_dropped(value):
    data = f"a\n{value}\n".encode()
    with pytest.raises(AnalysisFailure):
        report(data, AnalysisSpec(("a",), "a"))


def test_source_hash_and_missing_columns_fail():
    with pytest.raises(AnalysisFailure, match="source_changed"):
        analyze(CSV, ",", SPEC, "0" * 64)
    with pytest.raises(AnalysisFailure, match="unknown_column"):
        report(CSV, AnalysisSpec(("absent",), "absent"))


def test_semicolon_bom_and_literal_markup_group_are_data():
    data = "\ufeffg;a\n<script>alert(1)</script>;2\n".encode()
    bundle = analyze(data, ";", AnalysisSpec(("a",), "a", "g"), sha256(data).hexdigest())
    assert json.loads(bundle.report)["groups"][0]["group"] == "<script>alert(1)</script>"
    assert bundle.chart.startswith(b"\x89PNG")


def test_group_limit_and_chart_truncation_are_explicit():
    data = ("g,a\n" + "".join(f"group{i:03},1\n" for i in range(31))).encode()
    result = report(data, AnalysisSpec(("a",), "a", "g"))
    assert len(result["groups"]) == 31 and result["chart"]["groups_shown"] == 30
    data = ("g,a\n" + "".join(f"g{i},1\n" for i in range(101))).encode()
    with pytest.raises(AnalysisFailure, match="too_many_groups"):
        report(data, AnalysisSpec(("a",), "a", "g"))
