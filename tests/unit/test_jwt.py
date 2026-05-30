import time
from uuid import uuid4

import jwt
import pytest

from agentstack.config import settings
from agentstack.services.jwt_service import (
    InvalidTokenError,
    decode_access_token,
    issue_access_token,
)


@pytest.mark.unit
def test_issue_and_decode_roundtrip():
    user_id = uuid4()
    token, expires_in = issue_access_token(
        user_id=user_id, email="user@example.com", is_admin=False
    )
    claims = decode_access_token(token)
    assert claims.user_id == user_id
    assert claims.email == "user@example.com"
    assert claims.is_admin is False
    assert expires_in == settings.jwt_access_ttl_minutes * 60


@pytest.mark.unit
def test_decode_rejects_tampered_signature():
    token, _ = issue_access_token(user_id=uuid4(), email="x@y.com")
    forged = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(InvalidTokenError):
        decode_access_token(forged)


@pytest.mark.unit
def test_decode_rejects_expired_token():
    past = int(time.time()) - 3600
    payload = {
        "sub": str(uuid4()),
        "email": "x@y.com",
        "is_admin": False,
        "iat": past - 60,
        "exp": past,
        "iss": settings.jwt_issuer,
    }
    expired = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    with pytest.raises(InvalidTokenError):
        decode_access_token(expired)


@pytest.mark.unit
def test_decode_rejects_wrong_issuer():
    payload = {
        "sub": str(uuid4()),
        "email": "x@y.com",
        "is_admin": False,
        "iat": int(time.time()),
        "exp": int(time.time()) + 60,
        "iss": "not-agentstack",
    }
    bad = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    with pytest.raises(InvalidTokenError):
        decode_access_token(bad)
