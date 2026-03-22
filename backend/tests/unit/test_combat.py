import pytest

from app.core.combat import Combatant, CombatState, attack_roll, damage_roll, roll_initiative


def test_combatant_initialization():
    c = Combatant(name="Goblin", initiative=10, hp=7, max_hp=7, ac=12)
    assert c.name == "Goblin"
    assert c.initiative == 10
    assert c.hp == 7
    assert c.max_hp == 7
    assert c.ac == 12
    assert c.is_player is False
    assert c.conditions == []


def test_combat_state_advance_turn():
    c1 = Combatant(name="Hero", initiative=15)
    c2 = Combatant(name="Goblin", initiative=10)
    state = CombatState(combatants=[c1, c2])

    assert state.current_combatant.name == "Hero"
    assert state.round_number == 1

    state.advance_turn()
    assert state.current_combatant.name == "Goblin"
    assert state.round_number == 1

    state.advance_turn()
    assert state.current_combatant.name == "Hero"
    assert state.round_number == 2


def test_roll_initiative(mocker):
    # Mock roll_dice to return predictable values
    c1 = Combatant(name="Hero")
    c2 = Combatant(name="Goblin")
    c3 = Combatant(name="Dragon")

    # Predictable rolls: 15, 5, 20
    mocker.patch("app.core.combat.roll_dice", side_effect=[
        mocker.Mock(total=15),
        mocker.Mock(total=5),
        mocker.Mock(total=20),
    ])

    sorted_combatants = roll_initiative([c1, c2, c3])

    assert sorted_combatants[0].name == "Dragon"
    assert sorted_combatants[1].name == "Hero"
    assert sorted_combatants[2].name == "Goblin"

    assert sorted_combatants[0].initiative == 20
    assert sorted_combatants[1].initiative == 15
    assert sorted_combatants[2].initiative == 5


def test_attack_roll(mocker):
    mocker.patch("app.core.combat.roll_dice", return_value=mocker.Mock(
        total=16, rolls=[12], natural_20=False, natural_1=False
    ))
    res = attack_roll(attacker_modifier=4, target_ac=15)
    assert res["hits"] is True
    assert res["critical"] is False
    assert res["fumble"] is False

    # Miss
    mocker.patch("app.core.combat.roll_dice", return_value=mocker.Mock(
        total=12, rolls=[8], natural_20=False, natural_1=False
    ))
    res2 = attack_roll(attacker_modifier=4, target_ac=15)
    assert res2["hits"] is False


def test_attack_roll_critical(mocker):
    mocker.patch("app.core.combat.roll_dice", return_value=mocker.Mock(
        total=25, rolls=[20], natural_20=True, natural_1=False
    ))
    res = attack_roll(attacker_modifier=5, target_ac=30)  # Crit always hits
    assert res["hits"] is True
    assert res["critical"] is True


def test_damage_roll(mocker):
    mocker.patch("app.core.combat.roll_dice", return_value=mocker.Mock(total=8))
    res = damage_roll("2d6+1")
    assert res.total == 8
