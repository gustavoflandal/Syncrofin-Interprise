import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'

import { FinancialHealthCard } from '@/components/financial-health-card'
import { formatComponentValue } from '@/lib/health-format'
import { renderWithProviders } from '@/test/utils'
import type { CashFlowForecast, FinancialHealth, HealthComponent } from '@/types'

const api = vi.hoisted(() => ({ financialHealth: vi.fn(), cashFlowForecast: vi.fn() }))
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return { ...actual, dashboard: { ...actual.dashboard, ...api } }
})
vi.mock('@/hooks/use-display-locale', () => ({ useDisplayLocale: () => 'en-US' }))
// Recharts measures its container, which jsdom cannot; the card's own text is what is under test.
vi.mock('recharts', () => {
  const Stub = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>
  return {
    ResponsiveContainer: Stub, AreaChart: Stub, Area: Stub, CartesianGrid: Stub,
    ReferenceLine: Stub, Tooltip: Stub, XAxis: Stub, YAxis: Stub,
  }
})

const health = (over: Partial<FinancialHealth> = {}): FinancialHealth => ({
  score: 82,
  level: 'good',
  primary_currency: 'BRL',
  components: [
    { key: 'savings', value: 0.25, target: 0.2, score: 100, status: 'good' },
    { key: 'reserve', value: 3, target: 6, score: 50, status: 'attention' },
  ],
  avg_monthly_income: 1000,
  avg_monthly_expenses: 800,
  liquid_balance: 2400,
  over_budget: [],
  overdue_receivables: { count: 0, total: 0 },
  months_analysed: 3,
  ...over,
})

const forecast = (over: Partial<CashFlowForecast> = {}): CashFlowForecast => ({
  primary_currency: 'BRL',
  start_date: '2026-03-02',
  end_date: '2026-05-31',
  starting_balance: 2400,
  ending_balance: 1800,
  lowest_balance: 1500,
  lowest_balance_week_start: '2026-04-06',
  first_negative_week_start: null,
  net_by_source: {},
  buckets: [{ start: '2026-03-02', end: '2026-03-08', inflow: 0, outflow: 100, balance: 2300, events: 1 }],
  assumptions: { includes: [], excludes: [] },
  ...over,
})

describe('formatComponentValue', () => {
  const base: HealthComponent = { key: 'savings', value: 0.2, target: 0.2, score: 100, status: 'good' }

  it('shows savings and budget adherence as percentages', () => {
    expect(formatComponentValue(base, 'en-US', 'months')).toBe('20%')
    expect(formatComponentValue({ ...base, key: 'budget', value: 0.75 }, 'en-US', 'months')).toBe('75%')
  })

  it('shows the reserve as months of runway', () => {
    expect(formatComponentValue({ ...base, key: 'reserve', value: 4.5 }, 'en-US', 'months')).toBe('4.5 months')
  })
})

describe('FinancialHealthCard', () => {
  beforeEach(() => {
    api.financialHealth.mockReset()
    api.cashFlowForecast.mockReset()
    api.financialHealth.mockResolvedValue(health())
    api.cashFlowForecast.mockResolvedValue(forecast())
  })

  it('renders nothing until both answers are in', () => {
    api.financialHealth.mockReturnValue(new Promise(() => {}))
    renderWithProviders(<FinancialHealthCard />)
    expect(screen.queryByTestId('financial-health-card')).not.toBeInTheDocument()
  })

  it('shows the score, its level and every component with its target', async () => {
    renderWithProviders(<FinancialHealthCard />)

    expect(await screen.findByText('82')).toBeInTheDocument()
    expect(screen.getByText('In good shape')).toBeInTheDocument()
    expect(screen.getByText('Savings rate')).toBeInTheDocument()
    expect(screen.getByText('Emergency reserve')).toBeInTheDocument()
    expect(screen.getByText(/target 6 months/)).toBeInTheDocument()
    expect(screen.getByText('Based on the last 3 complete months')).toBeInTheDocument()
  })

  it('does not invent a verdict when there is no data', async () => {
    api.financialHealth.mockResolvedValue(health({ score: null, level: 'unknown', components: [] }))
    renderWithProviders(<FinancialHealthCard />)

    expect(await screen.findByText('No score yet')).toBeInTheDocument()
    expect(screen.getByText(/Not enough history yet/)).toBeInTheDocument()
  })

  it('warns, as an alert, when the forecast goes negative', async () => {
    api.cashFlowForecast.mockResolvedValue(
      forecast({ first_negative_week_start: '2026-04-13', lowest_balance: -900 }),
    )
    renderWithProviders(<FinancialHealthCard />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/goes negative from the week of/)
  })

  it('is quiet about the forecast when the balance stays positive', async () => {
    renderWithProviders(<FinancialHealthCard />)
    await screen.findByText('82')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('surfaces overdue receivables and states what the projection leaves out', async () => {
    api.financialHealth.mockResolvedValue(health({ overdue_receivables: { count: 2, total: 750 } }))
    renderWithProviders(<FinancialHealthCard />)

    await waitFor(() => expect(screen.getByText(/2 overdue receivable/)).toBeInTheDocument())
    expect(screen.getByText(/does not guess at everyday spending/)).toBeInTheDocument()
  })
})
