"""Create synthetic diagnostic runs against the local stack; no AI or source files."""

import json
import time
from urllib.request import Request, urlopen
from uuid import uuid4

BASE = "http://127.0.0.1:8000/api/v1"


def request(path, body=None):
    data = None if body is None else json.dumps(body).encode()
    with urlopen(
        Request(BASE + path, data=data, headers={"Content-Type": "application/json"}),
        timeout=5,
    ) as response:
        return response.status, json.load(response)


def main():
    _, project = request("/projects", {"name": "Synthetic execution smoke"})
    for outcome in ("success", "failure"):
        body = {
            "project_id": project["id"],
            "request_id": str(uuid4()),
            "task_type": "diagnostic",
            "input": {"outcome": outcome, "delay_seconds": 0},
        }
        status, accepted = request("/runs", body)
        assert status == 202
        identity = accepted["run_id"]
        assert request("/runs", body)[1]["run_id"] == identity
        deadline = time.monotonic() + 45
        while True:
            _, run = request("/runs/" + identity)
            if run["status"] in ("completed", "failed"):
                break
            assert time.monotonic() < deadline, "Worker did not complete diagnostic run"
            time.sleep(0.25)
        assert run["status"] == ("completed" if outcome == "success" else "failed")
        assert run["error_code"] == (None if outcome == "success" else "diagnostic_failed")
        _, events = request("/runs/" + identity + "/events")
        assert [e["event_type"] for e in events] == [
            "queued",
            "started",
            "completed" if outcome == "success" else "diagnostic_failed",
        ]
    print("PASS: live Worker success, controlled failure, idempotency and execution events")


if __name__ == "__main__":
    main()
