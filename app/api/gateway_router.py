from fastapi import APIRouter, Request, Response
from app.core import security
from app.proxy import proxy

router = APIRouter()

_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH"]


@router.api_route("/{service}/{path:path}", methods=_METHODS)
async def route(service: str, path: str, request: Request) -> Response:
    full_path = f"/api/{service}/{path}"
    extra_headers: dict = {}

    if not security.is_public(request.method, full_path):
        authorization = request.headers.get("authorization", "")
        payload = security.require_auth(authorization)
        extra_headers["X-User-ID"] = payload["sub"]
        extra_headers["X-User-Email"] = payload.get("email", "")
        extra_headers["X-User-Role"] = payload.get("role", "student")

    return await proxy.forward(request, service, path, extra_headers)
