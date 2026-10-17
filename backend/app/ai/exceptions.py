"""AI-specific exceptions."""

import openai
from google.genai.errors import APIError as GoogleAPIError

from app.exceptions import SagaError

PROVIDER_SDK_ERRORS = (openai.APIError, GoogleAPIError)


def provider_failure_message(error: openai.APIError | GoogleAPIError) -> str:
    status = 0
    if isinstance(error, openai.APIStatusError):
        status = error.status_code
    elif isinstance(error, GoogleAPIError):
        status = error.code
    return {
        401: "The provider rejected your API key; update it in settings.",
        403: "The provider denied access; check your API key and model.",
        404: "The requested model is unavailable; check it in settings.",
        429: "The provider rate limit or quota was exceeded; check your account or try later.",
        503: "The provider is temporarily unavailable; try again later.",
    }.get(status, "The provider request failed; check your settings or try again later.")


class ContentPolicyError(SagaError):
    """Raised when an AI provider refuses to generate content due to policy."""

    def __init__(self, provider: str, detail: str = "") -> None:
        msg = f"Content policy violation from '{provider}'"
        if detail:
            msg += f": {detail}"
        super().__init__(msg, status_code=422)
        self.provider = provider
