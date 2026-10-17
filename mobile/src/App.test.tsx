import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BiometricAuth, BiometryType } from '@aparajita/capacitor-biometric-auth'

import App from '@/App'
import { setLang } from '@/lib/i18n'
import * as queue from '@/lib/queue'

// The camera is hardware: the tests hand back a "photo" instead.
const takeReceiptPhoto = vi.hoisted(() => vi.fn())
vi.mock('@/lib/camera', () => ({ takeReceiptPhoto }))

// The OCR is native (ML Kit on the phone): the tests decide what it "read", and whether it exists.
const ocr = vi.hoisted(() => ({ available: false, readReceipt: vi.fn() }))
vi.mock('@/lib/ocr', () => ({ ocrAvailable: () => ocr.available, readReceipt: ocr.readReceipt }))

const SERVER = 'https://fin.exemplo.com'

interface FakeState {
  loginBody?: unknown
  created: unknown[]
  uploads: { transactionId: string; name: string }[]
  transactionRequests: URL[]
  failUpload: boolean
  createStatus: number
  loginResponse: () => Response
  verifyResponse: () => Response
  transactions: unknown[]
  attachments: Record<string, unknown[]>
  unauthorized: boolean
  /** The server requires a second factor this session does not have. */
  mfaBlocked?: boolean
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const ACCOUNTS = [
  { id: 'acc-1', name: 'Conta Corrente', type: 'checking', currency: 'BRL' },
  { id: 'acc-2', name: 'Carteira', type: 'cash', currency: 'BRL' },
]
const CATEGORIES = [
  { id: 'cat-1', name: 'Alimentação' },
  { id: 'cat-2', name: 'Transporte' },
]

const tx = (over: Record<string, unknown> = {}) => ({
  id: 't1',
  description: 'Mercado',
  amount: '123.40',
  date: '2026-09-10',
  type: 'debit',
  currency: 'BRL',
  status: 'posted',
  attachment_count: 0,
  category: { id: 'cat-1', name: 'Alimentação' },
  ...over,
})

let state: FakeState

function fakeServer(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = new URL(String(input))
  const method = init?.method ?? 'GET'
  const path = url.pathname

  if (state.unauthorized && path !== '/api/auth/login') return Promise.resolve(json(401, { detail: 'Unauthorized' }))

  if (path === '/api/auth/login') {
    state.loginBody = init?.body
    return Promise.resolve(state.loginResponse())
  }
  if (path === '/api/auth/2fa/verify') return Promise.resolve(state.verifyResponse())
  if (path === '/api/auth/mfa-status') return Promise.resolve(json(200, { blocked: !!state.mfaBlocked }))
  if (path === '/api/workspaces') {
    return Promise.resolve(json(200, [{ id: 'ws-1', name: 'Pessoal', kind: 'personal', is_archived: false }, { id: 'ws-2', name: 'Empresa', kind: 'business', is_archived: false }]))
  }
  if (path === '/api/workspaces/current') return Promise.resolve(json(200, { id: 'ws-1', name: 'Pessoal', kind: 'personal' }))
  if (path === '/api/accounts') return Promise.resolve(json(200, ACCOUNTS))
  if (path === '/api/categories') return Promise.resolve(json(200, CATEGORIES))
  if (path === '/api/transactions' && method === 'GET') {
    state.transactionRequests.push(url)
    const page = Number(url.searchParams.get('page') ?? 1)
    const all = state.transactions as unknown[]
    const items = all.slice((page - 1) * 30, page * 30)
    return Promise.resolve(json(200, { items, total: all.length, page, limit: 30 }))
  }
  if (path === '/api/transactions' && method === 'POST') {
    if (state.createStatus !== 201) return Promise.resolve(json(state.createStatus, { detail: 'nope' }))
    const body = JSON.parse(String(init?.body))
    state.created.push(body)
    return Promise.resolve(json(201, tx({ id: 'new-1', description: body.description })))
  }
  const attachments = /^\/api\/transactions\/([^/]+)\/attachments$/.exec(path)
  if (attachments && method === 'POST') {
    if (state.failUpload) return Promise.resolve(json(500, { detail: 'disk full' }))
    const file = (init?.body as FormData).get('file') as File
    state.uploads.push({ transactionId: attachments[1], name: file.name })
    return Promise.resolve(json(201, { id: 'att-new', transaction_id: attachments[1], filename: file.name, content_type: 'image/jpeg', size: 1 }))
  }
  if (attachments && method === 'GET') return Promise.resolve(json(200, state.attachments[attachments[1]] ?? []))
  if (/\/attachments\/[^/]+$/.test(path)) return Promise.resolve(new Response(new Uint8Array([255, 216, 255]), { status: 200, headers: { 'Content-Type': 'image/jpeg' } }))
  return Promise.resolve(json(404, { detail: `unhandled ${method} ${path}` }))
}

function signedInStorage() {
  localStorage.setItem('syncrofin_server', SERVER)
  localStorage.setItem('syncrofin_token', 'tok')
}

beforeEach(async () => {
  setLang('pt-BR')
  takeReceiptPhoto.mockReset()
  ocr.available = false
  ocr.readReceipt.mockReset()
  // The offline queue is a module-level store (mirroring the on-device file): left-over items
  // from one test must not leak into the next.
  for (const workspaceId of [null, 'ws-1', 'ws-2']) {
    for (const item of await queue.list(SERVER, workspaceId)) await queue.remove(item.clientId)
  }
  state = {
    created: [],
    uploads: [],
    transactionRequests: [],
    failUpload: false,
    createStatus: 201,
    loginResponse: () => json(200, { access_token: 'tok', refresh_token: 'ref', token_type: 'bearer' }),
    verifyResponse: () => json(200, { access_token: 'tok2', refresh_token: 'ref2', token_type: 'bearer' }),
    transactions: [tx()],
    attachments: {},
    unauthorized: false,
  }
  vi.stubGlobal('fetch', vi.fn(fakeServer))
  // No biometry unless a test opts in: the web plugin holds this as state on its singleton.
  void BiometricAuth.setBiometryType(undefined)
  void BiometricAuth.setBiometryIsEnrolled(false)
})

afterEach(() => vi.unstubAllGlobals())

async function fillLogin(user: ReturnType<typeof userEvent.setup>, server = 'fin.exemplo.com') {
  await user.type(screen.getByLabelText(/Endereço do servidor/), server)
  await user.type(screen.getByLabelText('E-mail'), 'ana@exemplo.com')
  await user.type(screen.getByLabelText('Senha'), 'segredo')
  await user.click(screen.getByRole('button', { name: 'Entrar' }))
}

describe('login', () => {
  it('starts on the login screen with no session', async () => {
    render(<App />)
    expect(await screen.findByRole('button', { name: 'Entrar' })).toBeInTheDocument()
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
  })

  it('shows the typed password on request, and hides it again', async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByRole('button', { name: 'Entrar' })
    await user.type(screen.getByLabelText('Senha'), 'segredo')

    const passwordInput = screen.getByLabelText('Senha')
    expect(passwordInput).toHaveAttribute('type', 'password')

    await user.click(screen.getByRole('button', { name: 'Mostrar senha' }))
    expect(passwordInput).toHaveAttribute('type', 'text')
    expect(passwordInput).toHaveValue('segredo')

    await user.click(screen.getByRole('button', { name: 'Ocultar senha' }))
    expect(passwordInput).toHaveAttribute('type', 'password')
  })

  it('signs in, adds https to the address, and remembers the session', async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByRole('button', { name: 'Entrar' })
    await fillLogin(user)

    expect(await screen.findByRole('button', { name: 'Lançamentos' })).toBeInTheDocument()
    expect(localStorage.getItem('syncrofin_server')).toBe(SERVER)
    expect(localStorage.getItem('syncrofin_token')).toBe('tok')
    expect(String(state.loginBody)).toContain('username=ana%40exemplo.com')
  })

  it('says what to do when the server requires a second factor this account has not set up, and keeps nothing', async () => {
    state.mfaBlocked = true
    const user = userEvent.setup()
    render(<App />)
    await screen.findByRole('button', { name: 'Entrar' })
    await fillLogin(user)

    expect(await screen.findByRole('alert')).toHaveTextContent(/verificação em duas etapas/)
    expect(screen.queryByRole('button', { name: 'Lançamentos' })).not.toBeInTheDocument()
    expect(localStorage.getItem('syncrofin_token')).toBeNull()
    expect(localStorage.getItem('syncrofin_refresh')).toBeNull()
  })

  it('says so when the password is wrong, and stays on the login screen', async () => {
    state.loginResponse = () => json(400, { detail: 'LOGIN_BAD_CREDENTIALS' })
    const user = userEvent.setup()
    render(<App />)
    await screen.findByRole('button', { name: 'Entrar' })
    await fillLogin(user)

    expect(await screen.findByRole('alert')).toHaveTextContent('E-mail ou senha incorretos.')
    expect(localStorage.getItem('syncrofin_token')).toBeNull()
  })

  it('refuses a plain-http address without calling the server', async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByRole('button', { name: 'Entrar' })
    await fillLogin(user, 'http://syncrofin.exemplo.com')

    expect(await screen.findByRole('alert')).toHaveTextContent('HTTPS')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('tells the difference between an unreachable server and a wrong password', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const user = userEvent.setup()
    render(<App />)
    await screen.findByRole('button', { name: 'Entrar' })
    await fillLogin(user)
    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível falar com o servidor')
  })

  it('asks for the 2FA code and finishes the sign-in with it', async () => {
    state.loginResponse = () => json(200, { requires_2fa: true, temp_token: 'tmp', available_methods: ['totp'] })
    const user = userEvent.setup()
    render(<App />)
    await screen.findByRole('button', { name: 'Entrar' })
    await fillLogin(user)

    await user.type(await screen.findByLabelText('Código'), '12a3456')
    expect(screen.getByLabelText('Código')).toHaveValue('123456') // digits only, six at most
    await user.click(screen.getByRole('button', { name: 'Verificar' }))

    expect(await screen.findByRole('button', { name: 'Lançamentos' })).toBeInTheDocument()
    expect(localStorage.getItem('syncrofin_token')).toBe('tok2')
  })

  it('goes back to the password when the 2FA step expired', async () => {
    state.loginResponse = () => json(200, { requires_2fa: true, temp_token: 'tmp', available_methods: ['totp'] })
    state.verifyResponse = () => json(401, { detail: 'Invalid or expired token' })
    const user = userEvent.setup()
    render(<App />)
    await screen.findByRole('button', { name: 'Entrar' })
    await fillLogin(user)
    await user.type(await screen.findByLabelText('Código'), '123456')
    await user.click(screen.getByRole('button', { name: 'Verificar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('sessão terminou')
    expect(screen.getByLabelText('Senha')).toBeInTheDocument()
  })

  it('goes back to the login screen when the server ends the session', async () => {
    signedInStorage()
    state.unauthorized = true
    render(<App />)
    // The stored session is tried on start; the 401 sends the person back with a reason.
    expect(await screen.findByRole('button', { name: 'Entrar' }, { timeout: 3000 })).toBeInTheDocument()
    expect(localStorage.getItem('syncrofin_token')).toBeNull()
  })
})

describe('signed in', () => {
  it('restores the session without asking for the password again', async () => {
    signedInStorage()
    render(<App />)
    expect(await screen.findByRole('button', { name: 'Lançamentos' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Entrar' })).not.toBeInTheDocument()
  })

  it('opens straight to the app when offline, instead of waiting on the workspace list', async () => {
    // The bug this guards against: /api/workspaces hanging (as it does on-device when offline,
    // since CapacitorHttp's fetch patch ignores the app's timeout — see api.ts) used to leave the
    // app on the "Carregando…" splash forever, because the session restore awaited it before
    // showing anything else. A person who is already signed in must not need a network call to
    // open the app.
    signedInStorage()
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input)).pathname
      if (path === '/api/workspaces' || path === '/api/workspaces/current') return new Promise(() => {}) // never settles
      return fakeServer(input, init)
    }))

    const { container } = render(<App />)

    expect(await screen.findByRole('button', { name: 'Lançamentos' })).toBeInTheDocument()
    // Distinct from NewTransactionScreen's own (unrelated, expected) "Carregando…" while it loads
    // accounts/categories: this checks specifically for the app-level splash from `Gate`.
    expect(container.querySelector('.splash')).not.toBeInTheDocument()
  })

  it('signs out and forgets the token', async () => {
    signedInStorage()
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: 'Sair' }))
    expect(await screen.findByRole('button', { name: 'Entrar' })).toBeInTheDocument()
    expect(localStorage.getItem('syncrofin_token')).toBeNull()
  })

  it('offers a workspace choice when there is more than one and remembers it', async () => {
    signedInStorage()
    const user = userEvent.setup()
    render(<App />)
    const select = await screen.findByLabelText('Workspace')
    // The server's default workspace is the one selected, not an empty "Workspace" placeholder.
    await waitFor(() => expect(select).toHaveValue('ws-1'))
    await user.selectOptions(select, 'ws-2')
    expect(localStorage.getItem('syncrofin_workspace')).toBe('ws-2')
  })
})

describe('biometric unlock', () => {
  async function enableBiometry() {
    await BiometricAuth.setBiometryType(BiometryType.fingerprintAuthentication)
    await BiometricAuth.setBiometryIsEnrolled(true)
  }

  it('does not ask for biometrics on a device with none enrolled', async () => {
    signedInStorage()
    render(<App />)
    expect(await screen.findByRole('button', { name: 'Lançamentos' })).toBeInTheDocument()
  })

  it('locks a restored session behind biometrics, and unlocks it on success', async () => {
    await enableBiometry()
    signedInStorage()
    // The web build of the plugin simulates biometry with a confirm() dialog: false = declined.
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)

    render(<App />)

    // The screen prompts automatically on mount; the first (automatic) attempt is declined.
    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível confirmar. Tente de novo.')
    expect(screen.queryByRole('button', { name: 'Lançamentos' })).not.toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Tentar de novo' }))

    expect(await screen.findByRole('button', { name: 'Lançamentos' })).toBeInTheDocument()
    expect(confirmSpy).toHaveBeenCalledTimes(2)
  })

  it('falls back to a fresh sign-in when the person chooses to use a password instead', async () => {
    await enableBiometry()
    signedInStorage()
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const user = userEvent.setup()

    render(<App />)
    await screen.findByRole('alert')

    await user.click(screen.getByRole('button', { name: 'Entrar com senha' }))

    expect(await screen.findByRole('button', { name: 'Entrar' })).toBeInTheDocument()
    expect(localStorage.getItem('syncrofin_token')).toBeNull()
  })
})

describe('new transaction', () => {
  async function openForm() {
    signedInStorage()
    const user = userEvent.setup()
    render(<App />)
    await screen.findByLabelText('Descrição')
    return user
  }

  it('checks the fields before calling the server', async () => {
    const user = await openForm()
    await user.click(screen.getByRole('button', { name: 'Salvar lançamento' }))

    expect(await screen.findByText('Informe um valor maior que zero.')).toBeInTheDocument()
    expect(screen.getByText('Informe uma descrição.')).toBeInTheDocument()
    expect(state.created).toHaveLength(0)
  })

  it('saves an expense with the amount exactly as a decimal string', async () => {
    const user = await openForm()
    await user.type(screen.getByLabelText('Valor'), '45,90')
    await user.type(screen.getByLabelText('Descrição'), 'Almoço')
    await user.selectOptions(screen.getByLabelText('Categoria'), 'cat-1')
    await user.click(screen.getByRole('button', { name: 'Salvar lançamento' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Lançamento salvo.')
    expect(state.created).toEqual([
      expect.objectContaining({ description: 'Almoço', amount: '45.90', type: 'debit', account_id: 'acc-1', category_id: 'cat-1', currency: 'BRL' }),
    ])
    // The form is ready for the next one.
    expect(screen.getByLabelText('Valor')).toHaveValue('')
  })

  it('saves income when that is chosen', async () => {
    const user = await openForm()
    await user.click(screen.getByRole('button', { name: 'Receita' }))
    await user.type(screen.getByLabelText('Valor'), '1.500,00')
    await user.type(screen.getByLabelText('Descrição'), 'Freela')
    await user.click(screen.getByRole('button', { name: 'Salvar lançamento' }))
    await screen.findByRole('status')
    expect(state.created).toEqual([expect.objectContaining({ type: 'credit', amount: '1500.00' })])
  })

  it('photographs the receipt and attaches it to the new transaction', async () => {
    takeReceiptPhoto.mockResolvedValue(new Blob(['jpeg'], { type: 'image/jpeg' }))
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: () => 'blob:preview', revokeObjectURL: () => undefined }))
    const user = await openForm()
    await user.type(screen.getByLabelText('Valor'), '10')
    await user.type(screen.getByLabelText('Descrição'), 'Táxi')
    await user.click(screen.getByRole('button', { name: 'Fotografar' }))
    expect(await screen.findByAltText('Comprovante')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Fotografar de novo' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Salvar lançamento' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Lançamento salvo.')
    expect(state.uploads).toEqual([{ transactionId: 'new-1', name: expect.stringMatching(/^comprovante-\d{8}-\d{6}\.jpg$/) }])
  })

  it('does not lose the transaction when only the photo fails, and says what to do', async () => {
    takeReceiptPhoto.mockResolvedValue(new Blob(['jpeg'], { type: 'image/jpeg' }))
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: () => 'blob:preview', revokeObjectURL: () => undefined }))
    state.failUpload = true
    const user = await openForm()
    await user.type(screen.getByLabelText('Valor'), '10')
    await user.type(screen.getByLabelText('Descrição'), 'Táxi')
    await user.click(screen.getByRole('button', { name: 'Fotografar' }))
    await screen.findByAltText('Comprovante')
    await user.click(screen.getByRole('button', { name: 'Salvar lançamento' }))

    expect(await screen.findByRole('status')).toHaveTextContent('a foto não foi enviada')
    expect(state.created).toHaveLength(1)
  })

  it('does nothing when the camera is cancelled', async () => {
    takeReceiptPhoto.mockResolvedValue(null)
    const user = await openForm()
    await user.click(screen.getByRole('button', { name: 'Fotografar' }))
    expect(screen.queryByAltText('Comprovante')).not.toBeInTheDocument()
  })

  it('explains a read-only role instead of a raw error', async () => {
    state.createStatus = 403
    const user = await openForm()
    await user.type(screen.getByLabelText('Valor'), '10')
    await user.type(screen.getByLabelText('Descrição'), 'Café')
    await user.click(screen.getByRole('button', { name: 'Salvar lançamento' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('somente leitura')
  })
})

describe('offline queue', () => {
  async function openForm() {
    signedInStorage()
    const user = userEvent.setup()
    render(<App />)
    await screen.findByLabelText('Descrição')
    return user
  }

  function stubOfflineCreate() {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const path = new URL(String(input)).pathname
        if (path === '/api/transactions' && (init?.method ?? 'GET') === 'POST') return Promise.reject(new TypeError('Failed to fetch'))
        return fakeServer(input, init)
      }),
    )
  }

  async function saveOneOffline(user: ReturnType<typeof userEvent.setup>) {
    stubOfflineCreate()
    await user.type(screen.getByLabelText('Valor'), '10')
    await user.type(screen.getByLabelText('Descrição'), 'Táxi')
    await user.click(screen.getByRole('button', { name: 'Salvar lançamento' }))
    await screen.findByRole('status')
  }

  it('saves on the phone instead of failing when the server cannot be reached', async () => {
    const user = await openForm()
    await saveOneOffline(user)

    expect(screen.getByRole('status')).toHaveTextContent('Salvo no aparelho')
    expect(state.created).toHaveLength(0)
    // The form is ready for the next one, same as a normal save.
    expect(screen.getByLabelText('Valor')).toHaveValue('')
  })

  it('shows the queued item in the transactions list, marked pending', async () => {
    const user = await openForm()
    await saveOneOffline(user)

    await user.click(screen.getByRole('button', { name: 'Lançamentos' }))
    expect(await screen.findByText('Táxi')).toBeInTheDocument()
    expect(screen.getByText('Aguardando sincronização (1)')).toBeInTheDocument()
    expect(screen.getByText('Pendente')).toBeInTheDocument()
  })

  it('syncs a pending item on demand, replaying the same client id', async () => {
    const user = await openForm()
    await saveOneOffline(user)
    await user.click(screen.getByRole('button', { name: 'Lançamentos' }))
    await screen.findByText('Táxi')

    // The connection is back.
    vi.stubGlobal('fetch', vi.fn(fakeServer))
    await user.click(screen.getByRole('button', { name: 'Sincronizar agora' }))

    expect(await screen.findByText('Sincronizado')).toBeInTheDocument()
    expect(state.created).toEqual([expect.objectContaining({ description: 'Táxi', client_id: expect.any(String) })])
  })

  it('warns before signing out with items still waiting to sync, and stays signed in until confirmed', async () => {
    const user = await openForm()
    await saveOneOffline(user)

    await user.click(screen.getByRole('button', { name: 'Sair' }))
    expect(await screen.findByText(/aguardando sincronização/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Entrar' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Sair mesmo assim' }))
    expect(await screen.findByRole('button', { name: 'Entrar' })).toBeInTheDocument()
  })

  it('signs out right away when nothing is pending', async () => {
    const user = await openForm()
    await user.click(screen.getByRole('button', { name: 'Sair' }))
    expect(await screen.findByRole('button', { name: 'Entrar' })).toBeInTheDocument()
  })
})

describe('transactions list', () => {
  async function openList() {
    signedInStorage()
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: 'Lançamentos' }))
    return user
  }

  it('lists the month with signed, formatted amounts', async () => {
    state.transactions = [tx(), tx({ id: 't2', description: 'Salário', type: 'credit', amount: '5000.00', attachment_count: 1, category: null })]
    await openList()

    expect(await screen.findByText('Mercado')).toBeInTheDocument()
    const row = screen.getByText('Salário').closest('button')!
    expect(within(row).getByText(/\+.*5\.000,00/)).toBeInTheDocument()
    expect(within(row).getByText(/📎/)).toBeInTheDocument()
    expect(within(screen.getByText('Mercado').closest('button')!).getByText(/−.*123,40/)).toBeInTheDocument()

    const first = state.transactionRequests[0]
    const now = new Date()
    expect(first.searchParams.get('from')).toMatch(new RegExp(`^${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01$`))
  })

  it('moves to the previous month and asks for that month', async () => {
    const user = await openList()
    await screen.findByText('Mercado')
    const before = state.transactionRequests.length
    await user.click(screen.getByRole('button', { name: 'Mês anterior' }))

    await waitFor(() => expect(state.transactionRequests.length).toBeGreaterThan(before))
    const now = new Date()
    const prev = new Date(now.getFullYear(), now.getMonth() - 1, 1)
    expect(state.transactionRequests.at(-1)!.searchParams.get('from')).toBe(
      `${prev.getFullYear()}-${String(prev.getMonth() + 1).padStart(2, '0')}-01`,
    )
  })

  it('says so when the month is empty', async () => {
    state.transactions = []
    await openList()
    expect(await screen.findByText('Nenhum lançamento neste mês.')).toBeInTheDocument()
  })

  it('loads more pages without repeating rows', async () => {
    state.transactions = Array.from({ length: 35 }, (_, i) => tx({ id: `t${i}`, description: `Item ${i}` }))
    const user = await openList()
    await screen.findByText('Item 0')
    expect(screen.queryByText('Item 30')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Carregar mais/ }))
    expect(await screen.findByText('Item 34')).toBeInTheDocument()
    expect(screen.getAllByText(/^Item \d+$/)).toHaveLength(35)
  })

  it('offers a retry when the list cannot be loaded', async () => {
    let calls = 0
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const path = new URL(String(input)).pathname
        if (path === '/api/transactions') {
          calls += 1
          if (calls === 1) return Promise.reject(new TypeError('offline'))
        }
        return fakeServer(input, init)
      }),
    )
    const user = await openList()
    expect(await screen.findByRole('status')).toHaveTextContent('Sem conexão')
    await user.click(screen.getByRole('button', { name: 'Tentar de novo' }))
    expect(await screen.findByText('Mercado')).toBeInTheDocument()
  })
})

describe('transaction detail and receipts', () => {
  async function openDetail() {
    state.transactions = [tx({ attachment_count: 1, notes: 'Compra do mês' })]
    state.attachments = { t1: [{ id: 'att-1', transaction_id: 't1', filename: 'nota.jpg', content_type: 'image/jpeg', size: 10 }] }
    signedInStorage()
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: 'Lançamentos' }))
    await user.click(await screen.findByText('Mercado'))
    return { user, dialog: await screen.findByRole('dialog') }
  }

  it('shows the transaction and its receipt thumbnail', async () => {
    const { dialog } = await openDetail()
    expect(within(dialog).getByText('Compra do mês')).toBeInTheDocument()
    expect(within(dialog).getByText('Alimentação')).toBeInTheDocument()
    expect(await within(dialog).findByAltText('nota.jpg')).toBeInTheDocument()
  })

  it('adds a receipt to an existing transaction', async () => {
    takeReceiptPhoto.mockResolvedValue(new Blob(['jpeg'], { type: 'image/jpeg' }))
    const { user, dialog } = await openDetail()
    await user.click(within(dialog).getByRole('button', { name: 'Adicionar comprovante' }))

    expect(await within(dialog).findByText('Comprovante enviado.')).toBeInTheDocument()
    expect(state.uploads).toEqual([{ transactionId: 't1', name: expect.stringMatching(/^comprovante-/) }])
  })

  it('closes back to the list', async () => {
    const { user, dialog } = await openDetail()
    await user.click(within(dialog).getByRole('button', { name: 'Fechar' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})

describe('receipt reading (OCR)', () => {
  const PHOTO = () => new Blob(['jpeg'], { type: 'image/jpeg' })

  async function openFormWithPhoto() {
    takeReceiptPhoto.mockResolvedValue(PHOTO())
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: () => 'blob:preview', revokeObjectURL: () => undefined }))
    ocr.available = true
    signedInStorage()
    const user = userEvent.setup()
    render(<App />)
    await screen.findByLabelText('Descrição')
    return user
  }

  it('offers nothing where the app has no recognizer (a browser)', async () => {
    ocr.available = false
    takeReceiptPhoto.mockResolvedValue(PHOTO())
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: () => 'blob:preview', revokeObjectURL: () => undefined }))
    signedInStorage()
    const user = userEvent.setup()
    render(<App />)
    await screen.findByLabelText('Descrição')
    await user.click(screen.getByRole('button', { name: 'Fotografar' }))
    await screen.findByAltText('Comprovante')
    expect(ocr.readReceipt).not.toHaveBeenCalled()
    expect(screen.queryByText('Lendo o comprovante…')).not.toBeInTheDocument()
  })

  it('reads the photo it was given (the original) and shows what it found, without filling anything in', async () => {
    ocr.readReceipt.mockResolvedValue({ amount: '100.00', date: '2026-06-06', merchant: 'Posto Trevao' })
    const user = await openFormWithPhoto()
    await user.click(screen.getByRole('button', { name: 'Fotografar' }))

    const card = await screen.findByRole('region', { name: 'Lido do comprovante' })
    expect(ocr.readReceipt).toHaveBeenCalledTimes(1)
    expect(within(card).getByText(/100,00/)).toBeInTheDocument()
    expect(within(card).getByText('Posto Trevao')).toBeInTheDocument()
    expect(within(card).getByText(/2026/)).toBeInTheDocument()
    // Suggestions are only suggestions: the form is untouched until the person taps.
    expect(screen.getByLabelText('Valor')).toHaveValue('')
    expect(screen.getByLabelText('Descrição')).toHaveValue('')
  })

  it('fills the form when the person accepts everything, and saves what they confirmed', async () => {
    ocr.readReceipt.mockResolvedValue({ amount: '100.00', date: '2026-06-06', merchant: 'Posto Trevao' })
    const user = await openFormWithPhoto()
    await user.click(screen.getByRole('button', { name: 'Fotografar' }))
    await user.click(await screen.findByRole('button', { name: 'Usar tudo' }))

    expect(screen.getByLabelText('Valor')).toHaveValue('100,00')
    expect(screen.getByLabelText('Descrição')).toHaveValue('Posto Trevao')
    expect(screen.getByLabelText('Data')).toHaveValue('2026-06-06')

    await user.click(screen.getByRole('button', { name: 'Salvar lançamento' }))
    await screen.findByRole('status')
    expect(state.created).toEqual([expect.objectContaining({ amount: '100.00', description: 'Posto Trevao', date: '2026-06-06', type: 'debit' })])
  })

  it('applies one field at a time and leaves the others as typed', async () => {
    ocr.readReceipt.mockResolvedValue({ amount: '100.00', date: '2026-06-06', merchant: 'Posto Trevao' })
    const user = await openFormWithPhoto()
    await user.type(screen.getByLabelText('Descrição'), 'Gasolina')
    await user.click(screen.getByRole('button', { name: 'Fotografar' }))
    const card = await screen.findByRole('region', { name: 'Lido do comprovante' })

    const amountRow = within(card).getByText(/100,00/).closest('li')!
    await user.click(within(amountRow).getByRole('button', { name: 'Usar' }))

    expect(screen.getByLabelText('Valor')).toHaveValue('100,00')
    expect(screen.getByLabelText('Descrição')).toHaveValue('Gasolina')
  })

  it('says so, and asks for the fields by hand, when nothing could be read', async () => {
    ocr.readReceipt.mockResolvedValue({})
    const user = await openFormWithPhoto()
    await user.click(screen.getByRole('button', { name: 'Fotografar' }))
    expect(await screen.findByText(/Não consegui ler valor nem data/)).toBeInTheDocument()
  })

  it('treats a recognizer failure like nothing read, and the photo still goes with the transaction', async () => {
    ocr.readReceipt.mockResolvedValue(null)
    const user = await openFormWithPhoto()
    await user.click(screen.getByRole('button', { name: 'Fotografar' }))
    expect(await screen.findByText(/Não consegui ler valor nem data/)).toBeInTheDocument()
    await user.type(screen.getByLabelText('Valor'), '10')
    await user.type(screen.getByLabelText('Descrição'), 'Café')
    await user.click(screen.getByRole('button', { name: 'Salvar lançamento' }))
    await screen.findByRole('status')
    expect(state.uploads).toHaveLength(1)
  })

  it('dismisses the suggestions', async () => {
    ocr.readReceipt.mockResolvedValue({ amount: '5.00' })
    const user = await openFormWithPhoto()
    await user.click(screen.getByRole('button', { name: 'Fotografar' }))
    await user.click(await screen.findByRole('button', { name: 'Ignorar' }))
    expect(screen.queryByRole('region', { name: 'Lido do comprovante' })).not.toBeInTheDocument()
  })

  it('drops a late reading that belongs to a photo that was already removed', async () => {
    let finish: (value: unknown) => void = () => undefined
    ocr.readReceipt.mockReturnValue(new Promise((resolve) => (finish = resolve)))
    const user = await openFormWithPhoto()
    await user.click(screen.getByRole('button', { name: 'Fotografar' }))
    expect(await screen.findByText('Lendo o comprovante…')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Remover foto' }))
    finish({ amount: '99.00' })
    await waitFor(() => expect(screen.queryByText('Lendo o comprovante…')).not.toBeInTheDocument())
    expect(screen.queryByRole('region', { name: 'Lido do comprovante' })).not.toBeInTheDocument()
  })
})
