"""Synthetic CSV -> run -> persisted JSON report and PNG, against the local stack."""

import json
import time
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4

BASE = "http://127.0.0.1:8000/api/v1"


def fetch(path, body=None):
    data = None if body is None else json.dumps(body).encode()
    with urlopen(
        Request(BASE + path, data=data, headers={"Content-Type": "application/json"}), timeout=5
    ) as r:
        return r.status, r.read()


def api(path, body=None):
    status, data = fetch(path, body)
    return status, json.loads(data)


def main():
    _, project = api("/projects", {"name": "Synthetic CSV analysis smoke"})
    source = Path(__file__).resolve().parents[1] / "examples/sample_campaigns.csv"
    boundary = "paw-" + uuid4().hex
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            'filename="sample_campaigns.csv"\r\n'
            "Content-Type: text/csv\r\n\r\n"
        ).encode()
        + source.read_bytes()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    req = Request(
        BASE + "/files?project_id=" + project["id"],
        data=body,
        headers={"Content-Type": "multipart/form-data; boundary=" + boundary},
    )
    with urlopen(req, timeout=5) as r:
        assert r.status == 201
        uploaded = json.load(r)
    request = {
        "project_id": project["id"],
        "request_id": str(uuid4()),
        "task_type": "csv_analysis",
        "input": {
            "file_id": uploaded["id"],
            "numeric_columns": ["impressions", "clicks", "cost"],
            "group_by": "campaign",
            "chart_column": "cost",
            "ratios": [
                {"name": "CTR", "numerator": "clicks", "denominator": "impressions", "scale": 100},
                {"name": "CPC", "numerator": "cost", "denominator": "clicks"},
            ],
        },
    }
    status, accepted = api("/runs", request)
    assert status == 202
    path = "/runs/" + accepted["run_id"]
    deadline = time.monotonic() + 50
    while True:
        _, run = api(path)
        if run["status"] in ("completed", "failed"):
            break
        assert time.monotonic() < deadline, "Analysis did not finish"
        time.sleep(0.25)
    assert run["status"] == "completed", run.get("error_code")
    _, report = api("/artifacts/" + run["output"]["report_artifact_id"])
    assert report["summary"]["impressions"]["sum"] == 3500
    assert report["summary"]["clicks"]["sum"] == 130
    assert report["summary"]["cost"]["sum"] == 53
    assert [g["sums"]["cost"] for g in report["groups"]] == [35, 18]
    _, chart = fetch("/artifacts/" + run["output"]["chart_artifact_id"])
    assert chart.startswith(b"\x89PNG\r\n\x1a\n")
    assert api("/runs", request)[1]["run_id"] == run["id"]
    print("PASS: CSV upload, deterministic totals, persisted JSON/PNG and idempotency")
    print("Synthetic run_id=" + run["id"])


if __name__ == "__main__":
    main()
