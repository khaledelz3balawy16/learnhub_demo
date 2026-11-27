import { AlertTriangle, ArrowLeft, CalendarDays, CalendarOff, ChevronDown, Pencil, Plus, Trash2, UserMinus, UserPlus, Users, UsersRound } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { useParams } from 'react-router-dom'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardHeader } from '@/components/ui/card'
import { CountUp } from '@/components/ui/count-up'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Field, Input, NativeSelect, Textarea } from '@/components/ui/input'
import { Menu, MenuContent, MenuItem, MenuTrigger } from '@/components/ui/menu'
import { EmptyState, ErrorState, PageHeader, StatCard } from '@/components/ui/misc'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ConfirmDialog, DetailSheet, InfoRow, LoadMore, StatusPill, useTabParam } from '@/features/console/ui'
import {
  CALENDARS,
  COHORT_NEXT,
  COHORT_STATUS,
  type CohortDetail,
  type CohortGroup,
  type GroupBody,
  WEEKDAYS,
  useAddMembers,
  useCohort,
  useCreateGroup,
  useDeleteGroup,
  useGroupMembers,
  useRemoveMember,
  useSetModuleStart,
  useTutors,
  useUpdateCohort,
  useUpdateGroup,
} from '@/features/programs/api'
import { ClosureDialog, ClosureRows, useClosureActions } from '@/features/programs/ui'
import { Link } from '@/lib/router'
import { dayRange, dayWithWeekday, timetable } from '@/lib/schedule'

import { GroupSessions } from './LiveSessions'
import { LearnerRecordSheet } from './OtjApprovalsPage'

const TABS = ['schedule', 'groups', 'closures'] as const
const err = (e: unknown) => toast.error((e as Error).message)
const statusTone = (s: string) => (s === 'running' ? 'active' : s)

// ---------------------------------------------------------------- cohort settings
function EditCohort({ cohort, open, onOpenChange }: { cohort: CohortDetail; open: boolean; onOpenChange: (o: boolean) => void }) {
  const update = useUpdateCohort(cohort.id)
  const [name, setName] = useState(cohort.name)
  const [start, setStart] = useState(cohort.start_date)
  const [calendar, setCalendar] = useState(cohort.calendar)
  const [capacity, setCapacity] = useState(cohort.capacity ? String(cohort.capacity) : '')
  const running = cohort.status === 'running'
  const submit = (e: FormEvent) => {
    e.preventDefault()
    update.mutate(
      {
        name: name.trim(),
        calendar,
        capacity: capacity ? Number(capacity) : null,
        ...(running ? {} : { start_date: start }),
      },
      {
        onSuccess: () => (toast.success('Cohort saved'), onOpenChange(false)),
        onError: err,
      },
    )
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Cohort details" description="Changing the start date or holidays works out every week's dates again.">
        <form className="grid gap-4" onSubmit={submit}>
          <Field label="Name">{(p) => <Input {...p} value={name} onChange={(e) => setName(e.target.value)} maxLength={120} required />}</Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Start date" hint={running ? 'Fixed once the cohort is running.' : undefined}>
              {(p) => <Input {...p} type="date" value={start} onChange={(e) => setStart(e.target.value)} disabled={running} required />}
            </Field>
            <Field label="Places (optional)">{(p) => <Input {...p} type="number" min={1} inputMode="numeric" value={capacity} onChange={(e) => setCapacity(e.target.value)} />}</Field>
          </div>
          <Field label="Bank holidays">
            {(p) => (
              <NativeSelect {...p} value={calendar} onChange={(e) => setCalendar(e.target.value)}>
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
            <Button type="submit" loading={update.isPending}>
              Save
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function StatusMenu({ cohort }: { cohort: CohortDetail }) {
  const update = useUpdateCohort(cohort.id)
  const [confirm, setConfirm] = useState<string | null>(null)
  const next = COHORT_NEXT[cohort.status] ?? []
  if (!next.length) return null
  return (
    <>
      <Menu>
        <MenuTrigger asChild>
          <Button variant="secondary">
            Change status <ChevronDown />
          </Button>
        </MenuTrigger>
        <MenuContent>
          {next.map((s) => (
            <MenuItem key={s} onSelect={() => setConfirm(s)}>
              {COHORT_STATUS[s]}
            </MenuItem>
          ))}
        </MenuContent>
      </Menu>
      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={`Mark as “${confirm ? COHORT_STATUS[confirm] : ''}”?`}
        body={confirm === 'cancelled' || confirm === 'finished' ? 'After this the cohort can’t be changed. Learners keep their progress.' : undefined}
        confirmLabel="Change status"
        tone={confirm === 'cancelled' ? 'danger' : 'primary'}
        loading={update.isPending}
        onConfirm={() =>
          confirm &&
          update.mutate(
            { status: confirm },
            {
              onSuccess: () => (toast.success('Status changed'), setConfirm(null)),
              onError: err,
            },
          )
        }
      />
    </>
  )
}

// ---------------------------------------------------------------- schedule
function ModuleStart({ cohort, moduleKey, override }: { cohort: CohortDetail; moduleKey: string; override: string | null }) {
  const set = useSetModuleStart(cohort.id)
  const [value, setValue] = useState(override ?? '')
  const save = (startsOn: string | null) =>
    set.mutate(
      { moduleKey, startsOn },
      {
        onSuccess: () => toast.success(startsOn ? 'Module start date saved' : 'Module starts automatically again'),
        onError: err,
      },
    )
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault()
        if (value) save(value)
      }}
    >
      <Field label="Start this module on" hint={override ? undefined : 'Leave empty to follow the previous module.'}>
        {(p) => <Input {...p} type="date" className="w-44" value={value} min={cohort.start_date} onChange={(e) => setValue(e.target.value)} />}
      </Field>
      <Button type="submit" size="sm" variant="secondary" loading={set.isPending} disabled={!value || value === override}>
        Save
      </Button>
      {override ? (
        <Button type="button" size="sm" variant="ghost" onClick={() => (setValue(''), save(null))}>
          Use automatic date
        </Button>
      ) : null}
    </form>
  )
}

function Schedule({ cohort }: { cohort: CohortDetail }) {
  if (!cohort.modules.length) return <EmptyState icon={<CalendarDays />} title="Nothing to schedule" body="The program has no published modules yet." />
  return (
    <div className="grid gap-4">
      {cohort.warnings.length ? (
        <div role="status" className="flex gap-3 rounded-lg border border-warning/30 bg-warning-soft p-4 text-sm text-warning">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
          <ul className="grid gap-1">
            {cohort.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <ol className="stagger grid gap-4">
        {cohort.modules.map((m, i) => (
          <li key={m.module_key}>
            <Card>
              <CardHeader
                className="flex-wrap"
                title={
                  <span>
                    <span className="mr-2 text-xs font-medium tracking-wide text-muted uppercase">Module {i + 1}</span>
                    {m.title}
                  </span>
                }
                description={
                  <span className="tabular">
                    {dayRange(m.starts_on, m.ends_on)}
                    {m.override ? ' · start date set by hand' : ''}
                  </span>
                }
              />
              <ol className="mt-3 divide-y divide-border border-t border-border">
                {m.weeks.map((w) => (
                  <li key={w.section_id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-2.5 text-sm">
                    <span className="w-16 shrink-0 font-medium text-muted tabular">Week {w.number}</span>
                    <span className="min-w-0 flex-1 truncate">{w.title}</span>
                    <span className="text-muted tabular">{dayRange(w.starts_on, w.ends_on)}</span>
                    {w.days_off.map((d) => (
                      <Badge key={d.date} tone="info" title={d.title}>
                        {dayWithWeekday(d.date)} off
                      </Badge>
                    ))}
                  </li>
                ))}
              </ol>
              {cohort.can_manage ? (
                <div className="border-t border-border px-5 py-4">
                  <ModuleStart key={m.override ?? 'auto'} cohort={cohort} moduleKey={m.module_key} override={m.override} />
                </div>
              ) : null}
            </Card>
          </li>
        ))}
      </ol>
      {cohort.breaks.length ? (
        <Card>
          <CardHeader title="Breaks" description="Weeks with no teaching day. The program carries on the week after." />
          <ul className="mt-3 divide-y divide-border border-t border-border">
            {cohort.breaks.map((b) => (
              <li key={b.starts_on} className="flex flex-wrap items-center gap-3 px-5 py-2.5 text-sm">
                <CalendarOff className="size-4 text-subtle" aria-hidden />
                <span className="flex-1">{b.reason}</span>
                <span className="text-muted tabular">{dayRange(b.starts_on, b.ends_on)}</span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  )
}

// ---------------------------------------------------------------- groups
function GroupDialog({ cohortId, group, open, onOpenChange }: { cohortId: string; group?: CohortGroup; open: boolean; onOpenChange: (o: boolean) => void }) {
  const create = useCreateGroup(cohortId)
  const update = useUpdateGroup(cohortId)
  const tutors = useTutors('')
  const [name, setName] = useState(group?.name ?? '')
  const [weekday, setWeekday] = useState(group?.weekday != null ? String(group.weekday) : '')
  const [startsAt, setStartsAt] = useState(group?.starts_at?.slice(0, 5) ?? '')
  const [endsAt, setEndsAt] = useState(group?.ends_at?.slice(0, 5) ?? '')
  const [capacity, setCapacity] = useState(group?.capacity ? String(group.capacity) : '')
  const [tutor, setTutor] = useState(group?.tutor_id ?? '')
  const busy = create.isPending || update.isPending
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (startsAt && endsAt && endsAt <= startsAt) return toast.error('The end time must be after the start time.')
    const body: GroupBody = {
      name: name.trim(),
      weekday: weekday === '' ? null : Number(weekday),
      starts_at: startsAt || null,
      ends_at: endsAt || null,
      capacity: capacity ? Number(capacity) : null,
      tutor_id: tutor || null,
    }
    const done = {
      onSuccess: () => (toast.success(group ? 'Group saved' : 'Group added'), onOpenChange(false)),
      onError: err,
    }
    if (group) update.mutate({ id: group.id, body }, done)
    else create.mutate(body, done)
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={group ? 'Group details' : 'New group'} description="Every group studies the same modules, with its own tutor and weekly session.">
        <form className="grid gap-4" onSubmit={submit}>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Name">{(p) => <Input {...p} value={name} onChange={(e) => setName(e.target.value)} placeholder="Group A" maxLength={80} required />}</Field>
            <Field label="Places (optional)">{(p) => <Input {...p} type="number" min={1} inputMode="numeric" value={capacity} onChange={(e) => setCapacity(e.target.value)} />}</Field>
          </div>
          <Field label="Tutor" hint={tutors.data && !tutors.data.length ? 'Give a staff member the Tutor role first.' : undefined}>
            {(p) => (
              <NativeSelect {...p} value={tutor} onChange={(e) => setTutor(e.target.value)}>
                <option value="">No tutor yet</option>
                {tutors.data?.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Session day">
              {(p) => (
                <NativeSelect {...p} value={weekday} onChange={(e) => setWeekday(e.target.value)}>
                  <option value="">Not set</option>
                  {WEEKDAYS.map((d, i) => (
                    <option key={d} value={i}>
                      {d}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
            <Field label="From">{(p) => <Input {...p} type="time" value={startsAt} onChange={(e) => setStartsAt(e.target.value)} />}</Field>
            <Field label="To">{(p) => <Input {...p} type="time" value={endsAt} onChange={(e) => setEndsAt(e.target.value)} />}</Field>
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={busy}>
              {group ? 'Save' : 'Add group'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function AddMembers({ cohortId, groupId }: { cohortId: string; groupId: string }) {
  const add = useAddMembers(cohortId, groupId)
  const [text, setText] = useState('')
  const emails = text.split(/[\s,;]+/).map((e) => e.trim()).filter(Boolean)
  const submit = (e: FormEvent) => {
    e.preventDefault()
    add.mutate(emails, {
      onSuccess: (r) => {
        if (r.added) toast.success(`${r.added} ${r.added === 1 ? 'learner' : 'learners'} added`)
        if (r.not_found.length) toast.error(`No account for: ${r.not_found.join(', ')}`)
        if (!r.added && !r.not_found.length) toast.info('Everyone is already in this group.')
        setText(r.not_found.join('\n'))
      },
      onError: err,
    })
  }
  return (
    <form className="grid gap-2" onSubmit={submit}>
      <Field label="Add learners by email" hint="One or more emails. People need an account first.">
        {(p) => <Textarea {...p} rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="sara@example.com" />}
      </Field>
      <div className="flex justify-end">
        <Button type="submit" size="sm" loading={add.isPending} disabled={!emails.length || emails.length > 200}>
          <UserPlus /> Add {emails.length > 1 ? `${emails.length} learners` : 'learner'}
        </Button>
      </div>
    </form>
  )
}

function GroupSheet({ cohort, group, onOpenChange }: { cohort: CohortDetail; group: CohortGroup | null; onOpenChange: (o: boolean) => void }) {
  // learners' names and emails: only for people who manage cohorts (the API says the same)
  const members = useGroupMembers(cohort.can_manage ? group?.id : undefined)
  const remove = useRemoveMember(cohort.id, group?.id ?? '')
  const del = useDeleteGroup(cohort.id)
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [removing, setRemoving] = useState<{ id: string; name: string } | null>(null)
  const [record, setRecord] = useState<string | null>(null)
  const rows = members.data?.pages.flatMap((p) => p.items) ?? []
  return (
    <DetailSheet open={!!group} onOpenChange={onOpenChange} title={group?.name ?? 'Group'} description={group ? timetable(group) : undefined}>
      {group ? (
        <div className="grid gap-5">
          <div>
            <InfoRow label="Tutor">{group.tutor_name ?? 'No tutor yet'}</InfoRow>
            <InfoRow label="Learners">
              {group.learner_count}
              {group.capacity ? ` of ${group.capacity}` : ''}
            </InfoRow>
            <InfoRow label="Status">
              <StatusPill status={group.status} />
            </InfoRow>
          </div>
          {cohort.can_manage ? (
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>
                <Pencil /> Edit group
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setDeleting(true)} disabled={group.learner_count > 0} title={group.learner_count ? 'Move the learners to another group first' : undefined}>
                <Trash2 /> Delete group
              </Button>
            </div>
          ) : null}
          {cohort.can_manage && group.status === 'active' ? <AddMembers cohortId={cohort.id} groupId={group.id} /> : null}
          {cohort.can_manage ? (
            <section aria-label="Learners in this group">
              <h3 className="mb-2 text-sm font-semibold">Learners</h3>
              {members.error ? (
                <ErrorState message={(members.error as Error).message} onRetry={() => void members.refetch()} />
              ) : !members.data ? (
                <div className="grid gap-2">
                  <Skeleton className="h-12" />
                  <Skeleton className="h-12" />
                </div>
              ) : !rows.length ? (
                <EmptyState icon={<Users />} title="No learners yet" body="Add people by email above." />
              ) : (
                <Card className="overflow-hidden">
                  <ul className="stagger divide-y divide-border">
                    {rows.map((m) => (
                      <li key={m.enrollment_id} className="flex items-center gap-3 px-4 py-3">
                        <div className="min-w-0 flex-1">
                          <button type="button" className="block max-w-full truncate text-left text-sm font-medium hover:text-primary hover:underline" onClick={() => setRecord(m.enrollment_id)} aria-label={`Open the record of ${m.name || m.email}`}>
                            {m.name || m.email}
                          </button>
                          <p className="truncate text-xs text-muted">{m.email}</p>
                        </div>
                        <div className="hidden w-24 sm:block">
                          <Progress value={m.progress_pct} label={`${Math.round(m.progress_pct)}% complete`} />
                        </div>
                        {cohort.can_manage ? (
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-label={`Remove ${m.name || m.email} from the group`}
                            onClick={() =>
                              setRemoving({
                                id: m.enrollment_id,
                                name: m.name || m.email,
                              })
                            }
                          >
                            <UserMinus />
                          </Button>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                  <LoadMore shown={rows.length} noun="learners" hasMore={!!members.hasNextPage} loading={members.isFetchingNextPage} onMore={() => void members.fetchNextPage()} />
                </Card>
              )}
            </section>
          ) : null}
          {cohort.can_manage ? <GroupSessions groupId={group.id} /> : null}
          <LearnerRecordSheet enrollmentId={record} onOpenChange={(o) => !o && setRecord(null)} />
          <GroupDialog key={`${group.id}-${editing}`} cohortId={cohort.id} group={group} open={editing} onOpenChange={setEditing} />
          <ConfirmDialog
            open={deleting}
            onOpenChange={setDeleting}
            title={`Delete ${group.name}?`}
            confirmLabel="Delete group"
            loading={del.isPending}
            onConfirm={() =>
              del.mutate(group.id, {
                onSuccess: () => (toast.success('Group deleted'), setDeleting(false), onOpenChange(false)),
                onError: err,
              })
            }
          />
          <ConfirmDialog
            open={!!removing}
            onOpenChange={(o) => !o && setRemoving(null)}
            title={`Remove ${removing?.name ?? ''} from ${group.name}?`}
            body="They keep their access and progress, but leave this group's timetable."
            confirmLabel="Remove from group"
            loading={remove.isPending}
            onConfirm={() =>
              removing &&
              remove.mutate(removing.id, {
                onSuccess: () => (toast.success('Removed from the group'), setRemoving(null)),
                onError: err,
              })
            }
          />
        </div>
      ) : null}
    </DetailSheet>
  )
}

function Groups({ cohort }: { cohort: CohortDetail }) {
  const [adding, setAdding] = useState(false)
  const [openId, setOpenId] = useState<string | null>(null)
  const open = cohort.groups.find((g) => g.id === openId) ?? null
  return (
    <div className="grid gap-4">
      {cohort.can_manage ? (
        <div className="flex justify-end">
          <Button onClick={() => setAdding(true)}>
            <Plus /> Add group
          </Button>
        </div>
      ) : null}
      {!cohort.groups.length ? (
        <EmptyState icon={<UsersRound />} title="No groups yet" body="Split the cohort into groups, each with a tutor and a weekly session." />
      ) : (
        <ul className="stagger grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {cohort.groups.map((g) => (
            <li key={g.id}>
              <button
                type="button"
                onClick={() => setOpenId(g.id)}
                className="block h-full w-full rounded-lg border border-border bg-surface p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none motion-reduce:transition-none motion-reduce:hover:translate-y-0"
              >
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-semibold">{g.name}</h3>
                  {g.status !== 'active' ? <StatusPill status={g.status} /> : null}
                </div>
                <p className="mt-1 text-sm text-muted">{timetable(g)}</p>
                <p className="mt-0.5 text-sm text-muted">{g.tutor_name ? `Tutor: ${g.tutor_name}` : 'No tutor yet'}</p>
                <div className="mt-4 flex items-center justify-between text-xs text-muted tabular">
                  <span>
                    {g.learner_count} {g.learner_count === 1 ? 'learner' : 'learners'}
                  </span>
                  {g.capacity ? <span>{g.capacity} places</span> : null}
                </div>
                {g.capacity ? <Progress className="mt-1.5" value={(g.learner_count / g.capacity) * 100} tone={g.learner_count >= g.capacity ? 'warning' : 'primary'} label={`${g.learner_count} of ${g.capacity} places taken`} /> : null}
              </button>
            </li>
          ))}
        </ul>
      )}
      <GroupDialog key={`new-${adding}`} cohortId={cohort.id} open={adding} onOpenChange={setAdding} />
      <GroupSheet cohort={cohort} group={open} onOpenChange={(o) => !o && setOpenId(null)} />
    </div>
  )
}

// ---------------------------------------------------------------- closures
function Closures({ cohort }: { cohort: CohortDetail }) {
  const [adding, setAdding] = useState(false)
  const { remove } = useClosureActions()
  const [removing, setRemoving] = useState<string | null>(null)
  const own = cohort.closures.filter((c) => !c.provider_wide)
  const shared = cohort.closures.filter((c) => c.provider_wide)
  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader
          title="This cohort's closures"
          description="Weeks with no teaching day are skipped and later weeks move on."
          action={
            cohort.can_manage ? (
              <Button size="sm" onClick={() => setAdding(true)}>
                <Plus /> Add closure
              </Button>
            ) : null
          }
        />
        <div className="mt-3 border-t border-border">
          {own.length ? <ClosureRows rows={own} onRemove={setRemoving} canManage={cohort.can_manage} /> : <EmptyState icon={<CalendarOff />} title="No closures for this cohort" />}
        </div>
      </Card>
      {shared.length ? (
        <Card>
          <CardHeader
            title="Closures for every cohort"
            action={
              <Button variant="ghost" size="sm" asChild>
                <Link to="/console/programs">Manage</Link>
              </Button>
            }
          />
          <div className="mt-3 border-t border-border">
            <ClosureRows rows={shared} onRemove={() => undefined} canManage={false} />
          </div>
        </Card>
      ) : null}
      <ClosureDialog open={adding} onOpenChange={setAdding} cohortId={cohort.id} />
      <ConfirmDialog
        open={!!removing}
        onOpenChange={(o) => !o && setRemoving(null)}
        title="Remove this closure?"
        body="The week dates will be worked out again."
        confirmLabel="Remove closure"
        loading={remove.isPending}
        onConfirm={() =>
          removing &&
          remove.mutate(removing, {
            onSuccess: () => (toast.success('Closure removed'), setRemoving(null)),
            onError: err,
          })
        }
      />
    </div>
  )
}

// ---------------------------------------------------------------- page
export function ConsoleCohortPage() {
  const { cohortId } = useParams()
  const q = useCohort(cohortId)
  const [tab, setTab] = useTabParam(TABS, 'schedule')
  const [editing, setEditing] = useState(false)
  if (q.error) return <ErrorState message={(q.error as Error).message} onRetry={() => void q.refetch()} />
  if (!q.data)
    return (
      <div className="grid gap-4" aria-busy="true">
        <Skeleton className="h-16" />
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-[118px]" />
          ))}
        </div>
        <Skeleton className="h-72" />
      </div>
    )
  const c = q.data
  const weeks = c.modules.reduce((n, m) => n + m.weeks.length, 0)
  const closed = c.status === 'finished' || c.status === 'cancelled'
  return (
    <div className="grid gap-6 animate-reveal">
      <PageHeader
        back={
          <Link to={`/console/programs/${c.program_id}`} className="inline-flex items-center gap-1 text-sm text-muted hover:text-text">
            <ArrowLeft className="size-4" aria-hidden /> {c.program_title}
          </Link>
        }
        title={
          <span className="inline-flex flex-wrap items-center gap-3">
            {c.name} <StatusPill status={statusTone(c.status)} label={COHORT_STATUS[c.status]} />
          </span>
        }
        description={`${dayRange(c.start_date, c.end_date)} · ${CALENDARS[c.calendar] ?? c.calendar} bank holidays`}
        actions={
          c.can_manage && !closed ? (
            <>
              <Button variant="secondary" onClick={() => setEditing(true)}>
                <Pencil /> Edit
              </Button>
              <StatusMenu cohort={c} />
            </>
          ) : null
        }
      />
      <div className="stagger grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Learners" value={<CountUp value={c.learner_count} />} icon={<Users />} hint={c.capacity ? `of ${c.capacity} places` : undefined} />
        <StatCard label="Groups" value={<CountUp value={c.groups.length} />} icon={<UsersRound />} tone="info" />
        <StatCard label="Teaching weeks" value={<CountUp value={weeks} />} icon={<CalendarDays />} tone="success" />
        <StatCard label="Breaks" value={<CountUp value={c.breaks.length} />} icon={<CalendarOff />} tone="warning" />
      </div>
      <Tabs value={tab} onValueChange={(v) => setTab(v as (typeof TABS)[number])}>
        <TabsList>
          <TabsTrigger value="schedule">Schedule</TabsTrigger>
          <TabsTrigger value="groups">Groups</TabsTrigger>
          <TabsTrigger value="closures">Closures</TabsTrigger>
        </TabsList>
        <TabsContent value="schedule">
          <Schedule cohort={c} />
        </TabsContent>
        <TabsContent value="groups">
          <Groups cohort={c} />
        </TabsContent>
        <TabsContent value="closures">
          <Closures cohort={c} />
        </TabsContent>
      </Tabs>
      {c.can_manage ? <EditCohort key={`${c.id}-${editing}`} cohort={c} open={editing} onOpenChange={setEditing} /> : null}
    </div>
  )
}
