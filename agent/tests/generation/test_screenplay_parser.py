"""screenplay_parser 유닛 테스트."""

from agent.generation.compilers.dsl_models import (
    BattleEvent,
    ChestEvent,
    NpcEvent,
    ShopEvent,
    TransferEvent,
)
from agent.generation.models import ExitSpec, MapSpec
from agent.generation.registry.id_table import IdTable
from agent.generation.screenplay_parser import parse_screenplay, scenes_to_dsl

SAMPLE_SCREENPLAY = """
## Scene 1: 항구 마을

[배경: 따뜻한 햇살이 비치는 작은 항구 마을. 어선들이 정박해 있다.]

NPC 선장 빌리 (퀘스트 부여자):
  첫만남: "젊은 잭, 전설의 해적 왕 보물을 찾고 싶다면 먼저 이 지도를 가져가게."
  진행중: "물고기 떼를 따라가면 상어 동굴을 찾을 수 있을 거다."
  완료후: "자네가 해냈군! 이 삼지창을 받게나."

NPC 바다 상인 (상점):
  인사: "어서오세요! 항해에 필요한 물품이 있습니다."

이동조건: 선장 빌리와 대화 후 → 항해 중인 바다
차단대사: "아직 선장과 이야기를 나누지 않았습니다."

## Scene 2: 상어 동굴

[배경: 어두운 동굴 안에 물방울 소리가 울려퍼진다.]

NPC 동굴 탐험가 (힌트 제공):
  첫만남: "이 동굴에는 무시무시한 상어가 산다네. 조심하게."
  진행중: "상어는 화염에 약하다고 들었네."
  완료후: "상어를 물리치다니 대단하군!"

전투: 물고기 떼×2
  승리보상: 단검

전투: 상어 샤크_단독
  승리보상: 삼지창

이동조건: 모든 전투 승리 후 → 보물섬 입구
차단대사: "아직 동굴의 몬스터를 처치하지 못했습니다."

## Scene 3: 해적 왕국 성채

[배경: 거대한 성채 안에 해적 왕의 왕좌가 빛나고 있다.]

보스전: 해적 왕_단독
  전투전: "네가 여기까지 올 줄은 몰랐다. 하지만 내 보물은 넘기지 않겠다!"
  승리후: "잘했다, 잭. 이 보물은 바다의 평화를 위해 쓰여질 것이다."
"""


def _make_id_table() -> IdTable:
    return IdTable(
        actors={"잭": 1},
        items={"회복 포션": 1},
        weapons={"단검": 1, "삼지창": 2},
        armors={"가죽 갑옷": 1},
        enemies={"물고기 떼": 1, "상어 샤크": 2, "해적 왕": 3},
        troops={"물고기 떼×1": 1, "물고기 떼×2": 2, "상어 샤크_단독": 3, "해적 왕_단독": 4},
        maps={"항구 마을": 1, "상어 동굴": 2, "해적 왕국 성채": 3},
    )


def _make_map_specs() -> list[MapSpec]:
    return [
        MapSpec(
            map_id=1,
            name="항구 마을",
            map_type="town",
            width=30,
            height=30,
            tileset_id=1,
            bgm="Town1",
            atmosphere="평화로운",
            landmarks=[],
            spawn_point=(15, 15),
            exits=[ExitSpec(direction="north", to_map_id=2, label="상어 동굴")],
        ),
        MapSpec(
            map_id=2,
            name="상어 동굴",
            map_type="dungeon",
            width=40,
            height=30,
            tileset_id=2,
            bgm="Dungeon1",
            atmosphere="어두운",
            landmarks=[],
            spawn_point=(20, 15),
            exits=[
                ExitSpec(direction="south", to_map_id=1, label="항구 마을"),
                ExitSpec(direction="north", to_map_id=3, label="해적 왕국 성채"),
            ],
        ),
        MapSpec(
            map_id=3,
            name="해적 왕국 성채",
            map_type="boss",
            width=20,
            height=20,
            tileset_id=2,
            bgm="Boss1",
            atmosphere="위압적",
            landmarks=[],
            spawn_point=(10, 10),
            exits=[],
        ),
    ]


def test_parse_screenplay_extracts_scenes() -> None:
    """각본에서 Scene 3개를 파싱."""
    scenes = parse_screenplay(SAMPLE_SCREENPLAY)
    assert len(scenes) == 3
    assert "항구 마을" in scenes[0].map_name
    assert "상어 동굴" in scenes[1].map_name
    assert "해적 왕국 성채" in scenes[2].map_name


def test_parse_scene1_npcs() -> None:
    """Scene 1: NPC 대사 3단계 + 상점."""
    scenes = parse_screenplay(SAMPLE_SCREENPLAY)
    s1 = scenes[0]
    assert len(s1.npcs) == 1
    assert s1.npcs[0].name == "선장 빌리"
    assert "전설" in s1.npcs[0].first_meet
    assert "물고기" in s1.npcs[0].hint
    assert "삼지창" in s1.npcs[0].reward
    assert s1.shop is not None
    assert s1.shop.name == "바다 상인"


def test_parse_scene2_battles() -> None:
    """Scene 2: 전투 2개 + 보상."""
    scenes = parse_screenplay(SAMPLE_SCREENPLAY)
    s2 = scenes[1]
    assert len(s2.battles) == 2
    assert "물고기" in s2.battles[0].troop
    assert s2.battles[0].reward_item == "단검"
    assert "상어" in s2.battles[1].troop
    assert s2.battles[1].reward_item == "삼지창"


def test_parse_scene3_boss() -> None:
    """Scene 3: 보스전 + 대사."""
    scenes = parse_screenplay(SAMPLE_SCREENPLAY)
    s3 = scenes[2]
    assert s3.boss is not None
    assert "해적 왕" in s3.boss.troop
    assert "몰랐다" in s3.boss.before_dialogue
    assert "평화" in s3.boss.after_dialogue


def test_parse_transfer_condition() -> None:
    """이동조건 + 차단대사 파싱."""
    scenes = parse_screenplay(SAMPLE_SCREENPLAY)
    s1 = scenes[0]
    assert s1.transfer is not None
    assert "선장" in s1.transfer.condition
    assert "이야기" in s1.transfer.blocked


def test_scenes_to_dsl_town() -> None:
    """town Scene → NPC + 상점 + transfer DSL."""
    scenes = parse_screenplay(SAMPLE_SCREENPLAY)
    id_table = _make_id_table()
    map_specs = _make_map_specs()

    dsl = scenes_to_dsl(scenes, map_specs, id_table)
    assert 1 in dsl
    events = dsl[1]

    npcs = [e for e in events if isinstance(e, NpcEvent)]
    assert len(npcs) >= 1
    assert npcs[0].dialogue[0] != "_FILL_"  # 실제 대사

    shops = [e for e in events if isinstance(e, ShopEvent)]
    assert len(shops) == 1

    transfers = [e for e in events if isinstance(e, TransferEvent)]
    assert len(transfers) >= 1


def test_scenes_to_dsl_dungeon() -> None:
    """dungeon Scene → 전투 + 보물상자 + transfer DSL."""
    scenes = parse_screenplay(SAMPLE_SCREENPLAY)
    id_table = _make_id_table()
    map_specs = _make_map_specs()

    dsl = scenes_to_dsl(scenes, map_specs, id_table)
    assert 2 in dsl
    events = dsl[2]

    battles = [e for e in events if isinstance(e, BattleEvent)]
    assert len(battles) >= 2

    chests = [e for e in events if isinstance(e, ChestEvent)]
    assert len(chests) >= 1
    assert chests[0].condition_switch is not None  # 전투 승리 조건

    transfers = [e for e in events if isinstance(e, TransferEvent)]
    assert len(transfers) >= 1


def test_scenes_to_dsl_boss() -> None:
    """boss Scene → 보스전 + NPC + 탈출 transfer, EndingEvent 없음."""
    scenes = parse_screenplay(SAMPLE_SCREENPLAY)
    id_table = _make_id_table()
    map_specs = _make_map_specs()

    dsl = scenes_to_dsl(scenes, map_specs, id_table)
    assert 3 in dsl
    events = dsl[3]

    battles = [e for e in events if isinstance(e, BattleEvent)]
    assert len(battles) == 1
    assert "해적" in battles[0].troop

    # 탈출 transfer (exits 없어도 자동 생성)
    transfers = [e for e in events if isinstance(e, TransferEvent)]
    assert len(transfers) >= 1
