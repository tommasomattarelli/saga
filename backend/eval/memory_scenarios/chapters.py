from dataclasses import dataclass

from pydantic import JsonValue

PLAYER_NAME = "Fixture Adventurer"


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, JsonValue]


@dataclass(frozen=True)
class Chapter:
    key: str
    action: str
    narration: str
    calls: tuple[ToolCall, ...] = ()
    expects: tuple[str, ...] = ()
    npc: str | None = None


def call(tool_name: str, **arguments: JsonValue) -> ToolCall:
    return ToolCall(tool_name, arguments)


CORE_CHAPTERS = (
    Chapter(
        "promise",
        "Fixture Adventurer asks {npc} to hold the sealed key until the last bell.",
        "{npc} accepts Fixture Adventurer's promise and marks the deadline beside the sealed key.",
        (
            call(
                "update_quest",
                quest_id="sealed_key",
                status="active",
                name="Return the sealed key",
                description="Return it before the last bell.",
            ),
        ),
        ("quest:sealed_key:active", "thread:sealed_key:open"),
    ),
    Chapter(
        "clue-belief",
        "Fixture Adventurer reports the ash mark as a possible clue, not a verified fact.",
        "Fixture Adventurer says the ash mark resembles the old ferry sign; this remains an unverified belief.",
        expects=("belief:unverified", "belief:speaker:Fixture Adventurer"),
    ),
    Chapter(
        "rejected-attempt",
        "Try to enter through a place that is not in the world map.",
        "The route cannot be found; the attempt fails without moving the party.",
        (call("move_to", location="__unknown_fixture_location__"),),
        ("move_to:rejected",),
    ),
    Chapter(
        "quiet-check",
        "Test whether the loose stones conceal a safe foothold.",
        "The stones remain undisturbed after the check.",
        (call("request_dice", stat="DEX", check="Balance", difficulty="normal"),),
        ("request_dice:succeeded:no_delta",),
    ),
    Chapter(
        "silent-witness",
        "Ask {npc} whether the ferry passed before dusk.",
        "{npc} gives no answer; no new claim is established.",
        (call("invoke_npc", name="{npc}", context="asked whether the ferry passed before dusk"),),
        ("invoke_npc:silent",),
        "silent",
    ),
    Chapter(
        "quest-completed",
        "Mark the sealed-key obligation complete while checking {npc}'s ledger.",
        "For this interval the ledger records the key as returned.",
        (call("update_quest", quest_id="sealed_key", status="completed"),),
    ),
    Chapter(
        "quest-reopened",
        "Discover the returned key was only a copy and reopen the obligation.",
        "The copy does not fit the lock. The original-key obligation is active again.",
        (call("update_quest", quest_id="sealed_key", status="active"),),
    ),
    Chapter(
        "silent-reask",
        "Ask {npc} again after finding the matching ferry mark.",
        "{npc} remains silent. The earlier clue is still not independently verified.",
        (
            call(
                "invoke_npc",
                name="{npc}",
                context="asked again after finding the matching ferry mark",
            ),
        ),
        ("invoke_npc:silent:no_delta", "belief:unverified"),
        "silent",
    ),
    Chapter(
        "landing-search",
        "Compare the ferry marks with the route noted earlier.",
        "The marks narrow the search to the old landing, but do not identify who left them.",
    ),
    Chapter(
        "deadline",
        "Wait through market closing and ask {npc} for an account.",
        "The deadline has passed; the original key remains missing.",
    ),
    Chapter(
        "ferry-ledger",
        "Check the ferry ledger for a crossing before dusk.",
        "One crossing is listed, but the passenger column is damaged.",
    ),
    Chapter(
        "torn-page",
        "Ask the archivist to preserve the torn ledger page.",
        "The page is set aside for comparison rather than treated as proof.",
    ),
    Chapter(
        "ink-comparison",
        "Compare the ash mark with ink on the ferry ledger.",
        "The pigments differ, weakening the first interpretation of the mark.",
    ),
    Chapter(
        "route-witness",
        "Ask {npc} which landing was open that evening.",
        "{npc}'s account points north, narrowing the route without verifying the ash mark.",
    ),
    Chapter(
        "north-bank",
        "Inspect the north-bank mooring for a key-sized impression.",
        "The worn wood has a narrow impression, but no key is present.",
    ),
    Chapter(
        "impression",
        "Measure the impression against {npc}'s lock.",
        "The width is consistent with the lock, not sufficient to identify a key.",
    ),
    Chapter(
        "false-lead",
        "Check whether the market copy could have opened the lock.",
        "The copy is too shallow; the false lead is ruled out.",
    ),
    Chapter(
        "copy-record",
        "Record who supplied the unusable copy.",
        "The seller's name is entered as a lead, not as proof of theft.",
    ),
    Chapter(
        "seller-account",
        "Ask the seller when the copy was made.",
        "The seller dates it after the ferry crossing, changing the search order.",
    ),
    Chapter(
        "weather-record",
        "Compare the crossing date with the storm register.",
        "The storm register places the crossing after the river rose.",
    ),
    Chapter(
        "washed-path",
        "Inspect the washed path below the landing.",
        "Fresh silt covers the lower steps, but the upper stones are clear.",
    ),
    Chapter(
        "upper-steps",
        "Search the clear upper steps for a dropped metal object.",
        "A broken clasp is found; it is not the sealed key.",
    ),
    Chapter(
        "clasp-owner",
        "Compare the broken clasp with {npc}'s description.",
        "The clasp belongs to a travel case, so it does not resolve the key's route.",
    ),
    Chapter(
        "case-trail",
        "Follow the case marks toward the old storehouse.",
        "The tracks end at the storehouse entrance and continue inside.",
    ),
    Chapter(
        "storehouse",
        "Search the storehouse shelves without disturbing sealed parcels.",
        "A ferry tag is found among open records; sealed parcels remain untouched.",
    ),
    Chapter(
        "tag-date",
        "Read the date on the ferry tag against the deadline.",
        "The tag predates the deadline and supports a narrower search window.",
    ),
    Chapter(
        "keeper-followup",
        "Ask {npc} which key ring was carried that day.",
        "{npc} recalls a spare ring, but cannot place it after the crossing.",
    ),
    Chapter(
        "spare-ring",
        "Search the public lost-property shelf for the spare ring.",
        "The shelf is empty; the inquiry is recorded without claiming recovery.",
    ),
    Chapter(
        "river-level",
        "Check the river-level marks from the crossing date.",
        "The water was high enough to move loose objects downstream.",
    ),
    Chapter(
        "downstream",
        "Trace the bank below the mooring to the stone weir.",
        "Debris collects at the weir; a narrow gap remains beneath its east side.",
    ),
    Chapter(
        "weir-gap",
        "Look through the east-side gap without entering the current.",
        "A metal glint is visible but cannot be reached safely from the bank.",
    ),
    Chapter(
        "safe-reach",
        "Use a hooked pole to draw the metal object from the bank.",
        "The hooked pole draws an oilskin ferry packet clear of the river stones.",
    ),
    Chapter(
        "key-recovery",
        "Open the recovered packet and recover the original key.",
        "The engraved mark matches {npc}'s description; the original key is recovered.",
        expects=("thread:sealed_key:open", "key:recovered"),
    ),
    Chapter(
        "fulfilment",
        "Fixture Adventurer returns the original key and explains how the false copy delayed the search.",
        "{npc} accepts Fixture Adventurer's explanation; the delayed promise is fulfilled.",
        (
            call("update_quest", quest_id="sealed_key", status="completed"),
            call(
                "change_npc_psychology",
                npc="{npc}",
                changes={"trust": 8},
                reason="kept the promise",
            ),
            call(
                "invoke_npc",
                name="{npc}",
                context="the original key is returned and the promise fulfilled",
            ),
        ),
        (
            "quest:sealed_key:completed",
            "thread:sealed_key:closed",
            "npc:trust:+8",
            "invoke_npc:speaking",
        ),
    ),
    Chapter(
        "ring-teeth",
        "Count the engraved cuts on the returned key for the final record.",
        "The key's cuts match {npc}'s earlier description; the record now supports closure.",
        expects=("thread:sealed_key:closed",),
    ),
    Chapter(
        "lock-test",
        "Use the returned key once more to verify the outer lock turns freely.",
        "The lock turns without force, confirming the recovered key resolved the obligation.",
        expects=("thread:sealed_key:closed",),
    ),
    Chapter(
        "last-account",
        "Reconcile the ferry tag, river marks, and {npc}'s deadline.",
        "The evidence and fulfilled promise are filed together; the sealed-key thread is closed.",
        expects=("thread:sealed_key:closed",),
    ),
)
