import { describe, expect, it } from 'vitest'

import { passwordErrorText, passwordReason, plainDetail } from '@/lib/password-policy'
import { t } from '@/test/utils'

const failure = (detail: unknown) => ({ response: { data: { detail } } })

describe('password policy errors', () => {
  it('reads the reason from the shape the server uses for a refused password', () => {
    expect(passwordReason(failure({ code: 'INVALID_PASSWORD', reason: 'PASSWORD_TOO_SHORT' }))).toBe('PASSWORD_TOO_SHORT')
    expect(passwordReason(failure({ code: 'UPDATE_USER_INVALID_PASSWORD', reason: 'PASSWORD_HAS_EMAIL' }))).toBe('PASSWORD_HAS_EMAIL')
  })

  it('ignores anything that is not a known reason', () => {
    expect(passwordReason(failure('A user with this email already exists'))).toBeNull()
    expect(passwordReason(failure({ reason: 'SOMETHING_ELSE' }))).toBeNull()
    expect(passwordReason(new Error('offline'))).toBeNull()
    expect(passwordReason(undefined)).toBeNull()
  })

  it('says it in the interface language, with the minimum', () => {
    const text = passwordErrorText(t as never, failure({ reason: 'PASSWORD_TOO_SHORT' }), 12, 'fallback')
    expect(text).toBe(t('passwordPolicy.reasons.PASSWORD_TOO_SHORT', { min: 12 }))
    expect(text).toContain('12')
  })

  it('falls back to the given message for other failures', () => {
    expect(passwordErrorText(t as never, failure('boom'), 10, 'fallback')).toBe('fallback')
  })

  it('shows only a string detail, never an object, in a toast', () => {
    expect(plainDetail(failure('plain'))).toBe('plain')
    expect(plainDetail(failure({ code: 'X', reason: 'Y' }))).toBeUndefined()
  })
})
