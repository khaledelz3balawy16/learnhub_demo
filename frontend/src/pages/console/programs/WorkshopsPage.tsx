import { CalendarPlus, CalendarX, Clock, Link2, MoreHorizontal, Pencil, Plus, Presentation, Upload, Users } from 'lucide-react'
import { type FormEvent, useEffect, useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Field, Input, NativeSelect, Textarea } from '@/components/ui/input'
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from '@/components/ui/menu'
import { EmptyState, ErrorState, PageHeader } from '@/components/ui/misc'
import { Skeleton } from '@/components/ui/skeleton'
import { LoadMore } from '@/features/console/ui'
import { type WorkshopRow, useMeetingNow, usePrograms, useProgram, useSaveWorkshop, useWorkshops } from '@/features/programs/api'
import { hours } from '@/features/programs/record'
import { fromLocalInput, sessionWhen, toLocalInput } from '@/lib/schedule'

import { AttendanceDialog, RecordingBadge, useRecordingUpload } from './LiveSessions'

const err = (e: unknown) => toast.error((e as Error).message)
const minutes = (v: string) => Number(v.replace(/\D/g, '') || 0)

function WorkshopDialog({ workshop, onOpenChange }: { workshop: WorkshopRow | 'new'; onOpenChange: (o: boolean) => void }) {
  const isNew = workshop === 'new'
  const w = isNew ? null : workshop
  const programs = usePrograms('')
  const save = useSaveWorkshop()
  const [programId, setProgramId] = useState(w?.program_id ?? '')
  const program = useProgram(programId || undefined)
  const [f, setF] = useState({
    title: w?.title ?? '',
    description: w?.description ?? '',
    start: w ? toLocalInput(w.starts_at) : '',
    length: String(w?.duration_min ?? 60),
    capacity: w?.capacity ? String(w.capacity) : '',
    otj: String(w?.expected_otj_min ?? 0),
    cpd: String(w?.cpd_min ?? 0),
    link: w?.join_url ?? '',
    cohort: w?.cohort_id ?? '',
  })
  const set = (patch: Partial<typeof f>) => setF((s) => ({ ...s, ...patch }))
  const options = programs.data?.pages.flatMap((p) => p.items) ?? []
  // every program can be chosen, not just the first page
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = programs
  useEffect(() => {
    if (hasNextPage && !isFetchingNextPage) void fetchNextPage()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const body = {
      title: f.title.trim(),
      description: f.description.trim(),
      starts_at: fromLocalInput(f.start),
      duration_min: minutes(f.length),
      capacity: f.capacity ? minutes(f.capacity) : null,
      expected_otj_min: minutes(f.otj),
      cpd_min: minutes(f.cpd),
      join_url: f.link.trim(),
      cohort_id: f.cohort || null,
    }
    const done = {
      onSuccess: () => (toast.success(isNew ? 'Workshop added' : 'Workshop saved'), onOpenChange(false)),
      onError: err,
    }
    if (w) save.mutate({ id: w.id, body }, done)
    else save.mutate({ id: null, body: { ...body, program_id: programId } }, done)
  }
  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent title={isNew ? 'New workshop' : 'Edit workshop'} description="An optional live event. Learners book a place, and attending adds off-the-job hours and CPD." className="max-w-xl">
        <form className="grid gap-4" onSubmit={submit}>
          {isNew ? (
            <Field label="Program">
              {(p) => (
                <NativeSelect {...p} value={programId} onChange={(e) => (setProgramId(e.target.value), set({ cohort: '' }))} required>
                  <option value="">Choose a program</option>
                  {options.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.title}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
          ) : null}
          <Field label="Who can book" hint="One cohort, or every learner on the program.">
            {(p) => (
              <NativeSelect {...p} value={f.cohort} onChange={(e) => set({ cohort: e.target.value })} disabled={!programId}>
                <option value="">Everyone on the program</option>
                {(program.data?.cohorts ?? []).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Title">{(p) => <Input {...p} value={f.title} onChange={(e) => set({ title: e.target.value })} minLength={3} maxLength={200} required />}</Field>
          <Field label="What it covers">{(p) => <Textarea {...p} rows={3} value={f.description} onChange={(e) => set({ description: e.target.value })} maxLength={4000} />}</Field>
          <div className="grid gap-3 sm:grid-cols-[1fr_7rem_7rem]">
            <Field label="Starts" hint="In your time zone.">
              {(p) => <Input {...p} type="datetime-local" value={f.start} onChange={(e) => set({ start: e.target.value })} required />}
            </Field>
            <Field label="Minutes">{(p) => <Input {...p} type="number" min={5} max={720} value={f.length} onChange={(e) => set({ length: e.target.value })} required />}</Field>
            <Field label="Places" hint="Empty: no limit.">
              {(p) => <Input {...p} type="number" min={1} max={10000} value={f.capacity} onChange={(e) => set({ capacity: e.target.value })} />}
            </Field>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Off-the-job minutes" hint="Counted when someone attends.">
              {(p) => <Input {...p} type="number" min={0} max={1440} value={f.otj} onChange={(e) => set({ otj: e.target.value })} />}
            </Field>
            <Field label="CPD minutes">{(p) => <Input {...p} type="number" min={0} max={6000} value={f.cpd} onChange={(e) => set({ cpd: e.target.value })} />}</Field>
          </div>
          <Field label="Meeting link" hint="Leave empty to have a Teams meeting created, when Teams is connected.">
            {(p) => <Input {...p} type="url" inputMode="url" placeholder="https://" value={f.link} onChange={(e) => set({ link: e.target.value })} />}
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={save.isPending}>
              {isNew ? 'Add workshop' : 'Save'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function WorkshopCard({
  w,
  canManage,
  teams,
  onEdit,
  onAttendance,
  onUpload,
}: {
  w: WorkshopRow
  canManage: boolean
  teams: boolean
  onEdit: () => void
  onAttendance: () => void
  onUpload: () => void
}) {
  const save = useSaveWorkshop()
  const meeting = useMeetingNow('workshop')
  const cancelled = w.status === 'cancelled'
  const started = new Date(w.starts_at) <= new Date()
  return (
    <Card className={`flex flex-wrap items-start gap-4 p-4 ${cancelled ? 'opacity-70' : ''}`}>
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium text-muted">
          {w.program_title} · {w.cohort_name ?? 'every cohort'}
        </p>
        <h2 className="mt-0.5 font-semibold">{w.title}</h2>
        <p className="text-sm text-muted tabular">{sessionWhen(w.starts_at, w.ends_at)}</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {cancelled ? <Badge tone="danger">Cancelled</Badge> : null}
          <Badge tone="primary">
            <Users className="size-3" aria-hidden /> {w.booked}
            {w.capacity ? ` of ${w.capacity}` : ''} booked
          </Badge>
          {w.expected_otj_min ? (
            <Badge tone="outline">
              <Clock className="size-3" aria-hidden /> {hours(w.expected_otj_min)} OTJ
            </Badge>
          ) : null}
          {w.cpd_min ? <Badge tone="outline">{hours(w.cpd_min)} CPD</Badge> : null}
          {!cancelled && !w.join_url ? <Badge tone="warning">No link yet</Badge> : null}
          <RecordingBadge state={w.recording_state} />
        </div>
      </div>
      {canManage ? (
      <Menu>
        <MenuTrigger asChild>
          <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${w.title}`}>
            <MoreHorizontal />
          </Button>
        </MenuTrigger>
        <MenuContent>
          {canManage ? (
            <MenuItem onSelect={onEdit} disabled={cancelled}>
              <Pencil /> Edit
            </MenuItem>
          ) : null}
          {teams && !w.join_url && !cancelled ? (
            <MenuItem
              onSelect={() =>
                meeting.mutate(w.id, {
                  onSuccess: () => toast.success('Teams meeting created'),
                  onError: err,
                })
              }
            >
              <CalendarPlus /> Create Teams meeting
            </MenuItem>
          ) : null}
          <MenuItem onSelect={onAttendance} disabled={!started || cancelled}>
            <Users /> Attendance
          </MenuItem>
          <MenuItem onSelect={onUpload} disabled={!started || cancelled}>
            <Upload /> Upload recording
          </MenuItem>
          {canManage && !cancelled && !started ? (
            <>
              <MenuSeparator />
              <MenuItem
                onSelect={() =>
                  save.mutate(
                    { id: w.id, body: { status: 'cancelled' } },
                    {
                      onSuccess: () => toast.success('Workshop cancelled'),
                      onError: err,
                    },
                  )
                }
              >
                <CalendarX /> Cancel workshop
              </MenuItem>
            </>
          ) : null}
        </MenuContent>
      </Menu>
      ) : null}
      {w.join_url && !cancelled ? (
        <a href={w.join_url} target="_blank" rel="noreferrer" className="inline-flex w-full items-center gap-1 text-xs text-primary hover:underline">
          <Link2 className="size-3.5" aria-hidden /> Meeting link
        </a>
      ) : null}
    </Card>
  )
}

/** Workshops (M20, plan D24): optional live events with booking, attendance, OTJ and CPD. */
export function ConsoleWorkshopsPage() {
  const q = useWorkshops()
  const upload = useRecordingUpload('workshop')
  const [editing, setEditing] = useState<WorkshopRow | 'new' | null>(null)
  const [attendance, setAttendance] = useState<{
    id: string
    title: string
  } | null>(null)
  const first = q.data?.pages[0]
  const rows = q.data?.pages.flatMap((p) => p.items)
  return (
    <div className="grid gap-6">
      <PageHeader
        title="Workshops"
        description={
          first && !first.teams_connected
            ? 'Optional live events. Teams is not connected, so add a meeting link to each one.'
            : 'Optional live events learners book. Attending adds off-the-job hours and CPD.'
        }
        actions={
          first?.can_manage ? (
            <Button onClick={() => setEditing('new')}>
              <Plus /> New workshop
            </Button>
          ) : null
        }
      />
      {upload.element}
      {q.error ? (
        <ErrorState message={(q.error as Error).message} onRetry={() => void q.refetch()} />
      ) : !rows ? (
        <div className="grid gap-3" aria-busy="true">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : !rows.length ? (
        <EmptyState icon={<Presentation />} title="No workshops yet" body={first?.can_manage ? 'Add one for a program, or for one cohort.' : 'Cohort managers add workshops.'} />
      ) : (
        <ul className="stagger grid gap-3 animate-reveal">
          {rows.map((w) => (
            <li key={w.id}>
              <WorkshopCard
                w={w}
                canManage={!!first?.can_manage}
                teams={!!first?.teams_connected}
                onEdit={() => setEditing(w)}
                onAttendance={() => setAttendance({ id: w.id, title: w.title })}
                onUpload={() => upload.pick(w.id)}
              />
            </li>
          ))}
        </ul>
      )}
      {rows?.length ? <LoadMore shown={rows.length} noun="workshops" hasMore={!!q.hasNextPage} loading={q.isFetchingNextPage} onMore={() => void q.fetchNextPage()} /> : null}
      {editing ? <WorkshopDialog key={editing === 'new' ? 'new' : editing.id} workshop={editing} onOpenChange={(o) => !o && setEditing(null)} /> : null}
      <AttendanceDialog kind="workshop" target={attendance} onOpenChange={(o) => !o && setAttendance(null)} />
    </div>
  )
}
