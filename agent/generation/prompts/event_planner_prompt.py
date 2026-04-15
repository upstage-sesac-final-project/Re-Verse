"""F 노드 — event_planner 프롬프트 빌더.

canonical: docs/The_world/prompt_engineering.md §F. 이벤트 기획자
canonical: docs/The_world/game_ending_design.md
"""

import re
from functools import cache

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent.generation.models import GameSpec, MapConnectionInfo, MapScreenplay, MapSpec
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
    # ⚠️ condition_switch는 반드시 set_switch와 다른 값을 사용하세요.
    # ⚠️ set_switch와 같은 값이면 대화 즉시 alt_dialogue가 표시됩니다 (의도치 않은 동작).
    # ⚠️ 보스 처치 후 대사를 보여주려면: condition_switch: "{보스_이름}_defeated"
    # 예시: NPC가 "보스를 물리쳐 오세요"라고 하고, 보스 처치 후 "해냈군요!"를 보여주려면
    #   set_switch: "지역명_npc1_talked"  ← 대화 후 켜지는 퀘스트 수락 스위치
    #   condition_switch: "보스이름_defeated"  ← 보스 처치 후에만 alt_dialogue 표시
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
  character_name: "!Crystal"  # 워프 마커 스프라이트 (아래 가이드 참고)
  character_index: 0          # 스프라이트 인덱스
  condition_switch: {스위치 이름}  # 선택 — 이 스위치 ON일 때만 이동 허용 (진입 조건)
  blocked_message: "아직 갈 수 없다."  # 선택 — condition_switch 미충족 시 표시 메시지

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
  character_name: "!Chest"  # 보물상자 스프라이트 (!Chest 고정)
  character_index: 0        # 0=빨강(기본), 1=금색(귀중품), 2=초록(자연·던전), 3=파랑(마법·특별)
  condition_switch: {스위치 이름}  # 선택 — 이 스위치 ON일 때만 보물 상자 등장

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
  character_name: People1  # 상점 NPC 스프라이트 — index로 외형 선택
  character_index: 0       # 추천: People4/4=쾌활상인·여관주인, People4/0=학자형상점주인,
  # People2/6=모험가상인, People2/7=발명가상인, People1/4=중년상인남

### gate (NPC 문지기 → 워프 전환, 맵 이동 조건 게이트)
- x: {정수}
  y: {정수}
  name: {게이트 이름}  # 예: "던전_입구_게이트", "마을_출구_문지기"
  type: gate
  to_map: {맵 이름}
  to_x: {정수}
  to_y: {정수}
  direction: retain
  keeper_character_name: People1  # 조건 미충족 시 NPC 스프라이트
  keeper_character_index: 6
  condition_switches:           # 1~2개 스위치 (모두 ON이어야 워프 활성화)
    - {스위치1 이름}
    - {스위치2 이름}
  stage_dialogues:              # 조건별 힌트 대사 (condition_switches 수만큼)
    - "아직 준비가 안 됐어. 먼저 안내를 받아."
    - "아이템을 획득해야 이곳을 통과할 수 있어."
  gate_character_name: "!Crystal"  # 조건 충족 시 워프 스프라이트
  gate_character_index: 0

**gate 사용 규칙:**
- 맵 이동 출구에는 반드시 gate 타입을 사용하세요 (transfer 대신).
- condition_switches는 스토리 스크립트의 departure_conditions 목록을 그대로 사용하세요.
- stage_dialogues 수는 condition_switches 수와 반드시 동일하게 작성하세요 (더 많거나 적으면 안 됨).
  예: condition_switches 2개 → stage_dialogues 2개 (초과 작성 금지)

### quest_chest (퀘스트 완료 → 보물상자 전환)
- x: {정수}
  y: {정수}
  name: {보물상자 이름}
  type: quest_chest
  quest_type: npc  # npc | battle
  quest_switch: {퀘스트 완료 스위치}  # 퀘스트 완료 시 ON되는 스위치
  # NPC 퀘스트 (quest_type: npc)
  quest_dialogue:
    - "이 보물은 내가 지키고 있어. 도움을 주면 열어줄게."
  quest_character_name: People1
  quest_character_index: 3
  # 몬스터 퀘스트 (quest_type: battle) — 승리 시에만 보물상자 등장
  # quest_type: battle
  # troop: {적 그룹 이름}
  # escape_allowed: true   # 도망가면 몬스터 유지
  # lose_condition: game_over  # 패배해도 몬스터 유지
  # battle_character_name: Monster
  # battle_character_index: 3
  # 보물상자 공통
  item: {아이템/무기/방어구 이름}
  item_type: weapon  # item | weapon | armor
  amount: 1
  chest_switch: {상자_열림_스위치}  # one_time 처리용
  dialogue_before: "빛나는 상자가 나타났다!"
  dialogue_after: "검을 손에 넣었다!"
  chest_character_name: "!Chest"
  chest_character_index: 1

**quest_chest 사용 규칙:**
- 무기/방어구/핵심 아이템은 반드시 quest_chest로 지급하세요 (chest 타입 대신).
- quest_type: npc → NPC가 퀘스트를 주고 대화 후 보물상자로 전환
- quest_type: battle → 몬스터를 처치해야 보물상자 등장 (도망/패배 시 몬스터 유지)
- quest_switch는 게이트(gate)의 condition_switches로 연결하여 진행 조건으로 활용하세요.

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

## 절대 금지 사항

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

YAML만 출력하세요. 설명 불필요.
- type 필드는 반드시 첫 번째로 작성
- dialogue, on_win 등 중첩 리스트 항목은 상위 필드보다 2칸 들여쓰기
반드시 아래 형식으로:

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
"""

# ── 맵 타입별 허용 이벤트 섹션 ──────────────────────────────────────────────
_ALLOWED_SECTIONS: dict[str, frozenset[str]] = {
    "town": frozenset({"npc", "transfer", "chest", "shop", "gate", "quest_chest"}),
    "dungeon": frozenset({"npc", "transfer", "chest", "battle", "gate", "quest_chest"}),
    "boss": frozenset({"npc", "battle", "ending", "quest_chest"}),
    "field": frozenset({"npc", "transfer", "chest", "battle", "gate", "quest_chest"}),
}
_ALLOWED_SECTIONS_DEFAULT = frozenset(
    {"npc", "transfer", "chest", "battle", "shop", "gate", "quest_chest", "ending"}
)

# ── _SYSTEM 파싱 (모듈 로드 시 1회) ─────────────────────────────────────────
_footer_idx = _SYSTEM.find("\n## trigger 규칙")
_SYSTEM_FOOTER = _SYSTEM[_footer_idx:] if _footer_idx >= 0 else ""
_body = _SYSTEM[:_footer_idx] if _footer_idx >= 0 else _SYSTEM

_SYSTEM_HEADER, *_section_parts = re.split(r"\n### ", _body)
_SYSTEM_SECTIONS: dict[str, str] = {}
for _part in _section_parts:
    _sec_name = _part.split()[0]  # "npc", "transfer", "chest", ...
    _SYSTEM_SECTIONS[_sec_name] = "\n### " + _part


@cache
def _build_system_prompt(map_type: str) -> str:
    """맵 타입별 슬림화된 시스템 프롬프트 반환.

    해당 맵 타입에서 등장할 수 없는 이벤트 타입 가이드를 제거하여
    토큰 수를 줄인다. map_type은 town/dungeon/boss/field 4가지뿐이므로
    lru_cache로 캐싱하여 매 호출마다 문자열 재조립을 방지한다.
    """
    allowed = _ALLOWED_SECTIONS.get(map_type, _ALLOWED_SECTIONS_DEFAULT)
    sections = "".join(v for k, v in _SYSTEM_SECTIONS.items() if k in allowed)
    return _SYSTEM_HEADER + sections + _SYSTEM_FOOTER


def build_event_planner_prompt(
    map_spec: MapSpec,
    game_spec: GameSpec,
    id_table: IdTable,
    switch_table: SwitchTable,
    connection_info: MapConnectionInfo,
    rag_context: str = "",
    map_story: MapScreenplay | None = None,
    feedback: str | None = None,
) -> list[BaseMessage]:
    # 목적지 맵 타입 조회용 (game_spec.maps 기반)
    game_map_types: dict[str, str] = {gm.name: gm.type for gm in game_spec.maps}

    # 출구를 forward/backward로 분류
    # forward: town→dungeon/field/boss, dungeon/field→dungeon/field/boss
    # backward: dungeon/field→town
    _forward_types = {"dungeon", "field", "boss"}
    forward_exits: list[tuple[int, int, str]] = []  # (x, y, to_name)
    backward_exits: list[tuple[int, int, str]] = []  # (x, y, to_name)

    for tile in connection_info.exit_tiles:
        to_map_id = tile.get("to_map_id")
        ex, ey = tile.get("x", 0), tile.get("y", 0)
        to_name = next(
            (name for name, mid in id_table.maps.items() if mid == to_map_id),
            f"Map{to_map_id}",
        )
        to_type = game_map_types.get(to_name, "dungeon")
        if to_type in _forward_types:
            forward_exits.append((ex, ey, to_name))
        else:
            backward_exits.append((ex, ey, to_name))

    # 출구 안내 구성 — forward 1개만 gate, backward는 transfer(조건 없음)
    exit_lines: list[str] = []

    if map_spec.map_type == "boss":
        exit_lines.append("없음 — boss 맵은 엔딩으로 종료, 맵 이동 이벤트 생성 금지")
    else:
        # forward: 첫 번째만 gate 대상, 나머지는 무시
        if forward_exits:
            ex, ey, to_name = forward_exits[0]
            exit_lines.append(
                f"▶ [gate 필수, 1개만] 좌표 ({ex}, {ey}) → '{to_name}'\n"
                f"  to_map: {to_name}, to_x: {ex}, to_y: 1\n"
                f"  → departure_conditions 스위치 충족 시 이동하는 gate 이벤트 생성"
            )
            for ex, ey, to_name in forward_exits[1:]:
                exit_lines.append(
                    f"✗ [무시] 좌표 ({ex}, {ey}) → '{to_name}' — 이벤트 생성 금지 (gate 중복 불가)"
                )
        # backward: 조건 없는 transfer
        for ex, ey, to_name in backward_exits:
            exit_lines.append(
                f"◀ [transfer 필수, 조건 없음] 좌표 ({ex}, {ey}) → '{to_name}'\n"
                f"  to_map: {to_name}, to_x: {ex}, to_y: 1\n"
                f"  → condition_switch 없이 항상 이동 가능한 transfer 이벤트 생성"
            )

    landmarks_text = "\n".join(
        f"- {lm.name} ({lm.position_hint})" + (f" — NPC: {lm.npc}" if lm.npc else "")
        for lm in map_spec.landmarks
    )

    existing_switches = "\n".join(f"  - {s}" for s in switch_table.switches)
    filtered_troops = _filter_troops_for_map(map_spec.map_type, id_table, game_spec)
    actor_names = ", ".join(id_table.actors.keys()) if id_table.actors else "없음"

    story_section = _build_story_section(map_story, map_spec) if map_story else ""

    human = f"""\
## 맵 정보
이름: {map_spec.name}
타입: {map_spec.map_type}
크기: 가로={map_spec.width}, 세로={map_spec.height}  ← x: 0~{map_spec.width - 1}, y: 0~{map_spec.height - 1}
분위기: {map_spec.atmosphere}

## 랜드마크
{landmarks_text if landmarks_text else "없음"}

## 맵 연결 정보 — 반드시 아래 구분대로만 이벤트 생성
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
{f"{chr(10)}## RPG Maker MZ 기술 참고{chr(10)}{rag_context}{chr(10)}" if rag_context else ""}\
{f"{chr(10)}## 이전 시도 오류 피드백 — 아래 오류를 반드시 수정하세요{chr(10)}{feedback}{chr(10)}" if feedback else ""}
YAML 출력:
"""
    return [
        SystemMessage(content=_build_system_prompt(map_spec.map_type)),
        HumanMessage(content=human),
    ]


def _build_story_section(map_story: MapScreenplay, map_spec: "MapSpec | None" = None) -> str:
    """MapScreenplay → 프롬프트 삽입용 대본 섹션 텍스트.

    대본(narrative) + 이벤트 체크리스트를 event_planner가 읽기 쉽게 변환한다.
    체크리스트에 있는 항목만 이벤트로 구현하도록 명확히 지시한다.
    """
    lines = [
        "",
        "## 대본 (Story Screenplay)",
        f"{map_story.narrative}",
    ]

    # ── NPC 체크리스트 ────────────────────────────────────────────────────────
    if map_story.npcs:
        lines.append("")
        lines.append("### [체크리스트 1] NPC — 아래 목록 그대로 생성 (임의 추가/이름 변경 금지)")
        for npc in map_story.npcs:
            lines.append(f"- 이름: {npc.name}  역할: {npc.role}")
            if npc.dialogues:
                lines.append(f"  대사: {' / '.join(npc.dialogues)}")
            if npc.set_switch:
                lines.append(
                    f"  ★ set_switch: {npc.set_switch}  "
                    f"← 대화 완료 후 이 스위치 ON"
                    f" (아래 quest_chest의 quest_switch로 연결됨)"
                )

    # ── 아이템 획득 체크리스트 ────────────────────────────────────────────────
    if map_story.acquisitions:
        lines.append("")
        lines.append(
            "### [체크리스트 2] 아이템 획득 — 아래 항목 전부 quest_chest로 생성 (생략 금지)"
        )
        lines.append("⚠️ chest_switch가 게이트 조건입니다. 이 이벤트 없으면 탈출 영구 불가")

        # 맵 타입별 quest_type 결정:
        # - boss맵: quest_type=npc, quest_switch={boss}_defeated
        # - town맵: quest_type=npc, quest_switch={npc_set_switch}
        # - dungeon/field맵: quest_type=battle, quest_switch={item}_battle_won (NPC set_switch와 분리!)
        is_boss_map = map_story.has_boss and map_story.boss_name
        map_type = map_spec.map_type if map_spec else "dungeon"
        use_battle_type = not is_boss_map and map_type in ("dungeon", "field")
        npc_set_switches = [npc.set_switch for npc in map_story.npcs if npc.set_switch]

        if is_boss_map:
            boss_defeated_sw = f"{map_story.boss_name}_defeated"
            lines.append(
                f"⚠️ 보스맵 아이템: quest_switch = {boss_defeated_sw} (보스 격파 후 상자 등장)"
            )
            lines.append("⚠️ quest_type: npc 사용 (battle 타입 사용 금지 — troop 필드 없음)")
        elif use_battle_type:
            lines.append("⚠️ 던전/필드 아이템: quest_type = battle 사용")
            lines.append(
                "⚠️ quest_switch = {아이템명}_battle_won 형식 사용 (NPC set_switch 재사용 금지!)"
            )
            lines.append("   → NPC set_switch와 별도 독립 스위치 — LLM이 임의로 변경 금지")
        else:
            lines.append("⚠️ quest_switch = 위 NPC의 set_switch 사용 (NPC 대화 후 상자 등장)")

        for i, acq in enumerate(map_story.acquisitions):
            if is_boss_map:
                quest_sw = f"{map_story.boss_name}_defeated"
                quest_type_hint = "npc"
            elif use_battle_type:
                quest_sw = f"{acq.item_name}_battle_won"
                quest_type_hint = "battle"
            else:
                quest_sw = (
                    npc_set_switches[i]
                    if i < len(npc_set_switches)
                    else (npc_set_switches[0] if npc_set_switches else "quest_완료")
                )
                quest_type_hint = "npc"
            lines.append(
                f"- item: {acq.item_name}  item_type: {acq.item_type}"
                f"  quest_type: {quest_type_hint}"
                f"  chest_switch: {acq.chest_switch}  ← 반드시 이 이름 그대로 사용"
                f"  quest_switch: {quest_sw}  ← 반드시 이 이름 그대로 사용"
            )

    # ── 이동 체크리스트 ───────────────────────────────────────────────────────
    forward_moves = [m for m in map_story.moves if m.direction == "forward"]
    backward_moves = [m for m in map_story.moves if m.direction == "backward"]

    if forward_moves or backward_moves:
        lines.append("")
        lines.append("### [체크리스트 3] 이동 이벤트 — 아래 항목만 생성 (추가 생성 금지)")

    for mv in forward_moves:
        lines.append(
            f"- ▶ {mv.to_map_name}으로 이동 (gate) — 조건: 이 맵 아이템 획득 완료\n"
            f"  ※ 이동 이벤트는 코드가 자동 생성합니다. 직접 생성하지 마세요."
        )

    for mv in backward_moves:
        lines.append(
            f"- ◀ {mv.to_map_name}으로 귀환 (transfer, 조건 없음)\n"
            f"  ※ 이동 이벤트는 코드가 자동 생성합니다. 직접 생성하지 마세요."
        )

    # ── 보스 ─────────────────────────────────────────────────────────────────
    if map_story.has_boss and map_story.boss_name:
        lines.append("")
        lines.append("### [체크리스트 4] 보스 전투 + 엔딩")
        lines.append(f"- 보스: {map_story.boss_name}")
        lines.append("  type: battle (보스 전투) + type: ending (보스 처치 후 자동 실행)")
        lines.append(
            "  ⚠️ gate/transfer 이벤트 생성 금지 — 이동 이벤트는 코드가 자동 생성, 직접 생성 금지"
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
    elif map_type in ("dungeon", "field"):
        filtered = [
            t
            for t in all_troops
            if enemy_tier.get(_troop_enemy_name(t), "normal") in ("weak", "normal", "elite")
        ]
        label = "던전/필드용 (weak/normal/elite 티어, boss 제외)"
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
    """맵 타입별 이벤트 생성 가이드. 대본 체크리스트를 보완하는 구현 규칙."""
    if spec.map_type == "town":
        return (
            "## 구현 규칙 (대본 체크리스트 기준)\n"
            "- [체크리스트 1] NPC → npc 타입 이벤트로 1:1 생성 (대사·set_switch 그대로)\n"
            "- [체크리스트 2] 아이템 → quest_chest 타입으로 1:1 생성 (chest_switch 그대로)\n"
            "  quest_type: npc (NPC 대화 → 보물상자 등장)\n"
            "- 상점 이벤트 (상점 랜드마크 있으면 선택)\n"
            "⚠️ 체크리스트에 없는 NPC/아이템 이벤트 추가 생성 금지\n"
            "⚠️ gate/transfer/battle/ending 이벤트 직접 생성 금지\n"
            "   — 이동 이벤트는 코드가 자동 생성하므로 YAML에 포함하지 마세요"
        )
    elif spec.map_type in ("dungeon", "field"):
        return (
            "## 구현 규칙 (대본 체크리스트 기준)\n"
            "- [체크리스트 1] NPC → npc 타입 이벤트로 1:1 생성 (있는 경우)\n"
            "- [체크리스트 2] 아이템 → quest_chest 타입으로 1:1 생성 (chest_switch 그대로)\n"
            "  quest_type: battle 권장 (전투 승리 → 보물상자 등장)\n"
            "  ⚠️ 이 이벤트 없으면 게이트 스위치 ON 불가 → 탈출 영구 불가\n"
            "- 전투 이벤트 1~2개 추가 가능 (battle 타입, one_time=true)\n"
            "⚠️ 체크리스트에 없는 NPC/아이템 이벤트 추가 생성 금지\n"
            "⚠️ gate/transfer/ending 이벤트 직접 생성 금지\n"
            "   — 이동 이벤트는 코드가 자동 생성하므로 YAML에 포함하지 마세요"
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
            "## 구현 규칙 (대본 체크리스트 기준)\n"
            f"- [체크리스트 4] 보스 전투 (type: battle, troop: {troop_key}, "
            f"lose_condition: game_over, battle_switch: {boss_name}_defeated)\n"
            f"- 엔딩 이벤트 (type: ending, condition_switch: {boss_name}_defeated, action: title)\n"
            "⚠️ gate/transfer 이벤트 직접 생성 금지 — 이동 이벤트는 코드가 자동 생성\n"
            "⚠️ battle과 ending의 x, y 좌표는 반드시 달라야 함"
        )
    return "맵 타입에 맞는 이벤트 생성 (대본 체크리스트 참고)"
