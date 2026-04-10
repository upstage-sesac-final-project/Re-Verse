"""event_scaffolder 유닛 테스트."""

from agent.generation.compilers.dsl_models import (
    BattleEvent,
    ChestEvent,
    EndingEvent,
    NpcEvent,
    ShopEvent,
    TransferEvent,
)
from agent.generation.models import (
    ExitSpec,
    GameQuestPlan,
    MapQuestScript,
    MapSpec,
    NpcRole,
    Quest,
    QuestStep,
)
from agent.generation.nodes.event_scaffolder import scaffold_map_events
from agent.generation.registry.id_table import IdTable

# ── 모델 테스트 (기존) ──────────────────────────────────────────────────────


def test_quest_step_model() -> None:
    step = QuestStep(
        map_name="동굴",
        type="battle",
        target="고블린_단독",
        description="고블린 대장을 처치한다",
        completion_switch="동굴_battle_1",
    )
    assert step.completion_switch == "동굴_battle_1"


def test_quest_model() -> None:
    quest = Quest(
        name="마왕 부하 토벌",
        steps=[
            QuestStep(
                map_name="마을",
                type="talk",
                target="촌장",
                description="촌장에게 의뢰를 받는다",
                completion_switch="마을_quest_accepted",
            ),
            QuestStep(
                map_name="동굴",
                type="battle",
                target="고블린_단독",
                description="고블린을 처치한다",
                completion_switch="동굴_고블린_defeated",
            ),
        ],
        reward_item="강철 검",
        reward_switch="동굴_cleared",
    )
    assert len(quest.steps) == 2
    assert quest.reward_item == "강철 검"


def test_game_quest_plan_model() -> None:
    plan = GameQuestPlan(
        quests=[
            Quest(
                name="메인 퀘스트",
                steps=[
                    QuestStep(
                        map_name="마을",
                        type="talk",
                        target="촌장",
                        description="시작",
                        completion_switch="quest_start",
                    )
                ],
                reward_switch="마을_cleared",
            )
        ],
        maps=[
            MapQuestScript(
                map_id=1,
                map_name="마을",
                map_type="town",
                act_index=0,
                npcs=[NpcRole(name="촌장", role="퀘스트 부여자", quest_ref="메인 퀘스트")],
            ),
        ],
        boss_name="마왕",
    )
    assert plan.boss_name == "마왕"
    assert plan.maps[0].npcs[0].quest_ref == "메인 퀘스트"


# ── scaffold_map_events 테스트 ──────────────────────────────────────────────


def _make_id_table() -> IdTable:
    return IdTable(
        actors={"용사": 1},
        items={"회복 포션": 1},
        weapons={"나무 검": 1, "강철 검": 2},
        armors={"가죽 갑옷": 1},
        enemies={"고블린": 1, "마왕": 2},
        troops={"고블린×1": 1, "고블린×2": 2, "마왕_단독": 3},
        maps={"시작 마을": 1, "어둠의 동굴": 2, "마왕의 성": 3},
    )


def _make_map_spec(
    map_id: int,
    name: str,
    map_type: str,
    exits: list[ExitSpec] | None = None,
) -> MapSpec:
    return MapSpec(
        map_id=map_id,
        name=name,
        map_type=map_type,
        width=30,
        height=30,
        tileset_id=1,
        bgm="Town1",
        atmosphere="평화로운",
        landmarks=[],
        spawn_point=(15, 15),
        exits=exits or [],
    )


def _make_quest_plan() -> GameQuestPlan:
    return GameQuestPlan(
        quests=[
            Quest(
                name="고블린 토벌",
                steps=[
                    QuestStep(
                        map_name="시작 마을",
                        type="talk",
                        target="촌장",
                        description="촌장에게 의뢰를 받는다",
                        completion_switch="시작_마을_quest_accepted",
                    ),
                    QuestStep(
                        map_name="어둠의 동굴",
                        type="battle",
                        target="고블린×2",
                        description="고블린을 처치한다",
                        completion_switch="어둠의_동굴_고블린_defeated",
                    ),
                ],
                reward_item="강철 검",
                reward_switch="어둠의_동굴_cleared",
            ),
        ],
        maps=[
            MapQuestScript(
                map_id=1,
                map_name="시작 마을",
                map_type="town",
                act_index=0,
                npcs=[NpcRole(name="촌장", role="퀘스트 부여자", quest_ref="고블린 토벌")],
            ),
            MapQuestScript(
                map_id=2,
                map_name="어둠의 동굴",
                map_type="dungeon",
                act_index=1,
                npcs=[NpcRole(name="모험가", role="힌트 제공")],
                gate_switch="시작_마을_quest_accepted",
            ),
            MapQuestScript(
                map_id=3,
                map_name="마왕의 성",
                map_type="boss",
                act_index=2,
                npcs=[],
                gate_switch="어둠의_동굴_cleared",
            ),
        ],
        boss_name="마왕",
    )


def test_scaffold_town_has_quest_npc() -> None:
    """town 맵: 퀘스트 NPC + 힌트 NPC + 상점 + transfer."""
    id_table = _make_id_table()
    plan = _make_quest_plan()
    map_spec = _make_map_spec(
        1,
        "시작 마을",
        "town",
        exits=[ExitSpec(direction="north", to_map_id=2, label="어둠의 동굴")],
    )

    events = scaffold_map_events(map_spec, plan, id_table)

    npcs = [e for e in events if isinstance(e, NpcEvent)]
    assert len(npcs) >= 1
    quest_npc = npcs[0]
    assert quest_npc.set_switch is not None  # 퀘스트 수락 스위치
    assert quest_npc.condition_switch is not None  # 보상 조건 스위치
    assert quest_npc.alt_dialogue is not None

    transfers = [e for e in events if isinstance(e, TransferEvent)]
    assert len(transfers) >= 1

    shops = [e for e in events if isinstance(e, ShopEvent)]
    assert len(shops) >= 1

    # NPC 2 + Shop 1 + Transfer 1 = 최소 4, exit 많으면 더 증가
    assert 4 <= len(events) <= 10


def test_scaffold_dungeon_has_battles_and_chest() -> None:
    """dungeon 맵: 전투 + 조건부 보물상자 + transfer."""
    id_table = _make_id_table()
    plan = _make_quest_plan()
    map_spec = _make_map_spec(
        2,
        "어둠의 동굴",
        "dungeon",
        exits=[
            ExitSpec(direction="south", to_map_id=1, label="시작 마을"),
            ExitSpec(direction="north", to_map_id=3, label="마왕의 성"),
        ],
    )

    events = scaffold_map_events(map_spec, plan, id_table)

    battles = [e for e in events if isinstance(e, BattleEvent)]
    assert len(battles) >= 1
    assert battles[0].battle_switch is not None
    assert len(battles[0].on_win) >= 1

    chests = [e for e in events if isinstance(e, ChestEvent)]
    assert len(chests) >= 1
    assert chests[0].condition_switch is not None

    assert 5 <= len(events) <= 10


def test_scaffold_boss_no_ending_event() -> None:
    """boss 맵: 보스 전투 있고, EndingEvent 없음 (CommonEvent로 처리)."""
    id_table = _make_id_table()
    plan = _make_quest_plan()
    map_spec = _make_map_spec(
        3,
        "마왕의 성",
        "boss",
        exits=[ExitSpec(direction="south", to_map_id=2, label="어둠의 동굴")],
    )

    events = scaffold_map_events(map_spec, plan, id_table)

    battles = [e for e in events if isinstance(e, BattleEvent)]
    assert len(battles) == 1
    assert "마왕" in battles[0].troop

    endings = [e for e in events if isinstance(e, EndingEvent)]
    assert len(endings) == 0

    assert len(events) <= 10
