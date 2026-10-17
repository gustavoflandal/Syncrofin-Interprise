/**
 * Teste de carga: dashboard e listagens principais
 *
 * Cenário: 50 usuários simultâneos por 2 minutos sobre base com ~1 M de transações.
 * Meta: p95 < 500 ms em todas as requisições.
 *
 * Variáveis de ambiente:
 *   BASE_URL    URL base da API  (padrão: http://localhost:8100)
 *   EMAIL       E-mail do usuário de teste (padrão: test@syncrofin.app)
 *   PASSWORD    Senha do usuário de teste  (padrão: SyncroFin123!)
 *   WORKSPACE   UUID do workspace (obrigatório quando a base tiver múltiplos workspaces)
 *
 * Execução:
 *   k6 run dashboard.js
 *   k6 run -e BASE_URL=http://prod:8100 -e EMAIL=... -e PASSWORD=... dashboard.js
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
    { duration: '30s', target: 10 },  // ramp-up
    { duration: '2m', target: 50 },   // carga estável
    { duration: '30s', target: 0 },   // ramp-down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],
    http_req_failed: ['rate<0.01'],
    dashboard_latency: ['p(95)<500'],
    accounts_latency: ['p(95)<400'],
    transactions_latency: ['p(95)<600'],
  },
}

const dashboardLatency = new Trend('dashboard_latency', true)
const accountsLatency = new Trend('accounts_latency', true)
const transactionsLatency = new Trend('transactions_latency', true)
const errorRate = new Rate('errors')

let headers

export function setup() {
  return { headers: login(EMAIL, PASSWORD) }
}

export default function (data) {
  headers = data.headers

  // Dashboard stats
  let res = http.get(`${BASE}/api/dashboard/stats`, { headers })
  dashboardLatency.add(res.timings.duration)
  errorRate.add(res.status !== 200)
  check(res, { 'dashboard stats 200': (r) => r.status === 200 })

  // Recent transactions (page 1)
  res = http.get(`${BASE}/api/transactions?limit=25&page=1`, { headers })
  transactionsLatency.add(res.timings.duration)
  errorRate.add(res.status !== 200)
  check(res, { 'transactions 200': (r) => r.status === 200 })

  // Accounts list
  res = http.get(`${BASE}/api/accounts`, { headers })
  accountsLatency.add(res.timings.duration)
  errorRate.add(res.status !== 200)
  check(res, { 'accounts 200': (r) => r.status === 200 })

  // Budget overview
  res = http.get(`${BASE}/api/budgets/overview`, { headers })
  errorRate.add(res.status !== 200 && res.status !== 404)

  sleep(1)
}
