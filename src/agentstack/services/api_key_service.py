"""Issue, hash, and revoke API keys. Keys are owned by a user."""

from __future__ import annotations

import hashlib
import secrets
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentstack.models.api_key import ApiKey


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_raw_key(prefix: str = "ask") -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


async def create_api_key(
    db: AsyncSession,
    *,
    user_id: UUID,
    name: str,
    rate_limit_per_minute: int = 60,
    rate_limit_per_day: int = 10_000,
) -> tuple[ApiKey, str]:
    raw = generate_raw_key()
    key_hash = hash_api_key(raw)
    record = ApiKey(
        user_id=user_id,
        name=name,
        key_hash=key_hash,
        key_prefix=raw[:8],
        rate_limit_per_minute=rate_limit_per_minute,
        rate_limit_per_day=rate_limit_per_day,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record, raw


async def revoke_api_key(db: AsyncSession, *, key_id: UUID, user_id: UUID) -> bool:
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        return False
    record.is_active = False
    await db.commit()
    return True


async def list_api_keys(db: AsyncSession, *, user_id: UUID) -> list[ApiKey]:
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user_id).order_by(ApiKey.created_at.desc())
    )
    return list(result.scalars().all())
