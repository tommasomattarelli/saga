from uuid import UUID

from pydantic import JsonValue


class ActionError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 409,
        result_turn_id: UUID | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.detail: dict[str, JsonValue] = {"code": code, "message": message}
        if code == "action_context_changed":
            self.detail["refresh_required"] = True
        if result_turn_id is not None:
            self.detail["result_turn_id"] = str(result_turn_id)


def context_changed(result_turn_id: UUID | None = None) -> ActionError:
    return ActionError(
        "action_context_changed",
        "The campaign history changed; refresh before acting again.",
        result_turn_id=result_turn_id,
    )
