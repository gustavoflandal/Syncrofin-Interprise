/**
 * Teste de carga: criação e listagem de transações
 *
 * Simula 30 usuários alternando entre leituras (80 %) e escritas (20 %).
 * Mede latência de INSERT e de queries com filtros pesados.
 *
 * Variáveis de ambiente: mesmas de dashboard.js
 *   ACCOUNT_ID  UUID de uma conta do workspace de teste (obrigatório para escritas)
 */
import http from 'k6/http'
import { check, sleep } from 'k6'
import { Trend, Rate, Counter } from 'k6/metrics'
import { login } from './auth.js'

const BASE = __ENV.BASE_URL || 'http://localhost:8100'
const EMAIL = __ENV.EMAIL || 'test@syncrofin.app'
const PASSWORD = __ENV.PASSWORD || 'SyncroFin123!'
const ACCOUNT_ID = __ENV.ACCOUNT_ID || ''

export const options = {
  stages: [
    { duration: '30s', target: 10 },
    { duration: '2m', target: 30 },
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<800'],
    http_req_failed: ['rate<0.01'],
    list_latency: ['p(95)<600'],
    create_latency: ['p(95)<800'],
  },
}

const listLatency = new Trend('list_latency', true)
const createLatency = new Trend('create_latency', true)
const errorRate = new Rate('errors')
const creates = new Counter('transactions_created')

const CATEGORIES = ['alimentação', 'transporte', 'moradia', 'lazer', 'saúde']
const TYPES = ['debit', 'credit']

export function setup() {
  return { headers: login(EMAIL, PASSWORD) }
}

export default function (data) {
  const headers = data.headers
  const isWrite = Math.random() < 0.2 && ACCOUNT_ID !== ''

  if (isWrite) {
    const amount = (Math.random() * 1000 + 1).toFixed(2)
    const payload = JSON.stringify({
      account_id: ACCOUNT_ID,
      date: new Date().toISOString().slice(0, 10),
      amount,
      type: TYPES[Math.floor(Math.random() * TYPES.length)],
      description: `k6 load test ${Date.now()}`,
    })
    const res = http.post(`${BASE}/api/transactions`, payload, {
      headers: { ...headers, 'Content-Type': 'application/json' },
    })
    createLatency.add(res.timings.duration)
    errorRate.add(res.status !== 201)
    if (res.status === 201) creates.add(1)
    check(res, { 'create 201': (r) => r.status === 201 })
  } else {
    // Listagem com filtro por tipo e página aleatória
    const page = Math.floor(Math.random() * 10) + 1
    const type = TYPES[Math.floor(Math.random() * TYPES.length)]
    const res = http.get(
      `${BASE}/api/transactions?limit=25&page=${page}&type=${type}`,
      { headers },
    )
    listLatency.add(res.timings.duration)
    errorRate.add(res.status !== 200)
    check(res, { 'list 200': (r) => r.status === 200 })
  }

  sleep(0.5)
}
