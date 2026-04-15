# RPG Maker MZ MCP Server - 使用説明書

![Tests](https://github.com/rein1225/RPGMakerMZ_MCP/actions/workflows/test.yml/badge.svg)

> ⚠ **実験版 / WIP / 作者環境専用**
>
> 이것은 "RPG 2 쿨 MZ를 AI에 괴롭히는 MCP 서버"의 **개발중 버전(0.x)**입니다.
>** 저자 환경(Windows+ Antigravity)에서만 작동 확인됨**입니다.
>
> **중요사항:**
> - 다른 환경 · MCP 클라이언트에서 ** 움직이지 않을 가능성이 높습니다 **
> - Antigravity의 구현이나 CWD의 사정으로, 범용적으로 보이는 설정 방법이 동작하지 않는 경우가 있습니다
> - 코드를 읽고 필요한 경우 경로 및 설정을 변경하십시오.
> - 테스트 프로젝트에서 사용 권장
> - 프로덕션 데이터를 터치하기 전에 백업 필수
>
> 「자신용 툴＋코드 공개」라고 하는 위치설정입니다. 자기 책임으로 사용하십시오.

## TL;DR（超短縮版）

### 가정 사용자
**RPG 투쿨 MZ를 AI에 괴롭히고 싶은 사람**

### 할 수있는 일
- ✅ AI에 맵을 만들게 한다
- ✅ 이벤트 증축
- ✅ 플러그인 추가 및 설정
- ✅ 테스트 플레이와 스크린샷까지 자동 실행

### 3행 빠른 시작(Google Antigravity)

1. **설치 불필요**: `npx`가 자동으로 패키지를 가져옵니다
2. **MCP 설정**: `mcp_config.json`에 다음을 추가
   ```json
   {
     "mcpServers": {
       "rpg-maker-mz": {
         "command": "npx",
         "args": ["-y", "@rein634/rpg-maker-mz-mcp"]
       }
     }
   }
   ```
3. **사용**: Antigravity 재시작 → MCP Servers → Refresh → "이 프로젝트를 구문 분석하여 첫 번째 맵에 대화 이벤트 추가"라고 AI에 말을 건다

> 💡 **다른 MCP 클라이언트(Cursor/Claude 등)를 사용하는 경우**: 설정 섹션의 "프로젝트 로컬"을 참조하십시오.

---

## 概要

이 MCP 서버는 RPG 투쿨 MZ의 게임 개발을 **완전 자동화**하는 도구입니다. AI에 자연 언어로 지시하는 것만으로 맵 작성, 이벤트 배치, 스위치 관리, 에셋 체크 등이 자동 실행됩니다.

**주요 특징:**
- ✅ **추상화 레이어**: MZ 내부 구조를 몰라도 개발 가능
- ✅ **자동 ID 관리**: 스위치 맵 ID 자동 해결/할당
- ✅ **하루시네이션 방지**: MCP Resources에서 사양을 참조 가능
- ✅ ** 품질 보증 **: Zod Validation 및 자산 무결성 검사
- ✅ **자동 백업**: 파일 쓰기 전에 자동 백업 생성
- ✅ **Undo 기능**: 이전 변경 사항을 쉽게 실행 취소
- ✅ **보안 강화**: 화이트리스트 방식의 코드 실행, 패스트래버설 대책

---

## 설정

### Google Antigravity

> ⚠️ **환경 의존 경고**: Antigravity의 구현이나 CWD의 편리함으로, 범용적으로 보이는 설정 방법(`npx`, `rpg-maker-mz-mcp`명령, 상대 경로 등)이 **동작하지 않을 가능성이 있습니다**.
> 다음은 **저자의 환경에서 실제로 동작한 설정예**입니다. 환경이 다른 경우 경로를 적절하게 변경하십시오.

#### 설정 방법(실제로 동작한 예)

첫째, 글로벌 설치 :

```bash
npm install -g @rein634/rpg-maker-mz-mcp
```

`mcp_config.json`에 다음을 추가합니다 (** 절대 경로 사용 **) :

```json
{
  "mcpServers": {
    "rpg-maker-mz": {
      "command": "node",
      "args": [
        "C:/Users/YOUR_USERNAME/AppData/Roaming/npm/node_modules/@rein634/rpg-maker-mz-mcp/dist/index.js"
      ]
    }
  }
}
```

> ⚠️ **重要**:
> - `C : /Users/YOUR_USERNAME/AppData/Roaming/npm/node_modules/...` 부분을 **환경의 실제 경로**로 바꾸십시오 (`YOUR_USERNAME`을 Windows 사용자 이름으로 변경)
> - Windows에서`C :/`와 같이 슬래시 (`/`)를 사용하고 백 슬래시 (`\`)를 사용하지 마십시오.
> - 경로는 환경 변수 `%APPDATA%\npm\node_modules\@rein634\rpg-maker-mz-mcp\dist\index.js`를 확장한 형태입니다.

#### 기타 설정 방법 (작동하지 않을 수 있음)

다음 설정 방법은 Antigravity의 환경 의존성에 따라 **작동하지 않을 수 있습니다**:

**방법 A: npx를 통해(권장되지 않음)**
```json
{
  "mcpServers": {
    "rpg-maker-mz": {
      "command": "npx",
      "args": ["-y", "@rein634/rpg-maker-mz-mcp"]
    }
  }
}
```

**방법 B: 명령 이름 직접 지정(권장되지 않음)**
```json
{
  "mcpServers": {
    "rpg-maker-mz": {
      "command": "rpg-maker-mz-mcp"
    }
  }
}
```

**방법 C: 상대 경로(작동하지 않음)**
```json
{
  "mcpServers": {
    "rpg-maker-mz": {
      "command": "node",
      "args": ["./node_modules/@rein634/rpg-maker-mz-mcp/dist/index.js"]
    }
  }
}
```
> ❌ Antigravity는 `.gemini/antigravity`를 현재 디렉토리로 시작하므로 상대 경로를 사용할 수 없습니다.

#### 起動確認

Antigravity를 다시 시작하고 **MCP Servers** → **Refresh**를 실행합니다.
터미널에는 다음과 같은 로그가 표시됩니다.

```text
[2025-11-29T05:43:43.574Z] [INFO] RPG Maker MZ MCP Server running on stdio.
```

이 메시지가 표시되고 그대로 입력을 기다리는 것은 **정상적인 동작**입니다. MCP 클라이언트로부터의 요청을 기다리는 상태입니다.

> 💡 **로그 정보**: 로그는 **stderr**에 출력되므로 MCP 프로토콜의 JSON(stdout)에는 영향을 주지 않습니다. 콘솔에 로그가 표시되어도 MCP에 문제가 없습니다.

---

### 프로젝트 로컬 (Cursor / Claude Code 등)

> ⚠️ **미확인**: 다음 설정은 **저자 환경에서는 검증하지 않았습니다**.
> 프로젝트 루트에 설정 파일을 넣는 MCP 클라이언트에 대한 가정 설정입니다. 작동하지 않는 경우 코드를 읽고 환경에 맞게 조정하십시오.

#### 1. 프로젝트에 설치

RPG 2 쿨 MZ 프로젝트의 루트 디렉토리에서 실행 :

```bash
npm install -D @rein634/rpg-maker-mz-mcp
```

#### 2. MCP 설정 파일 설정

프로젝트 루트에 구성 파일 (예 : `.cursor/mcp.json` 또는 `mcp_config.json`)을 만들고 다음을 추가하십시오.

```json
{
  "mcpServers": {
    "rpg-maker-mz": {
      "command": "node",
      "args": ["./node_modules/@rein634/rpg-maker-mz-mcp/dist/index.js"]
    }
  }
}
```

> ⚠️ **注意**:
> - 이 설정은 **저자 환경에서 확인하지 않았습니다**
> - MCP 클라이언트 구현이나 CWD 사정으로 작동하지 않을 수 있음
> - 작동하지 않으면 절대 경로를 사용하거나 환경에 맞게 조정하십시오.

---

### 기타 방법

#### 글로벌 설치(옵션·상급자용)

전역적으로 설치하고 명령 이름으로 직접 실행하는 방법입니다.

```bash
npm install -g @rein634/rpg-maker-mz-mcp
```

설치 후 MCP 구성 파일에 다음을 추가합니다.

```json
{
  "mcpServers": {
    "rpg-maker-mz": {
      "command": "rpg-maker-mz-mcp"
    }
  }
}
```

> ⚠️ **주의**: 일부 클라이언트(특히 Windows 환경)에서는 전역 래퍼 스크립트(`.cmd`/`.ps1`)가 제대로 시작되지 않고 `Error: calling "initialize": EOF`가 나타날 수 있습니다.
> 이 경우 위의 ** Antigravity ** 또는 ** 프로젝트 로컬 ** 설정을 사용하십시오.

#### 소스 코드에서 직접 실행 (개발자 용)

npm 패키지를 설치할 필요가 없습니다. 리포지토리를 복제하고 종속성을 설치하기만 하면 됩니다.

```bash
git clone https://github.com/rein1225/RPGMakerMZ_MCP.git
cd RPGMakerMZ_MCP
npm install
```

MCP 구성 파일에 다음을 추가:

```json
{
  "mcpServers": {
    "rpg-maker-mz": {
      "command": "npx",
      "args": ["tsx", "C:/path/to/RPGMakerMZ_MCP/index.ts"],
      "cwd": "C:/path/to/RPGMakerMZ_MCP"
    }
  }
}
```

> ⚠️ **重要**:
> - `C : /path/to/RPGMakerMZ_MCP`를 실제 프로젝트 경로로 바꾸십시오.
> - Windows에서`C :/`와 같이 슬래시 (`/`)를 사용하고 백 슬래시 (`\`)를 사용하지 마십시오.
> - `npx tsx`를 사용하여 TypeScript 파일을 직접 실행할 수 있습니다 (빌드 필요 없음)
> - **`cwd` 속성이 허용되지 않는 경우 ** : 문제 해결 Q1을 참조하십시오.

---

## 사용 가능한 도구

### Phase 1: 프로젝트 분석 및 데이터 조작

#### 1. `get_project_info` - 프로젝트 기본 정보 취득
**설명:** System.json에서 게임 타이틀, 버전, 통화 단위 등의 기본 정보를 가져옵니다.
**매개 변수:**
- `projectPath`(필수) : 프로젝트 폴더의 절대 경로

#### 2. `list_data_files` - 데이터 파일 목록
**설명:** data 폴더의 JSON 파일 목록을 가져옵니다.
**매개 변수:**
- `projectPath`(필수) : 프로젝트 폴더의 절대 경로

#### 3. `read_data_file` - 데이터 파일 읽기
**설명:** 지정된 데이터 파일(예: Actors.json)의 내용을 로드합니다.
**매개 변수:**
- `projectPath`(필수) : 프로젝트 폴더의 절대 경로
- `filename` (필수) : 파일 이름 (예 : 'Actors.json')

#### 4. `write_data_file` - 데이터 파일 쓰기
**설명:** 지정한 데이터 파일에 JSON 콘텐츠를 씁니다. 쓰기 전에 자동으로 백업이 생성됩니다.
**매개 변수:**
- `projectPath`(필수) : 프로젝트 폴더의 절대 경로
- `filename`(필수) : 파일 이름
- `content` (필수) : 쓸 JSON 문자열

#### 5. `search_events` - 이벤트 검색
**설명:** 지도 및 공통 이벤트에서 텍스트 및 명령 코드를 검색합니다.
**매개 변수:**
- `projectPath`(필수) : 프로젝트 폴더의 절대 경로
- `query` (필수) : 검색 할 텍스트 또는 숫자

#### 6. `get_event_page` - 이벤트 페이지 취득
**설명:** 지정한 이벤트 페이지의 명령 목록을 가져옵니다. 주요 명령(대화, 선택, 스위치 조작 등)에는 가독성이 높은 설명이 부여됩니다. 이를 통해 AI는 기존 이벤트의 내용을 이해하고 추측과 수정을 할 수 있습니다.
**매개 변수:**
- `projectPath`(필수) : 프로젝트 폴더의 절대 경로
- `mapId` (필수) : 맵 ID
- `eventId` (필수) : 이벤트 ID
- `pageIndex` (필수) : 페이지 번호 (0 시작)

---

### Phase 2: 자산 관리

#### 7. `list_assets` - 자산 목록
**설명:** img 및 audio 디렉토리의 파일 목록을 가져옵니다.
**매개 변수:**
- `projectPath`(필수) : 프로젝트 폴더의 절대 경로
- `assetType` (선택 사항): 'img', 'audio', 'all' (기본값: 'all')

#### 8. `check_assets_integrity` - 자산 무결성 검사
**설명:** 이벤트에서 참조된 자산(이미지, 오디오 등)이 프로젝트에 실제로 존재하는지 확인합니다.
**매개 변수:**
- `projectPath`(필수) : 프로젝트 폴더의 절대 경로

---

### Phase 3: 플러그인 관리

#### 9. `write_plugin_code` - 플러그인 생성
**설명:** js/plugins 디렉토리에 새 플러그인 파일(.js)을 만듭니다.
**매개 변수:**
- `projectPath`(필수) : 프로젝트 폴더의 절대 경로
- `filename` (필수) : 플러그인 파일 이름 (예 : 'MyPlugin.js')
- `code` (필수) : JavaScript 코드

#### 10. `get_plugins_config` - 플러그인 설정 얻기
**설명:** js/plugins.js에서 현재 플러그인 설정을 로드합니다.
**매개 변수:**
- `projectPath`(필수) : 프로젝트 폴더의 절대 경로

#### 11. `update_plugins_config` - 플러그인 설정 업데이트
**설명:** js/plugins.js의 플러그인 설정을 업데이트합니다.
**매개 변수:**
- `projectPath`(필수) : 프로젝트 폴더의 절대 경로
- `plugins` (필수) : 플러그인 설정 객체의 배열

---

### Phase 4: 맵 이벤트 조작(추상화 레이어)

#### 12. `add_dialogue` - 대화 이벤트 추가
**설명:** 메시지 창에 대화를 추가합니다.
**매개 변수:**
- `projectPath`(필수) : 프로젝트 폴더의 절대 경로
- `mapId` (필수) : 맵 ID
- `eventId` (필수) : 이벤트 ID
- `pageIndex` (필수) : 페이지 번호
- `insertPosition` (필수) : 삽입 위치 (-1로 끝)
- `text` (필수) : 표시 텍스트
- `face`, `faceIndex`, `background`, `position` (省略可)

**요청 예:**
```json
{
  "tool": "add_dialogue",
  "arguments": {
    "projectPath": "C:/Games/MyProject",
    "mapId": 1,
    "eventId": 1,
    "pageIndex": 0,
    "insertPosition": -1,
    "text": "안녕하세요!\n새로운 동료입니다."
  }
}
```

**응답 예:**
```json
{
  "content": [
    {
      "type": "text",
      "text": "대화 이벤트를 추가했습니다."
    }
  ]
}
```

#### 13. `add_choice` - 옵션 표시
**설명:** 이벤트에 옵션을 추가합니다. 최대 6가지 옵션을 설정할 수 있습니다.
**매개 변수:**
- `projectPath`(필수) : 프로젝트 폴더의 절대 경로
- `mapId` (필수) : 맵 ID
- `eventId` (필수) : 이벤트 ID
- `pageIndex` (필수) : 페이지 번호
- `insertPosition` (필수) : 삽입 위치 (-1로 끝)
- `options` (필수) : 옵션 문자열 배열 (최대 6 개)
- `cancelType` (선택 사항) : 취소시 동작 (-1 = 취소 불가, 0-5 = 옵션으로 분기, 기본값 : -1)

**요청 예:**
```json
{
  "tool": "add_choice",
  "arguments": {
    "projectPath": "C:/Games/MyProject",
    "mapId": 1,
    "eventId": 1,
    "pageIndex": 0,
    "insertPosition": -1,
    "options": ["예", "아니오"],
    "cancelType": -1
  }
}
```

**응답 예:**
```json
{
  "content": [
    {
      "type": "text",
      "text": "선택지를 추가했습니다."
    }
  ]
}
```

#### 14. `add_loop` - 루프 추가
**설명:** 이벤트 명령의 루프 구조(Loop + Repeat Above)를 추가합니다.
**매개 변수:**
- `projectPath`, `mapId`, `eventId`, `pageIndex`, `insertPosition` (必須)

#### 15. `add_break_loop` - 루프 중단
**설명:** 루프를 일시 중단하는 명령을 추가합니다.
**매개 변수:**
- `projectPath`, `mapId`, `eventId`, `pageIndex`, `insertPosition` (必須)

#### 16. `add_conditional_branch` - 条件分岐追加
**설명:** 조건 분기(If-Else-End)를 추가합니다.
**매개 변수:**
- `projectPath`, `mapId`, `eventId`, `pageIndex`, `insertPosition` (必須)
- `condition` (필수) : 조건 파라미터 객체
- `includeElse` (선택 사항) : Else 분기를 포함할지 (기본값: true)

#### 17. `delete_event_command` - 이벤트 명령 삭제
**설명:** 지정된 인덱스의 이벤트 명령을 삭제합니다.
**매개 변수:**
- `projectPath`, `mapId`, `eventId`, `pageIndex`, `commandIndex` (必須)

#### 18. `update_event_command` - 이벤트 명령 업데이트
**설명:** 지정된 인덱스의 이벤트 명령을 새 내용으로 덮어씁니다.
**매개 변수:**
- `projectPath`, `mapId`, `eventId`, `pageIndex`, `commandIndex`, `newCommand` (必須)

#### 19. `create_actor` - 액터 추가
**설명:** 데이터베이스에 새 액터를 추가합니다.
**매개 변수:**
- `projectPath`, `name` (必須)
- `classId`, `initialLevel`, `maxLevel` (省略可)

#### 20. `create_item` - 아이템 추가
**설명:** 데이터베이스에 새 항목을 추가합니다.
**매개 변수:**
- `projectPath`, `name` (必須)
- `price`, `consumable`, `scope`, `occasion` (省略可)

#### 21. `create_skill` - 스킬 추가
**설명:** 데이터베이스에 새로운 기술을 추가합니다.
**매개 변수:**
- `projectPath`, `name` (必須)
- `mpCost`, `tpCost`, `scope`, `occasion` (省略可)

#### 22. `draw_map_tile` - 맵 타일 그리기
**설명:** 맵의 지정된 좌표에 타일을 배치합니다.
**매개 변수:**
- `projectPath`, `mapId`, `x`, `y`, `layer`, `tileId` (必須)

#### 23. `create_map` - 새로운 맵 작성
**설명:** 새 맵을 만듭니다.
**매개 변수:**
- `projectPath`(필수) : 프로젝트 폴더의 절대 경로
- `mapName` (필수) : 맵 이름
- `width` (선택 사항): 맵 폭(타일 수, 기본값: 17)
- `height`(선택 사항): 맵 높이(타일 수, 기본값: 13)
- `parentMapId` (선택 사항): 상위 맵 ID(기본값: 0)

#### 24. `show_picture` - 그림 표시
**설명:** 이벤트에 그림 표시 명령을 추가합니다.
**매개 변수:**
- `projectPath`(필수) : 프로젝트 폴더의 절대 경로
- `mapId` (필수) : 맵 ID
- `eventId` (필수) : 이벤트 ID
- `pageIndex` (필수) : 페이지 번호
- `insertPosition` (필수) : 삽입 위치 (-1로 끝)
- `pictureId` (필수) : 그림 번호
- `pictureName`(필수) : 이미지 파일 이름
- `x`, `y` (必須): 表示座標
- `origin` (선택 사항) : 원점 위치 (0 = 왼쪽 위, 1 = 중앙, 기본값 : 0)
- `scaleX`, `scaleY` (선택 사항): 확대율(%, 기본값: 100)
- `opacity`(선택 사항): 불투명도(0-255, 기본값: 255)
- `blendMode` (선택 사항): 합성 모드(0-3, 기본값: 0)

#### 25. `inspect_game_state` - 게임 상태 검사
**설명:** 실행 중인 게임(Puppeteer 연결)에서 변수와 스위치 값을 가져옵니다.
**보안:** 화이트리스트 방식을 채용해, 허가된 패턴만 실행 가능합니다. 입력 길이 제한(100자)과 ID 범위 검사(1-9999)도 구현됩니다.
**허용된 패턴 예:**
- `$gameVariables.value(1)` - 변수의 값을 취득
- `$gameSwitches.value(1)` - 스위치의 값을 취득
- `$gameParty.gold()` - 소지금 취득
- `$gameMap.mapId()` - 현재의 맵 ID를 취득
- `SceneManager._scene` - 현재의 장면을 취득
**매개 변수:**
- `script` (필수) : 평가할 JavaScript 코드 (화이트리스트에 등록 된 패턴 만)
- `port` (선택 사항): 디버그 포트(기본값: 9222)

**요청 예:**
```json
{
  "tool": "inspect_game_state",
  "arguments": {
    "script": "$gameVariables.value(1)",
    "port": 9222
  }
}
```

**응답 예:**
```json
{
  "content": [
    {
      "type": "text",
      "text": "100"
    }
  ]
}
```

> ⚠️ **위험 도구**: 이 도구는 JavaScript 코드를 실행합니다. 자세한 내용은 "[위험 도구 봉인 가이드](#위험 도구 봉인 가이드)"를 참조하십시오.

---

### Phase 5: 테스트 및 자동화

#### 26. `run_playtest` - 테스트 플레이 실행
**설명:** Game.exe를 시작하고 지정된 시간 후에 스크린샷을 찍습니다. Game.exe를 찾을 수 없으면 브라우저 기반 테스트 플레이(폴백 모드)가 자동으로 실행됩니다. Puppeteer 연결용 디버그 포트도 지정할 수 있습니다.
**매개 변수:**
- `projectPath`(필수) : 프로젝트 폴더의 절대 경로
- `duration`(선택 사항): 촬영까지의 대기 시간(ms)(기본값: 5000)
- `autoClose` (선택 사항) : true이면 촬영 후 게임을 자동 종료합니다. (기본값: false)
- `debugPort` (선택 사항): 원격 디버깅 포트(예: 9222). Puppeteer로 연결할 때 사용합니다.
- `startNewGame` (선택 사항) : true이면 제목 화면을 건너 뛰고 새 게임을 시작합니다. (기본값: false)
- `postLaunchScript` (선택 사항) : 게임 시작 후 실행할 JavaScript 코드. 디버그 UI의 표시나 이벤트의 주입 등에 사용합니다.

**postLaunchScript 사용 예:**
```json
{
  "projectPath": "C:/Games/MyProject",
  "postLaunchScript": "Input._currentState['debug'] = true; setTimeout(() => { Input._currentState['debug'] = false; }, 100);"
}
```

### Phase 6: 백업 및 Undo 기능

#### 27. `undo_last_change` - 직전의 변경을 취소
**설명:** 최신 백업에서 파일을 복원합니다. `filename`을 지정하지 않으면 가장 최근에 변경된 파일을 자동으로 복원합니다.
**매개 변수:**
- `projectPath`(필수) : 프로젝트 폴더의 절대 경로
- `filename`(선택 사항): 복원할 파일 이름(예: 'Actors.json'). 생략하면 최신 변경 파일 자동 감지

#### 28. `list_backups` - 백업 목록 표시
**설명:** 지정한 파일 또는 모든 파일의 백업 목록을 표시합니다.
**매개 변수:**
- `projectPath`(필수) : 프로젝트 폴더의 절대 경로
- `filename` (선택 사항) : 백업을 표시하는 파일 이름. 생략하면 모든 파일의 백업 표시

**백업 기능 정보:**
- 모든 파일 쓰기 작업(`write_data_file`, `create_actor`, `create_item`, `create_skill`, `write_plugin_code`, `update_plugins_config`, 맵 작업 등)에서 자동으로 백업이 생성됩니다.
- 백업 파일은 `.{timestamp}.bak` 형식으로 저장됩니다
- 오래된 백업은 자동으로 정리됩니다 (최신 5 개 유지)
- 오류 발생 시 자동으로 롤백됩니다.

### Puppeteer로 고급 자동 테스트
`run_playtest`에서 `debugPort`를 지정하면 Puppeteer를 사용하여 게임의 UI 조작과 시나리오 테스트를 자동화할 수 있습니다.
자세한 API 사양은 `docs/API_REFERENCE.md`를 참조하십시오.

### E2E 테스트 실행 방법
자동화 시나리오 (`automation/test_*.js`)는 프로덕션 게임 환경을 전제로 한 수동 실행 전용 테스트입니다. CI에서는 실행되지 않습니다.

```bash
# 대표 시나리오를 한 번에 실행
npm run test:e2e

# 또는 개별 실행
node automation/test_full_suite.js
node automation/test_add_dialogue.js
```

> ⚠️ 브라우저 작업이나 Game.exe 시작을 수반하므로 **신뢰할 수 있는 로컬 환경만**에서 실행하십시오.

---

## MCP Resources

### `mz://docs/event_commands` - 이벤트 명령 참조
AI가 MZ인 이벤트 명령 사양을 참조하는 리소스입니다.

---

## 実用例

### 예 1 : 새로운 액터 생성 및 대화 이벤트 추가
```javascript
// 1. 액터 생성
create_actor({ projectPath, name: "새 캐릭터" });
// 2. 会話追加
add_dialogue({ projectPath, mapId: 1, eventId: 1, pageIndex: 0, insertPosition: -1, text: "안녕하세요!\n새로운 동료입니다." });
```

### 예 2: 이벤트 검색
```javascript
search_events({ projectPath: "c:/path/to/project", query: "포션" });
```

---

## 문제 해결

### Q1: MCP 설정에서 오류 "invalid character '-' after array element" 또는 "속성 cwd가 허용되지 않습니다"

> ✅ **v0.1.2에서 수정 ** : stdout으로의 로그 출력을 stderr로 변경했기 때문에 MCP 서버 측이 원인 인 `invalid character '-' after array element` 오류가 해결되었습니다.
>이 오류가 발생하면 **v0.1.2 이상 버전을 사용 **하십시오 : `npm install -g @rein634/rpg-maker-mz-mcp@latest`

**原因:**
- **MCP 서버 측 문제(v0.1.1 이하)**: 로그가 stdout으로 출력되었기 때문에 JSON-RPC 프로토콜이 손상되었습니다.
- JSON 구문 오류 (댓글, 후미 쉼표 등)
- 사용중인 MCP 클라이언트가 cwd 속성을 지원하지 않습니다.

**解決策:**

#### 1단계: JSON 구문 확인
1. **댓글 삭제**: JSON은 주석(`//` 또는 `#`)을 지원하지 않습니다.
2. **후행 쉼표 삭제**: 배열이나 객체의 마지막 요소 뒤에 쉼표가 없어야 합니다.
3. **온라인 유효성 검사기에서 확인**: [JSONLint](https://jsonlint.com/)에서 구문 확인

#### 2단계: 올바른 구성 예 확인

**Google Antigravity의 경우(권장):**

```json
{
  "mcpServers": {
    "rpg-maker-mz": {
      "command": "npx",
      "args": ["-y", "@rein634/rpg-maker-mz-mcp"]
    }
  }
}
```

> ✅ **이 방법의 장점 **:
> - `npm install`조차 불필요 (npx가 자동으로 패키지를 가져옵니다)
> - CWD에 의존하지 않기 때문에`.gemini/antigravity`에서도 동작
> - 모든 사용자 환경에서 동일한 설정으로 작동

**프로젝트 로컬(예: 커서/클라우드 코드):**

프로젝트 루트에서:

```bash
npm install -D @rein634/rpg-maker-mz-mcp
```

구성 파일(프로젝트 루트에 배치):

```json
{
  "mcpServers": {
    "rpg-maker-mz": {
      "command": "node",
      "args": ["./node_modules/@rein634/rpg-maker-mz-mcp/dist/index.js"]
    }
  }
}
```

> ✅ **이 방법의 장점 **:
> - 글로벌 PATH 또는 래퍼 스크립트에 의존하지 않음
> - Windows / Mac / Linux 공통 동작
> - 작업 공간의 상대 경로를 사용하기 위해 프로젝트 루트에 구성 파일을 배치하는 클라이언트에서 다루기 쉽습니다.

**선택사항: 글로벌 설치(일부 환경에서 문제가 발생할 수 있음)**

```bash
npm install -g @rein634/rpg-maker-mz-mcp
```

```json
{
  "mcpServers": {
    "rpg-maker-mz": {
      "command": "rpg-maker-mz-mcp"
    }
  }
}
```

> ⚠️ **주의**: Windows 환경 등에서는 전역 래퍼 스크립트가 제대로 시작되지 않고 `Error: calling "initialize": EOF` 가 나올 수 있습니다. 이 경우 위의 **Antigravity용** 또는 **프로젝트 로컬** 설정을 사용합니다.

**자주 하는 실수:**
- ❌ **코멘트 사용**: `// 이것은 코멘트` → JSON은 코멘트 비 대응
- ❌ **후행 쉼표**: `"args": ["tsx", "index.ts",]` → 마지막 쉼표는 불가능
- ❌ **싱글 쿼트**: ``path'' → JSON은 더블 쿼트 전용
- ❌ **백슬래시**: `C:\path\to\file` → 슬래시(`/`) 사용

#### 3단계: 구성 파일의 위치 확인
- **Antigravity**: `%APPDATA%\Antigravity\mcp_config.json` (Windows)
- **Claude Desktop**: `%APPDATA%\Claude\claude_desktop_config.json` (Windows)
- 구성 파일의 경로는 사용 중인 MCP 클라이언트에 따라 다릅니다.

#### 4단계: 디버깅 방법
1. 설정 파일을 텍스트 편집기에서 열기
2. [JSONLint](https://jsonlint.com/)에 복사 및 붙여넣기하여 확인
3. 에러 메시지의 행 번호를 확인하여 해당 부분을 수정
4. 수정 후 MCP 클라이언트를 재부팅

### Q2: 스위치를 찾을 수 없는 오류
**해결책:** 자동 등록 기능이 작동합니다. System.json의 쓰기 권한을 확인하십시오.

### Q3: 편집기와의 충돌
**해결책:** MCP 편집 중에는 편집기를 닫거나 편집 후 프로젝트를 다시 열어야 합니다.

### Q4: Game.exe를 찾을 수 없음
**해결 방법:** 배포 기능으로 테스트 플레이용 패키지를 만들거나 Game.exe를 수동으로 배포합니다.
또한 v1.2.0 이상에서는 Game.exe가 없는 경우에도 브라우저를 통해 테스트 플레이가 실행됩니다.

### Q5: npm 패키지를 찾을 수 없음
**解決策:**
- 글로벌 설치 :`npm install -g @rein634/rpg-maker-mz-mcp`
- 경로가 있는지 확인: `which rpg-maker-mz-mcp`(Linux/Mac) 또는 `where rpg-maker-mz-mcp`(Windows)
- 소스 코드에서 직접 실행하려면 'npx tsx'를 사용하십시오.

---

## 技術仕様

### 아키텍처
```
[AI] ← → [MCP Server] ← → [RPG Maker MZ Project]
           ├─ Tools (28個)
           ├─ Resources (1個)
           ├─ Schemas (Zod Validation)
           └─ Backup System (자동 백업/롤백)
```

### 테스트 커버리지

- **단위 테스트**: Vitest 사용
- **커버리지 리포트**: `npm run test:coverage`로 생성
- **CI/CD**: GitHub Actions에서 자동 테스트 실행, Codecov에서 커버리지 추적
- **통합 기준선**: `npm run build:baseline`에서 4계통 MCP의 비교 기준을 재생성
- ** 차이 보고서 ** :`npm run report : diff`로`PASS / DIFF / ENV-BLOCKED`를 출력
- **단독 배포 확인**: `npm run validate:standalone`로 단일 폴더 실행 가능성 확인

### 완전 통합 검사(단일 MCP)

4개의 MCP 구현을 `integration_MCP` 단일 서버에 통합한 상태를 검증하는 표준 커멘드입니다.

```bash
npm run build
npm run audit:tools
npm run test:tools
npm run report:diff
npm run validate:standalone
```

期待値:
- `audit : tools`의 `canonicalPending = 0`
- `tool-diff-report.json`의 `DIFF = 0`
- 외부 의존(Chrome/Gemini/엔진 경로)은 `ENV-BLOCKED`로 분리 관리

### npm公開

이 패키지는 npm에 게시됩니다.

```bash
npm install -g @rein634/rpg-maker-mz-mcp
```

패키지 정보: https://www.npmjs.com/package/@rein634/rpg-maker-mz-mcp

### 파일 구성
```
RPGMakerMZ_MCP/
├── index.ts                    # MCP 서버 본체 (TypeScript)
├── handlers/                   # 핸들러 계층 (TypeScript)
│   ├── project.ts
│   ├── database.ts
│   ├── plugins.ts
│   ├── map.ts
│   ├── events.ts
│   └── playtest.ts
├── utils/                      # 유틸리티 계층 (TypeScript)
│   ├── validation.ts
│   ├── mapHelpers.ts
│   └── ...
├── types/                      # 타입 정의 파일
├── resources/
│   └── event_commands.json     # 이벤트 커맨드 레퍼런스
├── schemas/
│   └── mz_structures.js        # Zod 검증 스키마
├── automation/                 # 자동화 스크립트
└── package.json
```

---

## 보안상의 주의

본 MCP 서버는, 로컬 개발 환경에서의 사용을 상정하고 있습니다.

### 구현된 보안 조치

- **`inspect_game_state`**: 화이트리스트 방식을 채용해, 허가된 패턴만 실행 가능. 입력 길이 제한(100자)과 ID 범위 체크(1-9999)도 구현.
- **패스 트래버설 대책**: `path.normalize()`와 `fs.realpath()`를 사용하여 심볼릭 링크 공격을 방지.
- **파일명 검증**: 플러그인 기입시는 영숫자·언더스코어·하이픈만 허가.
- **자동 백업**: 모든 파일 쓰기 작업에서 자동 백업을 만들고 오류 시 자동 롤백.

### 推奨事項

- 외부에 노출된 환경에서는 사용하지 마십시오.
- 신뢰할 수 있는 로컬 환경에서만 사용하십시오.
- 중요한 변경 전에 수동으로 백업을 수행하는 것이 좋습니다.

---

## 라이센스
MIT License

## 일반적인 유스 케이스

### 시나리오 1: 기존 프로젝트에 하위 퀘스트 추가

**목표**: 기존 마을 지도에 세 개의 하위 퀘스트 이벤트 추가

**手順**:
1. **프로젝트 분석**: `get_project_info`로 프로젝트 정보 얻기
2. **이벤트 검색**: `search_events`로 기존 이벤트 확인
3. **이벤트 페이지 취득**: `get_event_page`로 기존 이벤트의 구조를 이해
4. **대화 추가**: `add_dialogue`로 NPC와 대화 추가
5. **옵션 추가**: `add_choice`로 퀘스트 옵션 추가
6. **조건 분기**: `add_conditional_branch`로 퀘스트 완료 조건 설정
7. **테스트 플레이**: `run_playtest`로 동작 확인

**AI에 대한 지침 예**:
```
이 프로젝트를 분석하고 맵 1의 마을에 서브 퀘스트 3개를 추가해 주세요.
각 퀘스트에는 대화, 선택지, 완료 조건을 포함해 주세요.
```

### 시나리오 2: 새 맵 작성에서 이벤트 배치까지

** 목표 ** : 새로운 던전 맵을 만들고 보물 상자 이벤트를 배치합니다.

**手順**:
1. **맵 작성**: `create_map`으로 새로운 맵 작성
2. **타일 배치**: `draw_map_tile`로 맵 그리기
3. **이벤트 작성**: `add_dialogue`로 보물 상자 메시지 추가
4. **아이템 추가**: `create_item`로 보상 아이템 만들기
5. **이벤트 연계**: 조건 분기로 아이템 부여 설정
6. **테스트**: `run_playtest`로 동작 확인

**AI에 대한 지침 예**:
```
새로운 던전 맵을 만들고 보물상자 이벤트 3개를 배치해 주세요.
각 보물상자에는 서로 다른 아이템이 들어가도록 해 주세요.
```

### 시나리오 3: 플러그인 추가 및 설정

**목표**: 맞춤 플러그인을 추가하고 설정 업데이트

**手順**:
1. **플러그인 작성**: `write_plugin_code`로 플러그인 코드 추가
2. **설정 취득**: `get_plugins_config`로 현재 설정 확인
3. **설정 업데이트**: `update_plugins_config`로 플러그인 사용
4. **테스트**: `run_playtest`로 플러그인 동작 확인

**AI에 대한 지침 예**:
```
커스텀 전투 플러그인을 생성하고 활성화해 주세요.
```

---

## 위험 도구 봉인 가이드

### 위험 도구 목록

다음 도구는 보안상의 이유로 **주의 깊게 사용**해야 합니다.

- **`inspect_game_state`** : JavaScript 코드를 실행합니다 (화이트리스트 방식으로 보호되지만 런타임 오류가 발생할 수 있음)

### 推奨設定

**초기 상태에서는 비활성화하는 것이 좋습니다**. MCP 클라이언트 설정에서 특정 도구를 비활성화할 수 있습니다.

```json
{
  "mcpServers": {
    "rpg-maker-mz": {
      "command": "rpg-maker-mz-mcp",
      "disabledTools": ["inspect_game_state"]
    }
  }
}
```

> ⚠️ **주의**: 현재 MCP 클라이언트에 따라 `disabledTools` 속성이 지원되지 않을 수 있습니다. 이 경우 도구 사용을 피하거나 신뢰할 수 있는 환경에서만 사용하십시오.

### 보안 조치

`inspect_game_state` 도구는 다음과 같은 보안 조치를 구현합니다.

- ✅ ** 화이트리스트 방식 **: 허용된 패턴만 실행 가능
- ✅ **입력 길이 제한**: 최대 100자
- ✅ **ID 범위 체크**: 1-9999 범위만 허용
- ✅ **패스 트래버설 대책**: 부정한 패스 액세스를 방지

그래도 **신뢰할 수 없는 코드를 실행하지 마십시오**.

---

## 更新履歴

### v0.1.2 (2025-11-29)
- **중요 수정**: stdout에 대한 로그 출력을 stderr로 변경(MCP 프로토콜 준수)
- `invalid character'-' after array element` 오류 해결
- Logger.info()가 console.error()를 사용하도록 변경
- 테스트 업데이트 (console.log 스파이를 console.error로 변경)

### v0.1.1 (2025-11-29)
- logger.js가 빌드에 포함되도록 tsconfig.build.json 수정
- npm公開準備完了（@rein634/rpg-maker-mz-mcp）

### v0.1.0 (2025-11-29)
- npm 공개 최초 릴리스
- TypeScript 마이그레이션 완료: 모든 handlers 계층과 진입점을 TypeScript화
- CI/CD 통합: GitHub Actions에 유형 검사 추가
- undo_last_change 도구, list_backups 도구 구현
- 테스트 커버리지 개선 (undo.ts, backup.ts 테스트 추가)
- playtest.ts 리팩토링 (527 라인 → 311 라인, 약 41 % 감소)
- README 개선 (TL; DR 추가, 요청 예 추가, 유스 케이스 추가)
- 보안 강화: 패스트래버설 대책, 임의 코드 실행 경고 추가
- 새로운 도구 추가 :`add_choice`,`create_map`,`show_picture`,`check_assets_integrity`
- 유닛 테스트 도입 (Vitest)
- 로거 유틸리티 추가
- `run_playtest`에 브라우저 기반 폴백 기능 추가 (Game.exe 필요 없음)
- MCP Resources実装
- Zod Validation実装

---

## 추가 기능 로드맵

이하의 기능은 별도 사양을 책정해, 순차 실장 예정입니다. 자세한 내용은 `docs/feature-roadmap.md`를 참조하십시오.

| 우선 순위 | 기능 | 상태 |
| --- | --- | --- |
~~고~~ | ~~`undo` 기능(JSON 백업 / 롤백)~~ | ✅ 구현됨 |
| 중간 | `validate_project` 도구 (일관성 검사 일괄 실행) | 📋 계획 중 |
| 보통 | 일괄 처리 (복수 명령을 단일 요청으로 실행) | 📋 계획 중 |
| 낮음 | WebSocket 알림 (실시간 로그 / 상태 알림) | 📋 계획 중 |

## 開発・貢献

### 테스트 실행

```bash
# 단위 테스트
npm test

# 커버리지 리포트 생성
npm run test:coverage

# 타입 체크
npm run typecheck

# E2E 테스트 (수동 실행)
npm run test:e2e
```

### 빌드

```bash
# 전체 파일 빌드 (dist/ 출력)
npm run build

# 배포 전 확인
npm pack --dry-run
```

### 기여

풀 요청을 환영합니다! 다음 사항에 유의하십시오.

- 코드 스타일: TypeScript의 strict 모드에 준거
- 테스트 : 새로운 기능에 테스트를 추가하십시오.
- 보안 : 파일 조작 및 코드 실행에 적절한 검증을 구현하십시오.
