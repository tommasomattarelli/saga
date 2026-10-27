import copy
import hashlib
import json

from pydantic import ValidationError

from app.ai.tools.dm_tools import get_tool
from app.models.quest import QuestRegistry


class StepProgress:
    def __init__(
        self, world: dict, character: dict, quests: QuestRegistry, seen: list[str]
    ) -> None:
        self.before = copy.deepcopy((world, character, quests))
        self.fingerprints = list(seen)
        self.fresh_playable = False

    def record(self, name: str, args: dict, result: object, *, playable: bool = False) -> None:
        tool = get_tool(name)
        if tool is not None:
            try:
                args = tool(**args).model_dump(mode="json")
            except ValidationError:
                pass
        payload = json.dumps([name, args, result], sort_keys=True, ensure_ascii=False)
        fingerprint = hashlib.sha256(payload.encode()).hexdigest()
        if fingerprint not in self.fingerprints:
            self.fingerprints.append(fingerprint)
            self.fresh_playable |= playable

    def changed(self, world: dict, character: dict, quests: QuestRegistry) -> bool:
        return self.fresh_playable or self.before != (world, character, quests)
