"""JWT issue/decode. HS256 with the secret from settings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt

from agentstack.config import settings


class InvalidTokenError(Exception):
    pass


@dataclass(frozen=True)
class TokenClaims:
    sub: str
    email: str
    is_admin: bool
    iat: int
    exp: int
    iss: str

    @property
    def user_id(self) -> UUID:
        return UUID(self.sub)


def issue_access_token(*, user_id: UUID, email: str, is_admin: bool = False) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.jwt_access_ttl_minutes)
    payload = {
        "sub": str(user_id),
        "email": email,
        "is_admin": is_admin,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": settings.jwt_issuer,
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, settings.jwt_access_ttl_minutes * 60


def decode_access_token(token: str) -> TokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
    except jwt.ExpiredSignatureError as e:
        raise InvalidTokenError("token expired") from e
    except jwt.InvalidTokenError as e:
        raise InvalidTokenError(str(e)) from e

    return TokenClaims(
        sub=payload["sub"],
        email=payload.get("email", ""),
        is_admin=bool(payload.get("is_admin", False)),
        iat=int(payload["iat"]),
        exp=int(payload["exp"]),
        iss=str(payload["iss"]),
    )
