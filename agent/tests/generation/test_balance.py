"""balance.py 유닛 테스트."""

from agent.generation.balance import check_balance, simulate_battle


def test_player_wins_clearly():
    """강한 플레이어가 약한 적에게 빠르게 이김."""
    result = simulate_battle(
        player_hp=500,
        player_atk=50,
        player_def=10,
        enemy_hp=100,
        enemy_atk=20,
        enemy_def=5,
    )
    assert result.player_survived
    assert result.enemy_hp_remaining == 0
    assert result.turns <= 5


def test_player_loses_against_overwhelming_enemy():
    """압도적인 적에게 플레이어가 패배."""
    result = simulate_battle(
        player_hp=50,
        player_atk=5,
        player_def=0,
        enemy_hp=10000,
        enemy_atk=100,
        enemy_def=0,
    )
    assert not result.player_survived
    assert result.enemy_hp_remaining > 0


def test_max_turns_stops_battle():
    """양쪽이 서로 못 죽이는 경우 max_turns에서 멈춤."""
    result = simulate_battle(
        player_hp=1000,
        player_atk=1,
        player_def=9999,
        enemy_hp=1000,
        enemy_atk=1,
        enemy_def=9999,
        max_turns=5,
    )
    assert result.turns == 5


def test_player_first_strike():
    """플레이어가 선공 — HP 1인 적은 1턴에 처치."""
    result = simulate_battle(
        player_hp=100,
        player_atk=100,
        player_def=0,
        enemy_hp=1,
        enemy_atk=999,
        enemy_def=0,
    )
    assert result.player_survived
    assert result.turns == 0


def test_check_balance_no_warning_for_normal_enemy():
    """정상 밸런스 적에 대해 경고 없음."""
    project = {
        "Classes.json": [
            None,
            {
                "id": 1,
                "name": "전사",
                "params": [
                    [180] + [0] * 98,  # HP
                    [60] + [0] * 98,  # MP
                    [18] + [0] * 98,  # ATK
                    [10] + [0] * 98,  # DEF
                    [8] + [0] * 98,  # MAT
                    [8] + [0] * 98,  # MDF
                    [9] + [0] * 98,  # AGI
                    [8] + [0] * 98,  # LUK
                ],
            },
        ],
        "Enemies.json": [
            None,
            {"id": 1, "name": "약한 슬라임", "params": [80, 0, 10, 5, 0, 0, 10, 0]},
        ],
    }
    warnings = check_balance(project)
    assert len(warnings) == 0


def test_check_balance_warns_when_player_loses():
    """플레이어가 패배하는 경우 경고."""
    project = {
        "Classes.json": [
            None,
            {
                "id": 1,
                "name": "전사",
                "params": [
                    [50] + [0] * 98,  # HP (매우 낮음)
                    [60] + [0] * 98,
                    [5] + [0] * 98,  # ATK (매우 낮음)
                    [0] + [0] * 98,  # DEF
                    [8] + [0] * 98,
                    [8] + [0] * 98,
                    [9] + [0] * 98,
                    [8] + [0] * 98,
                ],
            },
        ],
        "Enemies.json": [
            None,
            {
                "id": 1,
                "name": "강력한 보스",
                "params": [3000, 0, 80, 20, 0, 0, 10, 0],  # boss tier
            },
        ],
    }
    warnings = check_balance(project)
    assert any("패배" in w or "BALANCE" in w for w in warnings)
