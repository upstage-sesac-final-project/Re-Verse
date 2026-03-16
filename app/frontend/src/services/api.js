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
