import { createSlice, createAsyncThunk } from '@reduxjs/toolkit'
import { authFetch } from '../services/api'

export const startGeneration = createAsyncThunk(
  'generation/start',
  async ({ projectId, prompt, options = {} }, { rejectWithValue }) => {
    try {
      return await authFetch('/v1/generate', {
        method: 'POST',
        body: JSON.stringify({ project_id: projectId, prompt, options }),
      })
    } catch (err) {
      return rejectWithValue(err.message)
    }
  },
)

export const fetchGenerationStatus = createAsyncThunk(
  'generation/fetchStatus',
  async (generationId, { rejectWithValue }) => {
    try {
      return await authFetch(`/v1/generate/${generationId}/status`)
    } catch (err) {
      return rejectWithValue(err.message)
    }
  },
)

export const fetchActiveGeneration = createAsyncThunk(
  'generation/fetchActive',
  async (projectId, { rejectWithValue }) => {
    try {
      const data = await authFetch(`/v1/generate/by-project/${projectId}/status`)
      return { ...data, projectId }
    } catch {
      return rejectWithValue(null)
    }
  },
)

export const cancelGeneration = createAsyncThunk(
  'generation/cancel',
  async (generationId, { rejectWithValue }) => {
    try {
      await authFetch(`/v1/generate/${generationId}`, { method: 'DELETE' })
      return generationId
    } catch (err) {
      return rejectWithValue(err.message)
    }
  },
)

const initialState = {
  projectId: null,
  generationId: null,
  wsUrl: null,
  status: 'idle', // idle | starting | queued | in_progress | completed | completed_with_warnings | failed | cancelled
  progress: 0,
  currentPhase: '',
  message: '',
  queuePosition: 0,
  queueWaitSeconds: 0,
  completedPhases: [],
  events: [],
  finalMessage: null,
  validationErrors: [],
  validationWarnings: [],
  isSuccess: null,
  error: null,
}

const generationSlice = createSlice({
  name: 'generation',
  initialState,
  reducers: {
    reset: () => initialState,
    wsEventReceived: (state, action) => {
      const evt = action.payload
      state.events.push(evt)

      const { type, phase, progress, message, summary, warnings } = evt

      if (typeof progress === 'number') state.progress = progress
      if (phase) state.currentPhase = phase
      if (message || summary) state.message = message || summary

      if (type === 'queued') {
        state.status = 'queued'
        state.queuePosition = evt.queue_position || 0
        state.queueWaitSeconds = (evt.queue_position || 0) * 300
      }
      if (type === 'phase_complete' && phase) {
        if (!state.completedPhases.includes(phase)) {
          state.completedPhases.push(phase)
        }
      }
      if (type === 'completed') {
        state.status = 'completed'
        state.isSuccess = true
        state.finalMessage = message || summary || ''
      }
      if (type === 'completed_with_warnings') {
        state.status = 'completed_with_warnings'
        state.isSuccess = true
        state.finalMessage = message || summary || ''
      }
      if (type === 'warning' && warnings) {
        state.validationWarnings = [...state.validationWarnings, ...warnings]
      }
      if (type === 'error') {
        state.status = 'failed'
        state.error = message || '생성 중 오류가 발생했습니다.'
      }
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(startGeneration.pending, (state, action) => {
        state.projectId = action.meta.arg.projectId
        state.status = 'starting'
        state.error = null
        state.progress = 0
        state.completedPhases = []
        state.events = []
        state.validationErrors = []
        state.validationWarnings = []
        state.finalMessage = null
        state.isSuccess = null
      })
      .addCase(startGeneration.fulfilled, (state, action) => {
        state.generationId = action.payload.generation_id
        state.wsUrl = action.payload.ws_url
        state.queuePosition = action.payload.queue_position || 0
        state.queueWaitSeconds = action.payload.queue_wait_seconds || 0
        state.status = action.payload.queue_position > 0 ? 'queued' : 'in_progress'
      })
      .addCase(startGeneration.rejected, (state, action) => {
        state.status = 'failed'
        state.error = action.payload || '생성 요청에 실패했습니다.'
      })
      .addCase(fetchGenerationStatus.fulfilled, (state, action) => {
        const s = action.payload
        if (!['completed', 'completed_with_warnings', 'failed'].includes(state.status)) {
          state.status = s.status
        }
        // 서버 progress가 클라이언트보다 높을 때만 업데이트 (서버가 0을 반환해도 기존 값 유지)
        if (s.progress > state.progress) state.progress = s.progress
        if (s.completed_phases?.length && s.completed_phases.length >= state.completedPhases.length) state.completedPhases = s.completed_phases
        if (s.is_success != null) state.isSuccess = s.is_success
        if (s.final_message) state.finalMessage = s.final_message
        if (s.validation_errors?.length) state.validationErrors = s.validation_errors
        if (s.error_message) state.error = s.error_message
      })
      .addCase(fetchActiveGeneration.fulfilled, (state, action) => {
        const s = action.payload
        state.projectId = s.projectId
        state.generationId = s.generation_id
        state.status = s.status
        state.wsUrl = `/api/v1/generate/ws/${s.generation_id}`
        if (s.progress > state.progress) state.progress = s.progress
        if (s.completed_phases?.length) state.completedPhases = s.completed_phases
        if (s.is_success != null) state.isSuccess = s.is_success
        if (s.final_message) state.finalMessage = s.final_message
        if (s.error_message) state.error = s.error_message
        if (s.queue_position != null) state.queuePosition = s.queue_position
        if (s.queue_wait_seconds != null) state.queueWaitSeconds = s.queue_wait_seconds
      })
      .addCase(cancelGeneration.fulfilled, (state) => {
        state.status = 'cancelled'
      })
  },
})

export const { reset, wsEventReceived } = generationSlice.actions
export default generationSlice.reducer
