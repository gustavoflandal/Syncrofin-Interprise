/**
 * Teste de carga: endpoints de relatórios (DRE/DFC)
 *
 * Meta: p95 < 2 s (relatórios são mais pesados que listagens).
 *
 * Variáveis de ambiente: mesmas de dashboard.js
 */
import http from 'k6/http'
import { check, sleep } from 'k6'
import { Trend, Rate } from 'k6/metrics'
import { login } from './auth.js'

const BASE = __ENV.BASE_URL || 'http://localhost:8100'
const EMAIL = __ENV.EMAIL || 'test@syncrofin.app'
const PASSWORD = __ENV.PASSWORD || 'SyncroFin123!'

export const options = {
  stages: [
    { duration: '30s', target: 5 },
    { duration: '2m', target: 20 },
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'],
    http_req_failed: ['rate<0.01'],
    dre_latency: ['p(95)<2000'],
    dfc_latency: ['p(95)<2000'],
    arap_latency: ['p(95)<1000'],
  },
}

const dreLatency = new Trend('dre_latency', true)
const dfcLatency = new Trend('dfc_latency', true)
const arapLatency = new Trend('arap_latency', true)
const errorRate = new Rate('errors')

const YEAR = new Date().getFullYear()
const MONTHS = Array.from({ length: 12 }, (_, i) => i + 1)

export function setup() {
  return { headers: login(EMAIL, PASSWORD) }
}

export default function (data) {
  const headers = data.headers
  const month = MONTHS[Math.floor(Math.random() * MONTHS.length)]
  const pad = String(month).padStart(2, '0')

  // DRE mensal
  let res = http.get(`${BASE}/api/reports/dre?year=${YEAR}&month=${pad}`, { headers })
  dreLatency.add(res.timings.duration)
  errorRate.add(res.status !== 200)
  check(res, { 'dre 200': (r) => r.status === 200 })

  // DFC
  res = http.get(`${BASE}/api/reports/dfc?year=${YEAR}&month=${pad}`, { headers })
  dfcLatency.add(res.timings.duration)
  errorRate.add(res.status !== 200)
  check(res, { 'dfc 200': (r) => r.status === 200 })

  // AR/AP overview
  res = http.get(`${BASE}/api/ar-ap/overview`, { headers })
  arapLatency.add(res.timings.duration)
  errorRate.add(res.status !== 200)
  check(res, { 'ar-ap overview 200': (r) => r.status === 200 })

  // AR/AP forecast
  res = http.get(`${BASE}/api/ar-ap/forecast`, { headers })
  arapLatency.add(res.timings.duration)
  errorRate.add(res.status !== 200)

  sleep(2)
}
