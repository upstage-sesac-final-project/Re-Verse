"""F 노드 — event_planner 프롬프트 빌더.

canonical: docs/The_world/prompt_engineering.md §F. 이벤트 기획자
canonical: docs/The_world/game_ending_design.md
"""

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent.generation.models import GameSpec, MapConnectionInfo, MapSpec, MapStoryScript
from agent.generation.registry.id_table import IdTable
from agent.generation.registry.switch_table import SwitchTable

_SYSTEM = """\
당신은 RPG Maker MZ 이벤트 기획자입니다.
맵 명세를 받아 해당 맵의 이벤트를 YAML DSL로 작성하세요.

## DSL 타입 및 필수 필드

### npc (NPC 대화)
- x: {정수}
  y: {정수}
  name: {NPC 이름 또는 역할}  # 예: "마을촌장", "상인", "경비병"
  type: npc
  trigger: action_button  # 고정 — 변경 금지
  character_name: People1  # 맵 위 스프라이트. 아래 목록에서 선택 (필수)
  character_index: 0       # 스프라이트 시트 내 인덱스 0~7
  dialogue:
    - "대사 1"
    - "대사 2"
  condition_switch: {스위치 이름}  # 선택 (이 스위치 ON일 때 alt_dialogue 사용)
  alt_dialogue:                    # 선택 (condition_switch가 ON일 때 대체 대사)
    - "대체 대사 1"
  set_switch: {스위치 이름}        # 선택 (대화 후 ON)
  required_item: {아이템 이름}       # 선택 (이 아이템 소지 시 alt_dialogue 사용)
  consume_item: true               # 선택 (true면 대화 후 아이템 1개 소비)

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
Nature (동물·요정): 0=검은개, 1=검은고양이, 2=분홍돼지, 3=황금소동물(여우),
  4=검은머리수인소녀(고양이귀), 5=금발날개요정(초록날개), 6=핑크머리날개요정, 7=황금날개빛요정
  → 숲·자연·동물 테마 맵 NPC에 사용 (마을 애완동물, 숲속 요정 등)
SF_People2 (SF 시민): 0=금발단발청소년남(흰셔츠), 1=핑크머리청소년여(흰셔츠),
  2=검은머리청소년(짙은복장), 3=초록머리여(흰복장),
  4=갈색머리안경성인(흰셔츠), 5=금발롱헤어여(흰셔츠), 6=갈색곱슬헤드밴드, 7=긴검은머리여
  → SF 도시·학교·시설의 일반 시민/학생 NPC에 사용
SF_People3 (SF 전투로봇): 0=파란전투로봇, 1=붉은전투로봇, 2=주황/금전투로봇, 3=초록전투로봇,
  4=노란전투로봇, 5=은색전투로봇, 6=검은크로스로봇, 7=갈색/회색로봇
  → SF 시설의 경비로봇·전투드론 NPC 이벤트에 사용 (대화 없는 장식 이벤트 권장)
SF_Monster (SF 빌런): 0=흰정장마피아, 1=선글라스바이커, 2=검은그림자생물, 3=빨간광대,
  4=파란황금로봇, 5=짙은전투로봇, 6=보라로브리치, 7=붉은도깨비장군

### transfer (맵 이동)
- x: {정수}
  y: {정수}
  name: {목적지}_이동  # 예: "던전_입구_이동", "마을_귀환"
  type: transfer
  trigger: player_touch  # 고정 — 변경 금지
  to_map: {맵 이름}
  to_x: {정수}
  to_y: {정수}
  direction: retain  # retain | down | left | right | up
  set_switch: {스위치 이름}  # 선택
  condition_switch: {스위치 이름}   # 선택 (이 스위치 ON일 때만 이동 가능)
  blocked_dialogue: "아직 갈 수 없습니다."  # 선택 (조건 미충족 시 표시 메시지)
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
- `!SF_Door1` index 0=SF 슬라이딩 도어 (밝은 금속)
  → SF 시설 내부 문
- `!SF_Door2` index 0=빨간SF슬라이딩문, 1=원형센서SF문(회색), 2=노란격자게이트,
  3=갈색목재문, 4=개방형문프레임, 5=파란에너지빔, 6=크리스탈젬이펙트, 7=초록포탈링
  → index 0~4: SF 실내 문; index 5~7: 포탈/이펙트 오브젝트
- `!$SF_Gate1` index 0=갈색격자목재문(아시아풍), 1=갈색조각목재문, 2=덩굴장식철제문
  → 전통/아시아풍 목재 게이트 (이름과 달리 SF 아님 — 판타지 시설 출입구)
- `!$SF_Gate2` index 0=노란SF전자문(육각패턴), 1=검은삼각SF문, 2=산업용회색문(T6마킹)
  → 실제 SF 전자/산업 문 (SF 맵 보스방·격납고 입구)
- `!$SF_Gate3` index 0=황금유럽아치철제문, 1=파란꽃장식철제문, 2=덩굴장식철제문(개방)
  → 유럽풍 철제 정원 게이트 (귀족 저택, 성 외곽 — 이름과 달리 SF 아님)
- `""` (빈 문자열): 완전 투명 — 자동 트리거나 눈에 안 보이는 워프가 필요할 때만

### chest (보물 상자)
- x: {정수}
  y: {정수}
  name: 보물상자_{번호}  # 예: "보물상자_01", "보물상자_02"
  type: chest
  item: {아이템 이름}
  item_type: item  # item | weapon | armor
  amount: {정수}
  one_time: true
  chest_switch: {스위치 이름}
  dialogue_before: "상자 발견 대사"
  dialogue_after: "아이템 획득 대사"
  condition_switch: {스위치 이름}   # 선택 (이 스위치 ON일 때만 보물상자 출현)
  character_name: "!Chest"  # 보물상자 스프라이트 (!Chest 고정)
  character_index: 0        # 0=빨강(기본), 1=금색(귀중품), 2=초록(자연·던전), 3=파랑(마법·특별)

### battle (전투)
- x: {정수}
  y: {정수}
  name: {적이름}_전투  # 예: "고블린_전투", "드래곤_보스전" — 반드시 전투임을 나타내는 이름
  type: battle
  trigger: player_touch # 고정 — 변경 금지 (플레이어 접촉 시 전투 시작)
  troop: {적 그룹 이름}  # ⚠️ 반드시 아래 "적 그룹" 목록의 정확한 이름 그대로 사용
                         # 형식: "적이름×숫자" 또는 "적이름_단독"
                         # 예시 ❌ 틀림: "고블린"  ✅ 맞음: "고블린×2" 또는 "고블린_단독"
  escape_allowed: true
  lose_condition: game_over  # game_over | continue
  on_win:
    - set_switch: {스위치 이름}
  one_time: true
  battle_switch: {고유한 스위치 이름}  # 각 battle마다 반드시 다른 이름 사용! 예: "{적이름}_battle_01"
  character_name: Monster  # 자동 결정됨 — 기본값 그대로 출력
  character_index: 0       # 자동 결정됨 — 기본값 그대로 출력

### shop (상점)
- x: {정수}
  y: {정수}
  name: {상점 NPC 이름}  # 예: "무기상인", "도구점주인"
  type: shop
  trigger: action_button  # 고정 — 변경 금지
  dialogue: "상점 인사 대사"
  items:
    - { item: {아이템 이름}, item_type: item }
    - { item: {무기 이름}, item_type: weapon }
  condition_switch: {스위치 이름}   # 선택 (이 스위치 ON일 때만 상점 오픈)
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

## trigger 규칙 (반드시 준수)

각 타입의 trigger는 고정값이며 변경하면 안 됩니다. trigger 필드를 생략하면 기본값이 적용됩니다.
- npc → action_button (결정키로 대화)
- transfer → player_touch (접촉 시 이동)
- chest → action_button (결정키로 상자 열기)
- battle → player_touch (접촉 시 전투 시작)
- shop → action_button (결정키로 상점 열기)

## 이벤트 이름 규칙

name은 이벤트의 실제 기능과 타입을 반영해야 합니다.
- npc: NPC 이름 또는 역할 (예: "마을촌장", "경비병")
- transfer: "{목적지}_이동" (예: "던전_입구_이동")
- chest: "보물상자_{번호}" (예: "보물상자_01")
- battle: "{적이름}_전투" (예: "고블린_전투", "드래곤_보스전")
- shop: 상점 NPC 이름 (예: "무기상인")
- ending: "엔딩_이벤트"

## battle_switch 규칙

각 battle 이벤트의 battle_switch는 반드시 서로 다른 고유한 이름이어야 합니다.
- 형식: "{적이름}_battle_{번호}" (예: "고블린_battle_01", "고블린_battle_02")
- 여러 battle 이벤트가 같은 battle_switch를 공유하면 안 됩니다

## 이벤트 수 제한

맵당 이벤트는 **최소 5개, 최대 10개**로 제한합니다. 초과 생성 금지.

## 절대 금지 사항

- 이벤트를 10개 초과 생성 금지 — 맵당 5~10개 엄수
- 스위치·아이템·맵을 번호(숫자)로 지정 금지 → 반드시 이름(문자열) 사용
- x, y 좌표가 맵 크기를 벗어나는 것 금지
- 동일한 (x, y)에 이벤트 2개 배치 금지
- to_map에 존재하지 않는 맵 이름 사용 금지
- 제공된 아이템/무기/방어구/적 그룹 목록에 없는 이름 사용 금지
- battle의 troop에 적 이름만 쓰는 것 금지 → 반드시 "이름×숫자" 또는 "이름_단독" 형식 사용
- 같은 맵 내 NPC에 동일한 (character_name + character_index) 조합 반복 금지
  → 예) People1/0 NPC가 이미 있으면 다음 NPC는 People1/1, People2/0 등 다른 조합 사용
  → 맵당 NPC 스프라이트 다양성 확보 필수 (같은 얼굴 NPC 2명 이상 배치 금지)
- trigger 값을 타입별 고정값과 다르게 지정 금지
- 서로 다른 battle 이벤트에 같은 battle_switch 이름 사용 금지
- NPC의 name 및 대화창 화자를 주인공(플레이어 파티) 이름으로 지정 금지 → Human 메시지의 주인공 이름 목록 참고
- dialogue 각 항목은 자연스러운 한 문장 단위로 작성 — 마침표·느낌표·물음표로 문장을 끝맺음하세요

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

  - x: 5
    y: 9
    name: 고블린_전투
    type: battle
    trigger: player_touch
    troop: 고블린 × 2
    escape_allowed: true
    lose_condition: game_over
    on_win:
      - set_switch: 고블린_battle_01
    one_time: true
    battle_switch: 고블린_battle_01

## 스위치 연동 규칙

### 스위치 이름 규칙
- 사전 할당된 스위치를 **우선** 사용할 것 (아래 목록 참조)
- 새 스위치 생성 시: `{목적}_{대상}` 형식 (예: `quest_elder_talked`)
- **절대 같은 개념에 다른 이름을 쓰지 말 것** (예: `고블린_battle_01`과 `고블린_배틀_01`은 다른 스위치)
- 같은 스위치 이름은 맵이 달라도 동일한 게임 상태를 의미함 — 글로벌 범위

### 스위치 연동 패턴
**패턴 1: 보스 처치 → NPC 대화 변경**
- battle의 on_win에서 set_switch로 스위치 ON
- npc의 condition_switch로 같은 스위치를 참조, alt_dialogue로 대체 대사

**패턴 2: NPC 대화 → 다른 이벤트 활성화**
- npc의 set_switch로 스위치 ON
- 다른 이벤트의 condition_switch로 같은 스위치를 참조

**패턴 3: 아이템 전달 퀘스트**
- chest에서 아이템 획득 후 set_switch로 NPC 대화 변경
- npc의 required_item으로 아이템 소지 확인, consume_item: true로 아이템 소비

### 금지 사항
- NPC의 set_switch에 `chest_` 접두어 스위치를 쓰지 말 것 (보물상자 스위치 오염)
- 전투 battle_switch와 on_win.set_switch에 같은 이름을 쓰지 말 것
- 이 맵에서 사용하지 않을 스위치를 임의로 만들지 말 것
"""


def build_event_planner_prompt(
    map_spec: MapSpec,
    game_spec: GameSpec,
    id_table: IdTable,
    switch_table: SwitchTable,
    connection_info: MapConnectionInfo,
    rag_context: str = "",
    map_story: MapStoryScript | None = None,
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
    filtered_troops = _filter_troops_for_map(map_spec.map_type, id_table, game_spec)
    actor_names = ", ".join(id_table.actors.keys()) if id_table.actors else "없음"

    story_section = _build_story_section(map_story) if map_story else ""

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
{story_section}
## 주인공(플레이어 파티) 이름 목록 — NPC 이름으로 절대 사용 금지
{actor_names}
NPC는 위 이름과 다른 고유한 이름을 가져야 합니다. 위 이름을 NPC name 또는 대화창 화자(speaker)로 사용하지 마세요.

## 사용 가능한 이름 목록 (목록에 없는 이름 사용 금지)

스위치 이름 (기할당):
{existing_switches if existing_switches else "  없음"}

아이템: {", ".join(list(id_table.items.keys())[:10])}
무기:   {", ".join(list(id_table.weapons.keys())[:8])}
방어구: {", ".join(list(id_table.armors.keys())[:8])}
적 그룹 (이 맵 타입에 적합한 그룹만 표시):
{filtered_troops}
이동 가능한 맵: {", ".join(id_table.maps.keys())}

## 이벤트 생성 가이드

{_describe_required_events(map_spec, game_spec, id_table)}
{f"{chr(10)}## RPG Maker MZ 기술 참고{chr(10)}{rag_context}{chr(10)}" if rag_context else ""}
YAML 출력:
"""
    return [SystemMessage(content=_SYSTEM), HumanMessage(content=human)]


def _build_story_section(map_story: MapStoryScript) -> str:
    """MapStoryScript → 프롬프트 삽입용 스토리 섹션 텍스트."""
    lines = [
        "",
        "## 스토리 스크립트",
        f"[현재 막: {map_story.act_index + 1}막]",
        f"스토리 역할: {map_story.story_role}",
    ]

    if map_story.npcs:
        lines.append("")
        lines.append("### 이 맵의 NPC 목록 — 반드시 아래 이름과 역할로만 NPC 생성 (임의 이름 금지)")
        for npc in map_story.npcs:
            lines.append(f"- 이름: {npc.name}  역할: {npc.role}")
            if npc.before_dialogue:
                lines.append(f"  기본 대사: {' / '.join(npc.before_dialogue)}")
            if npc.after_dialogue and npc.condition_switch:
                lines.append(
                    f"  조건 후 대사 ({npc.condition_switch} ON 시): "
                    f"{' / '.join(npc.after_dialogue)}"
                )

    if map_story.required_events:
        lines.append("")
        lines.append("### 반드시 포함할 이벤트")
        for ev in map_story.required_events:
            lines.append(f"- {ev}")

    if map_story.story_flags:
        lines.append("")
        lines.append(f"### 이 맵에서 ON해야 하는 스위치: {', '.join(map_story.story_flags)}")

    if map_story.requires_switches:
        lines.append("")
        lines.append(f"### 이 맵이 요구하는 선행 스위치: {', '.join(map_story.requires_switches)}")
        if map_story.gate_transfer:
            lines.append(
                "⚠️ 이 맵으로의 transfer 이벤트에 반드시 condition_switch를 설정하세요. "
                f"condition_switch: {map_story.requires_switches[0]}"
            )

    lines.append("")
    return "\n".join(lines)


def _filter_troops_for_map(
    map_type: str,
    id_table: IdTable,
    game_spec: GameSpec,
) -> str:
    """맵 타입에 맞는 troop 목록만 반환.

    - boss 맵: boss + elite 티어 troop만 (클라이막스 전투)
    - dungeon 맵: weak + normal + elite 티어 troop (보스 제외)
    - town 등 기타: 전체 troop (참고용)
    """
    # 적 이름 → 티어 매핑
    enemy_tier: dict[str, str] = {e.name: e.tier for e in game_spec.enemies}

    def _troop_enemy_name(troop_name: str) -> str:
        """troop 이름에서 적 이름 추출."""
        if "×" in troop_name:
            return troop_name.rsplit("×", 1)[0].rstrip("_").strip()
        if troop_name.endswith("_단독"):
            return troop_name[: -len("_단독")]
        return troop_name

    all_troops = list(id_table.troops.keys())

    if map_type == "boss":
        filtered = [
            t
            for t in all_troops
            if enemy_tier.get(_troop_enemy_name(t), "normal") in ("boss", "elite")
        ]
        label = "보스/엘리트급 (boss/elite 티어)"
    elif map_type == "dungeon":
        filtered = [
            t
            for t in all_troops
            if enemy_tier.get(_troop_enemy_name(t), "normal") in ("weak", "normal", "elite")
        ]
        label = "던전용 (weak/normal/elite 티어, boss 제외)"
    else:
        filtered = all_troops
        label = "전체"

    # 필터 결과가 없으면 전체 반환
    if not filtered:
        filtered = all_troops
        label = "전체 (필터 결과 없어 전체 표시)"

    return f"  [{label}]: {', '.join(filtered)}"


def _describe_required_events(
    spec: MapSpec,
    game_spec: GameSpec,
    id_table: IdTable,
) -> str:
    if spec.map_type == "town":
        return (
            "⚠️ 이벤트 수: 5~8개 (초과 금지)\n"
            "1. NPC 대화 최소 2개 (랜드마크마다 1개, 보스 처치 전후 조건부 대화 권장)\n"
            "2. 상점 이벤트 (상점 랜드마크가 있으면)\n"
            "3. 맵 이동 이벤트 (exits 수만큼, 위 좌표 정보 사용)\n"
            "4. 선택: 보물 상자 1개\n"
            "⚠️ 금지: battle 이벤트 생성 금지 — town은 안전 지역\n"
            "⚠️ 금지: ending 이벤트 생성 금지 — 엔딩은 boss 맵 전용"
        )
    elif spec.map_type == "dungeon":
        return (
            "⚠️ 이벤트 수: 5~8개 (초과 금지)\n"
            "1. 맵 이동 이벤트 (입구/출구, 위 좌표 정보 사용)\n"
            "2. 전투 이벤트 2~3개 (player_touch, one_time=true)\n"
            "3. 보물 상자 1~2개 (chest 타입)\n"
            "4. 선택: 경고 NPC 1개\n"
            "⚠️ 금지: ending 이벤트 생성 금지 — 엔딩은 boss 맵 전용\n"
            "⚠️ 스위치: 전투 battle_switch는 맵 고유 이름 사용 "
            "(예: {맵이름}_고블린_battle). 다른 맵과 절대 중복 금지"
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
            "⚠️ 이벤트 수: 5~7개 (초과 금지)\n"
            f"1. 보스 전투 이벤트 필수 (type: battle, troop: {troop_key}, "
            f"lose_condition: game_over, battle_switch: {boss_name}_defeated)\n"
            f"2. 엔딩 이벤트 필수 (type: ending, condition_switch: {boss_name}_defeated, "
            f"action: title)\n"
            "3. 맵 이동 이벤트 (탈출용)\n"
            "4. 선택: NPC 1~2개, 보물 상자 1~2개\n"
            "   ⚠️ battle 이벤트와 ending 이벤트의 x, y 좌표는 반드시 달라야 함\n"
            "   ⚠️ 엔딩은 이 맵에만 1개 — 다른 맵에 엔딩 이벤트 중복 생성 금지"
        )
    return "맵 타입에 맞는 이벤트 5~10개 (초과 금지)"
