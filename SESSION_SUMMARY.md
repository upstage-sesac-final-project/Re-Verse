# 이번 세션 따라가기 가이드

> 이 세션에서 우리가 뭘 했는지를, 배경지식 없이도 따라올 수 있게 단계별로 풀어쓴 글입니다.
> 대화는 복잡했지만 핵심은 "Docker 빌드가 왜 깨졌고, 어떻게 고치기로 했는가" 하나입니다.

---

## 0. 큰 그림 한 줄

**배포할 때 Docker 이미지 빌드가 실패하고 있었고, 원인은 "Dockerfile이 옛날 경로를 그대로 쓰고 있어서"였다. 그래서 Dockerfile을 최신 상태에 맞게 고쳤다.** 끝.

나머지는 "왜 그렇게 고쳐야 하는지", "다른 방법은 없는지", "고치면서 뭘 망가뜨리진 않을지" 확인한 과정입니다.

---

## 1. 배경지식 (최소한만)

이 세션을 이해하려면 아래 용어 5개만 알면 됩니다.

### 1-1. Docker 이미지 / Dockerfile
- **Docker 이미지**: 서버에서 돌릴 프로그램을 "통째로 묶어놓은 압축 파일" 같은 것. OS, 파이썬, 우리 코드까지 다 들어있음.
- **Dockerfile**: 이 이미지를 "어떻게 만들지" 적어둔 레시피 파일. `docker build` 실행하면 이 레시피대로 이미지가 만들어짐.
- **빌드(build)**: 레시피대로 이미지를 만드는 과정.
- 우리 레포에선 `docker/backend.Dockerfile`이 그 레시피.

### 1-2. 멀티스테이지 빌드
- Dockerfile 하나 안에서 `FROM ...` 이 여러 번 나올 수 있음. 각각을 "스테이지"라고 부름.
- 우리 Dockerfile은 2-스테이지:
  - **스테이지 1 (mcp-builder)**: Node.js로 MCP 서버를 빌드
  - **스테이지 2 (python:3.12-slim)**: 실제 백엔드 서버를 담는 최종 이미지. 스테이지 1의 결과물을 복사해옴.
- 이번에 깨진 건 **스테이지 1**.

### 1-3. MCP (Model Context Protocol)
- LLM이 외부 도구를 호출할 때 쓰는 프로토콜.
- 우리 프로젝트는 "RPG Maker MZ 게임 파일을 수정하는 도구들"을 MCP 서버로 제공함.
- 이 MCP 서버가 Node.js로 만들어져 있어서, 백엔드 컨테이너 안에 **Node로 빌드해서 같이 담아야 함**. 그래서 스테이지 1이 필요한 거.

### 1-4. `.dockerignore`
- `git`의 `.gitignore`와 비슷. **Docker 빌드 컨텍스트에 어떤 파일을 올리지 않을지** 적는 파일.
- 여기 적힌 경로는 Dockerfile에서 `COPY` 해도 안 복사됨.

### 1-5. npm / postinstall
- **npm**: Node의 패키지 관리자. `npm install` = 의존성 설치.
- **postinstall 스크립트**: npm이 패키지 설치 직후 자동으로 실행하는 스크립트. 어떤 패키지는 이 단계에서 "네이티브 바이너리 컴파일"이나 "Chromium 다운로드" 같은 무거운 일을 함.
- `--ignore-scripts` 옵션: 이 postinstall을 **실행 안 하고 그냥 파일만 설치**하게 함.

---

## 2. 문제: 뭐가 깨졌나

사용자가 받은 에러는 이랬어요:

```
err: backend.Dockerfile:17
err:   17 | >>> RUN --mount=type=cache,target=/root/.npm \
err:   18 | >>>     set -eux; \
err:   19 | >>>     git clone --depth 1 "$MCP_REPO" /tmp/src-mcp; \
err:   20 | >>>     cd /tmp/src-mcp; \
err:   21 | >>>     if [ -f package-lock.json ]; then npm ci; else npm install; fi; \
err:   22 | >>>     npm run build; \
err:   23 | >>>     cp -R /tmp/src-mcp/. /mcp/default/
err: exit code: 1
```

해석:
- Dockerfile 17~23줄의 `RUN` 명령이 **exit code 1**로 끝남. 즉 **어딘가에서 실패**.
- 이 RUN 블록이 하는 일은:
  1. GitHub에서 외부 MCP 리포(`rein1225/RPGMakerMZ_MCP`)를 **git clone**
  2. `npm ci` 또는 `npm install`로 의존성 설치
  3. `npm run build`로 TypeScript 컴파일
  4. 결과물 복사

어딘가에서 실패했지만 **구체적으로 어느 줄인지 에러 메시지만으론 안 나옴**. Docker는 RUN 블록 전체를 찍어줄 뿐.

---

## 3. 원인 찾기

### 3-1. 왜 외부 리포를 clone하고 있지?

확인해보니 우리 레포 안에 `mcp/integration_MCP/` 폴더가 이미 있었어요. 이건 팀이 여러 MCP를 하나로 합친 **통합본**. 즉:

- **과거**: 외부 리포 `rein1225/RPGMakerMZ_MCP`를 가져다 썼음
- **현재**: 그걸 포함해 여러 MCP를 레포 내부에 `integration_MCP`로 통합함
- **근데 Dockerfile은 아직도 옛날 외부 리포를 clone하고 있었음** ← 이게 근본 원인

### 3-2. 그런데 왜 이제야 깨졌나?

외부 리포의 `package.json`을 확인해보니 의존성 두 개가 문제였습니다:

1. **`robotjs`** (devDependency, 마우스/키보드 제어 라이브러리)
   - 이건 **C++ 네이티브 모듈**이라 설치할 때 `node-gyp`로 컴파일해야 함.
   - 컴파일하려면 `python3`, `make`, `g++`, X11 헤더 같은 OS 패키지 필요.
   - 우리 Dockerfile 스테이지 1은 `node:20-alpine` 기반인데 `git bash`만 설치 → **컴파일 도구 없음** → 설치 단계에서 실패.

2. **`puppeteer`** (dependency, headless Chrome 제어)
   - 설치할 때 postinstall 스크립트가 **Chromium 브라우저(~170MB)를 다운로드**함.
   - CI 환경에서 네트워크/용량 이슈로 종종 실패.

둘 중 어느 쪽이든 실패하면 `set -eux`(한 줄이라도 실패하면 즉시 중단) 때문에 전체 RUN이 exit 1.

**"왜 이제야"**: 아마 이전엔 외부 리포 상태가 좀 달랐거나, CI 환경이 바뀌었거나, 아니면 예전엔 "어떻게든" 통과됐을 수도. 어쨌든 **지금 시점에선 이 경로가 깨질 수밖에 없는 구조**였어요.

---

## 4. 해결 방향 정하기 (대안 비교)

그냥 아무렇게나 고치면 안 되니까 **4가지 옵션**을 놓고 비교했습니다.

| Option | 설명 | 판정 |
|---|---|---|
| 1 | git clone 유지, `--ignore-scripts`만 추가 | ❌ 옛 외부 소스를 계속 쓰게 되는 근본 문제 해결 안 됨 |
| **2** | **외부 clone 제거 → 레포 내부 `mcp/integration_MCP` COPY + `--ignore-scripts`** | ✅ **채택** |
| 3 | 빌드 산출물(`dist/`)을 레포에 커밋해서 npm 빌드 자체를 없앰 | ❌ 반쪽짜리(런타임에 `node_modules` 필요), 레포 관리 복잡 |
| 4 | alpine에 빌드 도구 다 깔고 정식으로 robotjs 컴파일 | ❌ alpine에서 robotjs 컴파일은 악명 높게 불안정 |

**Option 2 선택 이유**: 우리 실제 사용 흐름(통합본을 쓰고 싶음)과 맞고, 리스크가 가장 작음.

---

## 5. Option 2 실행 전 5가지 확인

"갑자기 고쳤다가 또 깨지면" 곤란하니까, PR 올리기 전에 **5가지를 확인**했습니다.

| # | 확인 항목 | 결과 |
|---|---|---|
| 1 | `mcp/integration_MCP/package-lock.json` 있나? | ✅ 있음 (결정적 빌드 가능) |
| 2 | `.dockerignore`에 `mcp/` 차단 라인 있나? | 🚨 **있음!** → 고쳐야 함 |
| 3 | 빌드에 필요한 파일(`tsconfig.build.json`, `scripts/build-tool-registry.mjs`) 다 있나? | ✅ 다 있음 |
| 4 | `puppeteer`/`screenshot-desktop`을 런타임에 실제로 쓰나? | ⚠️ 일부 툴(`playtest`)에서 씀 — 이번 배포에선 안 불러진다는 전제 |
| 5 | 로컬에서 `docker build` 돌려봤나? | ❌ 사용자가 직접 해야 함 |

**#2가 특히 중요**: `.dockerignore`에 `mcp/`가 통째로 막혀있으면, Dockerfile에서 `COPY mcp/integration_MCP/` 해도 **빈 폴더가 복사**됨. 그러면 또 깨짐.

**#4 한계**: `--ignore-scripts`로 Chromium을 설치 안 하니까, `playtest` 기능이 런타임에 호출되면 에러 남. 지금은 그 기능 안 쓰는 전제로 통과.

---

## 6. 부가 논의들

### 6-1. revert 할까?
사용자가 로컬 커밋 이력이 살짝 얽혀있어서 `git revert` 할까 고민했는데, **비추했어요**. 이유:
- 얽힌 건 "커밋 이력"이 아니라 "브랜치 간 내용 동기화" 문제라 revert로 안 풀림
- revert는 새 커밋을 쌓으니까 오히려 이력이 더 복잡해짐
- 지금 로컬 변경은 다 "유효한 변경"이라 되돌릴 이유 없음

### 6-2. Dockerfile 전면 리팩터?
EC2 디스크 압박(overlay2 2.4GB) 얘기가 나왔을 때 "Dockerfile 다이어트 계획"도 검토했어요. 하지만:
- 한 번에 너무 많이 바꾸면 **배포가 아예 안 될 리스크**
- 이번 PR의 우선순위는 "CI/CD 통과 + 배포 성공"
- 그래서 **이번엔 MCP 빌드 수정만**, 나머지 다이어트는 별도 PR로 미룸
- 관련 메모는 `docs/todo/todolist-deploy.md`에 정리

### 6-3. 빌드 캐시 자동 청소?
"build 끝나고 캐시 자동 삭제" 코드 넣을 수 있냐는 질문에 대해:
- Dockerfile 안에는 못 넣음 (캐시는 Docker 데몬 관리)
- CI 스텝 / EC2 cron / 배포 스크립트 중 하나 추가
- 결정은 나중에, 일단 `todolist-deploy.md`에 옵션 정리해둠

### 6-4. `PUPPETEER_SKIP_DOWNLOAD=true`는 뭐?
- puppeteer가 설치 중 Chromium 브라우저(~170MB)를 자동 다운로드하는 걸 막는 환경변수.
- 이미 `--ignore-scripts`로 막고 있지만 **이중 안전장치 + 의도 전달** 용도.
- 없어도 빌드는 되지만 두면 안전.

---

## 7. 최종 변경 내역

커밋 1개로 들어간 파일 3개:

### 7-1. `docker/backend.Dockerfile` (수정)
- 외부 `git clone` 코드 제거
- `COPY mcp/integration_MCP/` 로 변경
- `npm ci --ignore-scripts` + `ENV PUPPETEER_SKIP_DOWNLOAD=true` 추가

### 7-2. `.dockerignore` (수정)
- `mcp/` 전체 차단 라인 제거
- 대신 선별 제외:
  - `mcp/rpgmaker-mz-mcp/` (레거시 산출물, 사용 안 함)
  - `mcp/integration_MCP/node_modules` (로컬 설치물, 이미지에 들어가면 안 됨)
  - `mcp/integration_MCP/dist`, `generated`, `test_project`, `automation`, `vendor`, `docs`, `merger`
  - `**/*.test.*`

### 7-3. `docs/todo/todolist-deploy.md` (신규)
- **[기록] 섹션**: 이번에 왜 이렇게 고쳤는지, 어떤 대안을 기각했는지 메모
- **빌드 캐시 자동 정리 섹션**: 후속 과제. A/B/C 옵션 비교만 적어둠

---

## 8. 다음 단계 (사용자가 할 일)

1. **로컬에서 빌드 돌려보기** (가장 중요)
   ```bash
   docker build -f docker/backend.Dockerfile .
   ```
   성공하면 OK. 실패하면 그 에러 기반으로 추가 수정 필요.

2. **커밋 & 푸시**
   ```bash
   git commit  # 이미 스테이지돼 있음. 메시지는 세션 중 작성한 초안 참고.
   git push origin feat/etc
   ```

3. **develop 대상 PR 생성**
   - PR 제목/본문 초안은 세션 마지막에 작성해둠
   - develop CI(Backend/Frontend) 초록 확인
   - develop → main 머지 → 배포 스텝 통과 확인

---

## 9. 용어 사전 (세션 중 나온 것)

- **CI/CD**: Continuous Integration/Delivery. PR 올렸을 때 자동으로 테스트/빌드/배포 돌리는 파이프라인.
- **build context**: `docker build` 실행할 때 Docker 데몬에 전송되는 파일 묶음. `.dockerignore`가 이 범위를 제한.
- **스테이지**: Dockerfile 안의 `FROM ... AS name` 블록 하나.
- **alpine**: 가벼운 리눅스 배포판. 이미지 크기는 작지만 기본 도구가 적음.
- **slim**: Debian 기반의 경량 변종. alpine보단 크지만 호환성 좋음.
- **native module (네이티브 모듈)**: npm 패키지 중 설치 시 C/C++ 컴파일이 필요한 것.
- **node-gyp**: Node.js 네이티브 모듈을 컴파일하는 도구.
- **headless Chrome**: GUI 없이 돌아가는 크롬. 자동화/테스트용.
- **postinstall hook**: npm install 직후 자동 실행되는 스크립트.
- **`set -eux`**: 쉘 옵션. `e`=에러 나면 중단, `u`=정의 안 된 변수 쓰면 에러, `x`=실행 명령 출력.
- **overlay2**: Docker의 파일시스템 드라이버. 이미지 레이어를 여기에 쌓음.
- **builder cache**: 빌드 중 중간 레이어 캐시. 빠른 재빌드용이지만 쌓이면 용량 먹음.

---

## 10. 한 줄 요약 (다시)

**"외부 리포 clone 대신 레포 안의 통합본을 쓰도록 Dockerfile 고쳤고, 부수 효과로 `.dockerignore`랑 문서도 손봤다."**

이게 전부입니다.
