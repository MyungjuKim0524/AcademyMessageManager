/** Local calendar date as `YYYY-MM-DD` (not UTC — a lesson day is the academy's local day). */
export function todayLocal(): string {
  const now = new Date()
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset())
  return now.toISOString().slice(0, 10)
}

/** `YYYY-MM-DD` moved by `days` (negative = earlier). */
export function shiftDay(day: string, days: number): string {
  const date = new Date(`${day}T00:00:00`)
  date.setDate(date.getDate() + days)
  date.setMinutes(date.getMinutes() - date.getTimezoneOffset())
  return date.toISOString().slice(0, 10)
}
