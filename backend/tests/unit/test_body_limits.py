import asyncio

from paw.api.limits import BodyLimits


def test_chunked_request_is_limited_before_app_without_content_length():
    called = False
    messages = []

    async def app(scope, receive, send):
        nonlocal called
        called = True

    async def receive():
        return {"type": "http.request", "body": b"x" * 40000, "more_body": True}

    async def send(message):
        messages.append(message)

    asyncio.run(
        BodyLimits(app)(
            {"type": "http", "method": "POST", "path": "/api/v1/projects", "headers": []},
            receive,
            send,
        )
    )
    assert not called
    assert messages[0]["status"] == 413


def test_declared_oversize_does_not_read_body():
    async def never(*args):
        raise AssertionError("must reject without reading/parsing body")

    messages = []

    async def send(message):
        messages.append(message)

    asyncio.run(
        BodyLimits(never)(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/files",
                "headers": [(b"content-length", b"999999999")],
            },
            never,
            send,
        )
    )
    assert messages[0]["status"] == 413
