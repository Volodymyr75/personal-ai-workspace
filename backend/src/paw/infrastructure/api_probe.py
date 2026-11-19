import httpx

from paw.application.bootstrap import BootstrapUnavailable


class HttpApiProbe:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def verify(self) -> None:
        try:
            with httpx.Client(timeout=5, follow_redirects=False, trust_env=False) as client:
                for endpoint, expected in (("health", "ok"), ("ready", "ready")):
                    response = client.get(f"{self.base_url}/api/v1/{endpoint}")
                    response.raise_for_status()
                    data = response.json()
                    if not isinstance(data, dict) or data.get("service") != "paw-api":
                        raise ValueError("Unexpected service")
                    if data.get("status") != expected:
                        raise ValueError("Unexpected status")
        except (httpx.HTTPError, ValueError) as exc:
            raise BootstrapUnavailable("PAW API verification failed") from exc
