"""balance.py 유닛 테스트 — RPG Maker MZ 실제 공식 기반 (ATK*4 - DEF*2)."""

from agent.generation.balance import check_balance, simulate_battle


def test_player_wins_clearly():
    """강한 플레이어가 약한 적에게 빠르게 이김."""
    # ATK=50 vs DEF=5: dmg = 50*4 - 5*2 = 190. HP=100 → 1턴
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
    assert result.turns <= 2


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
    # ATK=1 vs DEF=9999: dmg = max(0, 1*4 - 9999*2) = 0
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
    # ATK=100 vs DEF=0: dmg = 400. HP=1 → 즉사
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


def test_party_size_multiplies_damage():
    """파티 3명이면 DPS 3배."""
    # ATK=30 vs DEF=10: dmg = 30*4 - 10*2 = 100. 3명=300/턴. HP=500 → 2턴
    result = simulate_battle(
        player_hp=500,
        player_atk=30,
        player_def=15,
        enemy_hp=500,
        enemy_atk=20,
        enemy_def=10,
        party_size=3,
    )
    assert result.player_survived
    assert result.turns <= 3


def _make_warrior_class_lv20():
    """warrior 클래스 lv1~20 곡선 (maxLevel=20 기준)."""

    def interp(lv, l1, l20):
        return round(l1 + (l20 - l1) * ((lv - 1) / 19))

    return {
        "id": 1,
        "name": "전사",
        "params": [
            [interp(lv, 400, 3000) for lv in range(1, 100)],  # MHP
            [interp(lv, 30, 300) for lv in range(1, 100)],  # MMP
            [interp(lv, 15, 60) for lv in range(1, 100)],  # ATK
            [interp(lv, 12, 50) for lv in range(1, 100)],  # DEF
            [interp(lv, 5, 25) for lv in range(1, 100)],  # MAT
            [interp(lv, 8, 35) for lv in range(1, 100)],  # MDF
            [interp(lv, 10, 35) for lv in range(1, 100)],  # AGI
            [interp(lv, 8, 25) for lv in range(1, 100)],  # LUK
        ],
    }


def test_check_balance_no_warning_for_normal_enemy():
    """정상 밸런스 적 (tier=weak, tier별 스탯)에 대해 경고 없음."""
    project = {
        "Actors.json": [None, {"id": 1, "name": "용사"}],
        "Classes.json": [None, _make_warrior_class_lv20()],
        "Weapons.json": [None, {"id": 1, "name": "단검", "params": [0, 0, 15, 0, 0, 0, 0, 0]}],
        "Armors.json": [None, {"id": 1, "name": "조끼", "params": [0, 0, 0, 10, 0, 0, 0, 0]}],
        "Enemies.json": [
            None,
            {
                "id": 1,
                "name": "슬라임",
                "params": [200, 20, 16, 10, 11, 8, 8, 5],
                "note": "tier:weak location:필드",
            },
        ],
    }
    warnings = check_balance(project)
    balance_warnings = [w for w in warnings if "패배" in w or "전투" in w]
    assert len(balance_warnings) == 0, f"예상치 못한 경고: {balance_warnings}"


def test_check_balance_warns_when_player_loses():
    """lv6 플레이어가 보스(tier:boss)에게 패배 → 경고."""
    project = {
        "Actors.json": [None, {"id": 1, "name": "용사"}],
        "Classes.json": [
            None,
            {
                "id": 1,
                "name": "전사",
                "params": [
                    [50] + [50] * 98,  # HP 매우 낮음
                    [30] * 99,
                    [5] + [5] * 98,  # ATK 매우 낮음
                    [3] + [3] * 98,  # DEF 매우 낮음
                    [5] * 99,
                    [5] * 99,
                    [5] * 99,
                    [5] * 99,
                ],
            },
        ],
        "Weapons.json": [None],
        "Armors.json": [None],
        "Enemies.json": [
            None,
            {
                "id": 1,
                "name": "최종 보스",
                "params": [4000, 400, 60, 42, 42, 34, 30, 18],
                "note": "tier:boss location:성",
            },
        ],
    }
    warnings = check_balance(project)
    assert any("패배" in w for w in warnings)


def test_check_balance_warns_weapon_zero_params():
    """ATK=0, MAT=0 무기에 대해 경고."""
    project = {
        "Actors.json": [None],
        "Classes.json": [None],
        "Weapons.json": [
            None,
            {"id": 1, "name": "빈무기", "params": [0, 0, 0, 0, 0, 0, 0, 0]},
        ],
        "Armors.json": [None],
        "Enemies.json": [None],
    }
    warnings = check_balance(project)
    assert any("빈무기" in w and "ATK=0" in w for w in warnings)


def test_check_balance_warns_armor_zero_params():
    """DEF=0, MDF=0 방어구에 대해 경고."""
    project = {
        "Actors.json": [None],
        "Classes.json": [None],
        "Weapons.json": [None],
        "Armors.json": [
            None,
            {"id": 1, "name": "빈갑옷", "params": [0, 0, 0, 0, 0, 0, 0, 0]},
        ],
        "Enemies.json": [None],
    }
    warnings = check_balance(project)
    assert any("빈갑옷" in w and "DEF=0" in w for w in warnings)
