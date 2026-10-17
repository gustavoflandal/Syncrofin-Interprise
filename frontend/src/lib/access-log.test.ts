import { describe, expect, it } from 'vitest'

import { ACCESS_ACTIONS, accessAction, accessReason } from '@/lib/access-log'
import { t } from '@/test/utils'

describe('access log labels', () => {
  it('names every action in the set', () => {
    for (const action of ACCESS_ACTIONS) {
      expect(accessAction(t, action)).toBe(t(`accessLog.actions.${action}`))
      expect(accessAction(t, action)).not.toContain('accessLog.')
    }
  })

  it('explains why a sign-in failed', () => {
    expect(accessReason(t, 'login_failed', 'bad_password')).toBe(t('accessLog.reasons.bad_password'))
  })

  it('shows which token was used', () => {
    expect(accessReason(t, 'token_access', 'api_token:sfn_ab12cd34')).toContain('sfn_ab12cd34')
  })

  it('shows an unknown reason as it came, and nothing when there is none', () => {
    expect(accessReason(t, 'session_revoked', 'something_new')).toBe('something_new')
    expect(accessReason(t, 'login', null)).toBeNull()
  })

  it('does not show the numbers of a lock as if they were a reason', () => {
    expect(accessReason(t, 'account_locked', '5 attempts, 15 min')).toBeNull()
  })
})
