"""Bound bodies before multipart parsing, even when Content-Length is absent or false."""

import asyncio

import anyio
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from paw.domain.files import MAX_FILE_BYTES


class BodyLimits:
    def __init__(self, app: ASGIApp):
        self.app = app
        self.slots = asyncio.Semaphore(2)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        limit = MAX_FILE_BYTES + 65536 if scope["path"] == "/api/v1/files" else 65536
        headers = dict(scope["headers"])
        try:
            declared = int(headers.get(b"content-length", b"0"))
            if declared < 0:
                raise ValueError()
        except ValueError:
            await JSONResponse({"code": "invalid_request"}, 400)(scope, receive, send)
            return
        if declared > limit:
            await JSONResponse({"code": "request_too_large"}, 413)(scope, receive, send)
            return
        async with self.slots:
            content = bytearray()
            try:
                with anyio.fail_after(30):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        part = message.get("body", b"")
                        if len(content) + len(part) > limit:
                            await JSONResponse({"code": "request_too_large"}, 413)(
                                scope, receive, send
                            )
                            return
                        content.extend(part)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                await JSONResponse({"code": "request_timeout"}, 408)(scope, receive, send)
                return
            delivered = False

            async def replay() -> Message:
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(content), "more_body": False}
                return await receive()

            await self.app(scope, replay, send)
