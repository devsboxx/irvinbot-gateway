import httpx
from fastapi import Request, Response, HTTPException
from fastapi.responses import StreamingResponse
from app.core.config import settings

_SKIP_HEADERS = {"host", "content-length", "transfer-encoding", "connection"}

_SERVICE_MAP = {
    "auth": lambda: settings.AUTH_SERVICE_URL + "/auth",
    "chat": lambda: settings.CHAT_SERVICE_URL + "/chat",
    "thesis": lambda: settings.CHAT_SERVICE_URL + "/thesis",
    "docs": lambda: settings.DOCS_SERVICE_URL + "/docs",
}


def _build_target_url(service: str, path: str, query: str) -> str:
    base = _SERVICE_MAP.get(service)
    if not base:
        raise HTTPException(status_code=404, detail=f"Unknown service: '{service}'")
    url = f"{base()}/{path}" if path else base()
    return f"{url}?{query}" if query else url


def _forward_headers(request: Request, extra: dict) -> dict:
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _SKIP_HEADERS}
    headers.update(extra)
    return headers


async def forward(request: Request, service: str, path: str, extra_headers: dict = {}) -> Response:
    target_url = _build_target_url(service, path, str(request.query_params))
    headers = _forward_headers(request, extra_headers)
    body = await request.body()

    if path.endswith("stream"):
        return _stream_response(request.method, target_url, headers, body)

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            upstream = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
            )
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail=f"Service '{service}' unavailable")

    response_headers = {
        k: v for k, v in upstream.headers.items()
        if k.lower() not in {"content-encoding", "transfer-encoding", "connection"}
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
    )


def _stream_response(method: str, url: str, headers: dict, body: bytes) -> StreamingResponse:
    async def generator():
        async with httpx.AsyncClient(timeout=None) as client:
            try:
                async with client.stream(method, url, headers=headers, content=body) as upstream:
                    async for chunk in upstream.aiter_bytes():
                        yield chunk
            except httpx.ConnectError:
                yield b"data: {\"error\": \"upstream unavailable\"}\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream")
