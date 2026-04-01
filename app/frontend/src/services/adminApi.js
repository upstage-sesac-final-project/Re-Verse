import { authFetch } from './api'

export function fetchOverview() {
  return authFetch('/v1/admin/stats/overview')
}

export function fetchSignups(period = 'daily', days = 30) {
  return authFetch(`/v1/admin/stats/signups?period=${period}&days=${days}`)
}

export function fetchLogins(period = 'daily', days = 30) {
  return authFetch(`/v1/admin/stats/logins?period=${period}&days=${days}`)
}

export function fetchUsage(period = 'daily', days = 30) {
  return authFetch(`/v1/admin/stats/usage?period=${period}&days=${days}`)
}

export function fetchIntents() {
  return authFetch('/v1/admin/stats/intents')
}

export function fetchHealth() {
  return authFetch('/v1/admin/health')
}
