# Frontend Redesign Design Spec
**Date:** 2026-04-01
**Approach:** B — 글로벌 CSS + 컴포넌트별 리스타일

---

## Decisions

| 항목 | 결정 |
|------|------|
| 디자인 방향 | Studio Pro (macOS/Figma/Linear 감성) |
| 액센트 컬러 | Coral Red `#ff3b5c` (기존 `#e60012` 교체) |
| 에디터 레이아웃 | 왼쪽 채팅 유지 (현재 구조 유지) |
| 타이포그래피 | Pretendard (CDN) |

---

## 1. 글로벌 스타일 (`globals.css`)

### CSS Variables
```css
--bg-primary:    #1c1c1e
--bg-secondary:  #2c2c2e
--bg-tertiary:   #3a3a3c   (신규)
--accent:        #ff3b5c
--accent-hover:  #ff2d55   (신규)
--border:        #3a3a3c
--text-primary:  #f2f2f7
--text-secondary:#8e8e93
```

### Font
- Pretendard Static (jsdelivr CDN) `@import` 추가
- `body { font-family: 'Pretendard', -apple-system, system-ui, sans-serif }`

### Border Radius 토큰
- 카드/패널/모달: `10px`
- 버튼/배지/태그: `6px`
- 입력 필드: `8px`

---

## 2. 컴포넌트별 변경

### Header (`Header.jsx`)
- 배경: `#1c1c1e` → `#232323` (살짝 밝게, 구분감)
- 하단 보더: `1px solid #2c2c2e`
- 로고 아이콘: 원형 → `border-radius:6px` 사각 버전
- 버튼 hover: `background: #2c2c2e`

### 사이드 패널 / ChatInterface
- 배경: `#161618`
- 메시지 버블: user `#2c2c2e`, ai `#ff3b5c18` (아주 연한 accent)
- 입력 필드: `background:#1c1c1e`, `border:1px solid #3a3a3c`, `border-radius:8px`

### 버튼
- Primary: `background:#ff3b5c`, `border-radius:6px`, hover `#ff2d55`
- Secondary: `background:#2c2c2e`, hover `#3a3a3c`
- Ghost: border `1px solid #3a3a3c`, hover bg `#2c2c2e`

### 카드 (Dashboard 프로젝트 카드)
- `background:#2c2c2e`, `border-radius:10px`, `border:1px solid #3a3a3c`
- hover: `border-color:#ff3b5c44`, 가벼운 shadow

### 탭 (Play/Map/Data)
- 활성: 텍스트 `#ff3b5c` + 하단 `2px solid #ff3b5c`
- 비활성: 텍스트 `#8e8e93`, hover `#f2f2f7`

---

## 3. 페이지별 변경

### Home.jsx
- Hero: 그라디언트 배경 대신 미드-다크 단색 + 미묘한 패턴 or 그라디언트 overlay 제거
- CTA 버튼: Primary 스타일 적용
- 피처 카드: 새 카드 스타일 적용

### Dashboard.jsx
- 프로젝트 카드: 새 카드 스타일 + hover 효과
- "새 프로젝트" 버튼: Primary 스타일

### GameEditor.jsx
- 전반적인 배경/패널 색상 업데이트
- 탭바 스타일 업데이트

### Admin.jsx
- 통계 카드: 새 카드 스타일
- 차트 accent 색상: `#ff3b5c` 반영

### Docs.jsx
- 타이포그래피 개선 (Pretendard 상속으로 자동)
- 편집 모드 버튼 스타일 업데이트

---

## 4. 작업 순서

1. `globals.css` — CSS vars + Pretendard + 기본 button/input 스타일
2. `tailwind.config.js` — accent 색상 토큰 교체 (있다면)
3. `Header.jsx` — 레이아웃 변경 없이 색상/radius만
4. `ChatInterface.jsx` + `PromptInput.jsx` + `MessageList.jsx`
5. `GamePreview.jsx` 탭바
6. `Dashboard.jsx` 카드
7. `Home.jsx` Hero + 카드
8. `Admin.jsx`, `Docs.jsx`

---

## 5. 제약

- 백엔드 코드 수정 시 사용자 확인 후 진행
- 기존 기능/구조 변경 없이 스타일만 교체
- Tailwind 하드코딩 색상(`text-red-500` 등) → CSS var 기반으로 교체
