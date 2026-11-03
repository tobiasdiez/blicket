/**
 * The time `iso` (ISO 8601) in UTC, as "2026-10-24 20:02 UTC", to the second with `seconds`;
 * `iso` itself when it is no time.
 */
export function utcTime(iso: string, seconds = false): string {
  const time = new Date(iso)
  if (Number.isNaN(time.getTime())) return iso
  return `${time.toISOString().slice(0, seconds ? 19 : 16).replace('T', ' ')} UTC`
}
