/**
 * Sent by the request layer when the server answers 403 MFA_ENROLLMENT_REQUIRED: the instance's
 * second-factor rule came into force while a page was open. Kept apart from `lib/api.ts` so the
 * listener does not have to import the whole request layer.
 */
export const MFA_REQUIRED_EVENT = 'syncrofin:mfa-required'
