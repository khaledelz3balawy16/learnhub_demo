import { CalendarOff, Plug } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { shortDate } from '@/lib/format'

import type { HrLeave, HrMemberLink } from './api'

/** "On leave until 12 Dec" while it lasts; "Leave from 3 Jan" when it is still ahead
 * (only where `upcoming` is wanted, e.g. the Person page). */
export function LeaveBadge({ leave, upcoming = false }: { leave?: HrLeave | null; upcoming?: boolean }) {
  if (!leave) return null
  const now = leave.current
  if (!now && !upcoming) return null
  return (
    <Badge tone={now ? 'warning' : 'outline'} title={leave.leave_type || undefined}>
      <CalendarOff className="size-3" /> {now ? `On leave until ${shortDate(leave.ends_on)}` : `Leave from ${shortDate(leave.starts_on)}`}
    </Badge>
  )
}

/** "Synced from Breathe HR" on the Person page header, with the HR id. */
export function HrLinkBadges({ link }: { link?: HrMemberLink }) {
  if (!link?.linked) return null
  return (
    <>
      <Badge tone="info" title={link.external_employee_id ? `${link.provider} ID ${link.external_employee_id}` : undefined}>
        <Plug className="size-3" /> Synced from {link.provider}
      </Badge>
      {link.is_leaver ? <Badge tone="danger">Leaver in {link.provider}</Badge> : null}
      <LeaveBadge leave={link.leave} upcoming />
    </>
  )
}
