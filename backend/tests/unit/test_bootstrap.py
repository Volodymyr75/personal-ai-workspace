from unittest.mock import Mock

import httpx
import pytest

from paw.application.bootstrap import BootstrapUnavailable, bootstrap
from paw.domain.registry import safe_metadata
from paw.infrastructure.api_probe import HttpApiProbe


def test_no_registration_when_api_verification_fails():
    api, database, registry = Mock(), Mock(), Mock()
    api.verify.side_effect = BootstrapUnavailable()
    with pytest.raises(BootstrapUnavailable):
        bootstrap(api, database, registry)
    database.is_ready.assert_not_called()
    registry.bootstrap.assert_not_called()


def test_no_registration_when_database_is_unavailable():
    api, database, registry = Mock(), Mock(), Mock()
    database.is_ready.return_value = False
    with pytest.raises(BootstrapUnavailable):
        bootstrap(api, database, registry)
    registry.bootstrap.assert_not_called()


@pytest.mark.parametrize(
    "metadata",
    [
        {"token": "private-test-marker"},
        {"runtime": "private-test-marker"},
        {"runtime": "python", "hostname": "private-test-marker"},
    ],
)
def test_metadata_rejects_unknown_keys_and_values_without_echoing(metadata):
    with pytest.raises(ValueError) as error:
        safe_metadata(metadata)
    assert "private-test-marker" not in str(error.value)


@pytest.mark.parametrize(
    "status,body",
    [
        (503, {"status": "ready", "service": "paw-api"}),
        (200, {"status": "ready", "service": "other"}),
        (200, {"status": "not_ready"}),
        (200, []),
    ],
)
def test_bootstrap_rejects_unverified_http_responses(monkeypatch, status, body):
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.get.return_value = httpx.Response(
        status, json=body, request=httpx.Request("GET", "http://api")
    )
    monkeypatch.setattr(httpx, "Client", Mock(return_value=client))
    with pytest.raises(BootstrapUnavailable):
        HttpApiProbe("http://api").verify()
