import { createSlice, createAsyncThunk } from '@reduxjs/toolkit'
import * as authApi from '../services/authApi'

export const initAuth = createAsyncThunk('user/initAuth', async (_, { rejectWithValue }) => {
  const refreshToken = localStorage.getItem('refresh_token')
  if (!refreshToken) return rejectWithValue('no token')
  try {
    return await authApi.refresh(refreshToken)
  } catch {
    localStorage.removeItem('refresh_token')
    return rejectWithValue('refresh failed')
  }
})

export const loginUser = createAsyncThunk(
  'user/login',
  async ({ email, password }, { rejectWithValue }) => {
    try {
      return await authApi.login(email, password)
    } catch (e) {
      return rejectWithValue(e.message)
    }
  },
)

export const registerUser = createAsyncThunk(
  'user/register',
  async ({ username, email, password }, { rejectWithValue }) => {
    try {
      return await authApi.register(username, email, password)
    } catch (e) {
      return rejectWithValue(e.message)
    }
  },
)

export const logoutUser = createAsyncThunk('user/logout', async () => {
  const refreshToken = localStorage.getItem('refresh_token')
  if (refreshToken) {
    try {
      await authApi.logout(refreshToken)
    } catch {
      // ignore logout errors
    }
  }
  localStorage.removeItem('refresh_token')
  sessionStorage.removeItem('access_token')
})

function applyTokenResponse(state, data) {
  state.user = { id: data.user_id, username: data.username, email: data.email ?? null, isAdmin: data.is_admin ?? false }
  state.accessToken = data.access_token
  state.isAuthenticated = true
  state.isLoading = false
  sessionStorage.setItem('access_token', data.access_token)
  if (data.refresh_token) {
    localStorage.setItem('refresh_token', data.refresh_token)
  }
}

const userSlice = createSlice({
  name: 'user',
  initialState: {
    user: null,
    accessToken: sessionStorage.getItem('access_token') || null,
    isAuthenticated: false,
    isLoading: true,
  },
  reducers: {
    setAccessToken(state, action) {
      state.accessToken = action.payload
      sessionStorage.setItem('access_token', action.payload)
    },
    clearAuth(state) {
      state.user = null
      state.accessToken = null
      state.isAuthenticated = false
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(initAuth.pending, (state) => {
        state.isLoading = true
      })
      .addCase(initAuth.fulfilled, (state, { payload }) => {
        applyTokenResponse(state, payload)
      })
      .addCase(initAuth.rejected, (state) => {
        state.isLoading = false
        state.isAuthenticated = false
      })
      .addCase(loginUser.fulfilled, (state, { payload }) => {
        applyTokenResponse(state, payload)
      })
      .addCase(loginUser.rejected, (state) => {
        state.isLoading = false
      })
      .addCase(registerUser.fulfilled, (state, { payload }) => {
        applyTokenResponse(state, payload)
      })
      .addCase(registerUser.rejected, (state) => {
        state.isLoading = false
      })
      .addCase(logoutUser.fulfilled, (state) => {
        state.user = null
        state.accessToken = null
        state.isAuthenticated = false
        state.isLoading = false
      })
  },
})

export const { setAccessToken, clearAuth } = userSlice.actions
export default userSlice.reducer
