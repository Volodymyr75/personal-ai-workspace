"""Fixed analysis in a terminable child; no DB handles or artifact publication in the child."""

import logging
import multiprocessing
import sys
import warnings
from multiprocessing.connection import Connection
from threading import Event
from time import monotonic

from paw.domain.analysis import AnalysisFailure, AnalysisSpec, SourceReader
from paw.domain.runs import HEARTBEAT_SECONDS, Run, RunRepository

logger = logging.getLogger("paw")
ANALYSIS_SECONDS = 30


def calculate(
    sender: Connection, data: bytes, delimiter: str, spec: AnalysisSpec, sha: str
) -> None:
    try:
        if sys.platform == "linux":
            import resource

            resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
            resource.setrlimit(resource.RLIMIT_CPU, (25, 25))
        warnings.filterwarnings("ignore", category=UserWarning)
        from paw.tools.csv_analysis import analyze

        sender.send(analyze(data, delimiter, spec, sha))
    except AnalysisFailure as exc:
        sender.send(exc.code)
    except Exception:
        sender.send("analysis_failed")
    finally:
        sender.close()


def execute_analysis(repo: RunRepository, source: SourceReader, run: Run, stop: Event) -> bool:
    if run.attempt_id is None or run.file_id is None or run.analysis is None:
        raise ValueError("Analysis input missing")
    context = {"run_id": str(run.id), "attempt_id": str(run.attempt_id)}
    if run.correlation_id:
        context["correlation_id"] = str(run.correlation_id)
    logger.info("analysis_started", extra=context)
    try:
        data, delimiter, sha = source.read(run.file_id)
    except AnalysisFailure as exc:
        return repo.finish(run.id, run.attempt_id, exc.code)
    ctx = multiprocessing.get_context("spawn")
    receiver, sender = ctx.Pipe(duplex=False)
    child = ctx.Process(target=calculate, args=(sender, data, delimiter, run.analysis, sha))
    try:
        child.start()
        sender.close()
        deadline = monotonic() + ANALYSIS_SECONDS
        next_heartbeat = monotonic()
        while not stop.is_set():
            now = monotonic()
            if now >= deadline:
                return repo.finish(run.id, run.attempt_id, "analysis_timeout")
            if now >= next_heartbeat:
                if not repo.heartbeat(run.id, run.attempt_id):
                    return False
                next_heartbeat = monotonic() + HEARTBEAT_SECONDS
            if receiver.poll(0.1):
                try:
                    result = receiver.recv()
                except EOFError:
                    return repo.finish(run.id, run.attempt_id, "analysis_failed")
                if isinstance(result, str):
                    return repo.finish(run.id, run.attempt_id, result)
                return repo.publish(run.id, run.attempt_id, result)
            if not child.is_alive():
                return repo.finish(run.id, run.attempt_id, "analysis_failed")
        return False
    finally:
        sender.close()
        receiver.close()
        if child.pid is not None:
            if child.is_alive():
                child.terminate()
            child.join(timeout=2)
            if child.is_alive():
                child.kill()
                child.join(timeout=2)
            child.close()
