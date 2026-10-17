/**
 * Helper: obtém access token via /api/auth/jwt/login e devolve o header Authorization.
 *
 * Uso:
 *   import { login } from './auth.js'
 *   const headers = login(__ENV.EMAIL, __ENV.PASSWORD)
 */
import http from 'k6/http'
import { check } from 'k6'

const BASE = __ENV.BASE_URL || 'http://localhost:8100'

export function login(email, password) {
  const res = http.post(
    `${BASE}/api/auth/jwt/login`,
    { username: email, password },
    { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
  )
  check(res, { 'login 200': (r) => r.status === 200 })
  const token = res.json('access_token')
  return { Authorization: `Bearer ${token}` }
}
