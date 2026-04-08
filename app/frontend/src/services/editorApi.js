import { authFetch } from './api'

/**
 * 편집 세션 시작 — S3에서 게임 데이터 다운로드
 * Backend: POST /api/v1/editor/{projectId}/enter
 */
export function enterEditor(projectId) {
  return authFetch(`/v1/editor/${projectId}/enter`, { method: 'POST' })
}

/**
 * 편집 세션 종료 — S3 업로드 + 로컬 정리
 * Backend: POST /api/v1/editor/{projectId}/exit
 */
export function exitEditor(projectId) {
  return authFetch(`/v1/editor/${projectId}/exit`, { method: 'POST' })
}

/**
 * 페이지 이탈 시 keepalive fetch로 exit 호출 (beforeunload용)
 */
export function exitEditorBeacon(projectId) {
  const token = sessionStorage.getItem('access_token')
  const baseUrl = import.meta.env.VITE_API_URL || '/api'
  fetch(`${baseUrl}/v1/editor/${projectId}/exit`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    keepalive: true,
  }).catch(() => {})
}
