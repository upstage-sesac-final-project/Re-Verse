const BASE_URL = import.meta.env.VITE_API_URL || '/api'

export async function submitBugReport({ content, image }) {
  const accessToken = sessionStorage.getItem('access_token')
  const formData = new FormData()
  formData.append('content', content)
  if (image) formData.append('image', image, image.name || 'screenshot.png')

  const res = await fetch(`${BASE_URL}/v1/bug-report`, {
    method: 'POST',
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    body: formData,
  })

  if (res.status === 204) return null
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}))
    throw new Error(errorBody.detail || `API error: ${res.status}`)
  }
  return res.json().catch(() => null)
}
