import 'vitest'
import type { AxeMatchers } from 'vitest-axe/matchers'

// vitest-axe's own augmentation targets the old `Vi` namespace; vitest 4 needs the module form.
declare module 'vitest' {
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type
  interface Assertion extends AxeMatchers {}
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type
  interface AsymmetricMatchersContaining extends AxeMatchers {}
}
