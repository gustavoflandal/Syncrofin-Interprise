import axios from 'axios'
import type { NumberFormat, DateFormat } from '@/lib/format'
import { getAccessToken, refreshAccessToken, setAccessToken } from '@/lib/access-token'
import { MFA_REQUIRED_EVENT } from '@/lib/mfa-events'
import type {
  User,
  AdminUser,
  AdminUserList,
  Passkey,
  PasskeyOptionsResponse,
  AppSetting,
  Category,
  CategoryRuleUsage,
  CategoryGroup,
  BankConnection,
  ConnectionSettings,
  Account,
  AccountSummary,
  Collection,
  CreditCardBill,
  Transaction,
  Payee,
  PayeeSummary,
  Invoice,
  InvoiceDirection,
  InvoiceDocumentPayload,
  InvoiceFacets,
  InvoiceLineInput,
  InvoiceShareLink,
  InvoiceWithholding,
  InvoiceWithholdingInput,
  IssuerProfile,
  IssuerTaxId,
  InvoiceSettings,
  InvoiceSummary,
  RecurringTransaction,
  ProjectedTransaction,
  TransactionCalendarResponse,
  Budget,
  BudgetVsActual,
  Rule,
  RuleAction,
  RuleConditionNode,
  RuleExportPayload,
  RuleImportResponse,
  RulePreviewResponse,
  ImportLog,
  ImportPreviewTransaction,
  FailedRow,
  PayeeTaxId,
  TaxIdKindOption,
  Workspace,
  WorkspaceKind,
  WorkspaceMember,
  WorkspaceRole,
  Asset,
  AssetGroup,
  AssetImportPreview,
  AssetImportResult,
  AssetOrderImport,
  AssetTransaction,
  AssetValue,
  MarketSymbolMatch,
  MarketSymbolQuote,
  Attachment,
  Goal,
  GoalSummary,
  DashboardSummary,
  SpendingByCategory,
  MonthlyTrend,
  BalanceHistory,
  PaginatedTransactions,
  ReportResponse,
  Group,
  GroupKind,
  GroupMember,
  GroupSettlement,
  GroupBalances,
  TransactionSplitsInput,
  TransactionEditPayload,
  InstallmentSeriesInput,
  TransactionApplyScope,
  InvoiceAttachment,
  ReconciliationNode,
  ReconciliationPolicyFile,
  ReconciliationRule,
  ReconciliationRuleDraft,
  ReconciliationRulePatch,
  ReconciliationSuggestion,
  ReconciliationHistoryEvent,
  FinancialHealth,
  CashFlowForecast,
  AppNotification,
  AuditFilters,
  RoleInfo,
  ApiTokenCreated,
  ApiTokenInfo,
  RolesCatalog,
  MfaPolicy,
  MfaStatus,
  DeviceSession,
  AuditPage,
  AuditVerification,
  AccessHistoryPage,
  AccessLogFilters,
  AccessRetention,
  DataRequest,
  DataRequestKind,
  DataRequestPage,
  AdminDataRequestPage,
  AdminDataRequest,
  CostCenter,
} from '@/types'

const api = axios.create({
  baseURL: '/api',
})

// Storage key for the currently-selected workspace ID. Lives in
// localStorage so reloads + new tabs stay on the same workspace until
// the user picks another one.
export const WORKSPACE_STORAGE_KEY = 'workspace_id'

// Add auth token + active workspace header to requests
api.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  const workspaceId = localStorage.getItem(WORKSPACE_STORAGE_KEY)
  if (workspaceId) {
    config.headers['X-Workspace-Id'] = workspaceId
  }
  return config
})

// Handle auth errors. The access token is short-lived, so a 401 on a request that carried one
// usually just means it ran out: renew it from the refresh cookie and send the request again,
// once. Only when there is no session left does the person go back to the login screen.
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error.config as (typeof error.config & { _retried?: boolean }) | undefined
    if (error.response?.status === 401) {
      const hadToken = !!config?.headers?.Authorization
      if (config && hadToken && !config._retried) {
        config._retried = true
        const fresh = await refreshAccessToken()
        if (fresh) {
          config.headers.Authorization = `Bearer ${fresh}`
          return api(config)
        }
      }
      setAccessToken(null)
      window.location.href = '/login'
    }
    if (error.response?.status === 403 && error.response?.data?.detail === 'MFA_ENROLLMENT_REQUIRED') {
      // The rule came into force while this page was open: let the app show the enrolment screen.
      window.dispatchEvent(new Event(MFA_REQUIRED_EVENT))
    }
    return Promise.reject(error)
  }
)

// Workspaces
export const workspaces = {
  list: async (): Promise<Workspace[]> => {
    const { data } = await api.get('/workspaces')
    return data
  },
  current: async (): Promise<Workspace> => {
    const { data } = await api.get('/workspaces/current')
    return data
  },
  create: async (payload: {
    name: string
    kind?: WorkspaceKind
    default_currency?: string
    locale?: string
    tax_jurisdiction?: string | null
    icon?: string
    color?: string
    self_membership?: boolean
  }): Promise<Workspace> => {
    const { data } = await api.post('/workspaces', payload)
    return data
  },
  // `kind` is absent on purpose: it is fixed when the workspace is created.
  update: async (
    id: string,
    payload: Partial<
      Pick<Workspace, 'name' | 'icon' | 'color' | 'default_currency' | 'locale'>
    > & {
      tax_jurisdiction?: string | null
      reconciliation_auto_apply_score?: number | null
      period_close_by?: string
      period_close_sync_mode?: string
      mfa_required?: boolean
      agents_enabled?: boolean
      agent_data_policy?: Record<string, boolean> | null
      segregation_enabled?: boolean
    },
  ): Promise<Workspace> => {
    const { data } = await api.patch(`/workspaces/${id}`, payload)
    return data
  },
  listMembers: async (id: string): Promise<WorkspaceMember[]> => {
    const { data } = await api.get(`/workspaces/${id}/members`)
    return data
  },
  invite: async (id: string, payload: { email: string; role?: WorkspaceRole; password?: string }): Promise<WorkspaceMember> => {
    const { data } = await api.post(`/workspaces/${id}/members`, payload)
    return data
  },
  changeRole: async (id: string, memberUserId: string, role: WorkspaceRole): Promise<WorkspaceMember> => {
    const { data } = await api.patch(`/workspaces/${id}/members/${memberUserId}`, { role })
    return data
  },
  removeMember: async (id: string, memberUserId: string): Promise<void> => {
    await api.delete(`/workspaces/${id}/members/${memberUserId}`)
  },
  stats: async (id: string): Promise<{ members: number; accounts: number; transactions: number }> => {
    const { data } = await api.get(`/workspaces/${id}/stats`)
    return data
  },
  archive: async (id: string): Promise<Workspace> => {
    const { data } = await api.post(`/workspaces/${id}/archive`)
    return data
  },
  listAccounts: async (id: string): Promise<Account[]> => {
    const { data } = await api.get(`/workspaces/${id}/accounts`)
    return data
  },
  setup: async (
    id: string,
    payload: { legal_name?: string; address?: string; tax_id?: string },
  ): Promise<Workspace> => {
    const { data } = await api.post(`/workspaces/${id}/setup`, payload)
    return data
  },
  uploadLogo: async (workspaceId: string, file: File): Promise<void> => {
    const form = new FormData()
    form.append('file', file)
    await api.post(`/workspaces/${workspaceId}/logo`, form)
  },
  deleteLogo: async (workspaceId: string): Promise<void> => {
    await api.delete(`/workspaces/${workspaceId}/logo`)
  },
  logoUrl: (workspaceId: string): string => `/api/workspaces/${workspaceId}/logo`,
}

// Setup
export const setup = {
  status: async (): Promise<{ has_users: boolean }> => {
    const { data } = await api.get('/setup/status')
    return data
  },
  createAdmin: async (email: string, password: string, currency = 'BRL', name = '', language = 'pt-BR'): Promise<{ access_token: string }> => {
    const { data } = await api.post('/setup/create-admin', { email, password, currency, name, language })
    return data
  },
}

// Auth
export const auth = {
  login: async (email: string, password: string) => {
    const formData = new URLSearchParams()
    formData.append('username', email)
    formData.append('password', password)
    const { data } = await api.post('/auth/login', formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    return data
  },
  register: async (email: string, password: string, preferences?: Record<string, string>) => {
    const { data } = await api.post('/auth/register', { email, password, preferences })
    return data
  },
  /** Ask for a reset link. The server answers 202 whether or not the address has an account. */
  forgotPassword: async (email: string): Promise<void> => {
    await api.post('/auth/forgot-password', { email })
  },
  /** Set a new password from an e-mailed token (a reset, or an invitation). */
  resetPassword: async (token: string, password: string): Promise<void> => {
    await api.post('/auth/reset-password', { token, password })
  },
  me: async (): Promise<User> => {
    const { data } = await api.get('/users/me')
    return data
  },
  /**
   * End this session on the server. The token is passed in because the caller clears it right
   * after, and a request interceptor would otherwise run too late to attach it.
   */
  logout: async (token?: string | null): Promise<void> => {
    await api.post('/auth/logout', null, token ? { headers: { Authorization: `Bearer ${token}` } } : undefined)
  },
  mfaStatus: async (): Promise<MfaStatus> => {
    const { data } = await api.get('/auth/mfa-status')
    return data
  },
  listSessions: async (): Promise<DeviceSession[]> => {
    const { data } = await api.get('/auth/sessions')
    return data
  },
  revokeSession: async (id: string): Promise<void> => {
    await api.delete(`/auth/sessions/${id}`)
  },
  revokeOtherSessions: async (): Promise<number> => {
    const { data } = await api.post('/auth/sessions/revoke-others')
    return data.revoked
  },
  /** The signed-in person's own recent accesses (sign-ins, failures, ended sessions, their tokens' use). */
  accessHistory: async (limit = 20): Promise<AccessHistoryPage> => {
    const { data } = await api.get('/auth/access-history', { params: { limit } })
    return data
  },
  updateMe: async (updates: Partial<User>): Promise<User> => {
    const { data } = await api.patch('/users/me', updates)
    return data
  },
  changePassword: async (password: string): Promise<User> => {
    const { data } = await api.patch('/users/me', { password })
    return data
  },
  setup2fa: async (): Promise<{ secret: string; otpauth_uri: string }> => {
    const { data } = await api.post('/auth/2fa/setup')
    return data
  },
  enable2fa: async (code: string): Promise<void> => {
    await api.post('/auth/2fa/enable', { code })
  },
  disable2fa: async (password: string, code: string): Promise<void> => {
    await api.post('/auth/2fa/disable', { password, code })
  },
  verify2fa: async (tempToken: string, code: string): Promise<{ access_token: string; token_type: string }> => {
    const { data } = await api.post('/auth/2fa/verify', { temp_token: tempToken, code })
    return data
  },
  listPasskeys: async (): Promise<Passkey[]> => {
    const { data } = await api.get('/auth/passkeys')
    return data
  },
  registerPasskeyOptions: async (name: string): Promise<PasskeyOptionsResponse> => {
    const { data } = await api.post('/auth/passkeys/register/options', { name })
    return data
  },
  verifyPasskeyRegistration: async (
    challengeId: string,
    name: string,
    credential: Record<string, unknown>,
  ): Promise<Passkey> => {
    const { data } = await api.post('/auth/passkeys/register/verify', {
      challenge_id: challengeId,
      name,
      credential,
    })
    return data
  },
  deletePasskey: async (id: string): Promise<void> => {
    await api.delete(`/auth/passkeys/${id}`)
  },
  passkeyAuthenticationOptions: async (email?: string): Promise<PasskeyOptionsResponse> => {
    const { data } = await api.post('/auth/passkeys/authenticate/options', { email })
    return data
  },
  verifyPasskeyAuthentication: async (
    challengeId: string,
    credential: Record<string, unknown>,
  ): Promise<{ access_token: string; token_type: string }> => {
    const { data } = await api.post('/auth/passkeys/authenticate/verify', {
      challenge_id: challengeId,
      credential,
    })
    return data
  },
  passkeySecondFactorOptions: async (tempToken: string): Promise<PasskeyOptionsResponse> => {
    const { data } = await api.post('/auth/passkeys/2fa/options', { temp_token: tempToken })
    return data
  },
  verifyPasskeySecondFactor: async (
    tempToken: string,
    challengeId: string,
    credential: Record<string, unknown>,
  ): Promise<{ access_token: string; token_type: string }> => {
    const { data } = await api.post('/auth/passkeys/2fa/verify', {
      temp_token: tempToken,
      challenge_id: challengeId,
      credential,
    })
    return data
  },
  oidcConfig: async (): Promise<{ enabled: boolean; provider_name: string; local_auth_enabled: boolean }> => {
    // The login card blocks on this call while it decides which sign-in
    // methods to offer, so a hung request must fail fast and let the caller
    // fall back instead of leaving the page stuck on its loading state.
    const { data } = await api.get('/auth/oidc/config', { timeout: 5000 })
    return data
  },
  samlConfig: async (): Promise<{ enabled: boolean; provider_name: string; local_auth_enabled: boolean }> => {
    const { data } = await api.get('/auth/saml/config', { timeout: 5000 })
    return data
  },
}

// Categories
export const categories = {
  list: async (): Promise<Category[]> => {
    const { data } = await api.get('/categories')
    return data
  },
  listIncludingHidden: async (): Promise<Category[]> => {
    const { data } = await api.get('/categories', { params: { include_hidden: true } })
    return data
  },
  create: async (category: Partial<Category>): Promise<Category> => {
    const { data } = await api.post('/categories', category)
    return data
  },
  update: async (
    id: string,
    category: Partial<Category>,
    options?: { deactivateRules?: boolean },
  ): Promise<Category> => {
    const { data } = await api.patch(`/categories/${id}`, category, {
      params: options?.deactivateRules ? { deactivate_rules: true } : undefined,
    })
    return data
  },
  ruleUsage: async (id: string): Promise<CategoryRuleUsage> => {
    const { data } = await api.get(`/categories/${id}/rule-usage`)
    return data
  },
  delete: async (id: string): Promise<void> => {
    await api.delete(`/categories/${id}`)
  },
  importCsv: async (file: File): Promise<{ created: number; skipped: number; failed: number; errors: string[] }> => {
    const form = new FormData()
    form.append('file', file)
    const { data } = await api.post('/categories/import', form)
    return data
  },
}

// Category Groups
export const categoryGroups = {
  list: async (): Promise<CategoryGroup[]> => {
    const { data } = await api.get('/category-groups')
    return data
  },
  listIncludingHidden: async (): Promise<CategoryGroup[]> => {
    const { data } = await api.get('/category-groups', { params: { include_hidden: true } })
    return data
  },
  create: async (group: Partial<CategoryGroup>): Promise<CategoryGroup> => {
    const { data } = await api.post('/category-groups', group)
    return data
  },
  update: async (id: string, group: Partial<CategoryGroup>): Promise<CategoryGroup> => {
    const { data } = await api.patch(`/category-groups/${id}`, group)
    return data
  },
  delete: async (id: string): Promise<void> => {
    await api.delete(`/category-groups/${id}`)
  },
}

// Bank Connections
export const connections = {
  list: async (): Promise<BankConnection[]> => {
    const { data } = await api.get('/connections')
    return data
  },
  getProviders: async (): Promise<{ name: string; display_name: string; description: string; flow_type: string; configured: boolean; requires_institution_select?: boolean; supports_asset_sync?: boolean }[]> => {
    const { data } = await api.get('/connections/providers')
    return data.providers
  },
  getConnectToken: async (provider = 'pluggy'): Promise<string> => {
    const { data } = await api.post('/connections/connect-token', { provider })
    return data.access_token
  },
  getOAuthUrl: async (provider: string, flow_params?: Record<string, unknown>): Promise<string> => {
    const { data } = await api.post('/connections/oauth/url', { provider, flow_params })
    return data.url
  },
  listInstitutions: async (
    provider: string,
    country?: string,
  ): Promise<{
    countries: string[]
    institutions: {
      name: string
      display_name: string
      country: string
      logo?: string | null
      bic?: string | null
      psu_types: string[]
      max_consent_days?: number | null
      max_history_days?: number | null
    }[]
  }> => {
    const { data } = await api.get(`/connections/${provider}/institutions`, {
      params: country ? { country } : undefined,
    })
    return data
  },
  handleCallback: async (
    code: string,
    provider: string,
    state?: string,
    settings?: Pick<ConnectionSettings, 'sync_assets'>,
    reconnectConnectionId?: string,
  ): Promise<BankConnection> => {
    const { data } = await api.post('/connections/oauth/callback', {
      code,
      provider,
      state,
      reconnect_connection_id: reconnectConnectionId,
      ...settings,
    })
    return data
  },
  getReauthUrl: async (connectionId: string): Promise<string> => {
    const { data } = await api.post(`/connections/${connectionId}/oauth/reauth-url`)
    return data.url
  },
  sync: async (id: string): Promise<BankConnection> => {
    const { data } = await api.post(`/connections/${id}/sync`)
    return data
  },
  getReconnectToken: async (connectionId: string): Promise<string> => {
    const { data } = await api.post(`/connections/${connectionId}/reconnect-token`)
    return data.access_token
  },
  updateSettings: async (
    id: string,
    settings: Partial<ConnectionSettings> & { display_name?: string | null },
  ): Promise<BankConnection> => {
    const { data } = await api.patch(`/connections/${id}/settings`, settings)
    return data
  },
  delete: async (id: string): Promise<void> => {
    await api.delete(`/connections/${id}`)
  },
}

// Accounts
export const accounts = {
  list: async (includeClosed = false): Promise<Account[]> => {
    const { data } = await api.get('/accounts', { params: { include_closed: includeClosed } })
    return data
  },
  get: async (id: string): Promise<Account> => {
    const { data } = await api.get(`/accounts/${id}`)
    return data
  },
  create: async (account: {
    name: string
    type: string
    balance?: number
    balance_date?: string
    currency?: string
    credit_limit?: number | null
    statement_close_day?: number | null
    payment_due_day?: number | null
  }): Promise<Account> => {
    const { data } = await api.post('/accounts', account)
    return data
  },
  update: async (id: string, account: Partial<Account>): Promise<Account> => {
    const { data } = await api.patch(`/accounts/${id}`, account)
    return data
  },
  delete: async (id: string): Promise<void> => {
    await api.delete(`/accounts/${id}`)
  },
  summary: async (id: string, from?: string, to?: string, billId?: string, unbilledOnly?: boolean): Promise<AccountSummary> => {
    const { data } = await api.get(`/accounts/${id}/summary`, { params: { from, to, bill_id: billId, unbilled_only: unbilledOnly || undefined } })
    return data
  },
  balanceHistory: async (id: string, from?: string, to?: string): Promise<{ date: string; balance: number; balance_primary?: number }[]> => {
    const { data } = await api.get(`/accounts/${id}/balance-history`, { params: { from, to } })
    return data
  },
  bills: async (id: string, limit = 24): Promise<CreditCardBill[]> => {
    const { data } = await api.get(`/accounts/${id}/bills`, { params: { limit } })
    return data
  },
  close: async (id: string): Promise<Account> => {
    const { data } = await api.post(`/accounts/${id}/close`)
    return data
  },
  reopen: async (id: string): Promise<Account> => {
    const { data } = await api.post(`/accounts/${id}/reopen`)
    return data
  },
}

// Transactions
export const transactions = {
  list: async (params?: {
    account_id?: string
    account_ids?: string[]
    category_id?: string
    category_ids?: string[]
    payee_id?: string
    uncategorized?: boolean
    type?: string
    status?: string
    from?: string
    to?: string
    bill_id?: string
    group_id?: string
    unbilled_only?: boolean
    q?: string
    page?: number
    limit?: number
    include_opening_balance?: boolean
    exclude_transfers?: boolean
    user_pnl_only?: boolean
    exclude_ignored?: boolean
    tags?: string[]
    min_amount?: number
    max_amount?: number
    sort_by?: string
    sort_dir?: 'asc' | 'desc'
  }): Promise<PaginatedTransactions> => {
    const { data } = await api.get('/transactions', {
      params,
      paramsSerializer: { indexes: null },
    })
    return data
  },
  calendar: async (params?: {
    month?: string
    account_id?: string
    account_ids?: string[]
  }): Promise<TransactionCalendarResponse> => {
    const { data } = await api.get('/transactions/calendar', {
      params,
      paramsSerializer: { indexes: null },
    })
    return data
  },
  get: async (id: string): Promise<Transaction> => {
    const { data } = await api.get(`/transactions/${id}`)
    return data
  },
  create: async (transaction: TransactionEditPayload): Promise<Transaction> => {
    const { data } = await api.post('/transactions', transaction)
    return data
  },
  createInstallments: async (payload: InstallmentSeriesInput): Promise<Transaction[]> => {
    const { data } = await api.post('/transactions/installments', payload)
    return data
  },
  update: async (
    id: string,
    transaction: TransactionEditPayload & {
      apply_to_transfer_pair?: boolean
      apply_to?: TransactionApplyScope
    },
  ): Promise<Transaction> => {
    const { data } = await api.patch(`/transactions/${id}`, transaction)
    return data
  },
  delete: async (id: string, applyTo: TransactionApplyScope = 'this'): Promise<void> => {
    await api.delete(`/transactions/${id}`, { params: { apply_to: applyTo } })
  },
  toggleIgnore: async (id: string): Promise<Transaction> => {
    const { data } = await api.patch(`/transactions/${id}/ignore`)
    return data
  },
  unlinkRecurring: async (id: string): Promise<Transaction> => {
    const { data } = await api.patch(`/transactions/${id}/unlink-recurring`)
    return data
  },
  createTransfer: async (transfer: {
    from_account_id: string
    to_account_id: string
    amount: number
    date: string
    description: string
    notes?: string
    destination_amount?: number
    to_workspace_id?: string
  }): Promise<{ debit: Transaction; credit: Transaction; transfer_pair_id: string }> => {
    const { data } = await api.post('/transactions/transfer', transfer)
    return data
  },
  bulkCategorize: async (transactionIds: string[], categoryId: string | null): Promise<{ updated: number }> => {
    const { data } = await api.patch('/transactions/bulk-categorize', {
      transaction_ids: transactionIds,
      category_id: categoryId,
    })
    return data
  },
  bulkAddTags: async (transactionIds: string[], tags: string[]): Promise<{ updated: number }> => {
    const { data } = await api.patch('/transactions/bulk-add-tags', {
      transaction_ids: transactionIds,
      tags,
    })
    return data
  },
  bulkRemoveTags: async (transactionIds: string[], tags: string[]): Promise<{ updated: number }> => {
    const { data } = await api.patch('/transactions/bulk-remove-tags', {
      transaction_ids: transactionIds,
      tags,
    })
    return data
  },
  bulkAddToGroup: async (
    transactionIds: string[],
    groupId: string,
    options?: {
      share_type?: 'equal' | 'percent'
      member_splits?: { group_member_id: string; share_pct?: number }[]
    },
  ): Promise<{ updated: number; skipped: number }> => {
    const { data } = await api.patch('/transactions/bulk-add-to-group', {
      transaction_ids: transactionIds,
      group_id: groupId,
      ...(options?.share_type ? { share_type: options.share_type } : {}),
      ...(options?.member_splits ? { member_splits: options.member_splits } : {}),
    })
    return data
  },
  bulkDelete: async (transactionIds: string[]): Promise<{ deleted: number }> => {
    const { data } = await api.post('/transactions/bulk-delete', {
      transaction_ids: transactionIds,
    })
    return data
  },
  linkTransfer: async (transactionIds: string[]): Promise<{ debit: Transaction; credit: Transaction; transfer_pair_id: string }> => {
    const { data } = await api.post('/transactions/link-transfer', {
      transaction_ids: transactionIds,
    })
    return data
  },
  createTransferCounterpart: async (
    transactionId: string,
    toAccountId: string,
  ): Promise<{ debit: Transaction; credit: Transaction; transfer_pair_id: string }> => {
    const { data } = await api.post(`/transactions/${transactionId}/create-counterpart`, {
      to_account_id: toAccountId,
    })
    return data
  },
  transferCandidates: async (transactionId: string, params?: { limit?: number; window_days?: number }): Promise<Transaction[]> => {
    const { data } = await api.get(`/transactions/${transactionId}/transfer-candidates`, { params })
    return data
  },
  transferPair: async (transactionId: string): Promise<Transaction | null> => {
    const { data } = await api.get(`/transactions/${transactionId}/transfer-pair`)
    return data
  },
  unlinkTransfer: async (pairId: string): Promise<void> => {
    await api.delete(`/connections/transfers/${pairId}`)
  },
  previewImport: async (file: File, options?: {
    date_format?: string
    flip_amount?: boolean
    inflow_column?: string
    outflow_column?: string
    column_mapping?: Record<string, string>
  }): Promise<{ transactions: ImportPreviewTransaction[]; detected_format: string; csv_columns?: string[]; parse_error?: string | null; failed_rows?: FailedRow[] }> => {
    const formData = new FormData()
    formData.append('file', file)
    if (options?.date_format) formData.append('date_format', options.date_format)
    if (options?.flip_amount) formData.append('flip_amount', 'true')
    if (options?.inflow_column) formData.append('inflow_column', options.inflow_column)
    if (options?.outflow_column) formData.append('outflow_column', options.outflow_column)
    if (options?.column_mapping && Object.keys(options.column_mapping).length > 0) {
      formData.append('column_mapping', JSON.stringify(options.column_mapping))
    }
    const { data } = await api.post('/transactions/import/preview', formData)
    return data
  },
  import: async (
    account_id: string,
    transactions: ImportPreviewTransaction[],
    filename: string,
    detected_format: string,
    options?: { detect_duplicates?: boolean },
  ): Promise<{ imported: number; skipped: number; excluded: number; import_log_id: string }> => {
    const payload: {
      account_id: string
      transactions: ImportPreviewTransaction[]
      filename: string
      detected_format: string
      detect_duplicates?: boolean
    } = { account_id, transactions, filename, detected_format }

    if (typeof options?.detect_duplicates === 'boolean') {
      payload.detect_duplicates = options.detect_duplicates
    }

    const { data } = await api.post('/transactions/import', payload)
    return data
  },
  export: async (params?: {
    account_id?: string
    account_ids?: string[]
    category_id?: string
    category_ids?: string[]
    payee_id?: string
    uncategorized?: boolean
    type?: string
    status?: string
    from?: string
    to?: string
    q?: string
    tags?: string[]
    exclude_ignored?: boolean
    transaction_ids?: string[]
  }): Promise<void> => {
    const { data } = await api.get('/transactions/export', {
      params,
      responseType: 'blob',
      paramsSerializer: { indexes: null },
    })
    const blob = new Blob([data], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `transactions-${new Date().toISOString().slice(0, 10)}.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  },
  attachments: {
    list: async (transactionId: string): Promise<Attachment[]> => {
      const { data } = await api.get(`/transactions/${transactionId}/attachments`)
      return data
    },
    upload: async (transactionId: string, file: File): Promise<Attachment> => {
      const formData = new FormData()
      formData.append('file', file)
      const { data } = await api.post(`/transactions/${transactionId}/attachments`, formData)
      return data
    },
    downloadUrl: async (transactionId: string, attachmentId: string): Promise<string> => {
      const { data } = await api.get(`/transactions/${transactionId}/attachments/${attachmentId}`, {
        responseType: 'blob',
      })
      return URL.createObjectURL(data)
    },
    rename: async (transactionId: string, attachmentId: string, filename: string): Promise<Attachment> => {
      const { data } = await api.patch(`/transactions/${transactionId}/attachments/${attachmentId}`, { filename })
      return data
    },
    delete: async (transactionId: string, attachmentId: string): Promise<void> => {
      await api.delete(`/transactions/${transactionId}/attachments/${attachmentId}`)
    },
  },
}

// Payees
/** Jurisdiction metadata. Labels, masks and ordering come from the server so
 *  the browser cannot disagree with it about what a document looks like. */
export const fiscal = {
  jurisdictions: async (): Promise<string[]> => {
    const { data } = await api.get('/fiscal/jurisdictions')
    return data.jurisdictions
  },
  taxIdKinds: async (): Promise<{
    jurisdiction: string | null
    kinds: TaxIdKindOption[]
    /** Country to documents, for grouping and searching the picker by country. */
    jurisdictions: { code: string; kinds: string[] }[]
  }> => {
    const { data } = await api.get('/fiscal/tax-id-kinds')
    return data
  },
}

export interface PayeeWritePayload {
  name?: string
  /** Null clears the legal nature. `source` is never writable. */
  type?: 'person' | 'company' | null
  notes?: string
  email?: string | null
  phone?: string | null
  address?: string | null
  website?: string | null
  is_favorite?: boolean
  /** Replaces the whole set. Omit to leave documents untouched. */
  tax_ids?: PayeeTaxId[]
}

export const payees = {
  list: async (params?: { q?: string; type?: string; is_favorite?: boolean } | Record<string, unknown>): Promise<Payee[]> => {
    const cleanParams = params && !('queryKey' in params) ? params : undefined
    const { data } = await api.get('/payees', { params: cleanParams })
    return data
  },
  get: async (id: string): Promise<Payee> => {
    const { data } = await api.get(`/payees/${id}`)
    return data
  },
  summary: async (id: string, from?: string, to?: string): Promise<PayeeSummary> => {
    const { data } = await api.get(`/payees/${id}/summary`, { params: { from, to } })
    return data
  },
  create: async (payee: PayeeWritePayload & { name: string }): Promise<Payee> => {
    const { data } = await api.post('/payees', payee)
    return data
  },
  update: async (id: string, payee: PayeeWritePayload): Promise<Payee> => {
    const { data } = await api.patch(`/payees/${id}`, payee)
    return data
  },
  delete: async (id: string): Promise<void> => {
    await api.delete(`/payees/${id}`)
  },
  merge: async (targetId: string, sourceIds: string[]): Promise<{ merged: number; transactions_reassigned: number }> => {
    const { data } = await api.post('/payees/merge', { target_id: targetId, source_ids: sourceIds })
    return data
  },
  bulkDelete: async (ids: string[]): Promise<{ deleted: number }> => {
    const { data } = await api.post('/payees/bulk-delete', { ids })
    return data
  },
  importCsv: async (file: File): Promise<{ created: number; skipped: number; failed: number; errors: string[] }> => {
    const form = new FormData()
    form.append('file', file)
    const { data } = await api.post('/payees/import', form)
    return data
  },
}

// Groups (split transactions)
export interface GroupCreatePayload {
  name: string
  kind?: GroupKind
  default_currency?: string
  icon?: string
  color?: string
  notes?: string | null
}

export interface GroupMemberPayload {
  name: string
  linked_user_id?: string | null
  email?: string | null
  is_self?: boolean
}

export interface GroupSettlementPayload {
  from_member_id: string
  to_member_id: string
  amount: number
  currency: string
  date: string
  transaction_id?: string | null
  notes?: string | null
  // When provided, the backend creates a debit transaction on this
  // account and links it via transaction_id. Mutually exclusive with
  // passing transaction_id directly.
  account_id?: string | null
  description?: string | null
}

export const groups = {
  list: async (includeArchived = false): Promise<Group[]> => {
    const { data } = await api.get('/groups', { params: { include_archived: includeArchived } })
    return data
  },
  get: async (id: string): Promise<Group> => {
    const { data } = await api.get(`/groups/${id}`)
    return data
  },
  create: async (payload: GroupCreatePayload): Promise<Group> => {
    const { data } = await api.post('/groups', payload)
    return data
  },
  update: async (id: string, payload: Partial<GroupCreatePayload> & { is_archived?: boolean }): Promise<Group> => {
    const { data } = await api.patch(`/groups/${id}`, payload)
    return data
  },
  delete: async (id: string): Promise<void> => {
    await api.delete(`/groups/${id}`)
  },
  members: {
    list: async (groupId: string): Promise<GroupMember[]> => {
      const { data } = await api.get(`/groups/${groupId}/members`)
      return data
    },
    create: async (groupId: string, payload: GroupMemberPayload): Promise<GroupMember> => {
      const { data } = await api.post(`/groups/${groupId}/members`, payload)
      return data
    },
    update: async (groupId: string, memberId: string, payload: Partial<GroupMemberPayload>): Promise<GroupMember> => {
      const { data } = await api.patch(`/groups/${groupId}/members/${memberId}`, payload)
      return data
    },
    delete: async (groupId: string, memberId: string): Promise<void> => {
      await api.delete(`/groups/${groupId}/members/${memberId}`)
    },
  },
  settlements: {
    list: async (groupId: string): Promise<GroupSettlement[]> => {
      const { data } = await api.get(`/groups/${groupId}/settlements`)
      return data
    },
    create: async (groupId: string, payload: GroupSettlementPayload): Promise<GroupSettlement> => {
      const { data } = await api.post(`/groups/${groupId}/settlements`, payload)
      return data
    },
    update: async (groupId: string, settlementId: string, payload: Partial<GroupSettlementPayload>): Promise<GroupSettlement> => {
      const { data } = await api.patch(`/groups/${groupId}/settlements/${settlementId}`, payload)
      return data
    },
    delete: async (groupId: string, settlementId: string): Promise<void> => {
      await api.delete(`/groups/${groupId}/settlements/${settlementId}`)
    },
  },
  balances: async (groupId: string): Promise<GroupBalances> => {
    const { data } = await api.get(`/groups/${groupId}/balances`)
    return data
  },
  transactions: async (groupId: string, limit = 20): Promise<Transaction[]> => {
    const { data } = await api.get(`/groups/${groupId}/transactions`, {
      params: { limit },
    })
    return data
  },
}

// Helper re-export so transaction-creation forms have a typed entry point.
export type { TransactionSplitsInput }

// User lookup: exact-match resolution for linking group members to
// existing SyncroFin users. Returns null on miss (404).
export interface UserLookupResult {
  id: string
  email: string
}

export const users = {
  lookupByEmail: async (email: string): Promise<UserLookupResult | null> => {
    try {
      const { data } = await api.get('/users/lookup', { params: { email } })
      return data
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 404) return null
      throw err
    }
  },
  directory: async (): Promise<UserLookupResult[]> => {
    const { data } = await api.get('/users/directory')
    return data
  },
}


// Categorization Rules
export const rules = {
  list: async (): Promise<Rule[]> => {
    const { data } = await api.get('/rules')
    return data
  },
  create: async (rule: Omit<Rule, 'id' | 'user_id'>): Promise<Rule & { applied_count: number }> => {
    const { data } = await api.post('/rules', rule)
    return data
  },
  update: async (id: string, rule: Partial<Rule>): Promise<Rule & { applied_count: number }> => {
    const { data } = await api.patch(`/rules/${id}`, rule)
    return data
  },
  delete: async (id: string): Promise<void> => {
    await api.delete(`/rules/${id}`)
  },
  preview: async (draft: {
    conditions_op: 'and' | 'or'
    conditions: RuleConditionNode[]
    actions: RuleAction[]
    is_active?: boolean
    apply_to_existing?: boolean
    overwrite_existing_categories?: boolean
    /** One window of the matches: `limit` of them starting at `offset`,
     * newest first. The counts are exact whatever the window is. */
    limit?: number
    offset?: number
  }): Promise<RulePreviewResponse> => {
    const { data } = await api.post('/rules/preview', draft)
    return data
  },
  applyAll: async (): Promise<{ applied: number }> => {
    const { data } = await api.post('/rules/apply-all')
    return data
  },
  exportFile: async (): Promise<void> => {
    const { data } = await api.get('/rules/export', { responseType: 'blob' })
    const blob = new Blob([data], { type: 'application/json;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `syncrofin-categorization-rules-${new Date().toISOString().slice(0, 10)}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  },
  importFile: async (payload: RuleExportPayload, overwrite = false): Promise<RuleImportResponse> => {
    const { data } = await api.post('/rules/import', { payload, overwrite })
    return data
  },
  packs: async (): Promise<{ code: string; name: string; flag: string; rule_count: number; installed: boolean }[]> => {
    const { data } = await api.get('/rules/packs')
    return data
  },
  installPack: async (
    packCode: string,
    createMissingCategories = false,
  ): Promise<{ installed: number; unresolved: number; categories_created: number }> => {
    const { data } = await api.post(`/rules/packs/${packCode}/install`, null, {
      params: { create_missing_categories: createMissingCategories },
    })
    return data
  },
}

// Recurring Transactions
// Reconciliation: the rules matching follows, and the matches it was
// not confident enough to make on its own.
export const reconciliation = {
  rules: async (): Promise<ReconciliationNode[]> => {
    const { data } = await api.get('/reconciliation/rules')
    return data
  },
  updateRule: async (
    node: string,
    id: string,
    patch: ReconciliationRulePatch,
  ): Promise<ReconciliationRule> => {
    const { data } = await api.patch(
      `/reconciliation/rules/${encodeURIComponent(node)}/${encodeURIComponent(id)}`,
      patch,
    )
    return data
  },
  /** Set the order rules are tried in. Names every rule in the set: the
   *  first match wins, so a half-implicit order rearranges itself the day
   *  a new default ships. */
  reorderRules: async (
    node: string,
    order: string[],
  ): Promise<ReconciliationRule[]> => {
    const { data } = await api.put(
      `/reconciliation/rules/${encodeURIComponent(node)}/order`,
      { order },
    )
    return data
  },
  createRule: async (rule: ReconciliationRuleDraft): Promise<ReconciliationRule> => {
    const { data } = await api.post('/reconciliation/rules', rule)
    return data
  },
  /** Get rid of a rule, whoever wrote it: ours included. What happens
   *  underneath differs (a rule of your own is a row and goes; one of
   *  ours ships in the image, so a tombstone records that this workspace
   *  does not run it) but that is our problem, not something to make a
   *  person learn. */
  deleteRule: async (node: string, id: string): Promise<void> => {
    await api.delete(
      `/reconciliation/rules/${encodeURIComponent(node)}/${encodeURIComponent(id)}`,
    )
  },
  /** Forget everything this workspace did to one of our rules (a moved
   *  threshold, a place in the order, a deletion), and go back to
   *  whatever we ship today. */
  resetRule: async (node: string, id: string): Promise<void> => {
    await api.post(
      `/reconciliation/rules/${encodeURIComponent(node)}/${encodeURIComponent(id)}/reset`,
    )
  },
  exportRules: async (): Promise<void> => {
    const { data } = await api.get('/reconciliation/rules/export', {
      responseType: 'blob',
    })
    const blob = new Blob([data], { type: 'application/json;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `syncrofin-reconciliation-rules-${new Date().toISOString().slice(0, 10)}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  },
  /** Replaces rather than merges: order is the mechanism here, and there
   *  is no correct way to interleave two orderings. Hence `overwrite`. */
  importRules: async (
    payload: ReconciliationPolicyFile,
    overwrite = false,
  ): Promise<{ imported: number; skipped: number }> => {
    const { data } = await api.post('/reconciliation/rules/import', {
      payload,
      overwrite,
    })
    return data
  },
  /** What matching did, newest first. `expectationId` narrows it to
   *  everything that ever happened to one invoice. */
  history: async (
    expectationId?: string,
  ): Promise<ReconciliationHistoryEvent[]> => {
    const { data } = await api.get('/reconciliation/history', {
      params: expectationId ? { expectation_id: expectationId } : undefined,
    })
    return data
  },
  suggestions: async (): Promise<ReconciliationSuggestion[]> => {
    const { data } = await api.get('/reconciliation/suggestions')
    return data
  },
  accept: async (id: string): Promise<ReconciliationSuggestion> => {
    const { data } = await api.post(`/reconciliation/suggestions/${id}/accept`)
    return data
  },
  decline: async (id: string): Promise<ReconciliationSuggestion> => {
    const { data } = await api.post(`/reconciliation/suggestions/${id}/decline`)
    return data
  },
}

export const recurring = {
  list: async (): Promise<RecurringTransaction[]> => {
    const { data } = await api.get('/recurring-transactions')
    return data
  },
  create: async (rt: Partial<RecurringTransaction>): Promise<RecurringTransaction> => {
    const { data } = await api.post('/recurring-transactions', rt)
    return data
  },
  update: async (id: string, rt: Partial<RecurringTransaction>): Promise<RecurringTransaction> => {
    const { data } = await api.patch(`/recurring-transactions/${id}`, rt)
    return data
  },
  delete: async (id: string): Promise<void> => {
    await api.delete(`/recurring-transactions/${id}`)
  },
  generate: async (): Promise<{ generated: number }> => {
    const { data } = await api.post('/recurring-transactions/generate')
    return data
  },
}

// Budgets
export const budgets = {
  list: async (month?: string): Promise<Budget[]> => {
    const { data } = await api.get('/budgets', { params: { month } })
    return data
  },
  create: async (budget: { category_id: string; amount: number; month: string; is_recurring?: boolean; cost_center_id?: string | null }): Promise<Budget> => {
    const { data } = await api.post('/budgets', budget)
    return data
  },
  update: async (id: string, budget: { amount?: number; cost_center_id?: string | null }): Promise<Budget> => {
    const { data } = await api.patch(`/budgets/${id}`, budget)
    return data
  },
  delete: async (id: string): Promise<void> => {
    await api.delete(`/budgets/${id}`)
  },
  comparison: async (month?: string): Promise<BudgetVsActual[]> => {
    const { data } = await api.get('/budgets/comparison', { params: { month } })
    return data
  },
}

// Goals
export const goals = {
  list: async (status?: string): Promise<Goal[]> => {
    const { data } = await api.get('/goals', { params: { status } })
    return data
  },
  get: async (id: string): Promise<Goal> => {
    const { data } = await api.get(`/goals/${id}`)
    return data
  },
  create: async (goal: Partial<Goal>): Promise<Goal> => {
    const { data } = await api.post('/goals', goal)
    return data
  },
  update: async (id: string, goal: Partial<Goal>): Promise<Goal> => {
    const { data } = await api.patch(`/goals/${id}`, goal)
    return data
  },
  delete: async (id: string): Promise<void> => {
    await api.delete(`/goals/${id}`)
  },
  summary: async (limit = 3): Promise<GoalSummary[]> => {
    const { data } = await api.get('/goals/summary', { params: { limit } })
    return data
  },
}

// Dashboard
// Repeated `account_ids=a&account_ids=b` (no [] brackets) so FastAPI's
// list[UUID] query param parses them. Only attached when a filter is active.
const acctIdsParam = (accountIds?: string[]) =>
  accountIds && accountIds.length > 0
    ? { params: { account_ids: accountIds }, paramsSerializer: { indexes: null as null } }
    : {}

export const dashboard = {
  summary: async (month?: string, balanceDate?: string, accountIds?: string[], assetGroupIds?: string[]): Promise<DashboardSummary> => {
    const hasFilter = (accountIds && accountIds.length > 0) || (assetGroupIds && assetGroupIds.length > 0)
    const { data } = await api.get('/dashboard/summary', {
      params: {
        month, balance_date: balanceDate,
        ...(accountIds && accountIds.length > 0 ? { account_ids: accountIds } : {}),
        ...(assetGroupIds && assetGroupIds.length > 0 ? { asset_group_ids: assetGroupIds } : {}),
      },
      ...(hasFilter ? { paramsSerializer: { indexes: null as null } } : {}),
    })
    return data
  },
  spendingByCategory: async (month?: string, accountIds?: string[]): Promise<SpendingByCategory[]> => {
    const extra = acctIdsParam(accountIds)
    const { data } = await api.get('/dashboard/spending-by-category', { params: { month, ...(extra.params ?? {}) }, ...(extra.paramsSerializer ? { paramsSerializer: extra.paramsSerializer } : {}) })
    return data
  },
  monthlyTrend: async (months = 6, accountIds?: string[]): Promise<MonthlyTrend[]> => {
    const extra = acctIdsParam(accountIds)
    const { data } = await api.get('/dashboard/monthly-trend', { params: { months, ...(extra.params ?? {}) }, ...(extra.paramsSerializer ? { paramsSerializer: extra.paramsSerializer } : {}) })
    return data
  },
  projectedTransactions: async (params?: { month?: string; account_id?: string; from?: string; to?: string }): Promise<ProjectedTransaction[]> => {
    const { data } = await api.get('/dashboard/projected-transactions', { params })
    return data
  },
  financialHealth: async (): Promise<FinancialHealth> => {
    const { data } = await api.get('/dashboard/financial-health')
    return data
  },
  cashFlowForecast: async (days = 90): Promise<CashFlowForecast> => {
    const { data } = await api.get('/dashboard/cash-flow-forecast', { params: { days } })
    return data
  },
  balanceHistory: async (month?: string, accountIds?: string[]): Promise<BalanceHistory> => {
    const extra = acctIdsParam(accountIds)
    const { data } = await api.get('/dashboard/balance-history', { params: { month, ...(extra.params ?? {}) }, ...(extra.paramsSerializer ? { paramsSerializer: extra.paramsSerializer } : {}) })
    return data
  },
}

// Assets
export const assets = {
  list: async (includeArchived = false): Promise<Asset[]> => {
    const { data } = await api.get('/assets', { params: { include_archived: includeArchived } })
    return data
  },
  get: async (id: string): Promise<Asset> => {
    const { data } = await api.get(`/assets/${id}`)
    return data
  },
  create: async (asset: Partial<Asset> & { name: string; type: string; current_value?: number }): Promise<Asset> => {
    const { data } = await api.post('/assets', asset)
    return data
  },
  update: async (id: string, asset: Partial<Asset>, opts?: { regenerateGrowth?: boolean }): Promise<Asset> => {
    const { data } = await api.patch(`/assets/${id}`, asset, {
      params: opts?.regenerateGrowth ? { regenerate_growth: true } : undefined,
    })
    return data
  },
  delete: async (id: string): Promise<void> => {
    await api.delete(`/assets/${id}`)
  },
  values: async (id: string): Promise<AssetValue[]> => {
    const { data } = await api.get(`/assets/${id}/values`)
    return data
  },
  valueTrend: async (id: string, months = 12): Promise<{ date: string; amount: number }[]> => {
    const { data } = await api.get(`/assets/${id}/value-trend`, { params: { months } })
    return data
  },
  addValue: async (id: string, value: { amount: number; date: string }): Promise<AssetValue> => {
    const { data } = await api.post(`/assets/${id}/values`, value)
    return data
  },
  deleteValue: async (valueId: string): Promise<void> => {
    await api.delete(`/assets/values/${valueId}`)
  },
  portfolioTrend: async (): Promise<{ assets: { id: string; name: string; type: string; group_id: string | null }[]; trend: Record<string, unknown>[]; total: number }> => {
    const { data } = await api.get('/assets/portfolio-trend')
    return data
  },
  marketSearch: async (q: string, limit = 15): Promise<MarketSymbolMatch[]> => {
    const { data } = await api.get('/assets/market/search', { params: { q, limit } })
    return data
  },
  marketQuote: async (symbol: string): Promise<MarketSymbolQuote> => {
    const { data } = await api.get('/assets/market/quote', { params: { symbol } })
    return data
  },
  refreshPrice: async (id: string): Promise<Asset> => {
    const { data } = await api.post(`/assets/${id}/refresh-price`)
    return data
  },
  // Transaction ledger (issue #235)
  transactions: async (id: string): Promise<AssetTransaction[]> => {
    const { data } = await api.get(`/assets/${id}/transactions`)
    return data
  },
  allTransactions: async (params?: { ticker?: string; kind?: 'buy' | 'sell' }): Promise<AssetTransaction[]> => {
    const { data } = await api.get('/assets/transactions', { params })
    return data
  },
  addTransaction: async (
    id: string,
    tx: { kind: 'buy' | 'sell'; quantity: number; price: number; fee?: number; date: string; notes?: string },
  ): Promise<Asset> => {
    const { data } = await api.post(`/assets/${id}/transactions`, tx)
    return data
  },
  updateTransaction: async (
    txId: string,
    tx: Partial<{ kind: 'buy' | 'sell'; quantity: number; price: number; fee: number; date: string; notes: string }>,
  ): Promise<Asset> => {
    const { data } = await api.patch(`/assets/transactions/${txId}`, tx)
    return data
  },
  deleteTransaction: async (txId: string): Promise<Asset> => {
    const { data } = await api.delete(`/assets/transactions/${txId}`)
    return data
  },
  buy: async (
    tx: { ticker: string; quantity: number; price: number; fee?: number; date: string; name?: string; group_id?: string | null; notes?: string },
  ): Promise<Asset> => {
    const { data } = await api.post('/assets/buy', tx)
    return data
  },
  previewImport: async (
    file: File,
    options?: { column_mapping?: Record<string, string>; date_format?: string; group_id?: string | null },
  ): Promise<AssetImportPreview> => {
    const formData = new FormData()
    formData.append('file', file)
    if (options?.date_format) formData.append('date_format', options.date_format)
    if (options?.group_id) formData.append('group_id', options.group_id)
    if (options?.column_mapping && Object.keys(options.column_mapping).length > 0) {
      formData.append('column_mapping', JSON.stringify(options.column_mapping))
    }
    const { data } = await api.post('/assets/import/preview', formData)
    return data
  },
  importOrders: async (
    orders: AssetOrderImport[],
    group_id?: string | null,
    filename?: string,
  ): Promise<AssetImportResult> => {
    const { data } = await api.post('/assets/import', { orders, group_id: group_id || null, filename })
    return data
  },
  importTemplate: async (): Promise<void> => {
    const { data } = await api.get('/assets/import/template', { responseType: 'blob' })
    const url = URL.createObjectURL(new Blob([data], { type: 'text/csv;charset=utf-8;' }))
    const a = document.createElement('a')
    a.href = url
    a.download = 'syncrofin-asset-orders.csv'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  },
}

// Asset Groups ("wallets")
export const assetGroups = {
  list: async (): Promise<AssetGroup[]> => {
    const { data } = await api.get('/asset-groups')
    return data
  },
  create: async (group: Partial<AssetGroup> & { name: string }): Promise<AssetGroup> => {
    const { data } = await api.post('/asset-groups', group)
    return data
  },
  update: async (id: string, group: Partial<AssetGroup>): Promise<AssetGroup> => {
    const { data } = await api.patch(`/asset-groups/${id}`, group)
    return data
  },
  delete: async (id: string): Promise<void> => {
    await api.delete(`/asset-groups/${id}`)
  },
}

// Collections — user-defined account groups for filtering (issue #105)
export const collections = {
  list: async (): Promise<Collection[]> => {
    const { data } = await api.get('/collections')
    return data
  },
  create: async (payload: { name: string; icon?: string; color?: string; account_ids?: string[]; wallet_ids?: string[] }): Promise<Collection> => {
    const { data } = await api.post('/collections', payload)
    return data
  },
  update: async (id: string, payload: Partial<{ name: string; icon: string; color: string; position: number; account_ids: string[]; wallet_ids: string[] }>): Promise<Collection> => {
    const { data } = await api.patch(`/collections/${id}`, payload)
    return data
  },
  delete: async (id: string): Promise<void> => {
    await api.delete(`/collections/${id}`)
  },
}

// Reports
export const reports = {
  netWorth: async (months = 12, interval = 'monthly', accountIds?: string[], assetGroupIds?: string[], period?: 'ytd'): Promise<ReportResponse> => {
    const hasFilter = (accountIds && accountIds.length > 0) || (assetGroupIds && assetGroupIds.length > 0)
    const { data } = await api.get('/reports/net-worth', {
      params: {
        months, interval, period,
        ...(accountIds && accountIds.length > 0 ? { account_ids: accountIds } : {}),
        ...(assetGroupIds && assetGroupIds.length > 0 ? { asset_group_ids: assetGroupIds } : {}),
      },
      ...(hasFilter ? { paramsSerializer: { indexes: null as null } } : {}),
    })
    return data
  },
  // `days` requests an exact rolling window ending today, instead of the
  // month-aligned window `months` produces.
  incomeExpenses: async (months = 12, interval = 'monthly', accountIds?: string[], period?: 'ytd', days?: number): Promise<ReportResponse> => {
    const extra = acctIdsParam(accountIds)
    const { data } = await api.get('/reports/income-expenses', { params: { months, interval, period, days, ...(extra.params ?? {}) }, ...(extra.paramsSerializer ? { paramsSerializer: extra.paramsSerializer } : {}) })
    return data
  },
  cashFlow: async (months = 6, interval = 'daily', baseline = false, accountIds?: string[]): Promise<ReportResponse> => {
    const extra = acctIdsParam(accountIds)
    const { data } = await api.get('/reports/cash-flow', { params: { months, interval, baseline, ...(extra.params ?? {}) }, ...(extra.paramsSerializer ? { paramsSerializer: extra.paramsSerializer } : {}) })
    return data
  },
  /** Download report as a file (PDF or XLSX). Uses blob pattern like accountantExport. */
  downloadFile: async (endpoint: string, filename: string): Promise<void> => {
    const { data } = await api.get(endpoint, { responseType: 'blob' })
    const blob = new Blob([data])
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  },
}

// DRE / DFC reports
// Note: Decimal fields are serialised as strings by Pydantic — convert with Number() before arithmetic.
export interface DreLine {
  label: string
  amount: string
  subcategories: DreLine[]
  budgeted?: string | null
}

export interface DreGroupLine {
  group_name: string
  lines: DreLine[]
  subtotal: string
  budgeted?: string | null
}

export interface DreSection {
  key: 'receita' | 'despesa' | 'custo' | 'neutro'
  label: string
  groups: DreGroupLine[]
  subtotal: string
  budgeted?: string | null
}

export interface DreReport {
  year: number
  month: number
  currency: string
  sections: DreSection[]
  gross_revenue: string
  deductions: string
  net_revenue: string
  operating_expenses: string
  result: string
  cost_center_id?: string | null
  prev_month?: DreReport
  accounting_mode?: string
  budget_result?: string | null
}

export interface DreQuarterlyReport {
  year: number
  quarter: number
  currency: string
  sections: DreSection[]
  gross_revenue: string
  operating_expenses: string
  result: string
  cost_center_id?: string | null
  months: DreReport[]
}

export interface DreAnnualReport {
  year: number
  currency: string
  sections: DreSection[]
  gross_revenue: string
  operating_expenses: string
  result: string
  cost_center_id?: string | null
  monthly: DreReport[]
}

export interface DfcReport {
  year: number
  month: number
  currency: string
  opening_balance: string
  closing_balance: string
  periods: { date: string; inflows: string; outflows: string; balance: string }[]
}

export const dreApi = {
  getDre: (
    year: number,
    month: number,
    ccId?: string | null,
    accountingMode?: string,
    showBudget?: boolean,
  ): Promise<DreReport> =>
    api
      .get('/reports/dre', {
        params: {
          year,
          month,
          ...(ccId ? { cost_center_id: ccId } : {}),
          ...(accountingMode && accountingMode !== 'competence' ? { accounting_mode: accountingMode } : {}),
          ...(showBudget ? { show_budget: true } : {}),
        },
      })
      .then((r) => r.data),
  getDfc: (year: number, month: number, ccId?: string | null): Promise<DfcReport> =>
    api
      .get('/reports/dfc', { params: { year, month, ...(ccId ? { cost_center_id: ccId } : {}) } })
      .then((r) => r.data),
  getDfcRange: (
    year: number,
    monthStart: number,
    monthEnd: number,
    ccId?: string | null,
  ): Promise<DfcReport[]> =>
    api
      .get('/reports/dfc/range', {
        params: {
          year,
          month_start: monthStart,
          month_end: monthEnd,
          ...(ccId ? { cost_center_id: ccId } : {}),
        },
      })
      .then((r) => r.data),
  getDreQuarterly: (
    year: number,
    quarter: number,
    ccId?: string | null,
    accountingMode?: string,
    showBudget?: boolean,
  ): Promise<DreQuarterlyReport> =>
    api
      .get('/reports/dre/quarterly', {
        params: {
          year,
          quarter,
          ...(ccId ? { cost_center_id: ccId } : {}),
          ...(accountingMode && accountingMode !== 'competence' ? { accounting_mode: accountingMode } : {}),
          ...(showBudget ? { show_budget: true } : {}),
        },
      })
      .then((r) => r.data),
  getDreAnnual: (
    year: number,
    ccId?: string | null,
    accountingMode?: string,
    showBudget?: boolean,
  ): Promise<DreAnnualReport> =>
    api
      .get('/reports/dre/annual', {
        params: {
          year,
          ...(ccId ? { cost_center_id: ccId } : {}),
          ...(accountingMode && accountingMode !== 'competence' ? { accounting_mode: accountingMode } : {}),
          ...(showBudget ? { show_budget: true } : {}),
        },
      })
      .then((r) => r.data),
  exportDre: (year: number, month: number, accountingMode?: string, showBudget?: boolean): Promise<void> =>
    api
      .get('/reports/dre/export', {
        params: {
          year,
          month,
          format: 'xlsx',
          ...(accountingMode && accountingMode !== 'competence' ? { accounting_mode: accountingMode } : {}),
          ...(showBudget ? { show_budget: true } : {}),
        },
        responseType: 'blob',
      })
      .then((r) => {
        const url = URL.createObjectURL(r.data)
        const a = document.createElement('a')
        a.href = url
        a.download = `dre_${year}_${String(month).padStart(2, '0')}.xlsx`
        a.click()
        URL.revokeObjectURL(url)
      }),
  exportDfc: (year: number, month: number): Promise<void> =>
    api
      .get('/reports/dfc/export', { params: { year, month, format: 'xlsx' }, responseType: 'blob' })
      .then((r) => {
        const url = URL.createObjectURL(r.data)
        const a = document.createElement('a')
        a.href = url
        a.download = `dfc_${year}_${String(month).padStart(2, '0')}.xlsx`
        a.click()
        URL.revokeObjectURL(url)
      }),
}

// Currencies
export const currencies = {
  list: async (): Promise<{ code: string; symbol: string; name: string; flag: string }[]> => {
    const { data } = await api.get('/currencies')
    return data
  },
}

// FX Rates
export const fxRates = {
  refresh: async (): Promise<{ synced: boolean; rates_count: number; date: string }> => {
    const { data } = await api.post('/fx-rates/refresh')
    return data
  },
  status: async (): Promise<{ last_sync_date: string | null; total_rates: number }> => {
    const { data } = await api.get('/fx-rates/status')
    return data
  },
}

// Import Logs
export const importLogs = {
  list: async (): Promise<ImportLog[]> => {
    const { data } = await api.get('/import-logs')
    return data
  },
  delete: async (id: string): Promise<void> => {
    await api.delete(`/import-logs/${id}`)
  },
}

// Settings
export const settings = {
  attachments: async (): Promise<{ allowed_extensions: string[]; max_file_size_mb: number; max_attachments_per_transaction: number }> => {
    const { data } = await api.get('/settings/attachments')
    return data
  },
}

// Backup
export const backup = {
  /**
   * Download the workspace archive, encrypted with AES-256 when a password is
   * given. POST rather than GET so the password stays out of browser history
   * and proxy logs.
   */
  download: async (password?: string): Promise<void> => {
    const { data } = await api.post(
      '/export/backup',
      password ? { password } : {},
      { responseType: 'blob' },
    )
    const blob = new Blob([data], { type: 'application/zip' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `syncrofin-backup-${new Date().toISOString().slice(0, 10)}.zip`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  },
}

// Accountant package: spreadsheet-ready CSVs for a period, in a zip.
export const accountantExport = {
  /**
   * POST rather than GET so an optional password stays out of browser history
   * and proxy logs (same reason as the backup).
   */
  download: async (start: string, end: string, password?: string): Promise<void> => {
    const { data } = await api.post(
      '/export/accountant',
      password ? { start, end, password } : { start, end },
      { responseType: 'blob' },
    )
    const blob = new Blob([data], { type: 'application/zip' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `syncrofin-contador-${start}_${end}.zip`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  },
  /** Same package as a single XLSX workbook (one sheet per CSV). */
  downloadXlsx: async (start: string, end: string): Promise<void> => {
    const { data } = await api.get('/export/accountant/xlsx', {
      params: { start, end },
      responseType: 'blob',
    })
    const blob = new Blob([data], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `syncrofin-contador-${start}_${end}.xlsx`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  },
}

// Notifications
export const notifications = {
  list: async (params?: { unread_only?: boolean; limit?: number }): Promise<AppNotification[]> => {
    const { data } = await api.get('/notifications', { params })
    return data
  },
  unreadCount: async (): Promise<number> => {
    const { data } = await api.get('/notifications/unread-count')
    return data.unread
  },
  /** Run the generators now instead of waiting for the hourly job. */
  refresh: async (): Promise<number> => {
    const { data } = await api.post('/notifications/refresh')
    return data.unread
  },
  markRead: async (id: string): Promise<void> => {
    await api.post(`/notifications/${id}/read`)
  },
  markAllRead: async (): Promise<void> => {
    await api.post('/notifications/read-all')
  },
}

// Roles of the current workspace and the permissions they are made of.
export const roles = {
  list: async (): Promise<RoleInfo[]> => {
    const { data } = await api.get('/roles')
    return data
  },
  catalog: async (): Promise<RolesCatalog> => {
    const { data } = await api.get('/roles/catalog')
    return data
  },
  create: async (payload: { name: string; description?: string; permissions: string[]; template?: string }): Promise<RoleInfo> => {
    const { data } = await api.post('/roles', payload)
    return data
  },
  update: async (id: string, payload: { name?: string; description?: string; permissions?: string[] }): Promise<RoleInfo> => {
    const { data } = await api.patch(`/roles/${id}`, payload)
    return data
  },
  remove: async (id: string): Promise<void> => {
    await api.delete(`/roles/${id}`)
  },
}

// API tokens of the current workspace: credentials for programs. The secret comes back once, from create and rotate.
export const apiTokens = {
  list: async (): Promise<ApiTokenInfo[]> => {
    const { data } = await api.get('/api-tokens')
    return data
  },
  create: async (payload: { name: string; scopes: string[]; days: number }): Promise<ApiTokenCreated> => {
    const { data } = await api.post('/api-tokens', payload)
    return data
  },
  rotate: async (id: string): Promise<ApiTokenCreated> => {
    const { data } = await api.post(`/api-tokens/${id}/rotate`)
    return data
  },
  revoke: async (id: string): Promise<void> => {
    await api.delete(`/api-tokens/${id}`)
  },
}

// Audit trail: read-only. There is deliberately nothing here that writes.
export const audit = {
  list: async (filters: AuditFilters, page: number, limit = 50): Promise<AuditPage> => {
    const { data } = await api.get('/audit', { params: { ...filters, page, limit } })
    return data
  },
  facets: async (): Promise<{ entity_types: string[]; actions: string[] }> => {
    const { data } = await api.get('/audit/facets')
    return data
  },
  exportCsv: async (filters: AuditFilters): Promise<void> => {
    const { data } = await api.get('/audit/export', { params: filters, responseType: 'blob' })
    const url = URL.createObjectURL(new Blob([data], { type: 'text/csv' }))
    const a = document.createElement('a')
    a.href = url
    a.download = 'auditoria.csv'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  },
  /** Administrator only: seals what is pending and checks the whole chain. */
  verify: async (): Promise<AuditVerification> => {
    const { data } = await api.get('/audit/verify')
    return data
  },
}

// Administrator: who got into the instance (or tried), and how long that is kept.
export const accessLog = {
  list: async (filters: AccessLogFilters, page: number, limit = 50): Promise<AuditPage> => {
    const { data } = await api.get('/admin/access-log', { params: { ...filters, page, limit } })
    return data
  },
  exportCsv: async (filters: AccessLogFilters): Promise<void> => {
    const { data } = await api.get('/admin/access-log/export', { params: filters, responseType: 'blob' })
    const url = URL.createObjectURL(new Blob([data], { type: 'text/csv' }))
    const a = document.createElement('a')
    a.href = url
    a.download = 'registros-de-acesso.csv'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  },
  retention: async (): Promise<AccessRetention> => {
    const { data } = await api.get('/admin/access-log/retention')
    return data
  },
  setRetention: async (days: number): Promise<AccessRetention> => {
    const { data } = await api.put('/admin/access-log/retention', { days })
    return data
  },
}

// D1: the titular's-channel requests (access, portability, correction, erasure).
export const dataRequests = {
  /** Access or portability: the same package either way. Downloads on the spot. */
  download: async (kind: Extract<DataRequestKind, 'access' | 'portability'>): Promise<void> => {
    const { data } = await api.post('/data-requests', { kind }, { responseType: 'blob' })
    const blob = new Blob([data], { type: 'application/zip' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `syncrofin-dados-${new Date().toISOString().slice(0, 10)}.zip`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  },
  createCorrection: async (selfService: boolean, detail?: string): Promise<DataRequest> => {
    const { data } = await api.post('/data-requests', { kind: 'correction', self_service: selfService, detail })
    return data
  },
  /** Throws on 401 (wrong password) or 409 (blocked by a shared workspace — see `WorkspacesBlockErasureBody`). */
  erasure: async (password: string): Promise<DataRequest> => {
    const { data } = await api.post('/data-requests/erasure', { password })
    return data
  },
  listOwn: async (): Promise<DataRequestPage> => {
    const { data } = await api.get('/data-requests')
    return data
  },
  adminList: async (status?: string): Promise<AdminDataRequestPage> => {
    const { data } = await api.get('/admin/data-requests', { params: status ? { status } : undefined })
    return data
  },
  adminResolve: async (id: string, status: 'resolved_manual' | 'rejected', resolutionNote?: string): Promise<AdminDataRequest> => {
    const { data } = await api.patch(`/admin/data-requests/${id}`, { status, resolution_note: resolutionNote })
    return data
  },
}

// Reconciliation: accept the suggestions above the workspace's confidence bar now.
export const reconciliationAuto = {
  run: async (): Promise<{ applied: number; skipped: number; failed: number }> => {
    const { data } = await api.post('/reconciliation/suggestions/auto-apply')
    return data
  },
}

// Data Retention (D2)
export interface RetentionPolicy {
  id: string
  workspace_id: string
  transaction_retention_days: number
  attachment_retention_days: number
  audit_retention_days: number
  anonymize_on_expiry: boolean
  last_purge_at: string | null
  created_at: string
  updated_at: string | null
}

export interface RetentionPolicyUpdate {
  transaction_retention_days?: number
  attachment_retention_days?: number
  audit_retention_days?: number
  anonymize_on_expiry?: boolean
}

export interface PurgeResult {
  transactions_anonymized: number
  attachments_deleted: number
  audit_anonymized: number
}

export const dataRetention = {
  get: async (): Promise<RetentionPolicy> => {
    const { data } = await api.get('/data-retention/')
    return data
  },
  update: async (payload: RetentionPolicyUpdate): Promise<RetentionPolicy> => {
    const { data } = await api.patch('/data-retention/', payload)
    return data
  },
  purge: async (): Promise<PurgeResult> => {
    const { data } = await api.post('/data-retention/purge')
    return data
  },
}

// Admin
export const admin = {
  listUsers: async (params?: { search?: string; page?: number; limit?: number }): Promise<AdminUserList> => {
    const { data } = await api.get('/admin/users', { params })
    return data
  },
  getUser: async (id: string): Promise<AdminUser> => {
    const { data } = await api.get(`/admin/users/${id}`)
    return data
  },
  createUser: async (user: { email: string; password: string; is_superuser?: boolean; preferences?: Record<string, unknown> }): Promise<AdminUser> => {
    const { data } = await api.post('/admin/users', user)
    return data
  },
  updateUser: async (id: string, user: Partial<{ email: string; password: string; is_active: boolean; is_superuser: boolean; preferences: Record<string, unknown> }>): Promise<AdminUser> => {
    const { data } = await api.patch(`/admin/users/${id}`, user)
    return data
  },
  deleteUser: async (id: string): Promise<void> => {
    await api.delete(`/admin/users/${id}`)
  },
  getSetting: async (key: string): Promise<AppSetting> => {
    const { data } = await api.get(`/admin/settings/${key}`)
    return data
  },
  updateSetting: async (key: string, value: string): Promise<AppSetting> => {
    const { data } = await api.patch(`/admin/settings/${key}`, { value })
    return data
  },
  mfaPolicy: async (): Promise<MfaPolicy> => {
    const { data } = await api.get('/admin/mfa-policy')
    return data
  },
  /** Lift the pause on an account locked by wrong passwords. */
  unlockUser: async (id: string): Promise<void> => {
    await api.post(`/admin/users/${id}/unlock`)
  },
  /** Remove someone's authenticator app and end their sessions (a lost phone). */
  resetTwoFactor: async (id: string): Promise<void> => {
    await api.post(`/admin/users/${id}/reset-2fa`)
  },
  registrationStatus: async (): Promise<{ enabled: boolean }> => {
    const { data } = await api.get('/admin/registration-status')
    return data
  },
  accountingMode: async (): Promise<{ mode: 'cash' | 'accrual' }> => {
    const { data } = await api.get('/admin/accounting-mode')
    return data
  },
  numberFormat: async (): Promise<{ format: NumberFormat }> => {
    const { data } = await api.get('/admin/number-format')
    return data
  },
  dateFormat: async (): Promise<{ format: DateFormat }> => {
    const { data } = await api.get('/admin/date-format')
    return data
  },
  defaultColors: async (): Promise<{ light: string | null; dark: string | null }> => {
    const { data } = await api.get('/admin/default-colors')
    return data
  },
}

// Global search (powers the command palette)
export type SearchHitType =
  | 'transaction'
  | 'account'
  | 'payee'
  | 'category'
  | 'goal'
  | 'asset'

export interface SearchHit {
  type: SearchHitType
  id: string
  label: string
  subtitle: string | null
  amount: number | null
  currency: string | null
  date: string | null
  icon: string | null
  color: string | null
  meta: Record<string, unknown>
}

export const search = {
  query: async (q: string, limit = 5): Promise<SearchHit[]> => {
    if (!q.trim()) return []
    const { data } = await api.get('/search', { params: { q, limit } })
    return data.results as SearchHit[]
  },
}

// App-level feature flags (whether optional modules like agents are mounted)
export interface AppInfo {
  /** `email`: the server has SMTP configured, so it can send reset links and invitations. */
  features: { agents: boolean; tesouro_direto?: boolean; email?: boolean }
  /** The shortest password the server accepts. */
  password_min_length?: number
}

export const info = {
  get: async (): Promise<AppInfo> => {
    const { data } = await api.get('/info')
    return data
  },
}

// Agents / MCP / RAG -- only meaningful when info.features.agents === true.
export interface Agent {
  id: string
  name: string
  description: string | null
  system_prompt: string
  icon: string
  color: string
  connection_id: string | null
  provider: string | null
  model: string | null
  temperature: number
  max_history_messages: number
  top_n: number
  similarity_threshold: number
  extra: Record<string, unknown>
  auto_context: boolean
  is_archived: boolean
  is_default: boolean
  // Populated by GET /agents (list endpoint) for the agents page.
  // Single-agent endpoints leave them at 0 since the row-level page
  // already shows tabs for both lists.
  conversation_count: number
  knowledge_count: number
  created_at: string
  updated_at: string
}

export type LlmConnectionKind = 'ollama' | 'openai' | 'anthropic' | 'openai_compatible'

export interface LlmConnection {
  id: string
  name: string
  kind: LlmConnectionKind
  base_url: string | null
  default_model: string | null
  extra: Record<string, unknown>
  is_default: boolean
  has_api_key: boolean
  created_at: string
  updated_at: string
}

export interface LlmConnectionPayload {
  name: string
  kind: LlmConnectionKind
  base_url?: string | null
  api_key?: string | null
  default_model?: string | null
  extra?: Record<string, unknown>
  is_default?: boolean
}

export interface LlmConnectionTestResult {
  ok: boolean
  detail: string
  models?: string[]
}

export interface AgentConversation {
  id: string
  agent_id: string
  channel: string
  title: string | null
  created_at: string
  updated_at: string
}

export interface AgentMessage {
  id: string
  role: 'system' | 'user' | 'assistant' | 'tool'
  ordinal: number
  content: string | null
  tool_calls: Array<{ id: string; name: string; arguments: Record<string, unknown> }> | null
  tool_result: { tool_call_id?: string; name?: string; data?: unknown; ok?: boolean } | null
  citations: unknown[] | null
  input_tokens: number | null
  output_tokens: number | null
  created_at: string
}

export interface AgentToolHandle {
  server: string
  name: string
  description: string
  is_proposal: boolean
  enabled: boolean
}

export interface KnowledgeDoc {
  id: string
  agent_id: string
  title: string
  source: string | null
  mime: string
  size_bytes: number
  status: 'pending' | 'processing' | 'ready' | 'failed'
  error: string | null
  chunk_count: number
  pinned: boolean
  created_at: string
  updated_at: string
}

export const agents = {
  info: async () => {
    const { data } = await api.get('/agents/info')
    return data as {
      enabled: boolean
      providers: string[]
      embedding_dim: number
      default_top_n: number
      default_similarity_threshold: number
      extra_mcp_servers_configured: boolean
      mcp_external_ttl_days: number
      external_mcp_url: string
    }
  },
  mcpTokens: {
    create: async (): Promise<{ token: string; expires_in_seconds: number; expires_in_days: number }> => {
      const { data } = await api.post('/agents/mcp-tokens')
      return data
    },
  },
  list: async (includeArchived = false): Promise<Agent[]> => {
    const { data } = await api.get('/agents', { params: { include_archived: includeArchived } })
    return data
  },
  // Default agent for the global slide-over chat panel. Returns the
  // user-flagged default; falls back to the most recent agent.
  // Throws 404 if the user has no agents at all.
  getDefault: async (): Promise<Agent> => {
    const { data } = await api.get('/agents/default')
    return data
  },
  get: async (id: string): Promise<Agent> => {
    const { data } = await api.get(`/agents/${id}`)
    return data
  },
  create: async (payload: Partial<Agent> & { name: string }): Promise<Agent> => {
    const { data } = await api.post('/agents', payload)
    return data
  },
  update: async (id: string, payload: Partial<Agent>): Promise<Agent> => {
    const { data } = await api.patch(`/agents/${id}`, payload)
    return data
  },
  remove: async (id: string): Promise<void> => {
    await api.delete(`/agents/${id}`)
  },
  tools: async (id: string): Promise<{ servers: { name: string }[]; tools: AgentToolHandle[] }> => {
    const { data } = await api.get(`/agents/${id}/tools`)
    return data
  },
  setTools: async (id: string, items: { server: string; tool_name: string; enabled: boolean }[]): Promise<void> => {
    await api.put(`/agents/${id}/tools`, items)
  },
  knowledge: {
    list: async (id: string): Promise<{ items: KnowledgeDoc[]; total: number }> => {
      const { data } = await api.get(`/agents/${id}/knowledge`)
      return data
    },
    upload: async (id: string, file: File, pinned = false): Promise<KnowledgeDoc> => {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('pinned', String(pinned))
      const { data } = await api.post(`/agents/${id}/knowledge`, fd)
      return data
    },
    pin: async (agentId: string, docId: string, pinned: boolean): Promise<KnowledgeDoc> => {
      const { data } = await api.patch(`/agents/${agentId}/knowledge/${docId}/pin`, null, {
        params: { pinned },
      })
      return data
    },
    remove: async (agentId: string, docId: string): Promise<void> => {
      await api.delete(`/agents/${agentId}/knowledge/${docId}`)
    },
  },
  conversations: {
    list: async (agentId?: string, limit = 50): Promise<AgentConversation[]> => {
      const { data } = await api.get('/agents/conversations', { params: { agent_id: agentId, limit } })
      return data
    },
    get: async (id: string): Promise<AgentConversation> => {
      const { data } = await api.get(`/agents/conversations/${id}`)
      return data
    },
    messages: async (id: string, limit = 200): Promise<AgentMessage[]> => {
      const { data } = await api.get(`/agents/conversations/${id}/messages`, { params: { limit } })
      return data
    },
    rename: async (id: string, title: string): Promise<AgentConversation> => {
      const { data } = await api.patch(`/agents/conversations/${id}`, { title })
      return data
    },
    generateTitle: async (id: string): Promise<AgentConversation> => {
      const { data } = await api.post(`/agents/conversations/${id}/generate-title`)
      return data
    },
    remove: async (id: string): Promise<void> => {
      await api.delete(`/agents/conversations/${id}`)
    },
  },
  // Streaming chat endpoint — caller handles the SSE response themselves
  // (see lib/agents-stream.ts). We just expose the URL + body builder.
  chatUrl: (agentId: string) => `/api/agents/${agentId}/chat`,

  connections: {
    list: async (): Promise<LlmConnection[]> => {
      const { data } = await api.get('/agents/connections')
      return data
    },
    get: async (id: string): Promise<LlmConnection> => {
      const { data } = await api.get(`/agents/connections/${id}`)
      return data
    },
    create: async (payload: LlmConnectionPayload): Promise<LlmConnection> => {
      const { data } = await api.post('/agents/connections', payload)
      return data
    },
    update: async (id: string, payload: Partial<LlmConnectionPayload>): Promise<LlmConnection> => {
      const { data } = await api.patch(`/agents/connections/${id}`, payload)
      return data
    },
    remove: async (id: string): Promise<void> => {
      await api.delete(`/agents/connections/${id}`)
    },
    test: async (id: string): Promise<LlmConnectionTestResult> => {
      const { data } = await api.post(`/agents/connections/${id}/test`)
      return data
    },
  },
}

export default api

// Invoices — business workspaces only. Every route 404s for a workspace
// without the module, so these are never called from a personal one.
export interface InvoiceWritePayload {
  direction?: InvoiceDirection
  /** Keep it a draft even where the workspace would open it on creation.
   *  Not a status field — only the difference between "still writing
   *  this" and "this is owed". Ignored on update. */
  as_draft?: boolean
  /** Provenance, for anything that did not originate here: a gateway
   *  sync, a forwarded email, a photographed supplier invoice. */
  origin?: 'local' | 'imported'
  external_source?: string
  external_id?: string
  payee_id?: string | null
  issue_date?: string
  due_date?: string
  competence_date?: string | null
  currency?: string
  total?: string
  discount?: string
  notes?: string | null
  internal_notes?: string | null
  custom_fields?: Record<string, string> | null
  lines?: InvoiceLineInput[]
  withholdings?: InvoiceWithholdingInput[]
}

export const invoices = {
  facets: async (year?: number, direction?: InvoiceDirection): Promise<InvoiceFacets> => {
    const { data } = await api.get('/invoices/facets', {
      params: { ...(year ? { year } : {}), ...(direction ? { direction } : {}) },
    })
    return data
  },
  list: async (params?: { state?: string; year?: number; direction?: InvoiceDirection; payee_id?: string; q?: string } | Record<string, unknown>): Promise<Invoice[]> => {
    const cleanParams = params && !('queryKey' in params) ? params : undefined
    const { data } = await api.get('/invoices', { params: cleanParams })
    return data
  },
  get: async (id: string): Promise<Invoice> => {
    const { data } = await api.get(`/invoices/${id}`)
    return data
  },
  summary: async (direction?: InvoiceDirection): Promise<InvoiceSummary> => {
    const { data } = await api.get('/invoices/summary', {
      params: direction ? { direction } : undefined,
    })
    return data
  },
  create: async (payload: InvoiceWritePayload): Promise<Invoice> => {
    const { data } = await api.post('/invoices', payload)
    return data
  },
  update: async (id: string, payload: InvoiceWritePayload): Promise<Invoice> => {
    const { data } = await api.patch(`/invoices/${id}`, payload)
    return data
  },
  remove: async (id: string): Promise<void> => {
    await api.delete(`/invoices/${id}`)
  },
  // The decisions. Each is its own call for the same reason it is its own
  // route on the server: a status change always has a cause.
  issue: async (id: string): Promise<Invoice> => {
    const { data } = await api.post(`/invoices/${id}/issue`)
    return data
  },
  void: async (id: string): Promise<Invoice> => {
    const { data } = await api.post(`/invoices/${id}/void`)
    return data
  },
  writeOff: async (id: string): Promise<Invoice> => {
    const { data } = await api.post(`/invoices/${id}/uncollectible`)
    return data
  },
  reopen: async (id: string): Promise<Invoice> => {
    const { data } = await api.post(`/invoices/${id}/reopen`)
    return data
  },
  allocate: async (id: string, transactionId: string, amount?: string): Promise<Invoice> => {
    const { data } = await api.post(`/invoices/${id}/allocations`, {
      transaction_id: transactionId,
      ...(amount ? { amount } : {}),
    })
    return data
  },
  unallocate: async (id: string, allocationId: string): Promise<Invoice> => {
    const { data } = await api.delete(`/invoices/${id}/allocations/${allocationId}`)
    return data
  },
  addWithholding: async (invoiceId: string, wh: InvoiceWithholdingInput): Promise<InvoiceWithholding> => {
    const { data } = await api.post(`/invoices/${invoiceId}/withholdings`, wh)
    return data
  },
  updateWithholding: async (invoiceId: string, whId: string, wh: InvoiceWithholdingInput): Promise<InvoiceWithholding> => {
    const { data } = await api.patch(`/invoices/${invoiceId}/withholdings/${whId}`, wh)
    return data
  },
  deleteWithholding: async (invoiceId: string, whId: string): Promise<void> => {
    await api.delete(`/invoices/${invoiceId}/withholdings/${whId}`)
  },
  settings: async (): Promise<InvoiceSettings> => {
    const { data } = await api.get('/invoices/settings')
    return data
  },
  updateSettings: async (payload: Partial<InvoiceSettings>): Promise<InvoiceSettings> => {
    const { data } = await api.patch('/invoices/settings', payload)
    return data
  },
  issuer: async (): Promise<IssuerProfile> => {
    const { data } = await api.get('/invoices/issuer')
    return data
  },
  updateIssuer: async (payload: {
    legal_name?: string | null
    address?: string | null
    tax_ids?: IssuerTaxId[]
  }): Promise<IssuerProfile> => {
    const { data } = await api.patch('/invoices/issuer', payload)
    return data
  },
  document: async (id: string): Promise<InvoiceDocumentPayload> => {
    const { data } = await api.get(`/invoices/${id}/document`)
    return data
  },
  /** Fetched as a blob rather than linked directly: the PDF route needs
   *  the Authorization header and the workspace header the interceptor
   *  adds, which a plain <a href> would not carry. */
  pdf: async (id: string): Promise<Blob> => {
    const { data } = await api.get(`/invoices/${id}/pdf`, { responseType: 'blob' })
    return data
  },
  share: async (id: string): Promise<InvoiceShareLink> => {
    const { data } = await api.post(`/invoices/${id}/share`)
    return data
  },
  unshare: async (id: string): Promise<void> => {
    await api.delete(`/invoices/${id}/share`)
  },
  /** The workspace's mark. Uploaded rather than linked, so a rendered
   *  document never fetches an image from somebody else's host. */
  uploadLogo: async (file: File): Promise<InvoiceSettings> => {
    const form = new FormData()
    form.append('file', file)
    const { data } = await api.post('/invoices/settings/logo', form)
    return data
  },
  removeLogo: async (): Promise<InvoiceSettings> => {
    const { data } = await api.delete('/invoices/settings/logo')
    return data
  },
  /** By id, not "the current one": a document issued under an older mark
   *  froze that id, and asking for the current logo would repaint it. */
  logoUrl: async (logoId: string): Promise<string> => {
    const { data } = await api.get(`/invoices/logo/${logoId}`, { responseType: 'blob' })
    return URL.createObjectURL(data)
  },
  /** The paper gathered under an invoice: the bill, the fiscal document,
   *  a receipt, the contract behind it. */
  attachments: {
    list: async (invoiceId: string): Promise<InvoiceAttachment[]> => {
      const { data } = await api.get(`/invoices/${invoiceId}/attachments`)
      return data
    },
    upload: async (
      invoiceId: string,
      file: File,
      fields: { kind?: string; document_number?: string; issued_at?: string; is_primary?: boolean } = {},
    ): Promise<InvoiceAttachment> => {
      const form = new FormData()
      form.append('file', file)
      Object.entries(fields).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') form.append(key, String(value))
      })
      const { data } = await api.post(`/invoices/${invoiceId}/attachments`, form)
      return data
    },
    /** Same reason as `pdf` above: the route needs headers a plain
     *  <a href> would not carry, so the bytes come back as a blob. */
    blobUrl: async (invoiceId: string, attachmentId: string): Promise<string> => {
      const { data } = await api.get(`/invoices/${invoiceId}/attachments/${attachmentId}`, {
        responseType: 'blob',
      })
      return URL.createObjectURL(data)
    },
    update: async (
      invoiceId: string,
      attachmentId: string,
      payload: Partial<Pick<InvoiceAttachment, 'kind' | 'document_number' | 'issued_at' | 'is_primary'>>,
    ): Promise<InvoiceAttachment> => {
      const { data } = await api.patch(`/invoices/${invoiceId}/attachments/${attachmentId}`, payload)
      return data
    },
    remove: async (invoiceId: string, attachmentId: string): Promise<void> => {
      await api.delete(`/invoices/${invoiceId}/attachments/${attachmentId}`)
    },
    /** Lock an attachment for fiscal document retention. Once locked it
     *  cannot be modified or deleted until the retention period ends. */
    lock: async (invoiceId: string, attachmentId: string): Promise<InvoiceAttachment> => {
      const { data } = await api.post(`/invoices/${invoiceId}/attachments/${attachmentId}/lock`)
      return data
    },
  },
}

// Cost Centers
export const costCenters = {
  list: async ({ includeInactive = false }: { includeInactive?: boolean } = {}): Promise<CostCenter[]> => {
    const { data } = await api.get('/cost-centers', {
      params: includeInactive ? { include_inactive: true } : undefined,
    })
    return data
  },
  create: async (payload: { name: string; code?: string | null; description?: string | null }): Promise<CostCenter> => {
    const { data } = await api.post('/cost-centers', payload)
    return data
  },
  update: async (id: string, payload: Partial<{ name: string; code: string | null; description: string | null; is_active: boolean }>): Promise<CostCenter> => {
    const { data } = await api.patch(`/cost-centers/${id}`, payload)
    return data
  },
  remove: async (id: string): Promise<CostCenter | null> => {
    const resp = await api.delete(`/cost-centers/${id}`, { validateStatus: (s) => s < 500 })
    if (resp.status === 204) return null
    return resp.data  // deactivated — returns updated object
  },
}

// AR/AP (Contas a Receber e a Pagar)
// Note: Decimal fields are serialised as strings by Pydantic — convert with Number() before arithmetic.
export interface UpcomingInvoice {
  id: string
  number: number | null
  series: string | null
  due_date: string
  total: string
  balance: string
  payee_name: string | null
}

export interface AgingSide {
  outstanding: string
  overdue_amount: string
  overdue_count: number
  current: string
  d1_30: string
  d31_60: string
  d61_90: string
  d90_plus: string
  collected_this_month: string
  upcoming: UpcomingInvoice[]
}

export interface ArApOverview {
  receivable: AgingSide
  payable: AgingSide
  net_position: string
}

export interface TitleRead {
  id: string
  direction: 'receivable' | 'payable'
  state: string
  number: number | null
  series: string | null
  external_number: string | null
  issue_date: string
  due_date: string
  currency: string
  total: string
  balance: string
  days_overdue: number
  payee_id: string | null
  payee_name: string | null
}

export interface TitlesPage {
  items: TitleRead[]
  total: number
  page: number
  page_size: number
}

export interface ArApForecastBucket {
  label: string
  period_start: string
  period_end: string
  receivable: string
  payable: string
  taxes: string
  net: string
}

export interface ArApForecast {
  currency: string
  period: 'week' | 'month'
  buckets: ArApForecastBucket[]
}

export interface NfeImportRow {
  filename: string
  status: 'imported' | 'duplicate' | 'error'
  invoice_id?: string
  chave?: string
  supplier_name?: string
  total?: number
  error?: string
}

export interface NfeImportResult {
  rows: NfeImportRow[]
  imported: number
  duplicates: number
  errors: number
}

export const taxObligations = {
  list: async (): Promise<RecurringTransaction[]> => {
    const { data } = await api.get('/tax-obligations')
    return data
  },
  summary: async (): Promise<{ month: string; total: string; by_type: Record<string, string> }> => {
    const { data } = await api.get('/tax-obligations/summary')
    return data
  },
}

export const arAp = {
  overview: (): Promise<ArApOverview> =>
    api.get('/ar-ap/overview').then((r) => r.data),
  titles: (
    direction: 'receivable' | 'payable',
    state?: string,
    page = 1,
    page_size = 25,
  ): Promise<TitlesPage> =>
    api
      .get('/ar-ap/titles', { params: { direction, state, page, page_size } })
      .then((r) => r.data),
  forecast: (
    currency: string,
    period: 'week' | 'month' = 'month',
    num_buckets = 12,
  ): Promise<ArApForecast> =>
    api
      .get('/ar-ap/forecast', { params: { currency, period, num_buckets } })
      .then((r) => r.data),
  importNfe: (files: File[]): Promise<NfeImportResult> => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    return api.post('/ar-ap/import/nfe', form).then((r) => r.data)
  },
}

// --- Period Closes (A5) ---

export interface PeriodClose {
  id: string
  workspace_id: string
  year: number
  month: number
  closed_by_user_id: string | null
  closed_at: string
  reason: string | null
  reopened_by_user_id: string | null
  reopened_at: string | null
  reopen_reason: string | null
}

export interface PeriodCloseCreate {
  year: number
  month: number
  reason?: string
}

export const periodClosesApi = {
  list: (wsId: string) =>
    api.get<PeriodClose[]>(`/workspaces/${wsId}/period-closes`).then(r => r.data),
  close: (wsId: string, data: PeriodCloseCreate) =>
    api.post<PeriodClose>(`/workspaces/${wsId}/period-closes`, data).then(r => r.data),
  reopen: (wsId: string, year: number, month: number, reason?: string) =>
    api.delete<PeriodClose>(`/workspaces/${wsId}/period-closes/${year}/${month}`, { data: { reason } }).then(r => r.data),
}

// --- Approvals (A6) ---

export interface ApprovalRule {
  id: string
  workspace_id: string
  category_group_id: string | null
  amount_threshold: string
  currency: string
}

export interface ThresholdResponse {
  threshold: string | null
  currency: string | null
  needs_approval: boolean
}

export const approvalsApi = {
  listPending: (wsId: string) =>
    api.get<Transaction[]>(`/workspaces/${wsId}/approvals/pending`).then(r => r.data),
  approve: (wsId: string, txId: string, note?: string) =>
    api.post<Transaction>(`/workspaces/${wsId}/approvals/${txId}/approve`, { note }).then(r => r.data),
  reject: (wsId: string, txId: string, note?: string) =>
    api.post<Transaction>(`/workspaces/${wsId}/approvals/${txId}/reject`, { note }).then(r => r.data),
  cancel: (wsId: string, txId: string) =>
    api.post<Transaction>(`/workspaces/${wsId}/approvals/${txId}/cancel`).then(r => r.data),
  settle: (wsId: string, txId: string, note?: string) =>
    api.post<Transaction>(`/workspaces/${wsId}/approvals/${txId}/settle`, { note }).then(r => r.data),
  getThreshold: (wsId: string, amount: number, categoryGroupId?: string) =>
    api.get<ThresholdResponse>(`/workspaces/${wsId}/approvals/threshold`, {
      params: { amount, ...(categoryGroupId ? { category_group_id: categoryGroupId } : {}) }
    }).then(r => r.data),
}

export const approvalRulesApi = {
  list: (wsId: string) =>
    api.get<ApprovalRule[]>(`/workspaces/${wsId}/approval-rules`).then(r => r.data),
  create: (wsId: string, data: { category_group_id?: string; amount_threshold: string; currency: string }) =>
    api.post<ApprovalRule>(`/workspaces/${wsId}/approval-rules`, data).then(r => r.data),
  delete: (wsId: string, ruleId: string) =>
    api.delete(`/workspaces/${wsId}/approval-rules/${ruleId}`),
}

// Webhooks de saída por workspace (F2)
export interface WebhookRead {
  id: string
  workspace_id: string
  url: string
  has_secret: boolean
  event_types: string[] | null
  active: boolean
  created_at: string
  last_fired_at: string | null
  last_status_code: number | null
}

export interface WebhookCreate {
  url: string
  secret?: string
  event_types?: string[] | null
}

export interface WebhookUpdate {
  url?: string
  secret?: string
  event_types?: string[] | null
  active?: boolean
}

export const webhooks = {
  list: async (): Promise<WebhookRead[]> => {
    const { data } = await api.get('/webhooks')
    return data
  },
  eventTypes: async (): Promise<string[]> => {
    const { data } = await api.get('/webhooks/event-types')
    return data
  },
  create: async (payload: WebhookCreate): Promise<WebhookRead> => {
    const { data } = await api.post('/webhooks', payload)
    return data
  },
  update: async (id: string, payload: WebhookUpdate): Promise<WebhookRead> => {
    const { data } = await api.put(`/webhooks/${id}`, payload)
    return data
  },
  remove: async (id: string): Promise<void> => {
    await api.delete(`/webhooks/${id}`)
  },
  test: async (id: string): Promise<{ scheduled: boolean }> => {
    const { data } = await api.post(`/webhooks/${id}/test`)
    return data
  },
}

// ---------------------------------------------------------------------------
// Consolidated multi-workspace DRE (A7)
// ---------------------------------------------------------------------------

export interface WorkspaceDreSummary {
  workspace_id: string
  workspace_name: string
  currency: string
  dre: DreReport
}

export interface ConsolidatedDreResponse {
  year: number
  month: number
  workspace_reports: WorkspaceDreSummary[]
  consolidated: DreReport
}

export const consolidatedApi = {
  dre: (params: {
    workspace_ids: string[]
    year: number
    month: number
    accounting_mode?: string
  }) => {
    const searchParams = new URLSearchParams()
    params.workspace_ids.forEach(id => searchParams.append('workspace_id', id))
    searchParams.set('year', String(params.year))
    searchParams.set('month', String(params.month))
    if (params.accounting_mode) searchParams.set('accounting_mode', params.accounting_mode)
    return api.get<ConsolidatedDreResponse>(`/consolidated/dre?${searchParams}`).then(r => r.data)
  },
}

// ---------------------------------------------------------------------------
// Webhooks Endpoints (F2 — endpoint-style)
// ---------------------------------------------------------------------------

export interface WebhookEndpoint {
  id: string
  workspace_id: string
  url: string
  events: string[]
  is_active: boolean
  created_at: string
}

export interface WebhookDelivery {
  id: string
  endpoint_id: string
  event_type: string
  attempt_count: number
  http_status: number | null
  last_error: string | null
  created_at: string
  delivered_at: string | null
}

export interface WebhookEndpointCreate {
  url: string
  secret?: string
  events: string[]
}

export interface WebhookEndpointUpdate {
  url?: string
  secret?: string
  events?: string[]
  is_active?: boolean
}

export const webhooksApi = {
  list: (wsId: string) =>
    api.get<WebhookEndpoint[]>(`/workspaces/${wsId}/webhooks`).then(r => r.data),
  create: (wsId: string, data: WebhookEndpointCreate) =>
    api.post<WebhookEndpoint>(`/workspaces/${wsId}/webhooks`, data).then(r => r.data),
  update: (wsId: string, epId: string, data: WebhookEndpointUpdate) =>
    api.patch<WebhookEndpoint>(`/workspaces/${wsId}/webhooks/${epId}`, data).then(r => r.data),
  delete: (wsId: string, epId: string) =>
    api.delete(`/workspaces/${wsId}/webhooks/${epId}`),
  listDeliveries: (wsId: string, epId: string) =>
    api.get<WebhookDelivery[]>(`/workspaces/${wsId}/webhooks/${epId}/deliveries`).then(r => r.data),
  redeliver: (wsId: string, epId: string, deliveryId: string) =>
    api.post<WebhookDelivery>(`/workspaces/${wsId}/webhooks/${epId}/deliveries/${deliveryId}/redeliver`).then(r => r.data),
}

// ─── ERP connectors (F3) ────────────────────────────────────────────────────

export interface ErpProvider {
  key: string
  available: boolean
}

export interface ErpConnection {
  id: string
  workspace_id: string
  provider: string
  is_active: boolean
  last_sync_at: string | null
  last_sync_status: 'running' | 'success' | 'error' | null
  last_sync_error: string | null
  sync_config: Record<string, unknown>
  created_at: string
}

export interface ErpConnectionCreate {
  provider: string
  credentials: Record<string, string>
  sync_config?: Record<string, unknown>
}

export type ErpEntityType = 'category' | 'payee' | 'transaction' | 'invoice'

export interface ErpSyncRun {
  id: string
  connection_id: string
  started_at: string
  finished_at: string | null
  status: 'running' | 'success' | 'error'
  entity_type: ErpEntityType | null
  direction: 'pull' | 'push' | null
  created_count: number
  updated_count: number
  error_count: number
  errors: string[]
}

export const erpApi = {
  providers: () => api.get<ErpProvider[]>('/erp/providers').then(r => r.data),
  list: () => api.get<ErpConnection[]>('/erp/connections').then(r => r.data),
  create: (data: ErpConnectionCreate) =>
    api.post<ErpConnection>('/erp/connections', data).then(r => r.data),
  update: (id: string, data: { is_active?: boolean; sync_config?: Record<string, unknown> }) =>
    api.patch<ErpConnection>(`/erp/connections/${id}`, data).then(r => r.data),
  remove: (id: string) => api.delete(`/erp/connections/${id}`),
  test: (id: string) =>
    api.post<{ ok: boolean; message: string | null }>(`/erp/connections/${id}/test`).then(r => r.data),
  sync: (id: string, data: { entity_type: ErpEntityType; date_from?: string; date_to?: string }) =>
    api.post(`/erp/connections/${id}/sync`, data).then(r => r.data),
  history: (id: string) =>
    api.get<ErpSyncRun[]>(`/erp/connections/${id}/history`).then(r => r.data),
}

// ─── NF-e import ────────────────────────────────────────────────────────────

export interface NfeItemPreview {
  description: string
  quantity: string
  unit_price: string
  total: string
}

export interface NfePreview {
  chave_acesso: string
  numero: string
  serie: string
  issue_date: string
  emitente_cnpj: string
  emitente_nome: string
  valor_total: string
  valor_produtos: string
  valor_impostos: string
  currency: string
  items: NfeItemPreview[]
  notes: string | null
  already_imported: boolean
}

export interface NfeSingleImportResult {
  invoice_id: string
  chave_acesso: string
  emitente_nome: string
  valor_total: string
  already_existed: boolean
}

export const nfeApi = {
  preview: (wsId: string, file: File): Promise<NfePreview> => {
    const form = new FormData()
    form.append('file', file)
    return api.post<NfePreview>(`/workspaces/${wsId}/nfe/preview`, form).then(r => r.data)
  },
  import: (wsId: string, file: File, dueDate: string, payeeId?: string): Promise<NfeSingleImportResult> => {
    const form = new FormData()
    form.append('file', file)
    form.append('due_date', dueDate)
    if (payeeId) form.append('payee_id', payeeId)
    return api.post<NfeSingleImportResult>(`/workspaces/${wsId}/nfe/import`, form).then(r => r.data)
  },
}

// ─── NF-e Emission (B1) ─────────────────────────────────────────────────────

export interface FiscalProviderConfig {
  workspace_id: string
  provider: string
  environment: string
  cnpj_emitente: string | null
  serie_padrao: string
  has_api_key: boolean
  updated_at: string
}

export interface FiscalProviderConfigSave {
  provider: string
  api_key: string
  environment: string
  cnpj_emitente?: string
  serie_padrao?: string
}

export interface FiscalEmission {
  id: string
  workspace_id: string
  invoice_id: string
  provider: string
  environment: string
  status: string
  provider_ref: string | null
  chave_acesso: string | null
  nfe_number: string | null
  nfe_serie: string | null
  xml_url: string | null
  pdf_url: string | null
  error_message: string | null
  error_code: string | null
  created_at: string
  updated_at: string
}

export const fiscalEmissionsApi = {
  getConfig: (wsId: string): Promise<FiscalProviderConfig> =>
    api.get<FiscalProviderConfig>(`/workspaces/${wsId}/fiscal/provider-config`).then(r => r.data),
  saveConfig: (wsId: string, data: FiscalProviderConfigSave): Promise<FiscalProviderConfig> =>
    api.put<FiscalProviderConfig>(`/workspaces/${wsId}/fiscal/provider-config`, data).then(r => r.data),
  listEmissions: (wsId: string, invoiceId?: string): Promise<FiscalEmission[]> => {
    const params = invoiceId ? `?invoice_id=${invoiceId}` : ''
    return api.get<FiscalEmission[]>(`/workspaces/${wsId}/fiscal/emissions${params}`).then(r => r.data)
  },
  emit: (wsId: string, invoiceId: string): Promise<FiscalEmission> =>
    api.post<FiscalEmission>(`/workspaces/${wsId}/invoices/${invoiceId}/emit-nfe`).then(r => r.data),
  refresh: (wsId: string, emissionId: string): Promise<FiscalEmission> =>
    api.post<FiscalEmission>(`/workspaces/${wsId}/fiscal/emissions/${emissionId}/refresh`).then(r => r.data),
  cancel: (wsId: string, emissionId: string, justificativa?: string): Promise<FiscalEmission> =>
    api.post<FiscalEmission>(`/workspaces/${wsId}/fiscal/emissions/${emissionId}/cancel`, {
      justificativa: justificativa ?? 'Cancelamento solicitado pelo emitente',
    }).then(r => r.data),
}

// ─── Boleto / PIX (B2) ──────────────────────────────────────────────────────

export interface BillingProviderConfig {
  provider: string
  environment: string
  webhook_token: string
  has_api_key: boolean
  updated_at: string
}

export interface BillingProviderConfigSave {
  provider: string
  api_key: string
  environment: string
}

export interface BillingCharge {
  id: string
  workspace_id: string
  invoice_id: string
  provider: string
  environment: string
  method: string
  external_id: string | null
  status: string
  amount: string
  due_date: string
  boleto_url: string | null
  boleto_line: string | null
  pix_copy_paste: string | null
  pix_qrcode: string | null
  paid_at: string | null
  paid_amount: string | null
  transaction_id: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface CreateBillingChargeRequest {
  provider?: string
  method: string
  amount: string
  due_date: string
  payer_name: string
  payer_cpf_cnpj: string
  payer_email?: string
  payer_phone?: string
  description?: string
  payer_address?: string
  payer_address_number?: string
  payer_complement?: string
  payer_neighborhood?: string
  payer_city?: string
  payer_state?: string
  payer_zip?: string
}

export const billingApi = {
  getConfig: (wsId: string, provider = 'asaas'): Promise<BillingProviderConfig> =>
    api.get<BillingProviderConfig>(`/workspaces/${wsId}/billing/provider-config`, { params: { provider } }).then(r => r.data),
  saveConfig: (wsId: string, data: BillingProviderConfigSave): Promise<BillingProviderConfig> =>
    api.put<BillingProviderConfig>(`/workspaces/${wsId}/billing/provider-config`, data).then(r => r.data),
  listCharges: (wsId: string, invoiceId?: string): Promise<BillingCharge[]> => {
    if (invoiceId) {
      return api.get<BillingCharge[]>(`/workspaces/${wsId}/invoices/${invoiceId}/billing/charges`).then(r => r.data)
    }
    return api.get<BillingCharge[]>(`/workspaces/${wsId}/billing/charges`).then(r => r.data)
  },
  createCharge: (wsId: string, invoiceId: string, data: CreateBillingChargeRequest): Promise<BillingCharge> =>
    api.post<BillingCharge>(`/workspaces/${wsId}/invoices/${invoiceId}/billing/charges`, data).then(r => r.data),
  refreshCharge: (wsId: string, chargeId: string): Promise<BillingCharge> =>
    api.post<BillingCharge>(`/workspaces/${wsId}/billing/charges/${chargeId}/refresh`).then(r => r.data),
  cancelCharge: (wsId: string, chargeId: string): Promise<BillingCharge> =>
    api.post<BillingCharge>(`/workspaces/${wsId}/billing/charges/${chargeId}/cancel`).then(r => r.data),
}

/** The shared invoice. Unauthenticated by design — the token is the whole
 *  credential — so these bypass the api instance and its interceptors. */
export const publicInvoices = {
  get: async (token: string): Promise<InvoiceDocumentPayload> => {
    // Bare axios, not the shared instance: the interceptors would attach
    // an Authorization header and a workspace id, and this route must
    // work for someone who has neither.
    const { data } = await axios.get(`/api/public/invoices/${token}`)
    return data
  },
  pdfUrl: (token: string): string => `/api/public/invoices/${token}/pdf`,
}

// --- Rateio entre centros de custo (A8) ---
// Decimais chegam como string (Pydantic): converta com Number() antes de somar.
export interface CostCenterAllocation {
  id: string
  cost_center_id: string
  cost_center_name: string | null
  amount: string
  percentage: string | null
}

export interface CostCenterAllocationInput {
  cost_center_id: string
  percentage?: number
  amount?: number
}

export const allocationsApi = {
  list: async (transactionId: string): Promise<CostCenterAllocation[]> => {
    const { data } = await api.get(`/transactions/${transactionId}/allocations`)
    return data
  },
  set: async (transactionId: string, items: CostCenterAllocationInput[]): Promise<CostCenterAllocation[]> => {
    const { data } = await api.put(`/transactions/${transactionId}/allocations`, items)
    return data
  },
  clear: async (transactionId: string): Promise<void> => {
    await api.delete(`/transactions/${transactionId}/allocations`)
  },
}

// --- Provisões e diferimentos (A8) ---
export type AccrualType = 'accrual' | 'deferral'
export type AccrualEntryStatus = 'pending' | 'posted' | 'skipped'

export interface AccrualEntry {
  id: string
  period_date: string
  amount: string
  transaction_id: string | null
  status: AccrualEntryStatus
  posted_at: string | null
}

export interface AccrualSchedule {
  id: string
  description: string
  type: AccrualType
  total_amount: string
  start_date: string
  end_date: string
  period_count: number
  amount_per_period: string
  currency: string
  category_id: string | null
  cost_center_id: string | null
  account_id: string | null
  is_active: boolean
  created_at: string
  posted_count: number
  pending_count: number
  skipped_count: number
  entries?: AccrualEntry[]
}

export interface AccrualScheduleCreate {
  type: AccrualType
  description: string
  total_amount: number
  start_date: string
  end_date: string
  account_id: string
  category_id?: string | null
  cost_center_id?: string | null
}

export const accrualsApi = {
  list: async (): Promise<AccrualSchedule[]> => {
    const { data } = await api.get('/accruals')
    return data
  },
  get: async (id: string): Promise<AccrualSchedule> => {
    const { data } = await api.get(`/accruals/${id}`)
    return data
  },
  create: async (payload: AccrualScheduleCreate): Promise<AccrualSchedule> => {
    const { data } = await api.post('/accruals', payload)
    return data
  },
  cancel: async (id: string): Promise<AccrualSchedule> => {
    const { data } = await api.delete(`/accruals/${id}`)
    return data
  },
  post: async (upToDate?: string): Promise<{ posted: number; skipped: number }> => {
    const { data } = await api.post('/accruals/post', { up_to_date: upToDate ?? null })
    return data
  },
}

// --- Payments: PIX/TED initiation with dual approval (F4) ---

export type PaymentStatus =
  | 'draft'
  | 'pending_approval'
  | 'approved'
  | 'sent'
  | 'confirmed'
  | 'failed'
  | 'cancelled'

export interface PaymentEvent {
  id: string
  user_id: string
  action: 'submit' | 'approve' | 'reject' | 'send' | 'cancel'
  note: string | null
  created_at: string | null
}

export interface PaymentOrder {
  id: string
  workspace_id: string
  idempotency_key: string
  method: 'pix' | 'ted'
  amount: string
  currency: string
  description: string | null
  beneficiary_name: string
  beneficiary_tax_id: string | null
  pix_key: string | null
  pix_key_type: string | null
  bank_code: string | null
  branch: string | null
  account_number: string | null
  account_type: string | null
  source_account_id: string | null
  status: PaymentStatus
  approval_status: 'none' | 'pending' | 'approved'
  created_by_user_id: string
  first_approver_id: string | null
  first_approved_at: string | null
  second_approver_id: string | null
  second_approved_at: string | null
  sent_by_user_id: string | null
  sent_at: string | null
  provider: string | null
  external_id: string | null
  provider_error: string | null
  receipt_url: string | null
  confirmed_at: string | null
  transaction_id: string | null
  created_at: string | null
  events?: PaymentEvent[]
}

export interface PaymentOrderCreate {
  idempotency_key?: string
  method: 'pix' | 'ted'
  amount: string
  description?: string
  beneficiary_name: string
  beneficiary_tax_id?: string
  pix_key?: string
  pix_key_type?: string
  bank_code?: string
  branch?: string
  account_number?: string
  account_type?: string
  source_account_id?: string
}

export const paymentsApi = {
  list: (status?: string, page = 1, limit = 50) =>
    api
      .get<{ items: PaymentOrder[]; total: number; page: number; limit: number }>('/payments', {
        params: { status: status || undefined, page, limit },
      })
      .then((r) => r.data),
  get: (id: string) => api.get<PaymentOrder>(`/payments/${id}`).then((r) => r.data),
  create: (body: PaymentOrderCreate) => api.post<PaymentOrder>('/payments', body).then((r) => r.data),
  cancel: (id: string) => api.delete<PaymentOrder>(`/payments/${id}`).then((r) => r.data),
  submit: (id: string) => api.post<PaymentOrder>(`/payments/${id}/submit`).then((r) => r.data),
  approve: (id: string, note?: string) =>
    api.post<PaymentOrder>(`/payments/${id}/approve`, { note }).then((r) => r.data),
  reject: (id: string, note?: string) =>
    api.post<PaymentOrder>(`/payments/${id}/reject`, { note }).then((r) => r.data),
  send: (id: string) => api.post<PaymentOrder>(`/payments/${id}/send`).then((r) => r.data),
  check: (id: string) => api.post<PaymentOrder>(`/payments/${id}/check`).then((r) => r.data),
}
