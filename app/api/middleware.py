"""Pure-ASGI middleware (streaming-safe): request IDs, access logging, request body size limit."""

from __future__ import annotations

import json
import re
import time
import uuid

from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import get_logger, request_id_var

logger = get_logger("app.access")
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9\-_.]{8,64}$")


class _BodyTooLarge(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=413, detail="Request body is too large.")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, *, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        incoming = headers.get("x-request-id", "")
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        status = {"code": 500}
        response_started = {"value": False}

        declared = headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > self.max_body_bytes:
            await self._reject(send, request_id)
            self._log(scope, 413, start)
            request_id_var.reset(token)
            return

        received = {"bytes": 0}

        async def limited_receive() -> Message:
            message = await receive()
            if message["type"] == "http.request":
                received["bytes"] += len(message.get("body", b""))
                if received["bytes"] > self.max_body_bytes:
                    raise _BodyTooLarge
            return message

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_started["value"] = True
                status["code"] = message["status"]
                message.setdefault("headers", [])
                message["headers"].append((b"x-request-id", request_id.encode()))
            await send(message)

        try:
            await self.app(scope, limited_receive, send_with_id)
        except _BodyTooLarge:
            if not response_started["value"]:
                await self._reject(send, request_id)
            status["code"] = 413
        finally:
            self._log(scope, status["code"], start)
            request_id_var.reset(token)

    @staticmethod
    async def _reject(send: Send, request_id: str) -> None:
        body = json.dumps({"error": {"code": "payload_too_large", "message": "Request body is too large.",
                                     "request_id": request_id}}).encode()
        await send({"type": "http.response.start", "status": 413, "headers": [
            (b"content-type", b"application/json"), (b"x-request-id", request_id.encode()),
            (b"content-length", str(len(body)).encode()),
        ]})
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    def _log(scope: Scope, status: int, start: float) -> None:
        logger.info("request", extra={
            "method": scope.get("method"), "endpoint": scope.get("path"), "status": status,
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
        })
