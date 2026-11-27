import { ArrowLeft, CalendarPlus, CalendarRange, Layers, PencilRuler } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { useParams } from 'react-router-dom'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Field, Input, NativeSelect } from '@/components/ui/input'
import { EmptyState, ErrorState, PageHeader } from '@/components/ui/misc'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, Td, Th, Tr } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { StatusPill, useTabParam } from '@/features/console/ui'
import { CALENDARS, COHORT_STATUS, type ProgramDetail, useCreateCohort, useProgram } from '@/features/programs/api'
import { Link, useNavigate } from '@/lib/router'

import { ProgramKsbs, ProgramSettingsTab } from './ProgramKsbs'
import { ProgramOffers } from './ProgramOffers'
import { dayRange } from '@/lib/schedule'

const TABS = ['cohorts', 'structure', 'offers', 'ksbs', 'settings'] as const

function NewCohort({ programId, open, onOpenChange }: { programId: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  const create = useCreateCohort(programId)
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [start, setStart] = useState('')
  const [calendar, setCalendar] = useState('') // '' = the provider's default (console settings)
  const [capacity, setCapacity] = useState('')
  const submit = (e: FormEvent) => {
    e.preventDefault()
    create.mutate(
      { name: name.trim(), start_date: start, calendar: calendar || null, capacity: capacity ? Number(capacity) : null },
      {
        onSuccess: (r) => {
          toast.success('Cohort created. Its weeks are dated.')
          onOpenChange(false)
          navigate(`/console/cohorts/${r.id}`)
        },
        onError: (e) => toast.error((e as Error).message),
      },
    )
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="New cohort" description="Week 1 starts on the start date. Weekends, bank holidays and closures are skipped.">
        <form className="grid gap-4" onSubmit={submit}>
          <Field label="Name" hint="For example the intake, like “January 2027”.">
            {(p) => <Input {...p} value={name} onChange={(e) => setName(e.target.value)} maxLength={120} required autoFocus />}
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Start date">{(p) => <Input {...p} type="date" value={start} onChange={(e) => setStart(e.target.value)} required />}</Field>
            <Field label="Places (optional)">{(p) => <Input {...p} type="number" min={1} inputMode="numeric" value={capacity} onChange={(e) => setCapacity(e.target.value)} />}</Field>
          </div>
          <Field label="Bank holidays">
            {(p) => (
              <NativeSelect {...p} value={calendar} onChange={(e) => setCalendar(e.target.value)}>
                <option value="">Provider default (Settings)</option>
                {Object.entries(CALENDARS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending}>
              Create cohort
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function Cohorts({ program }: { program: ProgramDetail }) {
  if (!program.cohorts.length)
    return (
      <EmptyState
        icon={<CalendarRange />}
        title="No cohorts yet"
        body={program.published ? 'Open the first intake to date its weeks and add groups.' : 'Publish the program in the studio first, then open a cohort.'}
      />
    )
  return (
    <Card className="overflow-hidden">
      <Table>
        <thead>
          <tr>
            <Th>Cohort</Th>
            <Th className="hidden md:table-cell">Dates</Th>
            <Th className="hidden sm:table-cell">Status</Th>
            <Th className="text-right">Groups</Th>
            <Th className="text-right">Learners</Th>
          </tr>
        </thead>
        <tbody className="stagger">
          {program.cohorts.map((c) => (
            <Tr key={c.id} className="relative transition-colors hover:bg-surface-2">
              <Td>
                <Link to={`/console/cohorts/${c.id}`} className="font-medium after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-primary">
                  {c.name}
                </Link>
                <span className="block text-xs text-muted md:hidden">{dayRange(c.start_date, c.end_date)}</span>
              </Td>
              <Td className="hidden md:table-cell tabular">{dayRange(c.start_date, c.end_date)}</Td>
              <Td className="hidden sm:table-cell">
                <StatusPill status={c.status === 'running' ? 'active' : c.status} label={COHORT_STATUS[c.status]} />
              </Td>
              <Td className="text-right tabular">{c.group_count}</Td>
              <Td className="text-right tabular">
                {c.learner_count}
                {c.capacity ? <span className="text-muted"> / {c.capacity}</span> : null}
              </Td>
            </Tr>
          ))}
        </tbody>
      </Table>
    </Card>
  )
}

function Structure({ program }: { program: ProgramDetail }) {
  if (!program.modules.length) return <EmptyState icon={<Layers />} title="No published modules" body="Build and publish the modules and weeks in the studio." />
  // first week number of each module (weeks are numbered across the whole program)
  const firstWeek = program.modules.map((_, i) => program.modules.slice(0, i).reduce((a, m) => a + m.weeks.length, 1))
  return (
    <ol className="stagger grid gap-3">
      {program.modules.map((m, i) => (
        <li key={m.id}>
          <Card className="p-4">
            <p className="text-xs font-medium tracking-wide text-muted uppercase">Module {i + 1}</p>
            <h3 className="mt-0.5 font-semibold">{m.title}</h3>
            <ol className="mt-3 grid gap-1.5 text-sm">
              {m.weeks.map((w, wi) => (
                <li key={w.id} className="flex gap-3">
                  <span className="w-16 shrink-0 text-muted tabular">Week {firstWeek[i]! + wi}</span>
                  <span className="min-w-0 truncate">{w.title}</span>
                </li>
              ))}
            </ol>
          </Card>
        </li>
      ))}
    </ol>
  )
}

export function ConsoleProgramPage() {
  const { programId } = useParams()
  const q = useProgram(programId)
  const [tab, setTab] = useTabParam(TABS, 'cohorts')
  const [creating, setCreating] = useState(false)
  const back = (
    <Link to="/console/programs" className="inline-flex items-center gap-1 text-sm text-muted hover:text-text">
      <ArrowLeft className="size-4" aria-hidden /> Programs
    </Link>
  )
  if (q.error) return <ErrorState message={(q.error as Error).message} onRetry={() => void q.refetch()} />
  if (!q.data)
    return (
      <div className="grid gap-4" aria-busy="true">
        <Skeleton className="h-16" />
        <Skeleton className="h-64" />
      </div>
    )
  const p = q.data
  return (
    <div className="grid gap-6 animate-reveal">
      <PageHeader
        back={back}
        title={p.title}
        description={p.published ? `${p.modules.length} modules · ${p.modules.reduce((a, m) => a + m.weeks.length, 0)} weeks` : 'Not published yet'}
        actions={
          <div className="flex flex-wrap gap-2">
            {p.can_build ? (
              <Button variant="secondary" asChild>
                <Link to={`/studio/courses/${p.id}/curriculum`}>
                  <PencilRuler /> Edit in studio
                </Link>
              </Button>
            ) : null}
            {p.can_manage ? (
              <Button onClick={() => setCreating(true)} disabled={!p.published} title={p.published ? undefined : 'Publish the program first'}>
                <CalendarPlus /> New cohort
              </Button>
            ) : null}
          </div>
        }
      />
      <Tabs value={tab} onValueChange={(v) => setTab(v as (typeof TABS)[number])}>
        <TabsList>
          <TabsTrigger value="cohorts">Cohorts</TabsTrigger>
          <TabsTrigger value="structure">Structure</TabsTrigger>
          <TabsTrigger value="offers">Offers</TabsTrigger>
          <TabsTrigger value="ksbs">KSBs</TabsTrigger>
          <TabsTrigger value="settings">Settings</TabsTrigger>
        </TabsList>
        <TabsContent value="cohorts">
          <Cohorts program={p} />
        </TabsContent>
        <TabsContent value="structure">
          <Structure program={p} />
        </TabsContent>
        <TabsContent value="offers">
          <ProgramOffers programId={p.id} />
        </TabsContent>
        <TabsContent value="ksbs">
          <ProgramKsbs programId={p.id} />
        </TabsContent>
        <TabsContent value="settings">
          <ProgramSettingsTab programId={p.id} />
        </TabsContent>
      </Tabs>
      {p.can_manage ? <NewCohort programId={p.id} open={creating} onOpenChange={setCreating} /> : null}
    </div>
  )
}
