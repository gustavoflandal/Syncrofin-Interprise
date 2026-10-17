/** Any translator: the `t` of `useTranslation` or the plain one the tests use. */
type Translate = (key: string, options?: Record<string, unknown>) => string

/** The audit actions that are accesses to the application (the same set the server reads). */
export const ACCESS_ACTIONS = [
  'login',
  'login_failed',
  'login_blocked',
  'account_locked',
  'account_unlocked',
  'session_revoked',
  'token_access',
] as const

/** What happened, in the person's language. An action this version does not know is shown as it came. */
export function accessAction(t: Translate, action: string): string {
  return t(`accessLog.actions.${action}`, { defaultValue: action })
}

/**
 * Why, when the event says: "wrong password", "ended from another device", "token sfn_ab12cd34".
 * Null when there is nothing worth adding (a lock's detail is only numbers).
 */
export function accessReason(t: Translate, action: string, detail: string | null): string | null {
  if (!detail) return null
  if (action === 'token_access') return t('accessLog.reasons.token', { prefix: detail.replace(/^api_token:/, '') })
  if (action === 'account_locked') return null
  return t(`accessLog.reasons.${detail}`, { defaultValue: detail })
}
