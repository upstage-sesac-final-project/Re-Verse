import { createSlice, createAsyncThunk } from '@reduxjs/toolkit'
import { authFetch } from '../services/api'

export const fetchProjects = createAsyncThunk('game/fetchProjects', async (_, { rejectWithValue }) => {
  try {
    return await authFetch('/v1/games')
  } catch (e) {
    return rejectWithValue(e.message)
  }
})

export const createProject = createAsyncThunk(
  'game/createProject',
  async ({ name, description }, { rejectWithValue }) => {
    try {
      return await authFetch('/v1/games', { method: 'POST', body: JSON.stringify({ name, description }) })
    } catch (e) {
      return rejectWithValue(e.message)
    }
  },
)

export const updateProject = createAsyncThunk(
  'game/updateProject',
  async ({ projectId, data }, { rejectWithValue }) => {
    try {
      return await authFetch(`/v1/games/${projectId}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      })
    } catch (e) {
      return rejectWithValue(e.message)
    }
  },
)

export const deleteProject = createAsyncThunk(
  'game/deleteProject',
  async (projectId, { rejectWithValue }) => {
    try {
      await authFetch(`/v1/games/${projectId}`, { method: 'DELETE' })
      return projectId
    } catch (e) {
      return rejectWithValue(e.message)
    }
  },
)

const gameSlice = createSlice({
  name: 'game',
  initialState: {
    projects: [],
    currentProject: null,
    isLoading: false,
  },
  reducers: {
    setCurrentProject(state, action) {
      state.currentProject = action.payload
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchProjects.pending, (state) => {
        state.isLoading = true
      })
      .addCase(fetchProjects.fulfilled, (state, { payload }) => {
        state.projects = payload.projects ?? payload
        state.isLoading = false
      })
      .addCase(fetchProjects.rejected, (state) => {
        state.isLoading = false
      })
      .addCase(createProject.fulfilled, (state, { payload }) => {
        state.projects.unshift(payload)
      })
      .addCase(updateProject.fulfilled, (state, { payload }) => {
        const idx = state.projects.findIndex((p) => p.id === payload.id)
        if (idx !== -1) state.projects[idx] = payload
        if (state.currentProject?.id === payload.id) state.currentProject = payload
      })
      .addCase(deleteProject.fulfilled, (state, { payload }) => {
        state.projects = state.projects.filter((p) => String(p.id) !== String(payload))
        if (String(state.currentProject?.id) === String(payload)) state.currentProject = null
        try { localStorage.removeItem(`chat_${payload}`) } catch { /* ignore */ }
      })
  },
})

export const { setCurrentProject } = gameSlice.actions
export default gameSlice.reducer
