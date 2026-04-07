"""F 노드 — event_planner 프롬프트 빌더.

canonical: docs/The_world/prompt_engineering.md §F. 이벤트 기획자
canonical: docs/The_world/game_ending_design.md
"""

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent.generation.models import GameSpec, MapConnectionInfo, MapSpec
from agent.generation.registry.id_table import IdTable
from agent.generation.registry.switch_table import SwitchTable

_SYSTEM = """\
당신은 RPG Maker MZ 이벤트 기획자입니다.
맵 명세를 받아 해당 맵의 이벤트를 YAML DSL로 작성하세요.

## DSL 타입 및 필수 필드

### npc (NPC 대화)
- x: {정수}
  y: {정수}
  name: {이벤트 이름}
  type: npc
  trigger: action_button  # action_button | player_touch | auto_run
  character_name: People1  # 맵 위 스프라이트. 아래 목록에서 선택 (필수)
  character_index: 0       # 스프라이트 시트 내 인덱스 0~7
  dialogue:
    - "대사 1"
    - "대사 2"
  condition_switch: {스위치 이름}  # 선택 (이 스위치 ON일 때 alt_dialogue 사용)
  alt_dialogue:                    # 선택 (condition_switch가 ON일 때 대체 대사)
    - "대체 대사 1"
  set_switch: {스위치 이름}        # 선택 (대화 후 ON)

**character_name + character_index 선택 가이드 (반드시 아래 목록에서만 선택):**

People1 (마을 주민): 0=빨간단발소년, 1=갈색양갈래소녀, 2=파란단발청년남, 3=적갈색단발여,
  4=검은콧수염중년남, 5=갈색땋은중년여, 6=흰머리노인남, 7=회색머리할머니
People2 (직업 NPC): 0=흰머리안경성직자, 1=보라롱헤어신비여, 2=보라단발마법사소년,
  3=갈색머리평민소녀, 4=짙은갈색귀족남(악역), 5=핑크머리수녀, 6=금발고글모험가, 7=고글발명가여
People3 (귀족·왕족): 0=흰수염노왕, 1=금발왕비·공주, 2=파란머리왕자, 3=금발공주,
  4=회색수염장군, 5=갈색머리귀족신사, 6=검은머리전사(근위대장), 7=파란투구기사
People4 (특수 직업): 0=파란머리안경학자(상점주인), 1=금발메이드, 2=금발귀족청년,
  3=주황머리소녀, 4=원형얼굴쾌활중년(여관주인·상인), 5=핑크머리댄서, 6=검은머리군인, 7=청록머리무녀
Evil (악당·빌런): 0=초록두건고글불량배, 1=안대학자형악당, 2=은백롱헤어냉혹여, 3=황금갑옷대악당,
  4=파란어두운남성빌런, 5=은발위선적악당, 6=금색갑옷언데드마왕, 7=갈색로브흑막빌런
Monster (맵위몬스터): 0=파란피부좀비여, 1=초록좀비남, 2=흰늑대인간, 3=검은어둠생물,
  4=흰여우구미호, 5=갈색악마몬스터, 6=좀비보스, 7=악마보스
Actor1 (주인공급): 0=갈색단발남, 1=적갈색단발여, 2=주황스파이크남, 3=적단발여,
  4=갈색기사남, 5=금발마법사여, 6=은발학자남, 7=초록머리신관여
Actor2 (기사급): 0=연파랑온화기사남, 1=분홍기사여, 2=연보라기사남, 3=보라귀족마법사여,
  4=초록스파이크남, 5=갈색전투여, 6=연녹궁수남, 7=은발궁수여
Actor3 (특수급): 0=검은전사남, 1=갈색땋은도적여, 2=백은냉철남, 3=흰머리신비마법사여,
  4=검은진지도적남, 5=금발활발도적여, 6=파란갑옷기사남, 7=검은롱헤어신관여
SF_People1 (SF 시민): 0=검은소년, 1=갈색양갈래소녀, 2=검은청년, 3=금발소녀,
  4=콧수염중년남, 5=땋은머리중년여, 6=베레모노인남, 7=회색노인여
SF_Actor1 (SF 주인공): 0=갈색교복남, 1=갈색교복여, 2=빨간후드남, 3=갈색노란자켓여,
  4=검은정장남, 5=보라베레모여, 6=교복조끼남, 7=파란안경여
SF_Actor2 (SF 동료): 0=금발스웨터남, 1=금발핑크스웨터여, 2=갈색셔츠남, 3=금발버킷햇여,
  4=초록스파이크남, 5=갈색운동여, 6=금발자켓남, 7=갈색실험복여(과학자)
SF_Actor3 (SF 요원): 0=검은근육남, 1=황금롱헤어여, 2=보라정장남(빌런), 3=빨간마스크여,
  4=회색마스크닌자남, 5=갈색캡소녀, 6=검은이어피스요원남, 7=검은교복여
SF_Monster (SF 빌런): 0=흰정장마피아, 1=선글라스바이커, 2=검은그림자생물, 3=빨간광대,
  4=파란황금로봇, 5=짙은전투로봇, 6=보라로브리치, 7=붉은도깨비장군

### transfer (맵 이동)
- x: {정수}
  y: {정수}
  name: {이벤트 이름}
  type: transfer
  trigger: player_touch
  to_map: {맵 이름}
  to_x: {정수}
  to_y: {정수}
  direction: retain  # retain | down | left | right | up
  set_switch: {스위치 이름}  # 선택
  character_name: "!Crystal"  # 워프 마커 스프라이트 (아래 가이드 참고)
  character_index: 0          # 스프라이트 인덱스

**transfer character_name 선택 가이드 (직접 이미지 확인 기준):**
- `!Crystal` index 0=빨강, 1=주황, 2=초록, 3=보라, 4=흰색, 5=파랑 크리스탈
  → 마법 포털/워프 마커 (기본값, 범용 — 어떤 맵 타입에도 어울림)
- `!Door1` index 0=철제 대문, index 1=아치형 나무문
  → 마을 건물 출입구, 던전 입구
- `!$Gate1` index 0=황금 아치문, index 1=목재 성문, index 2=크리스탈 포탈
  → 보스 방 입구, 특별한 장소
- `!$Gate2` index 0=파란 석재문, index 1=어두운 장식문, index 2=갈색 목재문
  → 던전 내부 구역 이동
- `!SF_Door1` index 0=SF 슬라이딩 도어
  → SF 배경 맵
- `""` (빈 문자열): 완전 투명 — 자동 트리거나 눈에 안 보이는 워프가 필요할 때만

### chest (보물 상자)
- x: {정수}
  y: {정수}
  name: {이벤트 이름}
  type: chest
  item: {아이템 이름}
  item_type: item  # item | weapon | armor
  amount: {정수}
  one_time: true
  chest_switch: {스위치 이름}
  dialogue_before: "상자 발견 대사"
  dialogue_after: "아이템 획득 대사"
  character_name: "!Chest"  # 보물상자 스프라이트 (!Chest 고정)

### battle (전투)
- x: {정수}
  y: {정수}
  name: {이벤트 이름}
  type: battle
  trigger: player_touch
  troop: {적 그룹 이름}
  escape_allowed: true
  lose_condition: game_over  # game_over | continue
  on_win:
    - set_switch: {스위치 이름}
  one_time: true
  battle_switch: {스위치 이름}
  character_name: Monster  # 몬스터 스프라이트 — index로 외형 선택
  # Monster: 0=좀비여, 1=좀비남, 2=늑대인간, 3=어둠생물, 4=구미호, 5=악마, 6=좀비보스, 7=악마보스
  # $BigMonster1: index 0~3 (대형 보스용, 2배 크기)
  # SF_Monster: 0=마피아, 1=바이커, 2=그림자생물, 3=광대, 4=파란로봇, 5=짙은로봇, 6=리치, 7=도깨비장군

### shop (상점)
- x: {정수}
  y: {정수}
  name: {이벤트 이름}
  type: shop
  trigger: action_button
  dialogue: "상점 인사 대사"
  items:
    - { item: {아이템 이름}, item_type: item }
    - { item: {무기 이름}, item_type: weapon }
  character_name: People1  # 상점 NPC 스프라이트 — index로 외형 선택
  character_index: 0       # 추천: People4/4=쾌활상인·여관주인, People4/0=학자형상점주인,
  # People2/6=모험가상인, People2/7=발명가상인, People1/4=중년상인남

### ending (엔딩, 보스 맵 전용)
- x: {정수}
  y: {정수}
  name: 엔딩_이벤트
  type: ending
  condition_switch: {보스이름}_defeated
  lines:
    - "보스를 쓰러뜨렸다!"
    - "세계에 평화가 찾아왔다."
    - "～ 완 ～"
  fade_type: black
  action: title

## 절대 금지 사항

- 스위치·아이템·맵을 번호(숫자)로 지정 금지 → 반드시 이름(문자열) 사용
- x, y 좌표가 맵 크기를 벗어나는 것 금지
- 동일한 (x, y)에 이벤트 2개 배치 금지
- to_map에 존재하지 않는 맵 이름 사용 금지
- 제공된 아이템/무기/방어구/적 그룹 목록에 없는 이름 사용 금지

## 출력 형식

YAML만 출력하세요. 설명 불필요. 반드시 아래 형식으로:

events:
  - type: npc
    ...
  - type: transfer
    ...

## 출력 예시

events:
  - x: 8
    y: 3
    name: 여관주인
    type: npc
    trigger: action_button
    dialogue:
      - "어서오세요, 용사여!"
      - "이 마을은 요즘 몬스터 때문에 큰일이에요."
    condition_switch: 드래곤_defeated
    alt_dialogue:
      - "덕분에 마을에 평화가 찾아왔어요!"

  - x: 8
    y: 12
    name: 던전_입구
    type: transfer
    trigger: player_touch
    to_map: 어둠의 던전
    to_x: 10
    to_y: 13

  - x: 14
    y: 5
    name: 보물상자_01
    type: chest
    item: 회복 포션
    item_type: item
    amount: 2
    one_time: true
    chest_switch: chest_1_01
    dialogue_before: "낡은 상자가 있다."
    dialogue_after: "회복 포션을 2개 손에 넣었다!"
"""


def build_event_planner_prompt(
    map_spec: MapSpec,
    game_spec: GameSpec,
    id_table: IdTable,
    switch_table: SwitchTable,
    connection_info: MapConnectionInfo,
    rag_context: str = "",
) -> list[BaseMessage]:
    exit_lines: list[str] = []
    for tile in connection_info.exit_tiles:
        to_map_id = tile.get("to_map_id")
        ex, ey = tile.get("x", 0), tile.get("y", 0)
        to_name = next(
            (name for name, mid in id_table.maps.items() if mid == to_map_id),
            f"Map{to_map_id}",
        )
        # 목적지 spawn 정보 조회 (entry_tiles에서 확인 불가 → 대략적 힌트만)
        exit_lines.append(
            f"- 출구 좌표: ({ex}, {ey}) → '{to_name}' 맵으로 이동\n"
            f"  to_map: {to_name}, to_x: {ex}, to_y: 1"
        )

    landmarks_text = "\n".join(
        f"- {lm.name} ({lm.position_hint})" + (f" — NPC: {lm.npc}" if lm.npc else "")
        for lm in map_spec.landmarks
    )

    existing_switches = "\n".join(f"  - {s}" for s in switch_table.switches)

    human = f"""\
## 맵 정보
이름: {map_spec.name}
타입: {map_spec.map_type}
크기: 가로={map_spec.width}, 세로={map_spec.height}  ← x: 0~{map_spec.width - 1}, y: 0~{map_spec.height - 1}
분위기: {map_spec.atmosphere}

## 랜드마크
{landmarks_text if landmarks_text else "없음"}

## 맵 연결 정보 (transfer 이벤트에 반드시 이 좌표 사용)
{chr(10).join(exit_lines) if exit_lines else "없음 (이 맵은 출구 없음)"}

## 스토리 컨텍스트
{game_spec.story.get("synopsis", "")}
현재 맵의 역할: {map_spec.atmosphere}

## 사용 가능한 이름 목록 (목록에 없는 이름 사용 금지)

스위치 이름 (기할당):
{existing_switches if existing_switches else "  없음"}

아이템: {", ".join(list(id_table.items.keys())[:10])}
무기:   {", ".join(list(id_table.weapons.keys())[:8])}
방어구: {", ".join(list(id_table.armors.keys())[:8])}
적 그룹: {", ".join(list(id_table.troops.keys()))}
이동 가능한 맵: {", ".join(id_table.maps.keys())}

## 이벤트 생성 가이드

{_describe_required_events(map_spec, game_spec, id_table)}
{f"{chr(10)}## RPG Maker MZ 기술 참고{chr(10)}{rag_context}{chr(10)}" if rag_context else ""}
YAML 출력:
"""
    return [SystemMessage(content=_SYSTEM), HumanMessage(content=human)]


def _describe_required_events(
    spec: MapSpec,
    game_spec: GameSpec,
    id_table: IdTable,
) -> str:
    if spec.map_type == "town":
        return (
            "1. NPC 대화 최소 2개 (랜드마크마다 1개, 보스 처치 전후 조건부 대화 권장)\n"
            "2. 상점 이벤트 (상점 랜드마크가 있으면)\n"
            "3. 맵 이동 이벤트 (exits 수만큼, 위 좌표 정보 사용)\n"
            "4. 선택: 보물 상자 1개"
        )
    elif spec.map_type == "dungeon":
        return (
            "1. 맵 이동 이벤트 (입구/출구, 위 좌표 정보 사용)\n"
            "2. 전투 이벤트 2~3개 (player_touch, one_time=true)\n"
            "3. 보물 상자 1~2개 (chest 타입)\n"
            "4. 선택: 경고 NPC 1개"
        )
    elif spec.map_type == "boss":
        boss_enemies = [e for e in game_spec.enemies if e.tier == "boss"]
        boss_name = boss_enemies[0].name if boss_enemies else "보스"
        troop_key = f"{boss_name} × 1"
        if troop_key not in id_table.troops:
            troop_key = next(
                (k for k in id_table.troops if boss_name in k), list(id_table.troops.keys())[-1]
            )
        return (
            f"1. 보스 전투 이벤트 필수 (type: battle, troop: {troop_key}, "
            f"lose_condition: game_over, battle_switch: {boss_name}_defeated)\n"
            f"2. 엔딩 이벤트 필수 (type: ending, condition_switch: {boss_name}_defeated, "
            f"action: title)\n"
            "3. 맵 이동 이벤트 (탈출용)\n"
            "   ⚠️ battle 이벤트와 ending 이벤트의 x, y 좌표는 반드시 달라야 함"
        )
    return "맵 타입에 맞는 이벤트 3~5개"
