from typing import Protocol


class Readiness(Protocol):
    def is_ready(self) -> bool: ...


class Registry(Protocol):
    def bootstrap(self) -> int:
        """Register verified foundation definitions atomically; return number of new events."""
        ...


class ApiProbe(Protocol):
    def verify(self) -> None:
        """Raise if the running PAW API cannot prove liveness and readiness."""
        ...
