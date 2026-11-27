import { ArrowLeft, CalendarClock, Clock, Plus, Trash2 } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardHeader } from '@/components/ui/card'
import { Field, Input, Textarea } from '@/components/ui/input'
import { EmptyState, ErrorState, PageHeader } from '@/components/ui/misc'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useEnrollmentId, useLogOtj, useMyOtj, useMyRecord, useWithdrawOtj } from '@/features/learning/api'
import { CpdList, hours, KsbGrid, ModuleCertificates, OtjPanel } from '@/features/programs/record'
import { Link } from '@/lib/router'
import { dayWithWeekday } from '@/lib/schedule'

const TABS = ['hours', 'ksbs', 'cpd', 'certificates'] as const
type Tab = (typeof TABS)[number]

/** The open tab lives in ?tab= so a link (e.g. from a notification) can open it. */
function useTab(): [Tab, (t: Tab) => void] {
  const [params, setParams] = useSearchParams()
  const raw = params.get('tab') as Tab | null
  return [raw && TABS.includes(raw) ? raw : 'hours', (t) => setParams((p) => (p.set('tab', t), p), { replace: true })]
}
const STATUS: Record<string, { label: string; tone: 'success' | 'warning' | 'danger' | 'neutral' }> = {
  auto_approved: { label: 'Counted', tone: 'success' },
  approved: { label: 'Approved', tone: 'success' },
  pending: { label: 'Waiting', tone: 'warning' },
  rejected: { label: 'Not approved', tone: 'danger' },
}
const SOURCE: Record<string, string> = {
  component: 'Component',
  live_session: 'Live session',
  workshop: 'Workshop',
  manual: 'You logged',
}

const today = () => new Date().toLocaleDateString('en-CA') // YYYY-MM-DD in the learner's time zone

function LogHours({ enrollmentId, cap }: { enrollmentId: string; cap: number }) {
  const log = useLogOtj(enrollmentId)
  const [day, setDay] = useState(today)
  const [h, setH] = useState('')
  const [m, setM] = useState('')
  const [note, setNote] = useState('')
  const minutes = (Number(h) || 0) * 60 + (Number(m) || 0)
  const submit = (e: FormEvent) => {
    e.preventDefault()
    log.mutate(
      { occurred_on: day, minutes, note: note.trim() },
      {
        onSuccess: () => (toast.success('Hours sent to your tutor'), setH(''), setM(''), setNote('')),
        onError: (err) => toast.error((err as Error).message),
      },
    )
  }
  return (
    <Card>
      <CardHeader title="Log off-the-job hours" description={`Time spent learning away from your normal work. Up to ${hours(cap)} a day. Your tutor approves each log.`} />
      <form className="grid gap-4 px-5 pb-5" onSubmit={submit}>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Day">{(p) => <Input {...p} type="date" value={day} max={today()} onChange={(e) => setDay(e.target.value)} required />}</Field>
          <Field label="Hours">{(p) => <Input {...p} type="number" inputMode="numeric" min={0} max={24} value={h} onChange={(e) => setH(e.target.value)} />}</Field>
          <Field label="Minutes">{(p) => <Input {...p} type="number" inputMode="numeric" min={0} max={59} value={m} onChange={(e) => setM(e.target.value)} />}</Field>
        </div>
        <Field label="What did you do?" hint="For example: research for the project report, a webinar, shadowing a colleague.">
          {(p) => <Textarea {...p} rows={3} value={note} onChange={(e) => setNote(e.target.value)} minLength={3} maxLength={1000} required />}
        </Field>
        <div className="flex justify-end">
          <Button type="submit" loading={log.isPending} disabled={minutes < 1 || minutes > cap}>
            <Plus /> Log {minutes ? hours(minutes) : 'hours'}
          </Button>
        </div>
      </form>
    </Card>
  )
}

function Ledger({ enrollmentId }: { enrollmentId: string }) {
  const q = useMyOtj(enrollmentId)
  const withdraw = useWithdrawOtj(enrollmentId)
  const rows = q.data?.pages.flatMap((p) => p.items)
  if (q.error) return <ErrorState message={(q.error as Error).message} onRetry={() => void q.refetch()} />
  if (!rows) return <Skeleton className="h-40" />
  if (!rows.length) return <EmptyState icon={<Clock />} title="No hours yet" body="Hours appear as you finish components, join sessions or log your own." />
  return (
    <Card className="overflow-hidden">
      <ul className="stagger divide-y divide-border">
        {rows.map((r) => {
          const s = STATUS[r.status] ?? STATUS.pending!
          return (
            <li key={r.id} className="flex flex-wrap items-start gap-3 px-4 py-3 text-sm">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{r.note || SOURCE[r.source]}</p>
                <p className="text-xs text-muted">
                  {dayWithWeekday(r.occurred_on)} · {SOURCE[r.source] ?? r.source}
                </p>
                {r.decision_note ? <p className="mt-1 text-xs text-muted">Tutor: {r.decision_note}</p> : null}
              </div>
              <span className="shrink-0 font-semibold tabular">{hours(r.minutes)}</span>
              <Badge tone={s.tone}>{s.label}</Badge>
              {r.status === 'pending' && r.source === 'manual' ? (
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`Withdraw the log for ${dayWithWeekday(r.occurred_on)}`}
                  loading={withdraw.isPending && withdraw.variables === r.id}
                  onClick={() =>
                    withdraw.mutate(r.id, {
                      onSuccess: () => toast.success('Log withdrawn'),
                      onError: (e) => toast.error((e as Error).message),
                    })
                  }
                >
                  <Trash2 />
                </Button>
              ) : null}
            </li>
          )
        })}
      </ul>
      {q.hasNextPage ? (
        <div className="flex justify-center border-t border-border p-3">
          <Button variant="ghost" size="sm" loading={q.isFetchingNextPage} onClick={() => void q.fetchNextPage()}>
            Show older hours
          </Button>
        </div>
      ) : null}
    </Card>
  )
}

export function ProgramRecordPage() {
  const { slug = '' } = useParams()
  const lookup = useEnrollmentId(slug)
  const rec = useMyRecord(lookup.enrollmentId)
  const [tab, setTab] = useTab()
  const error = lookup.error ?? rec.error
  const back = (
    <Link to={`/learn/${slug}`} className="inline-flex items-center gap-1 text-sm text-muted hover:text-text">
      <ArrowLeft className="size-4" aria-hidden /> Back to the program
    </Link>
  )
  if (lookup.notEnrolled) return <EmptyState icon={<Clock />} title="You're not on this program" action={<Button asChild><Link to="/learn">My learning</Link></Button>} />
  if (error) return <ErrorState message={(error as Error).message} onRetry={() => void (lookup.refetch(), rec.refetch())} />
  if (!rec.data)
    return (
      <div className="grid gap-4" aria-busy="true">
        <Skeleton className="h-16" />
        <Skeleton className="h-40" />
        <Skeleton className="h-64" />
      </div>
    )
  const r = rec.data
  return (
    <div className="grid gap-6 animate-reveal">
      <PageHeader
        back={back}
        title="My record"
        description={r.program_title}
        actions={
          <Button asChild variant="secondary">
            <Link to={`/learn/${slug}/sessions`}>
              <CalendarClock /> Live sessions
            </Link>
          </Button>
        }
      />
      <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)}>
        <TabsList>
          <TabsTrigger value="hours">Hours</TabsTrigger>
          <TabsTrigger value="ksbs">KSBs</TabsTrigger>
          <TabsTrigger value="cpd">CPD</TabsTrigger>
          <TabsTrigger value="certificates">Certificates</TabsTrigger>
        </TabsList>
        <TabsContent value="hours" className="grid gap-5">
          <OtjPanel otj={r.otj} />
          <LogHours enrollmentId={r.enrollment_id} cap={r.otj.daily_cap_min} />
          <section aria-labelledby="ledger" className="grid gap-3">
            <h2 id="ledger" className="text-base font-semibold">
              All hours
            </h2>
            <Ledger enrollmentId={r.enrollment_id} />
          </section>
        </TabsContent>
        <TabsContent value="ksbs">
          <KsbGrid ksbs={r.ksbs} />
        </TabsContent>
        <TabsContent value="cpd">
          <CpdList cpd={r.cpd} />
        </TabsContent>
        <TabsContent value="certificates">
          <ModuleCertificates certificates={r.certificates} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
