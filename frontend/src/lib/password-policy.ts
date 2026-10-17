import type { TFunction } from 'i18next'

/** What the server asks when it has not said (see `password_min_length` in /api/info). */
export const DEFAULT_MIN_PASSWORD_LENGTH = 10

const REASONS = new Set([
  'PASSWORD_TOO_SHORT',
  'PASSWORD_TOO_LONG',
  'PASSWORD_TOO_COMMON',
  'PASSWORD_HAS_EMAIL',
  'PASSWORD_TOO_SIMPLE',
])

/**
 * The reason code the server gave for refusing a password, from a failed request, or null when the
 * failure was about something else. Two shapes carry it: `{ detail: { code, reason } }` (sign-up,
 * reset, change, admin, setup, invitation).
 */
export function passwordReason(error: unknown): string | null {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (detail && typeof detail === 'object') {
    const reason = (detail as { reason?: unknown }).reason
    if (typeof reason === 'string' && REASONS.has(reason)) return reason
  }
  return null
}

/** The sentence, in the person's language, for a reason code. */
export function passwordReasonText(t: TFunction, reason: string, min: number): string {
  return t(`passwordPolicy.reasons.${reason}`, { min })
}

/** A message for any error that may be a refused password: the reason if it is one, otherwise `fallback`. */
export function passwordErrorText(t: TFunction, error: unknown, min: number, fallback: string): string {
  const reason = passwordReason(error)
  return reason ? passwordReasonText(t, reason, min) : fallback
}

/** An error `detail` from the admin API as something safe to show: a string, or nothing. */
export function plainDetail(error: unknown): string | undefined {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' ? detail : undefined
}
