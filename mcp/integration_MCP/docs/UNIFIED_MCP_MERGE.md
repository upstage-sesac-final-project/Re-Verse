# 단일 MCP 통합 가이드 (1~7단계)

이 문서는 **`RPGMakerMZ_MCP`(3번)를 베이스로** 워크스페이스의 MCP 1·2·4 기능을 **하나의 MCP 서버**로 합치는 절차를 단계별로 정리한 것입니다.
각 단계마다 **무엇을 하는지**와 **왜 그렇게 하는지**를 함께 적었습니다.

---

## 1. 목표 정의

### 무엇을 할지

- **산출물**: npm 패키지 **하나**, 실행 시 **프로세스 하나**, MCP `tools/list`에 **한 세트의 툴**이 보이게 할 것.
- **베이스**: 현재 저장소(`RPGMakerMZ_MCP`)의 `index.ts` → `handlers/` → `utils/` 구조를 유지.
- **이름 규칙**: `tool-registry.json`의 **canonical 이름 + alias + 프로파일(core/engine/generation/playtest)**.
- **호출 해석**: `resolveImplementationToolName`으로 레지스트리 이름 → 실제 `toolMap` 키로 매핑 (예: `create_actor` → `add_actor`).

### 왜 이렇게 정하는지

- “폴더를 한곳에 모았다”는 것만으로는 **MCP 서버가 하나**가 되지 않습니다. 목표를 **실행 단위(프로세스·툴 목록)** 로 명시해야 이후 작업이 흔들리지 않습니다.
- 이름 규칙을 먼저 고정해야 1·2·4에서 서로 다른 이름(`get_actors` vs `list_actors`)을 **한 규칙**으로 모을 수 있습니다.

### 저장소에 반영된 것

- `tool-registry.json`, `scripts/build-tool-registry.mjs`, `generated/toolRegistry.generated.ts`
- `index.ts`의 `CallTool`에서 구현 이름 해석

---

## 2. 준비: 인벤토리와 충돌·별칭

### 무엇을 할지

- 각 폴더에서 **등록 툴 이름**을 모읍니다.
  - `../-rpgmaker-mz-mcp` (MCP1): `src/index.ts`의 툴 정의
  - `../rpgmaker-mz-mcp` (MCP2): 대규모 `ListTools` 블록 + 시나리오/Gemini 툴
  - `./` (MCP3): `index.ts`의 `toolMap`
  - `../MCP-Maker` (MCP4): `src/tools/*.ts`의 `server.tool("이름", ...)`
- **의미가 겹치는 툴**은 표로 묶고, 통합 후 **canonical 하나 + alias**로 정합니다.

### 왜 하는지

- 나중에 포팅할 때 “이 툴이 어느 레포에서 왔는지”를 잃으면 중복 구현·이름 충돌이 납니다.
- 같은 일을 하는 툴을 미리 **한 이름으로 합치면** AI 클라이언트가 툴을 고르기 쉽습니다.

### 저장소에 반영된 것

- `merger/tool-inventory.json`: 폴더별 역할·대략적 툴 수·이름 충돌 예시
- `tool-registry.json`의 `aliasToCanonical`: 통합 별칭 표

---

## 3. 저장소 구조

### 무엇을 할지

- **실제 서버 코드**: 루트의 `index.ts`, `handlers/`, `utils/`, `toolSchemas.ts`만 런타임에 사용.
- **참고용 원본(선택)**: `vendor/` 아래에 1·2·4를 submodule/복사로 둘 수 있음 (`vendor/README.md` 참고).

### 왜 이렇게 나누는지

- 네 개 레포의 `package.json`·`node_modules`를 한꺼번에 합치면 **의존성 충돌**이 납니다.
- 통합 결과물은 **단일 패키지**로 배포하는 것이 목표이므로, 참고 코드는 **빌드에 포함하지 않는** 것이 안전합니다.

### 저장소에 반영된 것

- `vendor/README.md` (폴더 자체는 비어 있어도 됨)

---

## 4. 합치기 작업 순서 (페이즈)

### Phase 0 — 기반 고정

- **내용**: 3번의 `validateProjectPath`, `withBackup`, stderr 로깅, `CallTool` 응답 형식 유지.
- **이유**: 이후 포팅한 툴이 **같은 보안·복구 규칙**을 타도록 하기 위함.

### Phase 1 — 순수 데이터 (우선)

- **내용**: `data/*.json` 읽기/쓰기, 액터·아이템·스킬 CRUD 등 **파일만** 다루는 툴을 1·4에서 이식.
- **이유**: OS·exe에 덜 의존해 **테스트와 디버깅이 쉬움**.

### Phase 2 — 맵·이벤트

- **내용**: 맵 이벤트 조회/수정, 3번에 이미 있는 추상화(`add_dialogue` 등)와 겹치면 **한 구현만** 남기고 나머지는 alias.
- **이유**: 이벤트 리스트 구조가 깨지면 저장 파일이 망가지기 쉬움. **한 경로로만 쓰기**가 안전합니다.

### Phase 3 — 엔진·스캔·플러그인 설치

- **내용**: MCP4의 `install_plugin`, `scan_resources`, `get_database_limits` 등.
- **이유**: `RPGMAKER_ENGINE_PATH` 등 **환경 의존** → **engine 프로파일**로 묶고 기본 비활성 권장.

### Phase 4 — 생성·분석·외부 API (MCP2 등)

- **내용**: `generate_asset`, 시나리오, Gemini 호출.
- **이유**: API 키·비용·실패 모드가 다름 → **generation 프로파일**, 기본 off.

### Phase 5 — 플레이테스트

- **내용**: `run_playtest`, `inspect_game_state` (이미 3번에 있음).
- **이유**: OS·브라우저·Game.exe 의존 → **playtest 프로파일**.

### 저장소에 반영된 것

- `tool-registry.json`의 `profileByTool`, `defaultProfileFlags`
- (프로파일로 툴 목록을 필터링하는 로직은 **추가 구현 시** `ListTools`에서 적용 가능)

---

## 5. 코드 레벨 체크리스트

| 항목 | 이유 |
|------|------|
| 단일 `toolMap` | 여러 MCP 프로세스가 아니라 **한 라우팅 테이블**로 끝내야 함 |
| `toolSchemas`와 호출 가능 이름 일치 | 클라이언트가 보는 스키마와 실제 핸들러가 다르면 런타임 오류 |
| `@modelcontextprotocol/sdk` 버전 통일 | 프로토콜·타입 불일치 방지 |
| 쓰기 경로는 백업·검증 | 데이터 손실·path traversal 방지 |
| 미구현 canonical은 `ListTools`에서 제외 검토 | “보이는데 안 됨”을 줄임 |

### 감사 스크립트

- `node scripts/audit-tool-coverage.mjs` → `merger/implementation-status.json` 갱신
- **이유**: 레지스트리에만 있고 `index.ts`에 없는 툴을 **자동 집계**하기 위함.

---

## 6. 테스트 전략

### 무엇을 할지

- **유닛**: 핸들러별 — `test_project/` 또는 fixture JSON.
- **통합**: 짧은 시나리오 (예: 데이터 읽기 → 한 필드 수정 → undo).
- **E2E**: Game.exe·Puppeteer — 로컬·수동 또는 CI workflow_dispatch.

### 왜 나누는지

- 파일만 건드리는 툴은 CI에서 자주 돌리고, **실행 환경이 큰 툴**은 비용이 크므로 분리합니다.

---

## 7. 마이그레이션 후 (정리)

### 무엇을 할지

- 포팅이 끝난 레포는 `vendor/`에서 **삭제**하거나 submodule 해제.
- `tool-registry.json`에서 **사용하지 않는 canonical** 정리.
- `npm run build` / `audit:tools`로 **스키마·구현·레지스트리** 일치 확인.

### 왜 하는지

- 참고 코드를 영구 보관하면 **어느 코드가 진실인지** 혼란스러워집니다.
- 레지스트리에만 남은 이름은 **유지보수 부채**가 됩니다.

---

## 현재 스냅샷 (자동 생성)

`merger/implementation-status.json`을 생성하려면:

```bash
npm run audit:tools
```

최근 생성 기준 요약(예시):

- `canonicalTotal`: `tool-registry.json`의 canonical 개수
- `implementationKeysInIndex`: `index.ts` `toolMap`에 연결된 구현 키 개수
- `canonicalCallable`: 별칭·`canonicalToImplementationName`까지 적용해 **호출 가능한** canonical 개수
- `canonicalPending`: 아직 핸들러가 없는 canonical 목록

**의미**: 레지스트리는 “합친 뒤의 전체 설계도”이고, **실제 동작은 `canonicalPending`이 줄어드는 속도**로 따라갑니다.

### 기준선/동등성 리포트

```bash
npm run build:baseline
npm run report:diff
```

- `merger/compat-baseline.json`: 4개 원본 + 통합 레지스트리의 도구 이름/소스 분포 기준선
- `merger/tool-diff-report.json`: 도구별 `PASS / DIFF / ENV-BLOCKED` 분류 결과

### 단독 이동(standalone) 검증

```bash
npm run validate:standalone
```

- `merger/standalone-validation.json`를 생성해 아래를 검사:
  - 상대 경로(`file:../`) 의존성 없음
  - 엔트리 파일(`index.ts`)에서 형제 MCP 폴더 import 없음
  - `mcpToolMap.ts`가 내부 구현만 참조

---

## 관련 파일

| 파일 | 역할 |
|------|------|
| `tool-registry.json` | canonical / alias / 프로파일 / 구현 이름 매핑 |
| `scripts/build-tool-registry.mjs` | 레지스트리 → `generated/toolRegistry.generated.ts` |
| `scripts/build-compat-baseline.mjs` | 4개 MCP 기준선(`compat-baseline.json`) 생성 |
| `scripts/audit-tool-coverage.mjs` | 구현 커버리지 JSON 생성 |
| `scripts/report-tool-diff.mjs` | 원본 대비 `PASS/DIFF/ENV-BLOCKED` 리포트 |
| `scripts/validate-standalone.mjs` | 통합 폴더 단독 실행 가능성 검사 |
| `merger/tool-inventory.json` | 1·2·3·4 폴더 역할 요약 |
| `merger/implementation-status.json` | 감사 결과 (재생성) |
| `merger/compat-baseline.json` | 4개 MCP 기준선 산출물 |
| `merger/tool-diff-report.json` | 동등성 분류 리포트 |
| `merger/standalone-validation.json` | 단독 이동 검증 결과 |
| `vendor/README.md` | 참고 소스 보관 정책 |
