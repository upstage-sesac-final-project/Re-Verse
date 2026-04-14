import { authFetch } from './api'

export async function submitBugReport(content) {
  return authFetch('/v1/bug-report', {
    method: 'POST',
    body: JSON.stringify({ content }),
  })
}
