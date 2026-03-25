"""AI-specific exceptions."""

from app.exceptions import SagaError


class ContentPolicyError(SagaError):
    """Raised when an AI provider refuses to generate content due to policy."""

    def __init__(self, provider: str, detail: str = "") -> None:
        msg = f"Content policy violation from '{provider}'"
        if detail:
            msg += f": {detail}"
        super().__init__(msg, status_code=422)
        self.provider = provider
