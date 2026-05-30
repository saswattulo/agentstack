"""First-boot seeding: ensure a dev user exists in dev mode, with the configured
DEV_API_KEY bound to them. Idempotent — safe to run on every startup.
"""

from __future__ import annotations

import secrets

from sqlalchemy import select

from agentstack.config import settings
from agentstack.infra.db import get_sessionmaker
from agentstack.infra.logging import get_logger
from agentstack.models.api_key import ApiKey
from agentstack.models.user import User
from agentstack.services.api_key_service import hash_api_key
from agentstack.services.password import hash_password

logger = get_logger(__name__)


async def ensure_dev_user() -> None:
    if settings.app_env != "dev":
        return

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        result = await session.execute(
            select(User).where(User.email == settings.dev_user_email)
        )
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                email=settings.dev_user_email,
                name="Dev User",
                password_hash=hash_password(secrets.token_urlsafe(32)),
                is_active=True,
                is_admin=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info("seeded dev user", email=user.email, user_id=str(user.id))

        key_hash = hash_api_key(settings.dev_api_key)
        result = await session.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
        api_key = result.scalar_one_or_none()
        if api_key is None:
            api_key = ApiKey(
                user_id=user.id,
                name="dev",
                key_hash=key_hash,
                key_prefix=settings.dev_api_key[:8],
                is_active=True,
            )
            session.add(api_key)
            await session.commit()
            logger.info(
                "seeded dev api key",
                user_id=str(user.id),
                key_prefix=settings.dev_api_key[:8],
            )
        elif api_key.user_id != user.id or not api_key.is_active:
            api_key.user_id = user.id
            api_key.is_active = True
            await session.commit()
            logger.info(
                "rebound dev api key to current dev user",
                user_id=str(user.id),
                key_prefix=settings.dev_api_key[:8],
            )
