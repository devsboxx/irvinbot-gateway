from typing import Optional
from jose import JWTError, jwt
from fastapi import HTTPException, status
from app.core.config import settings

# Routes that don't require a JWT
_PUBLIC_ROUTES: set[tuple[str, str]] = {
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/register"),
}


def is_public(method: str, path: str) -> bool:
    return (method.upper(), path) in _PUBLIC_ROUTES


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


def require_auth(authorization: str) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer token")

    token = authorization.removeprefix("Bearer ").strip()
    payload = decode_token(token)

    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    return payload
