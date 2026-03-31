import { refresh } from './authApi'

const BASE_URL = import.meta.env.VITE_API_URL || '/api'

export async function post(path, body) {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}))
    throw new Error(errorBody.detail || `API error: ${res.status}`)
  }

  return res.json()
}

export async function get(path) {
  const res = await fetch(`${BASE_URL}${path}`)

  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}))
    throw new Error(errorBody.detail || `API error: ${res.status}`)
  }

  return res.json()
}

/**
 * Authenticated fetch — injects Authorization header, handles 401 + token refresh.
 * Reads tokens from sessionStorage/localStorage to avoid circular store imports.
 */
export async function authFetch(path, options = {}) {
  let accessToken = sessionStorage.getItem('access_token')
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
  }

  let res = await fetch(`${BASE_URL}${path}`, { ...options, headers })

  if (res.status === 401) {
    const refreshToken = localStorage.getItem('refresh_token')
    if (refreshToken) {
      try {
        const data = await refresh(refreshToken)
        accessToken = data.access_token
        sessionStorage.setItem('access_token', accessToken)
        if (data.refresh_token) {
          localStorage.setItem('refresh_token', data.refresh_token)
        }
        // Also update Redux store without importing it (dispatch via custom event)
        window.dispatchEvent(new CustomEvent('auth:token-refreshed', { detail: { accessToken } }))
        headers.Authorization = `Bearer ${accessToken}`
        res = await fetch(`${BASE_URL}${path}`, { ...options, headers })
      } catch {
        localStorage.removeItem('refresh_token')
        sessionStorage.removeItem('access_token')
        window.dispatchEvent(new CustomEvent('auth:session-expired'))
        window.location.href = '/login'
        throw new Error('Session expired')
      }
    } else {
      window.location.href = '/login'
      throw new Error('Unauthorized')
    }
  }

  if (res.status === 204) return null

  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}))
    throw new Error(errorBody.detail || `API error: ${res.status}`)
  }

  return res.json()
}
