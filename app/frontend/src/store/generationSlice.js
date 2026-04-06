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
  generationId: null,
  wsUrl: null,
  status: 'idle', // idle | starting | in_progress | completed | completed_with_warnings | failed | cancelled
  progress: 0,
  currentPhase: '',
  message: '',
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
      .addCase(startGeneration.pending, (state) => {
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
        state.status = 'in_progress'
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
        state.progress = s.progress
        if (s.completed_phases?.length) state.completedPhases = s.completed_phases
        if (s.is_success != null) state.isSuccess = s.is_success
        if (s.final_message) state.finalMessage = s.final_message
        if (s.validation_errors?.length) state.validationErrors = s.validation_errors
        if (s.error_message) state.error = s.error_message
      })
      .addCase(cancelGeneration.fulfilled, (state) => {
        state.status = 'cancelled'
      })
  },
})

export const { reset, wsEventReceived } = generationSlice.actions
export default generationSlice.reducer
