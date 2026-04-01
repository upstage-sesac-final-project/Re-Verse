const BASE_URL = import.meta.env.VITE_API_URL || '/api'

async function request(path, body) {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `API error: ${res.status}`)
  }
  return res.json()
}

export function login(email, password) {
  return request('/v1/auth/login', { email, password })
}

export function register(username, email, password) {
  return request('/v1/auth/register', { username, email, password })
}

export function refresh(refreshToken) {
  return request('/v1/auth/refresh', { refresh_token: refreshToken })
}

export async function logout(refreshToken) {
  const res = await fetch(`${BASE_URL}/v1/auth/logout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `API error: ${res.status}`)
  }
}
