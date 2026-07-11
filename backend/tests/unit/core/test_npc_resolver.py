"""ADR 0009 S1 — F2 resolver: name→UUID, living-first, reject-with-candidates."""

from app.core.npc_resolver import resolve_npc

U1 = "11111111-1111-1111-1111-111111111111"
U2 = "22222222-2222-2222-2222-222222222222"
U3 = "33333333-3333-3333-3333-333333333333"


def ws(npcs: dict) -> dict:
    return {"npcs": npcs}


class TestExactResolution:
    def test_resolves_by_name(self):
        state = ws({U1: {"name": "Lyra", "lifecycle": "alive"}})
        res = resolve_npc("Lyra", state)
        assert res.npc_id == U1
        assert res.error == ""

    def test_case_insensitive(self):
        state = ws({U1: {"name": "Lyra", "lifecycle": "alive"}})
        assert resolve_npc("lyra", state).npc_id == U1

    def test_resolves_by_slug(self):
        state = ws({U1: {"name": "Lyra the Ranger", "slug": "lyra", "lifecycle": "alive"}})
        assert resolve_npc("lyra", state).npc_id == U1

    def test_missing_lifecycle_treated_as_alive(self):
        state = ws({U1: {"name": "Lyra"}})
        assert resolve_npc("Lyra", state).npc_id == U1


class TestMisses:
    def test_unknown_name(self):
        res = resolve_npc("Ghost", ws({U1: {"name": "Lyra", "lifecycle": "alive"}}))
        assert res.npc_id is None
        assert "not a known NPC" in res.error

    def test_empty_state(self):
        assert resolve_npc("Lyra", ws({})).npc_id is None


class TestLifecycleScoping:
    def test_dead_excluded_by_default_with_specific_error(self):
        state = ws({U1: {"name": "Bandit", "lifecycle": "dead"}})
        res = resolve_npc("Bandit", state)
        assert res.npc_id is None
        assert "dead" in res.error

    def test_removed_excluded_by_default_with_specific_error(self):
        state = ws({U1: {"name": "Merchant", "lifecycle": "removed"}})
        res = resolve_npc("Merchant", state)
        assert res.npc_id is None
        assert "removed" in res.error

    def test_include_gone_resolves_removed(self):
        state = ws({U1: {"name": "Merchant", "lifecycle": "removed"}})
        assert resolve_npc("Merchant", state, include_gone=True).npc_id == U1

    def test_living_shadows_dead_homonym(self):
        state = ws(
            {
                U1: {"name": "Guard", "lifecycle": "dead"},
                U2: {"name": "Guard", "lifecycle": "alive"},
            }
        )
        assert resolve_npc("Guard", state).npc_id == U2


class TestAmbiguity:
    def test_two_living_homonyms_reject_with_candidates(self):
        state = ws(
            {
                U1: {"name": "Guard", "lifecycle": "alive"},
                U2: {"name": "Guard", "lifecycle": "alive"},
                U3: {"name": "Lyra", "lifecycle": "alive"},
            }
        )
        res = resolve_npc("Guard", state)
        assert res.npc_id is None
        assert set(res.candidates) == {U1, U2}
        assert "Guard" in res.error
