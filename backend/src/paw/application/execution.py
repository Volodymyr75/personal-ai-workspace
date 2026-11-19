"""Bounded diagnostic executor. Not an AI agent or arbitrary task runner."""

import logging
from threading import Event
from time import monotonic

from paw.domain.runs import HEARTBEAT_SECONDS, Run, RunRepository

logger = logging.getLogger("paw")


def execute_diagnostic(repo: RunRepository, run: Run, stop: Event) -> bool:
    if run.attempt_id is None or run.task_type != "diagnostic":
        raise ValueError("Unsupported execution")
    context = {"run_id": str(run.id), "attempt_id": str(run.attempt_id)}
    if run.correlation_id is not None:
        context["correlation_id"] = str(run.correlation_id)
    logger.info("run_started", extra=context)
    deadline = monotonic() + run.delay_seconds
    while True:
        if stop.is_set():
            # Do not mark success or release ownership prematurely. Lease recovery owns retry.
            return False
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        if stop.wait(min(HEARTBEAT_SECONDS, remaining)):
            return False
        if not repo.heartbeat(run.id, run.attempt_id):
            logger.warning("run_lease_lost", extra=context)
            return False
    saved = repo.finish(
        run.id, run.attempt_id, "diagnostic_failed" if run.outcome == "failure" else None
    )
    logger.info("run_finished" if saved else "run_lease_lost", extra=context)
    return saved
