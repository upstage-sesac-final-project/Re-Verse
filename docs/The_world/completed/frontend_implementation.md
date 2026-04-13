# 프론트엔드 구현 가이드

> Full Generation UI: Redux Toolkit 슬라이스, WebSocket 구독, 진행 상황 UI
> 기존 React 18 + Redux Toolkit + Vite 스택에 추가

---

## 기존 프론트엔드 구조와의 관계

```
app/frontend/src/
├── store/
│   ├── gameSlice.ts       ← 기존 (Incremental Edit 결과)
│   └── generationSlice.ts ← 신규 추가
├── services/
│   ├── gameService.ts     ← 기존
│   └── generationService.ts ← 신규 추가
├── pages/
│   ├── GamePage.tsx       ← 기존
│   └── GeneratePage.tsx   ← 신규 추가
└── components/
    ├── ...기존...
    └── generation/        ← 신규 디렉토리
        ├── GenerationForm.tsx
        ├── GenerationProgress.tsx
        └── GenerationResult.tsx
```

---

## Redux 슬라이스 (generationSlice.ts)

```typescript
// app/frontend/src/store/generationSlice.ts
import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';

// ── 타입 정의 ───────────────────────────────────────────────────────────────

export type GenerationStatus =
  | 'idle'
  | 'starting'
  | 'in_progress'
  | 'completed'              // 완전 성공
  | 'completed_with_warnings' // 부분 성공 (파일 저장됨, 검증 오류 존재)
  | 'failed'
  | 'cancelled';

export interface PhaseStatus {
  name: string;
  label: string;
  status: 'pending' | 'running' | 'done' | 'error';
  durationSeconds?: number;
  summary?: string;
}

export interface AssetsSummary {
  actors: number;
  skills: number;
  items: number;
  enemies: number;
  maps: number;
  events: number;
}

export interface GenerationState {
  generationId: string | null;
  status: GenerationStatus;
  progress: number;            // 0~100
  currentPhase: string | null;
  currentMessage: string | null;
  phases: PhaseStatus[];
  result: {
    title: string;
    assetsSummary: AssetsSummary;
    playUrl: string;
  } | null;
  error: string | null;
  warnings: string[];
  wsConnected: boolean;
}

// ── 페이즈 목록 (순서대로) ─────────────────────────────────────────────────

const PHASE_DEFINITIONS: Omit<PhaseStatus, 'status'>[] = [
  { name: 'spec',             label: '게임 기획' },
  { name: 'planning',         label: 'ID 테이블 구성' },
  { name: 'asset_generation', label: '캐릭터·스킬·적 생성' },
  { name: 'map_design',       label: '맵 설계' },
  { name: 'tile_generation',  label: '맵 타일 생성' },
  { name: 'event_planning',   label: '이벤트 기획' },
  { name: 'event_compilation',label: '이벤트 컴파일' },
  { name: 'integration',      label: '게임 파일 조립' },
  { name: 'validation',       label: '최종 검증' },
];

// ── 초기 상태 ─────────────────────────────────────────────────────────────

const initialState: GenerationState = {
  generationId: null,
  status: 'idle',
  progress: 0,
  currentPhase: null,
  currentMessage: null,
  phases: PHASE_DEFINITIONS.map(p => ({ ...p, status: 'pending' })),
  result: null,
  error: null,
  warnings: [],
  wsConnected: false,
};

// ── Async Thunks ───────────────────────────────────────────────────────────

export const startGeneration = createAsyncThunk(
  'generation/start',
  async (
    { prompt, projectId }: { prompt: string; projectId: number },
    { rejectWithValue }
  ) => {
    const res = await fetch('/api/v1/generate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem('access_token')}`,
      },
      body: JSON.stringify({ project_id: projectId, prompt }),
    });

    if (!res.ok) {
      const err = await res.json();
      return rejectWithValue(err.detail || '생성 시작 실패');
    }

    return await res.json();  // { generation_id, ws_url, ... }
  }
);

export const cancelGeneration = createAsyncThunk(
  'generation/cancel',
  async (generationId: string) => {
    await fetch(`/api/v1/generate/${generationId}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` },
    });
    return generationId;
  }
);

// ── 슬라이스 ──────────────────────────────────────────────────────────────

const generationSlice = createSlice({
  name: 'generation',
  initialState,
  reducers: {
    // WebSocket 이벤트 처리
    wsConnected(state) {
      state.wsConnected = true;
    },
    wsDisconnected(state) {
      state.wsConnected = false;
    },

    progressReceived(
      state,
      action: PayloadAction<{ phase: string; progress: number; message: string }>
    ) {
      const { phase, progress, message } = action.payload;
      state.status = 'in_progress';
      state.progress = progress;
      state.currentPhase = phase;
      state.currentMessage = message;

      // 현재 phase를 running으로 표시
      const phaseIdx = state.phases.findIndex(p => p.name === phase);
      if (phaseIdx >= 0) {
        state.phases[phaseIdx].status = 'running';
      }
    },

    phaseCompleted(
      state,
      action: PayloadAction<{
        phase: string;
        summary: string;
        durationSeconds: number;
      }>
    ) {
      const { phase, summary, durationSeconds } = action.payload;
      const phaseIdx = state.phases.findIndex(p => p.name === phase);
      if (phaseIdx >= 0) {
        state.phases[phaseIdx].status = 'done';
        state.phases[phaseIdx].summary = summary;
        state.phases[phaseIdx].durationSeconds = durationSeconds;
      }
    },

    generationCompleted(
      state,
      action: PayloadAction<{
        title: string;
        assetsSummary: AssetsSummary;
        playUrl: string;
        totalDurationSeconds: number;
      }>
    ) {
      state.status = 'completed';
      state.progress = 100;
      state.result = {
        title: action.payload.title,
        assetsSummary: action.payload.assetsSummary,
        playUrl: action.payload.playUrl,
      };
      // 미완료 phase는 모두 done으로
      state.phases = state.phases.map(p =>
        p.status !== 'done' ? { ...p, status: 'done' } : p
      );
    },

    generationFailed(
      state,
      action: PayloadAction<{ message: string; phase: string }>
    ) {
      state.status = 'failed';
      state.error = action.payload.message;
      const phaseIdx = state.phases.findIndex(
        p => p.name === action.payload.phase
      );
      if (phaseIdx >= 0) {
        state.phases[phaseIdx].status = 'error';
      }
    },

    warningReceived(state, action: PayloadAction<string[]>) {
      state.warnings = action.payload;
    },

    resetGeneration(state) {
      return {
        ...initialState,
        // 이전 결과 유지 (선택)
      };
    },
  },

  extraReducers: builder => {
    builder
      .addCase(startGeneration.pending, state => {
        state.status = 'starting';
        state.error = null;
        state.progress = 0;
        state.phases = PHASE_DEFINITIONS.map(p => ({ ...p, status: 'pending' }));
      })
      .addCase(startGeneration.fulfilled, (state, action) => {
        state.generationId = action.payload.generation_id;
      })
      .addCase(startGeneration.rejected, (state, action) => {
        state.status = 'failed';
        state.error = action.payload as string;
      })
      .addCase(cancelGeneration.fulfilled, state => {
        state.status = 'cancelled';
      });
  },
});

export const {
  wsConnected, wsDisconnected,
  progressReceived, phaseCompleted,
  generationCompleted, generationFailed,
  warningReceived, resetGeneration,
} = generationSlice.actions;

export default generationSlice.reducer;
```

---

## WebSocket 미들웨어 (generationMiddleware.ts)

Redux Toolkit의 Listener Middleware를 사용해서
WebSocket 연결/해제를 슬라이스와 연동한다.

```typescript
// app/frontend/src/store/generationMiddleware.ts
import { createListenerMiddleware } from '@reduxjs/toolkit';
import {
  startGeneration,
  wsConnected, wsDisconnected,
  progressReceived, phaseCompleted,
  generationCompleted, generationFailed,
  warningReceived,
} from './generationSlice';

export const generationListener = createListenerMiddleware();

let ws: WebSocket | null = null;

// startGeneration 성공 시 WebSocket 연결
generationListener.startListening({
  actionCreator: startGeneration.fulfilled,
  effect: async (action, listenerAPI) => {
    const { generation_id, ws_url } = action.payload;
    const token = localStorage.getItem('access_token');

    // 기존 연결 정리
    if (ws) {
      ws.close();
      ws = null;
    }

    ws = new WebSocket(`${ws_url}?token=${token}`);

    ws.onopen = () => {
      listenerAPI.dispatch(wsConnected());
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case 'progress':
          listenerAPI.dispatch(progressReceived({
            phase: data.phase,
            progress: data.progress,
            message: data.message,
          }));
          break;

        case 'phase_complete':
          listenerAPI.dispatch(phaseCompleted({
            phase: data.phase,
            summary: data.summary,
            durationSeconds: data.duration_seconds,
          }));
          break;

        case 'completed':
          listenerAPI.dispatch(generationCompleted({
            title: data.title,
            assetsSummary: data.assets_summary,
            playUrl: `/games/${data.game_id}/play`,
            totalDurationSeconds: data.total_duration_seconds,
          }));
          ws?.close();
          break;

        case 'completed_with_warnings':
          // 부분 성공: 파일은 저장됨, 검증 오류 존재 (responder_node.md 참조)
          listenerAPI.dispatch(generationCompleted({
            title: data.title || '',
            message: data.message,
            hasWarnings: true,
          }));
          ws?.close();
          break;

        case 'error':
          listenerAPI.dispatch(generationFailed({
            message: data.message,
            phase: data.phase || 'unknown',
          }));
          ws?.close();
          break;

        case 'warning':
          listenerAPI.dispatch(warningReceived(data.warnings));
          break;
      }
    };

    ws.onclose = () => {
      listenerAPI.dispatch(wsDisconnected());
    };

    ws.onerror = () => {
      listenerAPI.dispatch(generationFailed({
            message: 'WebSocket 연결 오류가 발생했습니다.',
            phase: 'connection',
          }));
    };
  },
});
```

---

## Store 등록

```typescript
// app/frontend/src/store/index.ts (기존에 추가)
import { configureStore } from '@reduxjs/toolkit';
import gameReducer from './gameSlice';
import generationReducer from './generationSlice';
import { generationListener } from './generationMiddleware';

export const store = configureStore({
  reducer: {
    game:       gameReducer,
    generation: generationReducer,   // 신규 추가
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware()
      .prepend(generationListener.middleware),  // 신규 추가
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
```

---

## UI 컴포넌트

### GenerationForm.tsx — 입력 폼

```typescript
// app/frontend/src/components/generation/GenerationForm.tsx
import { useState } from 'react';
import { useAppDispatch, useAppSelector } from '../../store/hooks';
import { startGeneration, resetGeneration } from '../../store/generationSlice';

interface Props {
  projectId: number;
}

export function GenerationForm({ projectId }: Props) {
  const [prompt, setPrompt] = useState('');
  const dispatch = useAppDispatch();
  const { status, error } = useAppSelector(s => s.generation);

  const isDisabled = ['starting', 'in_progress'].includes(status);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim() || isDisabled) return;
    dispatch(resetGeneration());
    dispatch(startGeneration({ prompt, projectId }));
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          어떤 게임을 만들까요?
        </label>
        <textarea
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          placeholder="예: 중세 판타지 게임 만들어줘. 기사 주인공으로."
          disabled={isDisabled}
          maxLength={500}
          rows={3}
          className="w-full border rounded-lg p-3 resize-none"
        />
        <p className="text-xs text-gray-400 text-right">{prompt.length}/500</p>
      </div>

      {error && (
        <div className="text-red-600 text-sm bg-red-50 p-3 rounded-lg">
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={isDisabled || !prompt.trim()}
        className="w-full bg-blue-600 text-white py-2 rounded-lg
                   disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {isDisabled ? '생성 중...' : '게임 생성하기'}
      </button>
    </form>
  );
}
```

### GenerationProgress.tsx — 진행 상황 UI

```typescript
// app/frontend/src/components/generation/GenerationProgress.tsx
import { useAppSelector, useAppDispatch } from '../../store/hooks';
import { cancelGeneration } from '../../store/generationSlice';

const PHASE_ICONS = {
  pending: '⬜',
  running: '⏳',
  done:    '✅',
  error:   '❌',
};

export function GenerationProgress() {
  const dispatch = useAppDispatch();
  const {
    status, progress, currentMessage, phases,
    generationId, warnings,
  } = useAppSelector(s => s.generation);

  if (status === 'idle') return null;

  return (
    <div className="bg-white border rounded-xl p-6 space-y-4">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-gray-800">
          {status === 'completed' ? '생성 완료!' : '게임 생성 중...'}
        </h3>
        {['starting', 'in_progress'].includes(status) && generationId && (
          <button
            onClick={() => dispatch(cancelGeneration(generationId))}
            className="text-sm text-gray-500 hover:text-red-500"
          >
            취소
          </button>
        )}
      </div>

      {/* 진행률 바 */}
      <div className="w-full bg-gray-100 rounded-full h-2">
        <div
          className="bg-blue-500 h-2 rounded-full transition-all duration-500"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* 현재 메시지 */}
      {currentMessage && (
        <p className="text-sm text-gray-600">{currentMessage}</p>
      )}

      {/* 단계별 상태 */}
      <ul className="space-y-2">
        {phases.map(phase => (
          <li
            key={phase.name}
            className={`flex items-start gap-2 text-sm ${
              phase.status === 'pending' ? 'text-gray-400' : 'text-gray-700'
            }`}
          >
            <span>{PHASE_ICONS[phase.status]}</span>
            <div>
              <span className={phase.status === 'running' ? 'font-medium' : ''}>
                {phase.label}
              </span>
              {phase.summary && (
                <p className="text-xs text-gray-500 mt-0.5">{phase.summary}</p>
              )}
              {phase.durationSeconds && phase.status === 'done' && (
                <span className="text-xs text-gray-400 ml-1">
                  ({phase.durationSeconds.toFixed(1)}s)
                </span>
              )}
            </div>
          </li>
        ))}
      </ul>

      {/* 밸런스 경고 */}
      {warnings.length > 0 && status === 'completed' && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
          <p className="text-xs font-medium text-yellow-800 mb-1">
            밸런스 주의사항
          </p>
          {warnings.map((w, i) => (
            <p key={i} className="text-xs text-yellow-700">{w}</p>
          ))}
        </div>
      )}
    </div>
  );
}
```

### GenerationResult.tsx — 완료 결과

```typescript
// app/frontend/src/components/generation/GenerationResult.tsx
import { useNavigate } from 'react-router-dom';
import { useAppSelector, useAppDispatch } from '../../store/hooks';
import { resetGeneration } from '../../store/generationSlice';

export function GenerationResult() {
  const navigate = useNavigate();
  const dispatch = useAppDispatch();
  const { status, result } = useAppSelector(s => s.generation);

  if (status !== 'completed' || !result) return null;

  const { title, assetsSummary, playUrl } = result;

  return (
    <div className="bg-green-50 border border-green-200 rounded-xl p-6 space-y-4">
      <div className="text-center">
        <h2 className="text-xl font-bold text-gray-900">"{title}"</h2>
        <p className="text-sm text-gray-500 mt-1">게임이 완성됐습니다!</p>
      </div>

      {/* 에셋 요약 */}
      <div className="grid grid-cols-3 gap-2 text-center">
        {[
          ['캐릭터', assetsSummary.actors],
          ['스킬', assetsSummary.skills],
          ['아이템', assetsSummary.items],
          ['적', assetsSummary.enemies],
          ['맵', assetsSummary.maps],
          ['이벤트', assetsSummary.events],
        ].map(([label, count]) => (
          <div key={label as string} className="bg-white rounded-lg p-2">
            <div className="text-lg font-bold text-blue-600">{count}</div>
            <div className="text-xs text-gray-500">{label}</div>
          </div>
        ))}
      </div>

      {/* 액션 버튼 */}
      <div className="flex gap-2">
        <button
          onClick={() => navigate(playUrl)}
          className="flex-1 bg-blue-600 text-white py-2 rounded-lg text-sm font-medium"
        >
          지금 플레이
        </button>
        <button
          onClick={() => dispatch(resetGeneration())}
          className="flex-1 border border-gray-300 py-2 rounded-lg text-sm"
        >
          새 게임 만들기
        </button>
      </div>
    </div>
  );
}
```

---

## GeneratePage.tsx — 전체 페이지

```typescript
// app/frontend/src/pages/GeneratePage.tsx
import { useParams } from 'react-router-dom';
import { GenerationForm } from '../components/generation/GenerationForm';
import { GenerationProgress } from '../components/generation/GenerationProgress';
import { GenerationResult } from '../components/generation/GenerationResult';
import { useAppSelector } from '../store/hooks';

export function GeneratePage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { status } = useAppSelector(s => s.generation);

  return (
    <div className="max-w-lg mx-auto py-8 px-4 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">게임 생성</h1>
        <p className="text-gray-500 text-sm mt-1">
          자연어로 RPG Maker MZ 게임을 자동 생성합니다.
        </p>
      </div>

      {/* 폼: 완료/실패 시에도 보여줌 (새 생성 가능) */}
      {status !== 'in_progress' && status !== 'starting' && (
        <GenerationForm projectId={Number(projectId)} />
      )}

      {/* 진행 상황 */}
      <GenerationProgress />

      {/* 완료 결과 */}
      <GenerationResult />
    </div>
  );
}
```

---

## 라우터 등록

```typescript
// app/frontend/src/App.tsx (기존에 추가)
import { GeneratePage } from './pages/GeneratePage';

// 라우트 추가
<Route path="/projects/:projectId/generate" element={<GeneratePage />} />
```

---

## 상태 흐름 다이어그램

```
idle
  │ 사용자 "게임 만들기" 클릭
  ▼
starting
  │ POST /api/v1/generate → generation_id 수신
  │ WebSocket 연결
  ▼
in_progress ←──────────────────────────────────┐
  │ progressReceived() 반복                     │
  │ phaseCompleted() 반복                       │
  │                              wsDisconnected │
  ├── (오류 발생) ──────────────────────────────┤
  │                                             │
  ▼                                        failed
completed
  │
  ▼
  (새 생성 시작 → resetGeneration() → idle)
```

---

## 에러 처리 UX

| 오류 상황 | UI 표시 | 사용자 액션 |
|---------|---------|-----------|
| 생성 시작 실패 (네트워크) | 인라인 오류 텍스트 | 다시 시도 버튼 |
| 생성 중 LLM 타임아웃 | "맵 생성 실패" + 재시도 가능 | 재시도 or 부분 재생성 선택 |
| 생성 중 서버 오류 | "오류가 발생했습니다" | 새 생성 시작 |
| WebSocket 연결 끊김 | 폴링으로 자동 전환 | 없음 (자동 처리) |

### WebSocket 실패 시 폴링 폴백

```typescript
// generationMiddleware.ts 추가
ws.onerror = () => {
  // WebSocket 실패 → 폴링으로 전환
  startPolling(generation_id, listenerAPI);
};

function startPolling(generationId: string, listenerAPI: any) {
  const interval = setInterval(async () => {
    const res = await fetch(`/api/v1/generate/${generationId}/status`);
    const data = await res.json();

    if (data.status === 'completed') {
      listenerAPI.dispatch(generationCompleted({ ... }));
      clearInterval(interval);
    } else if (data.status === 'failed') {
      listenerAPI.dispatch(generationFailed({ ... }));
      clearInterval(interval);
    } else {
      listenerAPI.dispatch(progressReceived({
        phase: data.phase,
        progress: data.progress,
        message: data.message,
      }));
    }
  }, 3000);  // 3초마다 폴링
}
```

---

## 참고 링크

- API 설계 (WebSocket 메시지 형식): `docs/The_world/generation_api.md`
- 워크플로우 (진행 상황 발행): `docs/The_world/workflow_implementation.md`
- 기존 프론트엔드: `app/frontend/src/`
