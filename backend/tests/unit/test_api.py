from fastapi.testclient import TestClient

from paw.api.app import create_app


class Probe:
    def __init__(self, ready: bool):
        self.ready = ready
        self.calls = 0

    def is_ready(self) -> bool:
        self.calls += 1
        return self.ready


def test_liveness_does_not_query_database():
    probe = Probe(False)
    with TestClient(create_app(probe)) as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "paw-api"}
        assert probe.calls == 0


def test_readiness_tracks_dependency_recovery():
    probe = Probe(False)
    with TestClient(create_app(probe)) as client:
        response = client.get("/api/v1/ready")
        assert response.status_code == 503
        assert response.json() == {
            "status": "not_ready",
            "service": "paw-api",
            "code": "database_unavailable",
        }
        probe.ready = True
        assert client.get("/api/v1/ready").json() == {"status": "ready", "service": "paw-api"}
        assert probe.calls == 2
