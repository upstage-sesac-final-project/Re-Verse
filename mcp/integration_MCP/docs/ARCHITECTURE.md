# RPGMakerMZ MCP Server - 아키텍처 & 기능 문서

## 1. 프로젝트 개요

RPG Maker MZ 프로젝트를 AI가 프로그래밍적으로 조작할 수 있게 해주는 **MCP (Model Context Protocol) 서버**.
AI 어시스턴트(Claude, Gemini 등)가 대화를 통해 RPG Maker MZ 게임을 자동으로 제작/수정할 수 있다.

```
┌─────────────────┐     JSON-RPC (stdin/stdout)     ┌──────────────────┐
│  AI Assistant    │ ◄──────────────────────────────► │  MCP Server      │
│  (Claude 등)     │       MCP Protocol               │  (index.ts)      │
└─────────────────┘                                   └────────┬─────────┘
                                                               │
                                                    ┌──────────┴──────────┐
                                                    │   Handler Layer     │
                                                    │  ┌────────────────┐ │
                                                    │  │ project.ts     │ │
                                                    │  │ events.ts      │ │
                                                    │  │ database.ts    │ │
                                                    │  │ map.ts         │ │
                                                    │  │ plugins.ts     │ │
                                                    │  │ playtest.ts    │ │
                                                    │  │ undo.ts        │ │
                                                    │  └────────────────┘ │
                                                    └──────────┬──────────┘
                                                               │
                                                    ┌──────────┴──────────┐
                                                    │  RPG Maker MZ       │
                                                    │  Project Files      │
                                                    │  (JSON/JS/Assets)   │
                                                    └─────────────────────┘
```

---

## 2. 디렉토리 구조

```
RPGMakerMZ_MCP/
├── index.ts                 # 진입점 - MCP 서버 초기화 & 라우팅
├── toolSchemas.ts           # 28개 도구의 입력 스키마 정의
├── handlers/                # 핵심 비즈니스 로직
│   ├── project.ts           # 프로젝트 정보, 데이터 파일, 에셋 관리
│   ├── events.ts            # 이벤트 커맨드 조작 (대화, 선택지 등)
│   ├── database.ts          # 액터/아이템/스킬 DB 관리
│   ├── map.ts               # 맵 생성, 타일 배치
│   ├── plugins.ts           # 플러그인 파일 & 설정 관리
│   ├── playtest.ts          # 게임 실행 & 스크린샷 캡처
│   └── undo.ts              # 백업 & 되돌리기
├── utils/                   # 유틸리티
│   ├── backup.ts            # 자동 백업/롤백 시스템
│   ├── validation.ts        # 경로 검증, 보안 체크
│   ├── mapHelpers.ts        # 맵 데이터 로드/저장
│   ├── playtestHelpers.ts   # Puppeteer 스크린샷
│   ├── gameStateInspector.ts # 게임 상태 검사 (화이트리스트)
│   ├── commandAnnotator.js  # 이벤트 코드 → 사람이 읽을 수 있는 설명
│   ├── constants.js         # 이벤트 코드, 경로, 제한값
│   ├── errors.js            # 에러 코드 & MCPError 클래스
│   └── logger.js            # stderr 로깅 (MCP 호환)
├── types/index.d.ts         # TypeScript 타입 정의
├── schemas/mz_structures.js # Zod 검증 스키마
├── resources/               # AI 참조용 정적 리소스
│   └── event_commands.json  # 이벤트 커맨드 레퍼런스
└── test_project/            # 테스트용 샘플 MZ 프로젝트
```

---

## 3. 동작 원리

### 3.1 MCP 프로토콜 통신

```
AI Client                    MCP Server
   │                            │
   │──── ListTools ────────────►│  "어떤 도구 있어?"
   │◄─── 28개 도구 스키마 ──────│
   │                            │
   │──── CallTool ─────────────►│  "add_dialogue 실행해줘"
   │     {name, arguments}      │
   │                            │  1. toolMap에서 핸들러 찾기
   │                            │  2. 핸들러 실행
   │                            │  3. 결과 반환
   │◄─── Result ────────────────│
   │     {content: [{text}]}    │
```

- **통신**: stdin/stdout으로 JSON-RPC 메시지 교환
- **로깅**: stderr로만 출력 (stdout 오염 방지)
- **에러 처리**: 모든 핸들러에서 try-catch → isError 플래그 반환

### 3.2 핸들러 실행 흐름

```typescript
// index.ts의 CallTool 핸들러
const handler = toolMap[name];      // 이름으로 핸들러 함수 매핑
return await handler(args);          // 타입된 인자로 핸들러 호출
```

### 3.3 자동 백업 시스템

```
write_data_file("Actors.json", newContent)
  │
  ├── 1. 기존 파일 → Actors.json.1710000000000.bak 복사
  ├── 2. newContent를 Actors.json에 쓰기
  ├── 3. 오래된 백업 정리 (최근 5개만 유지)
  └── 4. 쓰기 실패 시 → 백업에서 자동 롤백
```

---

## 4. 전체 기능 목록 (28개 도구)

### 4.1 프로젝트 분석 (Phase 1)

| 도구 | 기능 | 원리 |
|------|------|------|
| `get_project_info` | 프로젝트 메타정보 조회 | System.json 파싱 → gameTitle, versionId 등 반환 |
| `list_data_files` | 데이터 파일 목록 | data/ 디렉토리 스캔, .json 파일 필터링 |
| `read_data_file` | 데이터 파일 읽기 | 경로 순회 공격 방지 후 JSON 파일 읽기 |
| `write_data_file` | 데이터 파일 쓰기 | 자동 백업 생성 → 파일 쓰기 → 실패 시 롤백 |
| `search_events` | 이벤트 텍스트 검색 | CommonEvents.json + 모든 MapXXX.json 재귀 탐색 |

### 4.2 에셋 관리 (Phase 2)

| 도구 | 기능 | 원리 |
|------|------|------|
| `list_assets` | 이미지/오디오 목록 | img/, audio/ 디렉토리 재귀 스캔 |
| `check_assets_integrity` | 에셋 무결성 검사 | 참조된 이미지 존재 여부 + 고아 맵 파일 탐지 |

### 4.3 플러그인 관리 (Phase 3)

| 도구 | 기능 | 원리 |
|------|------|------|
| `write_plugin_code` | 플러그인 .js 파일 생성 | 파일명 검증(영숫자/_/-만) → js/plugins/ 에 쓰기 |
| `get_plugins_config` | 플러그인 설정 읽기 | plugins.js에서 `$plugins = [...]` 정규식 추출 |
| `update_plugins_config` | 플러그인 설정 변경 | plugins.js 전체 재생성 |

### 4.4 이벤트 조작 (Phase 4) - 추상화 레이어

| 도구 | 기능 | 원리 |
|------|------|------|
| `get_event_page` | 이벤트 페이지 조회 | 커맨드 목록 + annotateCommand()로 사람이 읽을 수 있는 설명 첨부 |
| `add_dialogue` | 대화 추가 | SHOW_TEXT(101) + TEXT_DATA(401) 커맨드 삽입 |
| `add_choice` | 선택지 추가 | SHOW_CHOICES(102) + CHOICE_WHEN(402) + CHOICE_END(404) 구조 생성 |
| `add_loop` | 반복문 추가 | LOOP(112) + REPEAT_ABOVE(413) 쌍 삽입 |
| `add_break_loop` | 반복 탈출 추가 | BREAK_LOOP(113) 커맨드 삽입 |
| `add_conditional_branch` | 조건 분기 추가 | CONDITIONAL_BRANCH(111) + ELSE(411) + END(412) 구조 생성 |
| `delete_event_command` | 커맨드 삭제 | 인덱스 기반 splice |
| `update_event_command` | 커맨드 수정 | 인덱스 기반 교체 |
| `show_picture` | 그림 표시 추가 | SHOW_PICTURE(231) 커맨드 삽입 |

### 4.5 데이터베이스 관리

| 도구 | 기능 | 원리 |
|------|------|------|
| `add_actor` | 액터 추가 | Actors.json에 자동 ID 부여 후 기본값 채워서 추가 |
| `add_item` | 아이템 추가 | Items.json에 자동 ID + 가격/소비/범위 등 설정 |
| `add_skill` | 스킬 추가 | Skills.json에 자동 ID + MP/TP 코스트, 데미지 공식 설정 |

### 4.6 맵 관리

| 도구 | 기능 | 원리 |
|------|------|------|
| `draw_map_tile` | 타일 배치 | 배열 인덱스 계산: `(layer * height + y) * width + x` |
| `create_map` | 새 맵 생성 | MapXXX.json 생성 + MapInfos.json에 엔트리 등록 |

### 4.7 테스트 & 자동화 (Phase 5)

| 도구 | 기능 | 원리 |
|------|------|------|
| `run_playtest` | 게임 실행 & 스크린샷 | Game.exe(--remote-debugging-port) 또는 브라우저 폴백 → Puppeteer로 스크린샷 |
| `inspect_game_state` | 게임 상태 조회 | 화이트리스트 검증 → Puppeteer로 JS 실행 ($gameVariables 등) |

### 4.8 백업 & 복원 (Phase 6)

| 도구 | 기능 | 원리 |
|------|------|------|
| `undo_last_change` | 마지막 변경 되돌리기 | .{timestamp}.bak 파일에서 최신 백업 복원 |
| `list_backups` | 백업 목록 조회 | 타임스탬프별 백업 파일 나열 |

---

## 5. 핵심 설계 원칙

### 5.1 추상화 레이어
AI가 RPG Maker MZ의 내부 구조를 몰라도 사용 가능:
- `add_dialogue("안녕하세요!")` → 내부적으로 code 101/401 커맨드 자동 생성
- `add_choice(["싸운다", "도망간다"])` → 102/402/404 구조 자동 생성

### 5.2 안전성
- **경로 순회 방지**: `path.normalize()` + `fs.realpath()` + 디렉토리 범위 검증
- **코드 실행 화이트리스트**: `inspect_game_state`는 `$gameVariables.value(N)` 등 허용된 패턴만 실행
- **자동 백업**: 모든 쓰기 작업에 백업 자동 생성, 실패 시 자동 롤백
- **파일명 검증**: 플러그인명은 영숫자/밑줄/하이픈만 허용

### 5.3 AI 친화적 설계
- `commandAnnotator.js`로 이벤트 코드에 사람이 읽을 수 있는 설명 자동 첨부
- `mz://docs/event_commands` 리소스로 AI가 이벤트 코드 참조 가능 (할루시네이션 방지)
- 에러 메시지에 에러 코드 포함 (E1000~E1699)

---

## 6. 보안 모델

```
┌─────────────────────────────────────────────┐
│ Layer 1: 입력 검증                           │
│  - Zod 스키마 검증                           │
│  - 파일명 sanitize (alphanumeric만)          │
│  - 파라미터 범위 체크                         │
├─────────────────────────────────────────────┤
│ Layer 2: 경로 보안                           │
│  - path.normalize() → ".." 방지              │
│  - fs.realpath() → 심볼릭 링크 해결          │
│  - 프로젝트 디렉토리 범위 내 접근만 허용       │
├─────────────────────────────────────────────┤
│ Layer 3: 실행 보안                           │
│  - inspect_game_state 화이트리스트           │
│  - 스크립트 길이 100자 제한                   │
│  - ID 범위 1-9999                            │
├─────────────────────────────────────────────┤
│ Layer 4: 데이터 보호                         │
│  - 모든 쓰기에 자동 백업                      │
│  - 실패 시 자동 롤백                          │
│  - 최근 5개 백업 유지                         │
└─────────────────────────────────────────────┘
```

---

## 7. 에러 코드 체계

| 범위 | 카테고리 | 예시 |
|------|----------|------|
| E1000-1099 | 프로젝트 검증 | 경로 없음, game.rmmzproject 없음 |
| E1100-1199 | 맵 에러 | 맵 파일 없음, 이벤트 없음, 페이지 없음 |
| E1200-1299 | 데이터 파일 | 읽기/쓰기 실패, 잘못된 JSON |
| E1300-1399 | 에셋 에러 | 에셋 없음, 잘못된 경로 |
| E1400-1499 | 플러그인 에러 | 잘못된 파일명, 쓰기 실패 |
| E1500-1599 | 검증 에러 | 잘못된 파라미터, 필수값 누락 |
| E1600-1699 | 런타임 에러 | 작업 실패 |

---

## 8. Solar Pro 2 연동 방안

### 8.1 Solar Pro 2란?
업스테이지(Upstage)의 한국어 특화 LLM. MCP 클라이언트로 사용하려면 MCP 프로토콜을 지원하는 환경이 필요.

### 8.2 연동 아키텍처

#### 방법 A: MCP 호환 클라이언트 경유 (권장)

```
┌─────────────┐     API      ┌──────────────┐    MCP     ┌──────────────┐
│ Solar Pro 2 │ ◄──────────► │ 중간 서버     │ ◄────────► │ RPGMakerMZ   │
│ (Upstage)   │   HTTP/REST  │ (Bridge)     │  stdin/out  │ MCP Server   │
└─────────────┘              └──────────────┘             └──────────────┘
```

중간 브릿지 서버가 하는 일:
1. Solar Pro 2에서 응답 받기 (tool_use 포맷)
2. MCP 서버에 JSON-RPC로 도구 호출 전달
3. 결과를 Solar Pro 2에 다시 전달

#### 방법 B: Function Calling 직접 사용

Solar Pro 2가 OpenAI 호환 Function Calling을 지원한다면:

```python
# Solar Pro 2 Function Calling 예시
import openai

client = openai.OpenAI(
    api_key="your-upstage-api-key",
    base_url="https://api.upstage.ai/v1/solar"
)

# MCP 도구를 OpenAI Function 형식으로 변환
tools = [
    {
        "type": "function",
        "function": {
            "name": "add_dialogue",
            "description": "이벤트에 대화 텍스트를 추가합니다",
            "parameters": {
                "type": "object",
                "properties": {
                    "projectPath": {"type": "string"},
                    "mapId": {"type": "number"},
                    "eventId": {"type": "number"},
                    "pageIndex": {"type": "number"},
                    "insertPosition": {"type": "number"},
                    "text": {"type": "string"},
                    "face": {"type": "string"},
                    "faceIndex": {"type": "number"}
                },
                "required": ["projectPath", "mapId", "eventId", "pageIndex",
                             "insertPosition", "text"]
            }
        }
    },
    # ... 나머지 27개 도구도 동일 형식으로 변환
]

response = client.chat.completions.create(
    model="solar-pro2",
    messages=[
        {"role": "system", "content": "당신은 RPG Maker MZ 게임 개발을 도와주는 AI입니다."},
        {"role": "user", "content": "마을 입구에 NPC를 추가하고 '환영합니다!' 대화를 넣어줘"}
    ],
    tools=tools,
    tool_choice="auto"
)

# Solar Pro 2의 tool_call을 MCP 서버로 전달
if response.choices[0].message.tool_calls:
    for tool_call in response.choices[0].message.tool_calls:
        # MCP 서버에 JSON-RPC 호출
        result = call_mcp_tool(
            name=tool_call.function.name,
            arguments=json.loads(tool_call.function.arguments)
        )
```

#### 방법 C: Agent 루프 구현

```python
import subprocess
import json

class RPGMakerAgent:
    """Solar Pro 2 + RPGMakerMZ MCP 에이전트"""

    def __init__(self, project_path: str):
        self.project_path = project_path
        # MCP 서버를 자식 프로세스로 실행
        self.mcp_process = subprocess.Popen(
            ["npx", "-y", "@rein634/rpg-maker-mz-mcp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        self._initialize_mcp()

    def _initialize_mcp(self):
        """MCP 핸드셰이크"""
        self._send_jsonrpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "solar-pro2-agent", "version": "1.0.0"}
        })

    def _send_jsonrpc(self, method: str, params: dict) -> dict:
        """MCP 서버에 JSON-RPC 메시지 전송"""
        msg = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        }) + "\n"
        self.mcp_process.stdin.write(msg.encode())
        self.mcp_process.stdin.flush()
        response = self.mcp_process.stdout.readline()
        return json.loads(response)

    def call_tool(self, name: str, args: dict) -> str:
        """MCP 도구 호출"""
        args["projectPath"] = self.project_path
        result = self._send_jsonrpc("tools/call", {
            "name": name,
            "arguments": args
        })
        return result.get("result", {}).get("content", [{}])[0].get("text", "")

    def chat(self, user_message: str) -> str:
        """
        Solar Pro 2와 대화하면서 도구를 자동 호출하는 에이전트 루프

        1. 사용자 메시지 → Solar Pro 2
        2. Solar Pro 2가 tool_call 반환 → MCP 서버 호출
        3. 결과 → Solar Pro 2에 다시 전달
        4. 최종 텍스트 응답 반환
        """
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]

        while True:
            response = solar_pro2_api_call(messages, tools=MCP_TOOLS)

            if response.tool_calls:
                for tc in response.tool_calls:
                    result = self.call_tool(tc.function.name,
                                           json.loads(tc.function.arguments))
                    messages.append({"role": "tool", "content": result,
                                    "tool_call_id": tc.id})
            else:
                return response.content  # 최종 텍스트 응답
```

### 8.3 Solar Pro 2 사용 시 고려사항

| 항목 | 설명 |
|------|------|
| **한국어 강점** | RPG 대화/스토리 작성에 유리. NPC 대사, 아이템 설명 등을 자연스러운 한국어로 생성 |
| **Function Calling 지원 여부** | Solar Pro 2가 OpenAI 호환 tool_use를 지원하는지 확인 필요 |
| **컨텍스트 윈도우** | 28개 도구 스키마가 컨텍스트를 많이 차지하므로, 자주 쓰는 도구만 선별 등록 권장 |
| **도구 선택 정확도** | Claude 대비 도구 선택 정확도가 낮을 수 있음 → 시스템 프롬프트에 예시 추가 권장 |
| **로컬 실행** | MCP 서버는 로컬에서 실행되므로 Solar Pro 2 API를 호출하는 브릿지가 필요 |

### 8.4 시스템 프롬프트 예시 (Solar Pro 2용)

```
당신은 RPG Maker MZ 게임 개발을 도와주는 AI 어시스턴트입니다.

## 사용 가능한 도구
- add_dialogue: NPC 대화를 추가합니다
- add_choice: 선택지를 추가합니다
- add_actor: 새 캐릭터를 추가합니다
- add_item: 새 아이템을 추가합니다
- create_map: 새 맵을 만듭니다

## 작업 순서
1. get_project_info로 프로젝트 상태 확인
2. 필요한 작업 수행 (대화 추가, 아이템 생성 등)
3. run_playtest로 결과 확인

## 예시
사용자: "마을에 상인 NPC를 만들어줘"
→ add_dialogue로 인사말 추가
→ add_choice로 "사다/판다/그만두기" 선택지 추가
→ run_playtest로 확인
```

### 8.5 권장 도구 우선순위 (Solar Pro 2 컨텍스트 절약)

Solar Pro 2의 컨텍스트 윈도우가 제한적이라면, 단계별로 도구를 나눠 등록:

**필수 (항상 등록)**
- `get_project_info`, `read_data_file`, `write_data_file`
- `add_dialogue`, `add_choice`
- `undo_last_change`

**스토리 작업 시 추가**
- `search_events`, `get_event_page`
- `add_conditional_branch`, `show_picture`

**데이터 작업 시 추가**
- `add_actor`, `add_item`, `add_skill`

**맵 작업 시 추가**
- `create_map`, `draw_map_tile`

**테스트 시 추가**
- `run_playtest`, `inspect_game_state`

---

## 9. 의존성

| 패키지 | 버전 | 용도 |
|--------|------|------|
| `@modelcontextprotocol/sdk` | 1.22.0 | MCP 프로토콜 구현 |
| `puppeteer` | 24.31.0 | 게임 스크린샷 & 상태 조회 |
| `zod` | 4.1.12 | 입력 스키마 검증 |
| `serve-handler` | 6.1.6 | 브라우저 모드 정적 파일 서버 |
| `jimp` | 1.6.0 | 이미지 처리 |
| `screenshot-desktop` | 1.15.3 | 데스크톱 스크린샷 폴백 |
| `tsx` | 4.20.6 | TypeScript 직접 실행 |
| `vitest` | 2.1.0 | 단위 테스트 |

---

## 10. 실행 방법

```bash
# 개발 모드
npx tsx index.ts

# 빌드 & 실행
npm run build && node dist/index.js

# npx로 실행 (npm 패키지)
npx -y @rein634/rpg-maker-mz-mcp

# 테스트
npm test              # 단위 테스트
npm run test:coverage # 커버리지
npm run test:e2e      # E2E (Windows 전용)
```
