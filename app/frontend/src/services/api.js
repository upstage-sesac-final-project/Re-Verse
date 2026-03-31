import { refresh } from './authApi'

const BASE_URL = import.meta.env.VITE_API_URL || '/api'

// 동시에 여러 401이 발생해도 refresh 한 번만 실행
let _refreshPromise = null

async function _doRefresh() {
  const refreshToken = localStorage.getItem('refresh_token')
  if (!refreshToken) throw new Error('No refresh token')

  const data = await refresh(refreshToken)
  sessionStorage.setItem('access_token', data.access_token)
  if (data.refresh_token) {
    localStorage.setItem('refresh_token', data.refresh_token)
  }
  return data.access_token
}

/**
 * Authenticated fetch — injects Authorization header, handles 401 + token refresh.
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
    try {
      if (!_refreshPromise) {
        _refreshPromise = _doRefresh().finally(() => { _refreshPromise = null })
      }
      accessToken = await _refreshPromise
      headers.Authorization = `Bearer ${accessToken}`
      res = await fetch(`${BASE_URL}${path}`, { ...options, headers })
    } catch {
      localStorage.removeItem('refresh_token')
      sessionStorage.removeItem('access_token')
      window.dispatchEvent(new CustomEvent('auth:session-expired'))
      window.location.href = `/login?redirect=${encodeURIComponent(window.location.pathname)}`
      throw new Error('Session expired')
    }
  }

  if (res.status === 204) return null

  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}))
    throw new Error(errorBody.detail || `API error: ${res.status}`)
  }

  return res.json()
}
