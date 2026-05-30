from fastapi import HTTPException, status


class AppError(HTTPException):
    code: str = "app_error"

    def __init__(
        self,
        message: str,
        *,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=message)
        self.message = message
        self.details = details or {}


class NotFoundError(AppError):
    code = "not_found"

    def __init__(self, message: str = "Resource not found", **kwargs):
        super().__init__(message, status_code=status.HTTP_404_NOT_FOUND, **kwargs)


class ConflictError(AppError):
    code = "conflict"

    def __init__(self, message: str = "Conflict", **kwargs):
        super().__init__(message, status_code=status.HTTP_409_CONFLICT, **kwargs)


class UnauthorizedError(AppError):
    code = "unauthorized"

    def __init__(self, message: str = "Unauthorized", **kwargs):
        super().__init__(message, status_code=status.HTTP_401_UNAUTHORIZED, **kwargs)


class RateLimitedError(AppError):
    code = "rate_limited"

    def __init__(self, message: str = "Rate limit exceeded", **kwargs):
        super().__init__(message, status_code=status.HTTP_429_TOO_MANY_REQUESTS, **kwargs)


class ValidationError(AppError):
    code = "validation_error"

    def __init__(self, message: str = "Validation failed", **kwargs):
        super().__init__(message, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, **kwargs)


class PayloadTooLargeError(AppError):
    code = "payload_too_large"

    def __init__(self, message: str = "Payload too large", **kwargs):
        super().__init__(message, status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, **kwargs)
