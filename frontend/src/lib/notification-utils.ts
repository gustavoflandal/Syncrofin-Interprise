/** "9+" past nine, so the badge never outgrows the bell. */
export function badgeLabel(count: number): string {
  return count > 9 ? '9+' : String(count)
}
