from __future__ import annotations


class RequestSizeLimitMiddleware:
    """ASGI request-body limiter that also covers chunked uploads."""
    def __init__(self, app, max_bytes: int = 12 * 1024 * 1024):
        self.app = app
        self.max_bytes = int(max_bytes)

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        total = 0
        started = False

        async def limited_receive():
            nonlocal total
            message = await receive()
            if message.get("type") == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_bytes:
                    raise _BodyTooLarge()
            return message

        async def tracked_send(message):
            nonlocal started
            if message.get("type") == "http.response.start":
                started = True
            await send(message)

        try:
            return await self.app(scope, limited_receive, tracked_send)
        except _BodyTooLarge:
            if not started:
                await send({
                    "type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json; charset=utf-8")],
                })
                await send({
                    "type": "http.response.body",
                    "body": '{"detail":"حجم الطلب أكبر من الحد المسموح"}'.encode("utf-8"),
                })


class _BodyTooLarge(Exception):
    pass
