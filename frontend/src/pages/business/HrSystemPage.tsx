import { AlertTriangle, Building2, CalendarOff, CheckCircle2, GraduationCap, History, KeyRound, Link2, Pause, Play, Plug, RefreshCw, Search, ShieldCheck, Unplug, UserCheck, UserPlus, Users } from 'lucide-react'
import { type FormEvent, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'

import { Avatar } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardHeader } from '@/components/ui/card'
import { Dialog, DialogClose, DialogContent } from '@/components/ui/dialog'
import { Field, Input, NativeSelect } from '@/components/ui/input'
import { EmptyState, ErrorState, PageHeader, StatCard } from '@/components/ui/misc'
import { PasswordInput } from '@/components/ui/password'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Table, Td, Th, Tr } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useRequirements } from '@/features/compliance/api'
import {
  HR_FEATURES,
  HR_STATUS,
  type HrConnection,
  type HrFeature,
  type HrOverview,
  type HrPerson,
  isRunActive,
  PERSON_STATUS,
  useAfterSync,
  useHrConnect,
  useHrDepartments,
  useHrDisconnect,
  useHrFeatures,
  useHrIgnore,
  useHrInvite,
  useHrLinkDepartment,
  useHrMapTraining,
  useHrMatch,
  useHrOverview,
  useHrPause,
  useHrPeople,
  useHrReplaceKey,
  useHrRuns,
  useHrSync,
  useHrTrainingRecords,
  useHrTrainingTitles,
  useHrValidate,
} from '@/features/integrations/api'
import { ROLE_LABEL, unitLabel, useAssignableRoles, usePeopleSearch, useUnits } from '@/features/org/api'
import { cn } from '@/lib/cn'
import { relativeDate, shortDate } from '@/lib/format'

const err = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong. Try again.')
const TABS = ['people', 'departments', 'training', 'history'] as const
type Tab = (typeof TABS)[number]

/** /business/hr-system (M17): connect Breathe HR and keep people, departments, training
 * records and approved leave in step. Admins change things; managers read. */
export function HrSystemPage() {
  const { data, isPending, error, refetch } = useHrOverview()
  useSyncFinished(data)

  return (
    <div>
      <PageHeader title="HR system" description="Keep your people, departments, training records and leave in step with Breathe HR." />
      {isPending ? (
        <div className="grid gap-4">
          <Skeleton className="h-36 rounded-lg" />
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28 rounded-lg" />)}
          </div>
          <Skeleton className="h-72 rounded-lg" />
        </div>
      ) : error || !data ? (
        <ErrorState message={err(error)} onRetry={() => void refetch()} />
      ) : !data.connection ? (
        <div className="animate-reveal">
          {!data.configured ? (
            <Card>
              <EmptyState icon={<ShieldCheck />} title="HR connections aren't switched on yet" body="The platform team needs to finish setting up secure key storage on this server. Nothing for you to do until then." />
            </Card>
          ) : data.can_manage ? (
            <ConnectCard />
          ) : (
            <Card>
              <EmptyState icon={<Plug />} title="No HR system connected" body="A company admin can connect Breathe HR here. You'll then see who is synced and who is on leave." />
            </Card>
          )}
        </div>
      ) : (
        <Connected data={data} connection={data.connection} />
      )}
    </div>
  )
}

/** When a sync that was running finishes: refresh everything it may have changed, and say so. */
function useSyncFinished(data?: HrOverview) {
  const afterSync = useAfterSync()
  const was = useRef<string | null>(null)
  const run = data?.latest_run
  useEffect(() => {
    if (!run) return
    if (was.current === run.id && !isRunActive(run)) {
      void afterSync()
      if (run.status === 'failed') toast.error(run.error_message || 'The sync did not finish.')
      else toast.success('Sync finished')
    }
    was.current = isRunActive(run) ? run.id : null
  }, [run, afterSync])
}

// ---------------------------------------------------------------- connect
function FeatureSwitches({ value, onChange, disabled }: { value: HrFeature[]; onChange: (v: HrFeature[]) => void; disabled?: boolean }) {
  return (
    <ul className="grid gap-3">
      {HR_FEATURES.map((f) => {
        const on = value.includes(f.key)
        const id = `hr-feature-${f.key}`
        return (
          <li key={f.key} className="flex items-start justify-between gap-4">
            <label htmlFor={id} className="min-w-0 cursor-pointer">
              <span className="block text-sm font-medium">{f.label}</span>
              <span className="block text-[13px] text-muted">{f.hint}</span>
            </label>
            <Switch id={id} checked={on} disabled={disabled} onCheckedChange={(c) => onChange(c ? [...value, f.key] : value.filter((k) => k !== f.key))} />
          </li>
        )
      })}
    </ul>
  )
}

function ConnectCard() {
  const connect = useHrConnect()
  const [apiKey, setApiKey] = useState('')
  const [env, setEnv] = useState<'production' | 'sandbox'>('production')
  const [features, setFeatures] = useState<HrFeature[]>(HR_FEATURES.map((f) => f.key))
  const submit = (e: FormEvent) => {
    e.preventDefault()
    connect.mutate(
      { api_key: apiKey, environment: env, features },
      {
        onSuccess: (c) => {
          setApiKey('')
          toast.success(`Connected to ${c.account_name}. The first sync has started.`)
        },
        onError: (e) => toast.error(err(e)),
      },
    )
  }
  return (
    <Card className="overflow-hidden">
      <div className="grid gap-0 lg:grid-cols-[1.2fr_1fr]">
        <form onSubmit={submit} className="grid gap-5 p-5 sm:p-6">
          <div className="flex items-center gap-3">
            <span className="flex size-11 items-center justify-center rounded-xl bg-primary-soft text-primary-soft-text">
              <Plug className="size-5" />
            </span>
            <div>
              <h2 className="text-base font-semibold">Connect Breathe HR</h2>
              <p className="text-sm text-muted">Paste an API key from Breathe: Settings, then API.</p>
            </div>
          </div>
          <Field label="API key" hint="We check it with Breathe, then store it encrypted. It is never shown again.">
            {(p) => <PasswordInput {...p} value={apiKey} onChange={(e) => setApiKey(e.target.value)} autoComplete="off" required minLength={8} maxLength={200} />}
          </Field>
          <Field label="Breathe account type">
            {(p) => (
              <NativeSelect {...p} value={env} onChange={(e) => setEnv(e.target.value as 'production' | 'sandbox')}>
                <option value="production">Live account</option>
                <option value="sandbox">Sandbox (for trying it out)</option>
              </NativeSelect>
            )}
          </Field>
          <fieldset className="grid gap-3">
            <legend className="mb-3 text-sm font-medium">What to keep in step</legend>
            <FeatureSwitches value={features} onChange={setFeatures} />
          </fieldset>
          <div>
            <Button type="submit" loading={connect.isPending} disabled={apiKey.trim().length < 8}>
              <Link2 /> Connect
            </Button>
          </div>
        </form>
        <aside className="border-t border-border bg-surface-2/50 p-5 sm:p-6 lg:border-t-0 lg:border-l">
          <h3 className="text-sm font-semibold">What we read from Breathe</h3>
          <ul className="mt-3 grid gap-2 text-sm text-muted [&_li]:flex [&_li]:gap-2 [&_svg]:mt-0.5 [&_svg]:size-4 [&_svg]:shrink-0 [&_svg]:text-success">
            <li><CheckCircle2 /> Each person's name, work email, job title, department, line manager, status, start date, hours and working pattern</li>
            <li><CheckCircle2 /> Training recorded in Breathe, to count towards your requirements</li>
            <li><CheckCircle2 /> Approved leave dates, never the reason</li>
          </ul>
          <h3 className="mt-6 text-sm font-semibold">What we never do</h3>
          <ul className="mt-3 grid gap-2 text-sm text-muted [&_li]:flex [&_li]:gap-2 [&_svg]:mt-0.5 [&_svg]:size-4 [&_svg]:shrink-0">
            <li><ShieldCheck className="text-primary" /> Write anything back to Breathe</li>
            <li><ShieldCheck className="text-primary" /> Add anyone without an admin confirming it</li>
            <li><ShieldCheck className="text-primary" /> Remove people who leave: we flag them for you</li>
          </ul>
        </aside>
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------- connected
function Connected({ data, connection }: { data: HrOverview; connection: HrConnection }) {
  const [params, setParams] = useSearchParams()
  const tab = (TABS as readonly string[]).includes(params.get('tab') ?? '') ? (params.get('tab') as Tab) : 'people'
  const c = data.counts
  return (
    <div className="grid gap-6">
      <ConnectionCard data={data} connection={connection} />
      {c ? (
        <div className="stagger grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard label="People to review" value={c.to_review} icon={<UserPlus />} tone={c.to_review ? 'warning' : 'success'} hint={`${c.people} in Breathe`} />
          <StatCard label="Linked to accounts" value={c.linked} icon={<UserCheck />} tone="success" hint={c.invited ? `${c.invited} invited` : undefined} />
          <StatCard label="Departments linked" value={c.departments_linked} icon={<Building2 />} tone="info" hint={`of ${c.departments}`} />
          <StatCard label="On leave today" value={c.on_leave} icon={<CalendarOff />} tone="primary" hint={c.leavers ? `${c.leavers} marked as leavers` : undefined} />
        </div>
      ) : null}
      <Tabs value={tab} onValueChange={(v) => setParams((p) => (p.set('tab', v), p), { replace: true })}>
        <TabsList>
          <TabsTrigger value="people"><Users /> People</TabsTrigger>
          <TabsTrigger value="departments"><Building2 /> Departments</TabsTrigger>
          <TabsTrigger value="training"><GraduationCap /> Training</TabsTrigger>
          <TabsTrigger value="history"><History /> History</TabsTrigger>
        </TabsList>
        <TabsContent value="people"><PeopleTab canManage={data.can_manage} /></TabsContent>
        <TabsContent value="departments"><DepartmentsTab canManage={data.can_manage} enabled={connection.features.includes('departments')} /></TabsContent>
        <TabsContent value="training"><TrainingTab canManage={data.can_manage} enabled={connection.features.includes('training')} /></TabsContent>
        <TabsContent value="history"><HistoryTab /></TabsContent>
      </Tabs>
    </div>
  )
}

function ConnectionCard({ data, connection: c }: { data: HrOverview; connection: HrConnection }) {
  const sync = useHrSync()
  const check = useHrValidate()
  const pause = useHrPause()
  const status = HR_STATUS[c.status] ?? HR_STATUS.active!
  const running = isRunActive(data.latest_run)
  const usable = c.status === 'active' || c.status === 'attention'
  return (
    <Card className="animate-reveal p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-center gap-4">
          <span className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary-soft-text">
            <Plug className="size-6" />
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="truncate text-base font-semibold">{c.account_name}</h2>
              <Badge tone={status.tone} dot>{status.label}</Badge>
              {c.environment === 'sandbox' ? <Badge tone="outline">Sandbox</Badge> : null}
            </div>
            <p className="mt-1 text-sm text-muted">
              Breathe HR · {c.last_sync_at ? `last synced ${relativeDate(c.last_sync_at)}` : 'not synced yet'} · syncs every hour
            </p>
          </div>
        </div>
        {data.can_manage ? (
          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={() => sync.mutate(undefined, { onSuccess: () => toast.success('Sync started'), onError: (e) => toast.error(err(e)) })} loading={sync.isPending} disabled={running || !usable}>
              <RefreshCw className={cn(running && 'animate-spin motion-reduce:animate-none')} /> {running ? 'Syncing…' : 'Sync now'}
            </Button>
            <Button variant="secondary" onClick={() => check.mutate(undefined, { onSuccess: () => toast.success('The connection works'), onError: (e) => toast.error(err(e)) })} loading={check.isPending} disabled={c.status === 'disabled'}>
              <ShieldCheck /> Check connection
            </Button>
            <ReplaceKeyDialog />
            {c.status !== 'disabled' ? (
              <Button variant="ghost" onClick={() => pause.mutate(c.status !== 'paused', { onSuccess: (r) => toast.success(r.status === 'paused' ? 'Syncing paused' : 'Syncing resumed'), onError: (e) => toast.error(err(e)) })} loading={pause.isPending}>
                {c.status === 'paused' ? <><Play /> Resume</> : <><Pause /> Pause</>}
              </Button>
            ) : null}
            <FeaturesDialog connection={c} />
            {c.status !== 'disabled' ? <DisconnectDialog /> : null}
          </div>
        ) : null}
      </div>
      {c.last_error ? (
        <p role="alert" className="mt-4 flex gap-2 rounded-lg bg-warning-soft p-3 text-sm text-warning">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" /> {c.last_error}
        </p>
      ) : null}
      {c.status === 'disabled' ? (
        <p className="mt-4 rounded-lg bg-surface-2 p-3 text-sm text-muted">Disconnected. Linked people and imported records stay. Replace the key to connect again.</p>
      ) : null}
    </Card>
  )
}

function ReplaceKeyDialog() {
  const replace = useHrReplaceKey()
  const [open, setOpen] = useState(false)
  const [apiKey, setApiKey] = useState('')
  const submit = (e: FormEvent) => {
    e.preventDefault()
    replace.mutate(apiKey, {
      onSuccess: () => (toast.success('API key replaced'), setApiKey(''), setOpen(false)),
      onError: (e) => toast.error(err(e)),
    })
  }
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button variant="ghost" onClick={() => setOpen(true)}><KeyRound /> Replace key</Button>
      <DialogContent title="Replace the API key" description="Use a new key for the same Breathe account. The old one stops being used at once.">
        <form onSubmit={submit} className="grid gap-5">
          <Field label="New API key">{(p) => <PasswordInput {...p} value={apiKey} onChange={(e) => setApiKey(e.target.value)} autoComplete="off" required minLength={8} />}</Field>
          <div className="flex justify-end gap-2">
            <DialogClose asChild><Button type="button" variant="secondary">Cancel</Button></DialogClose>
            <Button type="submit" loading={replace.isPending}>Replace key</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function FeaturesDialog({ connection }: { connection: HrConnection }) {
  const save = useHrFeatures()
  const [open, setOpen] = useState(false)
  const [features, setFeatures] = useState<HrFeature[]>(connection.features as HrFeature[])
  return (
    <Dialog open={open} onOpenChange={(o) => (setOpen(o), o && setFeatures(connection.features as HrFeature[]))}>
      <Button variant="ghost" onClick={() => setOpen(true)}>Settings</Button>
      <DialogContent title="What to keep in step" description="Changes apply from the next sync.">
        <FeatureSwitches value={features} onChange={setFeatures} />
        <div className="mt-6 flex justify-end gap-2">
          <DialogClose asChild><Button variant="secondary">Cancel</Button></DialogClose>
          <Button loading={save.isPending} onClick={() => save.mutate(features, { onSuccess: () => (toast.success('Saved'), setOpen(false)), onError: (e) => toast.error(err(e)) })}>Save</Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function DisconnectDialog() {
  const disconnect = useHrDisconnect()
  const [open, setOpen] = useState(false)
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button variant="ghost" className="text-danger" onClick={() => setOpen(true)}><Unplug /> Disconnect</Button>
      <DialogContent title="Disconnect Breathe HR?" description="Syncing stops and the saved key is deleted. Linked people, departments and imported training records stay as they are.">
        <div className="flex justify-end gap-2">
          <DialogClose asChild><Button variant="secondary">Keep connected</Button></DialogClose>
          <Button variant="danger" loading={disconnect.isPending} onClick={() => disconnect.mutate(undefined, { onSuccess: () => (toast.success('Disconnected'), setOpen(false)), onError: (e) => toast.error(err(e)) })}>Disconnect</Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------- people
const PEOPLE_FILTERS = [
  { key: '', label: 'Everyone' },
  { key: 'pending', label: 'To review' },
  { key: 'matched', label: 'Linked' },
  { key: 'invited', label: 'Invited' },
  { key: 'ignored', label: 'Ignored' },
  { key: 'leaver', label: 'Leavers' },
]

function useDebounced(value: string, ms = 250) {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value.trim()), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

function PeopleTab({ canManage }: { canManage: boolean }) {
  const [status, setStatus] = useState(canManage ? 'pending' : '')
  const [text, setText] = useState('')
  const q = useDebounced(text)
  const { data, isLoading, error, refetch, fetchNextPage, hasNextPage, isFetchingNextPage } = useHrPeople(status, q)
  const [open, setOpen] = useState<HrPerson | null>(null)
  const rows = data?.pages.flatMap((p) => p.items) ?? []
  return (
    <Card className="mt-4">
      <div className="flex flex-wrap items-center justify-between gap-3 p-4">
        <div role="group" aria-label="Filter people" className="flex flex-wrap gap-1.5">
          {PEOPLE_FILTERS.map((f) => (
            <button key={f.key} type="button" aria-pressed={status === f.key} onClick={() => setStatus(f.key)}
              className={cn('rounded-full border px-3 py-1 text-[13px] font-medium transition-colors', status === f.key ? 'border-primary bg-primary-soft text-primary-soft-text' : 'border-border text-muted hover:text-text')}>
              {f.label}
            </button>
          ))}
        </div>
        <Input icon={<Search />} value={text} onChange={(e) => setText(e.target.value)} placeholder="Search name, email or job" aria-label="Search people from Breathe" className="w-full sm:w-64" />
      </div>
      {isLoading ? (
        <div className="grid gap-2 p-4">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-12" />)}</div>
      ) : error ? (
        <ErrorState message={err(error)} onRetry={() => void refetch()} />
      ) : !rows.length ? (
        <EmptyState icon={<Users />} title={status === 'pending' && !q ? 'Nobody to review' : 'No people here'} body={status === 'pending' && !q ? 'Everyone from Breathe is linked, invited or ignored.' : 'Try another filter or search.'} />
      ) : (
        <div className="animate-reveal">
          <Table>
            <thead>
              <tr>
                <Th>Person</Th>
                <Th className="hidden md:table-cell">Job title</Th>
                <Th className="hidden lg:table-cell">Department</Th>
                <Th>Status</Th>
                <Th className="sr-only sm:not-sr-only">Action</Th>
              </tr>
            </thead>
            <tbody className="stagger">
              {rows.map((p) => {
                const s = PERSON_STATUS[p.status] ?? PERSON_STATUS.pending!
                return (
                  <Tr key={p.id}>
                    <Td>
                      <div className="flex min-w-0 items-center gap-3">
                        <Avatar name={p.name} size="sm" />
                        <div className="min-w-0">
                          <p className="truncate font-medium">{p.name}</p>
                          <p className="truncate text-xs text-muted">{p.email || 'No email in Breathe'}</p>
                        </div>
                      </div>
                    </Td>
                    <Td className="hidden text-muted md:table-cell">{p.job_title || '–'}</Td>
                    <Td className="hidden text-muted lg:table-cell">{p.department || '–'}</Td>
                    <Td>
                      <div className="flex flex-wrap gap-1">
                        <Badge tone={s.tone}>{s.label}</Badge>
                        {p.is_leaver ? <Badge tone="danger">Leaver</Badge> : null}
                        {p.status === 'pending' && p.suggestion ? <Badge tone="outline">Match found</Badge> : null}
                      </div>
                    </Td>
                    <Td className="text-right">
                      <Button variant="ghost" size="sm" onClick={() => setOpen(p)} aria-label={`Open ${p.name}`}>
                        {canManage && p.status === 'pending' ? 'Review' : 'View'}
                      </Button>
                    </Td>
                  </Tr>
                )
              })}
            </tbody>
          </Table>
          {hasNextPage ? (
            <div className="flex justify-center p-4">
              <Button variant="secondary" onClick={() => void fetchNextPage()} loading={isFetchingNextPage}>Show more</Button>
            </div>
          ) : null}
        </div>
      )}
      <Dialog open={!!open} onOpenChange={(o) => !o && setOpen(null)}>
        {open ? (
          <DialogContent side="right" title={open.name} description="From Breathe HR" className="w-[min(420px,92vw)]">
            <PersonSheet person={open} canManage={canManage} onDone={() => setOpen(null)} />
          </DialogContent>
        ) : null}
      </Dialog>
    </Card>
  )
}

function PersonSheet({ person: p, canManage, onDone }: { person: HrPerson; canManage: boolean; onDone: () => void }) {
  const match = useHrMatch()
  const ignore = useHrIgnore()
  const facts: [string, string | null | undefined][] = [
    ['Breathe ID', p.external_employee_id],
    ['Email', p.email],
    ['Job title', p.job_title],
    ['Department', p.department],
    ['Status', p.employment_status],
    ['Started', p.start_date ? shortDate(p.start_date) : null],
    ['Hours a week', p.contracted_hours != null ? String(p.contracted_hours) : null],
    ['Working pattern', p.working_pattern],
  ]
  const link = (memberId: string, name: string) =>
    match.mutate({ personId: p.id, memberId }, { onSuccess: () => (toast.success(`Linked to ${name}`), onDone()), onError: (e) => toast.error(err(e)) })
  return (
    <div className="grid gap-6 p-4">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
        {facts.filter(([, v]) => v).map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted">{k}</dt>
            <dd className="min-w-0 break-words">{v}</dd>
          </div>
        ))}
      </dl>
      {p.is_leaver ? <p className="rounded-lg bg-danger-soft p-3 text-sm text-danger">Breathe marks this person as a leaver. They stay in LearnHub until an admin removes them.</p> : null}

      {p.member ? (
        <section className="grid gap-3">
          <h3 className="text-sm font-semibold">Linked account</h3>
          <div className="flex items-center gap-3 rounded-lg border border-border p-3">
            <Avatar name={p.member.name} size="sm" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{p.member.name}</p>
              <p className="truncate text-xs text-muted">{p.member.email}</p>
            </div>
          </div>
          {canManage ? (
            <Button variant="ghost" className="justify-self-start" loading={ignore.isPending} onClick={() => ignore.mutate({ personId: p.id, undo: true }, { onSuccess: () => (toast.success('Unlinked'), onDone()), onError: (e) => toast.error(err(e)) })}>
              Unlink
            </Button>
          ) : null}
        </section>
      ) : !canManage ? null : p.status === 'ignored' || p.status === 'invited' ? (
        <section className="grid gap-3">
          <p className="text-sm text-muted">{p.status === 'invited' ? 'An invitation was sent. They are linked as soon as they accept it.' : 'This person is ignored and not counted as "to review".'}</p>
          <Button variant="secondary" className="justify-self-start" loading={ignore.isPending} onClick={() => ignore.mutate({ personId: p.id, undo: true }, { onSuccess: () => (toast.success('Back to review'), onDone()), onError: (e) => toast.error(err(e)) })}>
            Review again
          </Button>
        </section>
      ) : (
        <>
          {p.suggestion ? (
            <section className="grid gap-3 rounded-lg border border-primary/30 bg-primary-soft/40 p-3">
              <p className="text-sm"><span className="font-medium">{p.suggestion.name}</span> has the same email address. Is it the same person?</p>
              <Button className="justify-self-start" loading={match.isPending} onClick={() => link(p.suggestion!.member_id, p.suggestion!.name)}>
                <UserCheck /> Link to {p.suggestion.name}
              </Button>
            </section>
          ) : null}
          <ChooseMember onPick={link} busy={match.isPending} />
          <InviteForm person={p} onDone={onDone} />
          <Button variant="ghost" className="justify-self-start text-muted" loading={ignore.isPending} onClick={() => ignore.mutate({ personId: p.id }, { onSuccess: () => (toast.success('Ignored'), onDone()), onError: (e) => toast.error(err(e)) })}>
            Ignore this person
          </Button>
        </>
      )}
    </div>
  )
}

function ChooseMember({ onPick, busy }: { onPick: (memberId: string, name: string) => void; busy: boolean }) {
  const [text, setText] = useState('')
  const q = useDebounced(text)
  const { data, isFetching } = usePeopleSearch(q, q.length >= 2)
  const people = data?.items ?? []
  return (
    <section className="grid gap-2">
      <h3 className="text-sm font-semibold">Link to someone already here</h3>
      <Input icon={<Search />} value={text} onChange={(e) => setText(e.target.value)} placeholder="Type a name or email" aria-label="Find a person to link" />
      {q.length >= 2 ? (
        <ul className="grid max-h-56 gap-1 overflow-y-auto" aria-busy={isFetching}>
          {people.slice(0, 8).map((m) => (
            <li key={m.member_id}>
              <button type="button" disabled={busy} onClick={() => onPick(m.member_id, m.name || m.email)} className="flex w-full items-center gap-3 rounded-md p-2 text-left text-sm transition-colors hover:bg-surface-2 disabled:opacity-60">
                <Avatar name={m.name || m.email} size="sm" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{m.name || m.email}</span>
                  <span className="block truncate text-xs text-muted">{m.email}</span>
                </span>
              </button>
            </li>
          ))}
          {!people.length && !isFetching ? <li className="p-2 text-sm text-muted">Nobody matches.</li> : null}
        </ul>
      ) : null}
    </section>
  )
}

function InviteForm({ person, onDone }: { person: HrPerson; onDone: () => void }) {
  const invite = useHrInvite()
  const roles = useAssignableRoles()
  const { data: units } = useUnits()
  const [role, setRole] = useState('learner')
  const [unitId, setUnitId] = useState('')
  if (!person.email) return <p className="text-sm text-muted">To invite this person, add their work email in Breathe first.</p>
  const submit = (e: FormEvent) => {
    e.preventDefault()
    invite.mutate({ personId: person.id, role, unitId: unitId || null }, { onSuccess: (r) => (toast.success(`Invitation sent to ${r.email}`), onDone()), onError: (e) => toast.error(err(e)) })
  }
  return (
    <form onSubmit={submit} className="grid gap-3 rounded-lg border border-border p-3">
      <h3 className="text-sm font-semibold">Or invite them</h3>
      <p className="text-[13px] text-muted">An invitation goes to {person.email}. They are linked when they accept.</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Role">
          {(p) => (
            <NativeSelect {...p} value={role} onChange={(e) => setRole(e.target.value)}>
              {roles.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
            </NativeSelect>
          )}
        </Field>
        <Field label="Team or location">
          {(p) => (
            <NativeSelect {...p} value={unitId} onChange={(e) => setUnitId(e.target.value)}>
              <option value="">Their Breathe department</option>
              {(units ?? []).map((u) => <option key={u.id} value={u.id}>{unitLabel(u, units ?? [])}</option>)}
            </NativeSelect>
          )}
        </Field>
      </div>
      <Button type="submit" variant="secondary" className="justify-self-start" loading={invite.isPending}><UserPlus /> Send invitation</Button>
    </form>
  )
}

// ---------------------------------------------------------------- departments
function DepartmentsTab({ canManage, enabled }: { canManage: boolean; enabled: boolean }) {
  const { data, isLoading, error, refetch } = useHrDepartments()
  const { data: units } = useUnits()
  const link = useHrLinkDepartment()
  const [busy, setBusy] = useState<string | null>(null)
  const act = (deptId: string, v: { unitId?: string | null; create?: boolean }, done: string) => {
    setBusy(deptId)
    link.mutate({ deptId, ...v }, { onSuccess: () => toast.success(done), onError: (e) => toast.error(err(e)), onSettled: () => setBusy(null) })
  }
  return (
    <Card className="mt-4">
      <CardHeader title="Departments" description={enabled ? 'Link each Breathe department to a team. Linked people are placed in it, and its required training applies to them.' : 'Turn on "Departments" in Settings to place people in teams automatically.'} />
      <div className="p-4">
        {isLoading ? (
          <div className="grid gap-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}</div>
        ) : error ? (
          <ErrorState message={err(error)} onRetry={() => void refetch()} />
        ) : !data?.length ? (
          <EmptyState icon={<Building2 />} title="No departments yet" body="They appear here after the next sync." />
        ) : (
          <Table className="animate-reveal">
            <thead>
              <tr>
                <Th>Breathe department</Th>
                <Th className="hidden sm:table-cell">People</Th>
                <Th>Team in LearnHub</Th>
              </tr>
            </thead>
            <tbody className="stagger">
              {data.map((d) => (
                <Tr key={d.id}>
                  <Td>
                    <p className="font-medium">{d.name}</p>
                    {d.status === 'linked' ? <Badge tone="success" className="mt-1">Linked</Badge> : null}
                  </Td>
                  <Td className="hidden text-muted tabular sm:table-cell">{d.people}</Td>
                  <Td>
                    {canManage ? (
                      <div className="flex flex-wrap items-center gap-2">
                        <NativeSelect aria-label={`Team for ${d.name}`} value={d.unit_id ?? ''} disabled={busy === d.id} onChange={(e) => act(d.id, { unitId: e.target.value || null }, e.target.value ? 'Department linked' : 'Department unlinked')} className="min-w-0 sm:w-56">
                          <option value="">Not linked</option>
                          {(units ?? []).map((u) => <option key={u.id} value={u.id}>{unitLabel(u, units ?? [])}</option>)}
                        </NativeSelect>
                        {!d.unit_id ? (
                          <Button variant="secondary" size="sm" loading={busy === d.id} onClick={() => act(d.id, { create: true }, `Created the team "${d.name}"`)}>
                            Create team
                          </Button>
                        ) : null}
                      </div>
                    ) : (
                      <span className="text-muted">{d.unit_name ?? 'Not linked'}</span>
                    )}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------- training
function TrainingTab({ canManage, enabled }: { canManage: boolean; enabled: boolean }) {
  const titles = useHrTrainingTitles(enabled)
  const records = useHrTrainingRecords(enabled)
  const { data: requirements } = useRequirements()
  const map = useHrMapTraining()
  const [busy, setBusy] = useState<string | null>(null)
  if (!enabled) {
    return (
      <Card className="mt-4">
        <EmptyState icon={<GraduationCap />} title="Training records are off" body='Turn on "Training records" in Settings to count training from Breathe towards your requirements.' />
      </Card>
    )
  }
  const onMap = (title: string, requirementId: string) => {
    setBusy(title)
    map.mutate(
      { title, requirementId: requirementId || null },
      {
        onSuccess: (r) => toast.success(requirementId ? (r.applied ? `${r.applied} records now count` : 'Saved. Matching records count from now on.') : 'No longer counted'),
        onError: (e) => toast.error(err(e)),
        onSettled: () => setBusy(null),
      },
    )
  }
  return (
    <div className="mt-4 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
      <Card>
        <CardHeader title="Training titles" description="Choose which requirement each Breathe course counts towards. Imported records expire by that requirement's renewal rule." />
        <div className="p-4">
          {titles.isLoading ? (
            <div className="grid gap-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}</div>
          ) : titles.error ? (
            <ErrorState message={err(titles.error)} onRetry={() => void titles.refetch()} />
          ) : !titles.data?.length ? (
            <EmptyState icon={<GraduationCap />} title="No training records yet" body="Training recorded in Breathe appears here after a sync." />
          ) : (
            <Table className="animate-reveal">
              <thead>
                <tr>
                  <Th>Breathe course</Th>
                  <Th>Counts towards</Th>
                </tr>
              </thead>
              <tbody className="stagger">
                {titles.data.map((t) => (
                  <Tr key={t.title}>
                    <Td>
                      <p className="font-medium">{t.title}</p>
                      <p className="text-xs text-muted">{t.records} {t.records === 1 ? 'record' : 'records'}{t.applied ? ` · ${t.applied} counted` : ''}</p>
                    </Td>
                    <Td>
                      {canManage ? (
                        <NativeSelect aria-label={`Requirement for ${t.title}`} value={t.requirement_id ?? ''} disabled={busy === t.title} onChange={(e) => onMap(t.title, e.target.value)} className="min-w-0 sm:w-60">
                          <option value="">Not counted</option>
                          {(requirements ?? []).map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
                        </NativeSelect>
                      ) : (
                        <span className="text-muted">{t.requirement_name ?? 'Not counted'}</span>
                      )}
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </div>
      </Card>
      <Card>
        <CardHeader title="Latest records" description="The newest training from Breathe." />
        <div className="p-4">
          {records.isLoading ? (
            <div className="grid gap-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-10" />)}</div>
          ) : records.error ? (
            <ErrorState message={err(records.error)} onRetry={() => void records.refetch()} />
          ) : !records.data?.length ? (
            <p className="text-sm text-muted">Nothing yet.</p>
          ) : (
            <ul className="stagger grid gap-2">
              {records.data.slice(0, 12).map((r) => (
                <li key={r.id} className="flex items-start justify-between gap-3 rounded-md border border-border p-2.5 text-sm">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{r.title}</p>
                    <p className="truncate text-xs text-muted">{r.person_name ?? 'Unknown person'}{r.completion_date ? ` · ${shortDate(r.completion_date)}` : ''}</p>
                  </div>
                  {r.applied ? <Badge tone="success">Counted</Badge> : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------- history
const RUN_TONE: Record<string, 'success' | 'danger' | 'info' | 'neutral'> = { completed: 'success', failed: 'danger', running: 'info', queued: 'neutral' }
const TRIGGER: Record<string, string> = { manual: 'Sync now', hourly: 'Hourly', connect: 'First sync' }

function HistoryTab() {
  const { data, isLoading, error, refetch } = useHrRuns()
  return (
    <Card className="mt-4">
      <CardHeader title="Sync history" description="The last 20 syncs." />
      <div className="p-4">
        {isLoading ? (
          <div className="grid gap-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-14" />)}</div>
        ) : error ? (
          <ErrorState message={err(error)} onRetry={() => void refetch()} />
        ) : !data?.length ? (
          <EmptyState icon={<History />} title="No syncs yet" />
        ) : (
          <ol className="stagger grid gap-2">
            {data.map((r) => {
              const n = r.counts
              return (
                <li key={r.id} className="rounded-lg border border-border p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <Badge tone={RUN_TONE[r.status] ?? 'neutral'} dot>{r.status[0]!.toUpperCase() + r.status.slice(1)}</Badge>
                      <span className="text-sm font-medium">{TRIGGER[r.trigger] ?? r.trigger}</span>
                      {r.triggered_by ? <span className="text-sm text-muted">by {r.triggered_by}</span> : null}
                    </div>
                    <span className="text-xs text-muted">{relativeDate(r.created_at)}</span>
                  </div>
                  {r.status === 'completed' && n ? (
                    <p className="mt-1.5 text-[13px] text-muted">
                      {n.people ?? 0} people{n.new_people ? ` (${n.new_people} new)` : ''} · {n.departments ?? 0} departments · {n.training ?? 0} training records{n.applied ? ` (${n.applied} counted)` : ''} · {n.leave ?? 0} leave
                    </p>
                  ) : null}
                  {r.error_message ? <p className="mt-1.5 text-[13px] text-danger">{r.error_message}</p> : null}
                </li>
              )
            })}
          </ol>
        )}
      </div>
    </Card>
  )
}
