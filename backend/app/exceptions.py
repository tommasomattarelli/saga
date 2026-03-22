class SagaError(Exception):
    def __init__(self, message: str = "An error occurred", status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class NotFoundError(SagaError):
    def __init__(self, resource: str = "Resource") -> None:
        super().__init__(f"{resource} not found", status_code=404)


class UnauthorizedError(SagaError):
    def __init__(self, message: str = "Not authenticated") -> None:
        super().__init__(message, status_code=401)


class ForbiddenError(SagaError):
    def __init__(self, message: str = "Permission denied") -> None:
        super().__init__(message, status_code=403)


class ConflictError(SagaError):
    def __init__(self, message: str = "Resource already exists") -> None:
        super().__init__(message, status_code=409)


class AIProviderError(SagaError):
    def __init__(self, provider: str, message: str) -> None:
        super().__init__(f"AI provider '{provider}' error: {message}", status_code=502)


class ValidationError(SagaError):
    def __init__(self, message: str = "Validation error") -> None:
        super().__init__(message, status_code=422)
