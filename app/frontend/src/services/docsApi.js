import { authFetch } from './api'

export async function fetchDocs() {
  const res = await fetch('/api/v1/docs')
  if (!res.ok) throw new Error('문서를 불러올 수 없습니다')
  return res.json()
}

export async function saveDocs(sections) {
  return authFetch('/v1/docs', {
    method: 'PUT',
    body: JSON.stringify({ sections }),
  })
}
