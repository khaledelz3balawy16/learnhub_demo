import { CalendarCheck, Clock, GraduationCap, Target, Users } from 'lucide-react'
import { type ReactNode, useState } from 'react'

import { Avatar } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { EmptyState, ErrorState, PageHeader } from '@/components/ui/misc'
import { Progress } from '@/components/ui/progress'
import { Ring } from '@/components/ui/ring'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, Td, Th, Tr } from '@/components/ui/table'
import { type SeatTeamRow, useSeatTeam } from '@/features/corporate/programSeats'
import { useCountUp } from '@/lib/motion'

const RAG: Record<string, { label: string; tone: 'success' | 'warning' | 'danger' }> = {
  on_track: { label: 'On track', tone: 'success' },
  behind: { label: 'Behind', tone: 'warning' },
  at_risk: { label: 'At risk', tone: 'danger' },
}
const hours = (min: number) => `${Math.round((min / 60) * 10) / 10}h`

function Otj({ r }: { r: SeatTeamRow }) {
  const rag = r.otj_rag ? RAG[r.otj_rag] : null
  return (
    <span className="grid gap-0.5">
      {rag ? (
        <Badge tone={rag.tone} dot>
          {rag.label}
        </Badge>
      ) : (
        <span className="text-xs text-muted">No target</span>
      )}
      <span className="text-xs text-muted tabular">
        {hours(r.otj_counted_min)}
        {r.otj_expected_min != null ? ` of ${hours(r.otj_expected_min)} so far` : ' logged'}
      </span>
    </span>
  )
}

function Attendance({ r }: { r: SeatTeamRow }) {
  if (!r.live) return <span className="text-xs text-muted">Recorded</span>
  if (!r.sessions_past) return <span className="text-xs text-muted">No sessions yet</span>
  const pct = Math.round((r.sessions_attended / r.sessions_past) * 100)
  return (
    <span className="grid gap-1">
      <Progress value={pct} tone={pct >= 80 ? 'success' : pct >= 60 ? 'warning' : 'danger'} label={`${pct}% attendance`} />
      <span className="text-xs text-muted tabular">
        {r.sessions_attended} of {r.sessions_past} sessions
      </span>
    </span>
  )
}

const where = (r: SeatTeamRow) => (r.live ? [r.cohort_name, r.group_name].filter(Boolean).join(' · ') || 'Live' : 'Recorded')

function Stat({ icon, label, value, suffix = '' }: { icon: ReactNode; label: string; value: number; suffix?: string }) {
  const n = useCountUp(value)
  return (
    <Card className="flex items-center gap-3 p-4">
      <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary [&_svg]:size-5">{icon}</span>
      <span className="min-w-0">
        <span className="block text-xl font-semibold tabular">
          {Math.round(n)}
          {suffix}
        </span>
        <span className="block truncate text-xs text-muted">{label}</span>
      </span>
    </Card>
  )
}

/** /business/team (M22, D22): the line manager's view of the people they look after on a
 * program seat: progress, KSBs, off-the-job hours and attendance. Owners and admins see
 * everyone; a manager sees their own units. */
export function TeamPage() {
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined])
  const q = useSeatTeam(cursors[cursors.length - 1])
  const rows = q.data?.items ?? []
  const avg = rows.length ? rows.reduce((s, r) => s + r.progress_pct, 0) / rows.length : 0
  const onTrack = rows.filter((r) => r.otj_rag === 'on_track').length

  return (
    <>
      <PageHeader title="My team" description="How the people you look after are getting on with their programs." />
      {q.error ? (
        <ErrorState message={(q.error as Error).message} onRetry={() => void q.refetch()} />
      ) : !q.data ? (
        <div className="grid gap-3">
          <Skeleton className="h-20" />
          <Skeleton className="h-64" />
        </div>
      ) : !rows.length && cursors.length === 1 ? (
        <EmptyState icon={<Users />} title="Nobody on a program yet" body="When people in your team get a program seat, their progress shows here." />
      ) : (
        <div className="grid gap-4 animate-reveal">
          <div className="stagger grid gap-3 sm:grid-cols-3">
            <Stat icon={<Users />} label="People shown" value={rows.length} />
            <Card className="flex items-center gap-3 p-4">
              <Ring value={Math.round(avg)} size={56} stroke={7} label={`${Math.round(avg)}%`} />
              <span className="min-w-0">
                <span className="flex items-center gap-1 text-sm font-medium">
                  <GraduationCap className="size-4 text-primary" aria-hidden /> Average progress
                </span>
                <span className="block text-xs text-muted">Across the people shown</span>
              </span>
            </Card>
            <Stat icon={<Clock />} label="On track with off-the-job hours" value={onTrack} />
          </div>
          <Card className="hidden overflow-hidden md:block">
            <Table>
              <thead>
                <tr>
                  <Th>Person</Th>
                  <Th>Progress</Th>
                  <Th>KSBs met</Th>
                  <Th>Off-the-job</Th>
                  <Th>Attendance</Th>
                </tr>
              </thead>
              <tbody className="stagger">
                {rows.map((r) => (
                  <Tr key={r.enrollment_id}>
                    <Td>
                      <span className="flex min-w-0 items-center gap-2.5">
                        <Avatar name={r.name} size="sm" />
                        <span className="min-w-0">
                          <span className="block truncate font-medium">{r.name}</span>
                          <span className="block truncate text-xs text-muted">
                            {r.program_title} · {where(r)}
                          </span>
                        </span>
                      </span>
                    </Td>
                    <Td className="w-40">
                      <Progress value={r.progress_pct} label={`${Math.round(r.progress_pct)}% done`} />
                    </Td>
                    <Td className="tabular">{r.ksb_total ? `${r.ksb_met} of ${r.ksb_total}` : <span className="text-xs text-muted">None mapped</span>}</Td>
                    <Td>
                      <Otj r={r} />
                    </Td>
                    <Td className="w-44">
                      <Attendance r={r} />
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          </Card>
          <ul className="stagger grid gap-3 md:hidden" aria-label="Team">
            {rows.map((r) => (
              <li key={r.enrollment_id}>
                <Card className="grid gap-3 p-4">
                  <span className="flex min-w-0 items-center gap-2.5">
                    <Avatar name={r.name} size="sm" />
                    <span className="min-w-0">
                      <span className="block truncate font-medium">{r.name}</span>
                      <span className="block text-xs text-muted break-words">
                        {r.program_title} · {where(r)}
                      </span>
                    </span>
                  </span>
                  <Progress value={r.progress_pct} label={`${Math.round(r.progress_pct)}% done`} />
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <span className="grid gap-0.5">
                      <span className="flex items-center gap-1 text-xs text-muted">
                        <Target className="size-3.5" /> KSBs met
                      </span>
                      <span className="tabular">{r.ksb_total ? `${r.ksb_met} of ${r.ksb_total}` : 'None mapped'}</span>
                    </span>
                    <span className="grid gap-0.5">
                      <span className="flex items-center gap-1 text-xs text-muted">
                        <Clock className="size-3.5" /> Off-the-job
                      </span>
                      <Otj r={r} />
                    </span>
                    <span className="col-span-2 grid gap-0.5">
                      <span className="flex items-center gap-1 text-xs text-muted">
                        <CalendarCheck className="size-3.5" /> Attendance
                      </span>
                      <Attendance r={r} />
                    </span>
                  </div>
                </Card>
              </li>
            ))}
          </ul>
          <div className="flex justify-between gap-2">
            <Button variant="secondary" disabled={cursors.length === 1} onClick={() => setCursors((c) => c.slice(0, -1))}>
              Previous
            </Button>
            <Button variant="secondary" disabled={!q.data.next_cursor || q.isFetching} onClick={() => setCursors((c) => [...c, q.data!.next_cursor!])}>
              Next
            </Button>
          </div>
        </div>
      )}
    </>
  )
}
