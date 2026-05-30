"""Register and authenticate users."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentstack.api.errors import ConflictError, UnauthorizedError
from agentstack.models.user import User
from agentstack.services.password import hash_password, needs_rehash, verify_password


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def get_user(db: AsyncSession, user_id: UUID) -> User | None:
    return await db.get(User, user_id)


async def register_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    name: str | None = None,
    is_admin: bool = False,
) -> User:
    user = User(
        email=email.lower(),
        name=name,
        password_hash=hash_password(password),
        is_admin=is_admin,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ConflictError(f"Email already registered: {email}") from e
    await db.refresh(user)
    return user


async def authenticate(db: AsyncSession, *, email: str, password: str) -> User:
    user = await get_user_by_email(db, email)
    if user is None or not user.is_active:
        raise UnauthorizedError("Invalid email or password")
    if not verify_password(password, user.password_hash):
        raise UnauthorizedError("Invalid email or password")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        await db.commit()
    return user
