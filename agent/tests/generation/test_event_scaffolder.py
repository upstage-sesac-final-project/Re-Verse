"""event_scaffolder 유닛 테스트."""

from agent.generation.models import (
    GameQuestPlan,
    MapQuestScript,
    NpcRole,
    Quest,
    QuestStep,
)


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
