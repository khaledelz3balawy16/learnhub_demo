// Program schedule formatting (M18), shared by the console and the learner player.

export const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

/** API dates are plain ISO days (2027-01-04); never shift them through time zones. */
const asDay = (iso: string) => {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d))
}
const dayFmt = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  timeZone: 'UTC',
})
const dayYearFmt = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  timeZone: 'UTC',
})
const weekdayFmt = new Intl.DateTimeFormat('en-GB', {
  weekday: 'short',
  day: 'numeric',
  month: 'short',
  timeZone: 'UTC',
})

export const day = (iso: string) => dayYearFmt.format(asDay(iso))
export const dayShort = (iso: string) => dayFmt.format(asDay(iso))
export const dayWithWeekday = (iso: string) => weekdayFmt.format(asDay(iso))
/** "4 – 8 Jan 2027" style range (same year shown once). */
export function dayRange(from?: string | null, to?: string | null) {
  if (!from) return 'Not scheduled'
  if (!to || to === from) return day(from)
  return from.slice(0, 4) === to.slice(0, 4) ? `${dayShort(from)} – ${day(to)}` : `${day(from)} – ${day(to)}`
}

/** "Wednesdays, 10:00–12:00" from a group's timetable. */
export function timetable(g: { weekday?: number | null; starts_at?: string | null; ends_at?: string | null }) {
  const when = g.weekday != null ? `${WEEKDAYS[g.weekday]}s` : null
  const time = g.starts_at ? `${g.starts_at.slice(0, 5)}${g.ends_at ? `–${g.ends_at.slice(0, 5)}` : ''}` : null
  return [when, time].filter(Boolean).join(', ') || 'No timetable yet'
}

// ---------------------------------------------------------------- live sessions (M20): real instants, shown in local time
const whenFmt = new Intl.DateTimeFormat('en-GB', {
  weekday: 'short',
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
})
const timeFmt = new Intl.DateTimeFormat('en-GB', {
  hour: '2-digit',
  minute: '2-digit',
})

/** "Wed 6 Jan, 18:00–19:30" in the viewer's time zone. */
export function sessionWhen(startsAt: string, endsAt?: string | null) {
  const start = whenFmt.format(new Date(startsAt))
  return endsAt ? `${start}–${timeFmt.format(new Date(endsAt))}` : start
}

/** An ISO instant as a datetime-local input value (viewer's time zone), and back. */
export function toLocalInput(iso: string) {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
export const fromLocalInput = (value: string) => new Date(value).toISOString()
