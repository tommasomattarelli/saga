from eval.memory_scenarios.chapters import Chapter, call

EPILOGUE = (
    Chapter(
        "smuggler-warning",
        "Fixture Adventurer records {npc}'s unverified warning about a second ferry manifest.",
        "The note attributes the possible duplicate manifest to {npc}; the sealed-key thread stays closed.",
        (
            call(
                "update_quest",
                quest_id="ferry_manifest",
                status="active",
                name="Trace the altered ferry manifest",
                description="Unverified warning attributed to {npc}: a second manifest may exist.",
            ),
        ),
        ("thread:ferry_manifest:open", "attribution:{npc}"),
    ),
    Chapter(
        "manifest-copy",
        "Compare the public manifest with the copy cited in {npc}'s warning.",
        "Fixture Adventurer finds one extra crossing on the copy; its origin remains unknown.",
        (
            call(
                "update_quest",
                quest_id="ferry_manifest",
                status="active",
                description="A copy lists an extra crossing; origin unverified.",
            ),
        ),
        ("thread:ferry_manifest:open",),
    ),
    Chapter(
        "seal-impression",
        "Inspect the impression beside the extra crossing without assigning an owner.",
        "The impression is incomplete and cannot identify the hand that made it.",
    ),
    Chapter(
        "berth-number",
        "Check the berth number written beside the disputed crossing.",
        "The number matches an unused berth, a discrepancy rather than proof of smuggling.",
    ),
    Chapter(
        "dock-time",
        "Compare the crossing time with {npc}'s dated warning.",
        "The warning predates the listed crossing; its source is attributed to {npc}, not verified.",
        (
            call(
                "update_quest",
                quest_id="ferry_manifest",
                status="active",
                description="Timing discrepancy remains unresolved; warning attributed to {npc}.",
            ),
        ),
        ("thread:ferry_manifest:open", "attribution:{npc}"),
    ),
    Chapter(
        "cargo-mark",
        "Read the cargo mark beside the disputed berth.",
        "The mark is used by several traders and does not identify a smuggler.",
    ),
    Chapter(
        "duplicate-stamp",
        "Compare the copy's stamp with the town archive impression.",
        "The copy's stamp is blurred; the archive cannot confirm whether it is genuine.",
    ),
    Chapter(
        "archive-gap",
        "Record the missing archive interval without filling it with an assumption.",
        "The register skips one page. Fixture Adventurer leaves the gap explicitly unresolved.",
        (
            call(
                "update_quest",
                quest_id="ferry_manifest",
                status="active",
                description="One archive page is missing; no responsible party identified.",
            ),
        ),
        ("thread:ferry_manifest:open",),
    ),
    Chapter(
        "rope-fiber",
        "Compare fibers on the manifest wrapper with the dock ropes.",
        "The fibers are common hemp and cannot tie the wrapper to one vessel.",
    ),
    Chapter(
        "night-watch",
        "Review the night watch intervals around the disputed crossing.",
        "Two watch intervals overlap on paper; neither record names a passenger.",
    ),
    Chapter(
        "passenger-alias",
        "Check whether the extra crossing used an alias in the passenger column.",
        "The handwriting differs, but the name is too damaged to read reliably.",
        (
            call(
                "update_quest",
                quest_id="ferry_manifest",
                status="active",
                description="Passenger alias is illegible; attribution and identity remain unresolved.",
            ),
        ),
        ("thread:ferry_manifest:open",),
    ),
    Chapter(
        "river-route",
        "Compare the disputed crossing with the river level recorded that night.",
        "The water level allowed a crossing, but establishes neither cargo nor intent.",
    ),
    Chapter(
        "sealed-crate",
        "Check the crate tally for an unaccounted sealed container.",
        "The tally differs by one mark; the missing crate is not linked to the manifest copy.",
    ),
    Chapter(
        "source-review",
        "Review {npc}'s warning alongside the incomplete stamp and archive gap.",
        "Fixture Adventurer retains {npc}'s warning as a lead, not a verified accusation.",
        (
            call(
                "update_quest",
                quest_id="ferry_manifest",
                status="active",
                description="Unverified lead attributed to {npc}; stamp, archive, and cargo evidence conflict.",
            ),
        ),
        ("thread:ferry_manifest:open", "attribution:{npc}"),
    ),
    Chapter(
        "open-investigation",
        "Leave the ferry-manifest investigation open pending an independent record.",
        "The sealed-key promise remains closed; the separate ferry-manifest question remains unresolved.",
        expects=("thread:sealed_key:closed", "thread:ferry_manifest:open"),
    ),
)
