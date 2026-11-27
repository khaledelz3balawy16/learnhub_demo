import { CalendarClock, School, Users } from 'lucide-react'
import { useState } from 'react'

import { Card } from '@/components/ui/card'
import { EmptyState, ErrorState, PageHeader } from '@/components/ui/misc'
import { Skeleton } from '@/components/ui/skeleton'
import { DetailSheet } from '@/features/console/ui'
import { useMyTeaching } from '@/features/programs/api'
import { sessionWhen, timetable } from '@/lib/schedule'

import { GroupSessions } from './LiveSessions'

type Group = NonNullable<ReturnType<typeof useMyTeaching>['data']>[number]

/** A tutor's groups (M20): open one to run its live sessions, attendance and recordings. */
export function ConsoleTeachingPage() {
  const q = useMyTeaching()
  const [open, setOpen] = useState<Group | null>(null)
  return (
    <div className="grid gap-6">
      <PageHeader title="My teaching" description="The groups you tutor. Open one to add meeting links, mark attendance and upload recordings." />
      {q.error ? (
        <ErrorState message={(q.error as Error).message} onRetry={() => void q.refetch()} />
      ) : !q.data ? (
        <div className="grid gap-3 sm:grid-cols-2" aria-busy="true">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : !q.data.length ? (
        <EmptyState icon={<School />} title="No groups yet" body="When a cohort manager makes you a group's tutor, it appears here." />
      ) : (
        <ul className="stagger grid gap-3 sm:grid-cols-2 animate-reveal">
          {q.data.map((g) => (
            <li key={g.id} className="min-w-0">
              <Card className="h-full">
                <button type="button" className="grid h-full w-full gap-1.5 rounded-lg p-4 text-left transition-colors duration-150 hover:bg-surface-2" onClick={() => setOpen(g)}>
                  <span className="text-xs font-medium text-muted">
                    {g.program_title} · {g.cohort_name}
                  </span>
                  <span className="font-semibold break-words">{g.name}</span>
                  <span className="text-sm text-muted">{timetable(g)}</span>
                  <span className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
                    <span className="inline-flex items-center gap-1">
                      <Users className="size-3.5" aria-hidden /> {g.learner_count} learners
                    </span>
                    <span className="inline-flex items-center gap-1 tabular">
                      <CalendarClock className="size-3.5" aria-hidden /> {g.next_session_at ? `Next: ${sessionWhen(g.next_session_at)}` : 'No session planned'}
                    </span>
                  </span>
                </button>
              </Card>
            </li>
          ))}
        </ul>
      )}
      <DetailSheet open={!!open} onOpenChange={(o) => !o && setOpen(null)} title={open?.name ?? 'Group'} description={open ? `${open.program_title} · ${timetable(open)}` : undefined}>
        {open ? <GroupSessions groupId={open.id} /> : null}
      </DetailSheet>
    </div>
  )
}
