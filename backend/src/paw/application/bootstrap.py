from paw.domain.ports import ApiProbe, Readiness, Registry


class BootstrapUnavailable(Exception):
    pass


def bootstrap(probe: ApiProbe, database: Readiness, registry: Registry) -> int:
    probe.verify()
    if not database.is_ready():
        raise BootstrapUnavailable("Database is not ready")
    return registry.bootstrap()
