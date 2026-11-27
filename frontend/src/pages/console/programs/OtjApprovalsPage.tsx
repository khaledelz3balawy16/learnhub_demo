import { Check, ClipboardList, ShieldCheck, X } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Field, Textarea } from '@/components/ui/input'
import { EmptyState, ErrorState, PageHeader } from '@/components/ui/misc'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DetailSheet } from '@/features/console/ui'
import { type OtjPending, useDecideOtj, useLearnerRecord, useOtjPending } from '@/features/programs/api'
import { CpdList, hours, KsbGrid, ModuleCertificates, OtjPanel } from '@/features/programs/record'
import { shortDate } from '@/lib/format'
import { dayWithWeekday } from '@/lib/schedule'

const err = (e: unknown) => toast.error((e as Error).message)

/** A learner's program record for their tutor or a cohort manager (hours, KSBs, CPD). */
export function LearnerRecordSheet({ enrollmentId, onOpenChange }: { enrollmentId: string | null; onOpenChange: (o: boolean) => void }) {
  const q = useLearnerRecord(enrollmentId)
  const r = q.data
  return (
    <DetailSheet open={!!enrollmentId} onOpenChange={onOpenChange} title={r ? r.learner_name || r.learner_email : 'Learner record'} description={r?.program_title}>
      {q.error instanceof ApiError && q.error.status === 404 ? (
        <EmptyState icon={<ShieldCheck />} title="You can't see this record" body="Only the learner's tutor and cohort managers can open it." />
      ) : q.error ? (
        <ErrorState message={(q.error as Error).message} onRetry={() => void q.refetch()} />
      ) : !r ? (
        <div className="grid gap-3">
          <Skeleton className="h-32" />
          <Skeleton className="h-48" />
        </div>
      ) : (
        <Tabs defaultValue="hours">
          <TabsList>
            <TabsTrigger value="hours">Hours</TabsTrigger>
            <TabsTrigger value="ksbs">KSBs</TabsTrigger>
            <TabsTrigger value="cpd">CPD</TabsTrigger>
          </TabsList>
          <TabsContent value="hours" className="grid gap-4">
            <OtjPanel otj={r.otj} />
            <ModuleCertificates certificates={r.certificates} />
          </TabsContent>
          <TabsContent value="ksbs">
            <KsbGrid ksbs={r.ksbs} />
          </TabsContent>
          <TabsContent value="cpd">
            <CpdList cpd={r.cpd} />
          </TabsContent>
        </Tabs>
      )}
    </DetailSheet>
  )
}

function RejectDialog({ entry, onOpenChange }: { entry: OtjPending | null; onOpenChange: (o: boolean) => void }) {
  const decide = useDecideOtj()
  const [note, setNote] = useState('')
  const [forId, setForId] = useState<string | null>(null)
  if ((entry?.id ?? null) !== forId) {
    // a new entry starts with an empty reason (state adjusted during render, no effect needed)
    setForId(entry?.id ?? null)
    setNote('')
  }
  return (
    <Dialog open={!!entry} onOpenChange={onOpenChange}>
      <DialogContent title="Don't approve these hours?" description="The learner sees your reason and can log the time again.">
        <form
          className="grid gap-4"
          onSubmit={(e) => {
            e.preventDefault()
            if (entry)
              decide.mutate(
                { id: entry.id, approve: false, note: note.trim() },
                {
                  onSuccess: () => (toast.success('Learner told'), setNote(''), onOpenChange(false)),
                  onError: err,
                },
              )
          }}
        >
          <Field label="Reason">{(p) => <Textarea {...p} rows={3} value={note} onChange={(e) => setNote(e.target.value)} minLength={3} maxLength={500} required autoFocus />}</Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="danger" loading={decide.isPending}>
              Don't approve
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function ConsoleOtjApprovalsPage() {
  const q = useOtjPending()
  const decide = useDecideOtj()
  const [rejecting, setRejecting] = useState<OtjPending | null>(null)
  const [record, setRecord] = useState<string | null>(null)
  const rows = q.data?.pages.flatMap((p) => p.items)
  if (q.error instanceof ApiError && q.error.status === 403)
    return <EmptyState icon={<ShieldCheck />} title="You can't approve hours" body="Tutors approve hours for their own groups. Cohort managers approve for everyone." />
  return (
    <div className="grid gap-6">
      <PageHeader title="Hours to approve" description="Off-the-job hours learners logged themselves. Oldest first." />
      {q.error ? (
        <ErrorState message={(q.error as Error).message} onRetry={() => void q.refetch()} />
      ) : !rows ? (
        <div className="grid gap-3" aria-busy="true">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : !rows.length ? (
        <EmptyState icon={<ClipboardList />} title="Nothing to approve" body="New logs from your learners appear here." />
      ) : (
        <ul className="stagger grid gap-3 animate-reveal">
          {rows.map((e) => (
            <li key={e.id}>
              <Card className="flex flex-wrap items-start gap-4 p-4">
                <div className="min-w-0 flex-1">
                  <button type="button" className="text-left font-semibold hover:text-primary hover:underline" onClick={() => setRecord(e.enrollment_id)}>
                    {e.learner_name || e.learner_email}
                  </button>
                  <p className="text-xs text-muted">
                    {e.program_title}
                    {e.group_name ? ` · ${e.group_name}` : ''} · logged {shortDate(e.created_at)}
                  </p>
                  <p className="mt-2 text-sm">
                    <span className="font-semibold tabular">{hours(e.minutes)}</span> on {dayWithWeekday(e.occurred_on)}
                  </p>
                  <p className="mt-1 text-sm text-muted">{e.note}</p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button variant="secondary" size="sm" onClick={() => setRejecting(e)}>
                    <X /> Don't approve
                  </Button>
                  <Button
                    size="sm"
                    loading={decide.isPending && decide.variables?.id === e.id}
                    onClick={() =>
                      decide.mutate(
                        { id: e.id, approve: true, note: '' },
                        {
                          onSuccess: () => toast.success('Hours approved'),
                          onError: err,
                        },
                      )
                    }
                  >
                    <Check /> Approve
                  </Button>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
      {q.hasNextPage ? (
        <div className="flex justify-center">
          <Button variant="ghost" loading={q.isFetchingNextPage} onClick={() => void q.fetchNextPage()}>
            Show more
          </Button>
        </div>
      ) : null}
      <RejectDialog entry={rejecting} onOpenChange={(o) => !o && setRejecting(null)} />
      <LearnerRecordSheet enrollmentId={record} onOpenChange={(o) => !o && setRecord(null)} />
    </div>
  )
}
