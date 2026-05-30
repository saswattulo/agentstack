from fastapi import APIRouter, status

from agentstack.api.deps import CurrentUserDep, DbSession
from agentstack.schemas.user import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyRead,
    TokenResponse,
    UserLogin,
    UserRead,
    UserRegister,
)
from agentstack.services import api_key_service, user_service
from agentstack.services.jwt_service import issue_access_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserRegister, db: DbSession) -> TokenResponse:
    user = await user_service.register_user(
        db,
        email=payload.email,
        password=payload.password,
        name=payload.name,
    )
    token, expires_in = issue_access_token(
        user_id=user.id, email=user.email, is_admin=user.is_admin
    )
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserRead.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin, db: DbSession) -> TokenResponse:
    user = await user_service.authenticate(db, email=payload.email, password=payload.password)
    token, expires_in = issue_access_token(
        user_id=user.id, email=user.email, is_admin=user.is_admin
    )
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserRead.model_validate(user),
    )


@router.get("/me", response_model=UserRead)
async def me(current: CurrentUserDep, db: DbSession) -> UserRead:
    user = await user_service.get_user(db, current.id)
    if user is None:
        from agentstack.api.errors import UnauthorizedError

        raise UnauthorizedError("User no longer exists")
    return UserRead.model_validate(user)


@router.get("/api-keys", response_model=list[ApiKeyRead])
async def list_keys(current: CurrentUserDep, db: DbSession) -> list[ApiKeyRead]:
    keys = await api_key_service.list_api_keys(db, user_id=current.id)
    return [ApiKeyRead.model_validate(k) for k in keys]


@router.post(
    "/api-keys",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_key(
    payload: ApiKeyCreate, current: CurrentUserDep, db: DbSession
) -> ApiKeyCreated:
    record, raw = await api_key_service.create_api_key(
        db,
        user_id=current.id,
        name=payload.name,
        rate_limit_per_minute=payload.rate_limit_per_minute,
        rate_limit_per_day=payload.rate_limit_per_day,
    )
    return ApiKeyCreated(
        id=record.id,
        name=record.name,
        key_prefix=record.key_prefix,
        is_active=record.is_active,
        rate_limit_per_minute=record.rate_limit_per_minute,
        rate_limit_per_day=record.rate_limit_per_day,
        last_used_at=record.last_used_at,
        created_at=record.created_at,
        raw_key=raw,
    )


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_key(key_id, current: CurrentUserDep, db: DbSession) -> None:
    ok = await api_key_service.revoke_api_key(db, key_id=key_id, user_id=current.id)
    if not ok:
        from agentstack.api.errors import NotFoundError

        raise NotFoundError("API key not found")
