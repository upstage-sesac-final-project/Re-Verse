"""사용자 가이드 문서 엔드포인트.

GET  /docs        — 공개 (누구나 읽기)
PUT  /docs        — 관리자 전용 (내용 수정)
"""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.backend.core.security import get_admin_user

router = APIRouter()

_DOCS_PATH = Path("storage/docs.json")

_DEFAULT_SECTIONS = [
    {
        "key": "getting-started",
        "title": "시작하기",
        "content": """## Re:Verse란?

Re:Verse는 자연어로 RPG Maker MZ 게임을 제작할 수 있는 AI 기반 도구입니다.
복잡한 에디터 조작 없이 채팅으로 게임 요소를 만들고 수정할 수 있습니다.

## 첫 번째 프로젝트 만들기

1. **회원가입** 후 로그인하세요.
2. 대시보드에서 **새 프로젝트** 버튼을 클릭하세요.
3. 프로젝트 이름과 설명을 입력하고 생성합니다.
4. 에디터가 열리면 왼쪽 채팅창에 원하는 내용을 입력하세요.

## 기본 인터페이스

- **왼쪽**: AI 채팅 패널 — 명령어를 입력하는 곳
- **오른쪽 Play**: 게임 실행 미리보기
- **오른쪽 Map Viewer**: 맵과 이벤트 시각화
- **오른쪽 Game Data**: JSON 데이터 직접 확인""",
    },
    {
        "key": "ai-commands",
        "title": "AI 명령어 사용법",
        "content": """## 명령어 입력 방법

자연어로 원하는 내용을 입력하면 됩니다. 구체적일수록 결과가 정확합니다.

## 생성 예시

```
슬라임 몬스터를 HP 200, 공격력 30으로 만들어줘
파이어볼 마법 스킬 추가해줘 (MP 30, 불 속성, 전체 공격)
체력 회복 포션 아이템 만들어줘
```

## 수정 예시

```
고블린 HP를 500으로 올려줘
주인공 초기 레벨을 5로 설정해줘
슬라임 공격력을 두 배로 올려줘
```

## 조회 예시

```
현재 등록된 몬스터 목록 보여줘
주인공 스탯이 어떻게 돼?
스킬 목록 알려줘
```

## 팁

- 대상과 수치를 함께 명시하면 더 정확합니다.
- 한 번에 여러 요소를 요청할 수 있습니다.
- 모호한 요청은 AI가 추가 정보를 요청합니다.""",
    },
    {
        "key": "game-elements",
        "title": "게임 요소 종류",
        "content": """## 지원하는 RPG Maker MZ 요소

### 캐릭터 & 적
- **액터(Actor)**: 파티 캐릭터. 이름, 스탯, 직업, 장비 설정
- **적(Enemy)**: 몬스터. HP, 공격력, 드롭 아이템 등 설정
- **직업(Class)**: 직업별 스탯 성장률, 스킬 습득 레벨 설정

### 스킬 & 아이템
- **스킬(Skill)**: 공격/마법/버프 스킬. 속성, MP 소비, 범위 설정
- **아이템(Item)**: 회복 포션, 소모품 등. 효과와 가격 설정
- **무기(Weapon)** / **방어구(Armor)**: 장비 아이템 생성

### 시스템
- **상태이상(State)**: 독, 마비, 수면 등 상태 효과
- **시스템(System)**: 게임 제목, 화폐 단위, 시작 맵 등

## 속성(Element) 목록

기본 제공 속성: 물리, 불, 얼음, 번개, 물, 땅, 바람, 신성, 어둠""",
    },
    {
        "key": "map-viewer",
        "title": "맵 뷰어",
        "content": """## 맵 뷰어 사용법

에디터 오른쪽 **Map Viewer** 탭에서 게임 맵을 시각적으로 확인할 수 있습니다.

## 기능

- **맵 선택**: 상단 드롭다운으로 맵 전환
- **줌 조절**: 슬라이더 또는 +/- 버튼으로 확대/축소
- **이벤트 확인**: 맵 위 마커를 클릭하면 이벤트 상세 정보 표시

## 이벤트 색상 표시

| 색상 | 의미 |
|------|------|
| 파란색 | 장소 이동 (워프) |
| 초록색 | NPC |
| 주황색 | 기타 이벤트 |

## 이벤트 상세 패널

이벤트를 클릭하면 오른쪽에 상세 패널이 열립니다:
- 이벤트 이름, 좌표
- 페이지별 트리거 조건
- 실행 명령어 목록 (대화, 스위치, 아이템 등)""",
    },
    {
        "key": "faq",
        "title": "자주 묻는 질문",
        "content": """## Q. 요청이 실패하면 어떻게 하나요?

AI가 수정에 실패하면 자동으로 백업 파일에서 복구됩니다.
좀 더 구체적으로 요청을 다시 입력해보세요.

## Q. 프로젝트는 몇 개까지 만들 수 있나요?

기본 제공은 계정당 최대 3개입니다.

## Q. 게임 데이터를 직접 수정할 수 있나요?

오른쪽 **Game Data** 탭에서 JSON 형태로 데이터를 확인할 수 있습니다.
직접 편집은 현재 지원하지 않으며, AI 채팅을 통해 수정하세요.

## Q. 지원하지 않는 요소가 있나요?

현재 다음은 지원하지 않습니다:
- 스프라이트/그래픽 변경
- 배경음악/효과음 변경
- 플러그인 추가
- 맵 레이아웃 직접 편집

## Q. 변경 내용이 게임에 즉시 반영되나요?

네, AI 수정 후 **Play** 탭을 새로고침하면 반영된 게임을 바로 확인할 수 있습니다.""",
    },
]


def _load() -> list[dict]:
    if _DOCS_PATH.exists():
        try:
            return json.loads(_DOCS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return _DEFAULT_SECTIONS


def _save(sections: list[dict]) -> None:
    _DOCS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _DOCS_PATH.write_text(json.dumps(sections, ensure_ascii=False, indent=2), encoding="utf-8")


class DocsPayload(BaseModel):
    sections: list[dict]


@router.get("")
async def get_docs():
    """사용자 가이드 문서를 반환한다 (공개)."""
    return {"sections": _load()}


@router.put("", dependencies=[Depends(get_admin_user)])
async def update_docs(payload: DocsPayload):
    """사용자 가이드 문서를 수정한다 (관리자 전용)."""
    for s in payload.sections:
        if not s.get("key") or not s.get("title"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="각 섹션에 key와 title이 필요합니다.",
            )
    _save(payload.sections)
    return {"sections": payload.sections}
