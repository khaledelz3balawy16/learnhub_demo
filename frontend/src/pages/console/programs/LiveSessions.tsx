import { useQueryClient } from '@tanstack/react-query'
import { CalendarClock, CalendarPlus, CalendarX, Link2, MoreHorizontal, RefreshCw, Undo2, Upload, Users, Video } from 'lucide-react'
import { type FormEvent, useRef, useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Field, Input } from '@/components/ui/input'
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from '@/components/ui/menu'
import { EmptyState, ErrorState } from '@/components/ui/misc'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import {
  type AttendanceRow,
  type LiveKind,
  type LiveSessionRow,
  type SessionPatch,
  startRecordingUpload,
  useGroupSessions,
  useLiveAttendance,
  useMarkAttendance,
  useMeetingNow,
  usePlanSessions,
  useSyncAttendance,
  useUpdateSession,
} from '@/features/programs/api'
import { fromLocalInput, sessionWhen, toLocalInput } from '@/lib/schedule'
import { tusUpload, videoFileError } from '@/pages/studio/builder/curriculum/shared'

// Live teaching in the console (M20): a group's sessions, attendance and recordings.
// Shared by the cohort page (managers), the Teaching page (tutors) and Workshops.

const err = (e: unknown) => toast.error((e as Error).message)
/** Draft marker for "present for the whole event": sent as null, so the server applies the full length
 * (and, for a workshop, its expected off-the-job minutes). */
const PRESENT = 'present'

const RECORDING: Record<string, { label: string; tone: 'success' | 'warning' | 'danger' | 'info' } | undefined> = {
  pending: { label: 'Copying from Teams', tone: 'info' },
  processing: { label: 'Recording processing', tone: 'info' },
  ready: { label: 'Recording ready', tone: 'success' },
  failed: { label: "Recording couldn't be copied", tone: 'danger' },
}

export function RecordingBadge({ state }: { state: string }) {
  const r = RECORDING[state]
  return r ? (
    <Badge tone={r.tone}>
      <Video className="size-3" aria-hidden /> {r.label}
    </Badge>
  ) : null
}

/** Upload a recording straight to the video service (the manual fallback when Teams isn't connected). */
export function useRecordingUpload(kind: LiveKind) {
  const qc = useQueryClient()
  const [progress, setProgress] = useState<number | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const target = useRef<string | null>(null)
  const pick = (id: string) => {
    target.current = id
    input.current?.click()
  }
  const onFile = async (file?: File) => {
    const id = target.current
    if (!file || !id) return
    const problem = videoFileError(file)
    if (problem) return void toast.error(problem)
    setProgress(0)
    try {
      const ticket = await startRecordingUpload(kind, id, file)
      await tusUpload(ticket.upload, file, setProgress)
      toast.success('Recording uploaded. It plays once the video service has processed it.')
      await qc.invalidateQueries({ queryKey: ['console', 'programs'] })
    } catch (e) {
      err(e)
    } finally {
      setProgress(null)
      if (input.current) input.current.value = ''
    }
  }
  const element = (
    <>
      <input ref={input} type="file" accept="video/*" className="sr-only" tabIndex={-1} aria-hidden onChange={(e) => void onFile(e.target.files?.[0])} />
      {progress !== null ? (
        <div className="grid gap-1" role="status" aria-live="polite">
          <p className="text-xs text-muted">Uploading the recording… {progress}%</p>
          <Progress value={progress} label="Upload progress" />
        </div>
      ) : null}
    </>
  )
  return { pick, busy: progress !== null, element }
}

// ---------------------------------------------------------------- attendance
function AttendanceForm({
  kind,
  id,
  rows,
  duration,
  presentMin,
  hasMeeting,
  onDone,
}: {
  kind: LiveKind
  id: string
  rows: AttendanceRow[]
  duration: number
  presentMin: number
  hasMeeting: boolean
  onDone: () => void
}) {
  const mark = useMarkAttendance(kind, id)
  const sync = useSyncAttendance(kind, id)
  const [draft, setDraft] = useState<Record<string, string>>(() => Object.fromEntries(rows.map((r) => [r.enrollment_id, r.minutes == null ? '' : String(r.minutes)])))
  const set = (eid: string, v: string) => setDraft((d) => ({ ...d, [eid]: v === PRESENT ? v : v.replace(/\D/g, '').slice(0, 4) }))
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const marks = rows
      .filter((r) => draft[r.enrollment_id] !== '')
      .map((r) => ({
        enrollment_id: r.enrollment_id,
        minutes: draft[r.enrollment_id] === PRESENT ? null : Math.min(Number(draft[r.enrollment_id]), duration),
      }))
    if (!marks.length) return void toast.error('Mark at least one person.')
    mark.mutate(marks, {
      onSuccess: () => (toast.success('Attendance saved'), onDone()),
      onError: err,
    })
  }
  if (!rows.length) return <EmptyState icon={<Users />} title="Nobody to mark" body={kind === 'session' ? 'This group has no learners yet.' : 'Nobody has booked this workshop.'} />
  return (
    <form className="grid gap-4" onSubmit={submit}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted">
          Minutes each person attended, up to {duration}. {presentMin} or more counts as present and adds off-the-job hours.
        </p>
        <div className="flex gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={() => setDraft(Object.fromEntries(rows.map((r) => [r.enrollment_id, PRESENT])))}>
            Everyone present
          </Button>
          {hasMeeting ? (
            <Button
              type="button"
              variant="secondary"
              size="sm"
              loading={sync.isPending}
              onClick={() =>
                sync.mutate(undefined, {
                  onSuccess: (r) => (toast.success(`${r.written} marked from Teams`), onDone()),
                  onError: err,
                })
              }
            >
              <RefreshCw /> Fetch from Teams
            </Button>
          ) : null}
        </div>
      </div>
      <Card className="overflow-hidden">
        <ul className="divide-y divide-border">
          {rows.map((r) => {
            const v = draft[r.enrollment_id] ?? ''
            const label = r.name || r.email
            return (
              <li key={r.enrollment_id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{label}</p>
                  <p className="truncate text-xs text-muted">
                    {r.email}
                    {r.source === 'graph' ? ' · from Teams' : r.source === 'manual' ? ' · marked by staff' : ''}
                  </p>
                </div>
                <div className="flex items-center gap-1.5" role="group" aria-label={`Attendance for ${label}`}>
                  <Button type="button" size="sm" variant={v === PRESENT ? 'primary' : 'ghost'} aria-pressed={v === PRESENT} onClick={() => set(r.enrollment_id, PRESENT)}>
                    Present
                  </Button>
                  <Button type="button" size="sm" variant={v === '0' ? 'danger' : 'ghost'} aria-pressed={v === '0'} onClick={() => set(r.enrollment_id, '0')}>
                    Absent
                  </Button>
                  <Input className="w-20" inputMode="numeric" aria-label={`Minutes ${label} attended`} placeholder={v === PRESENT ? 'all' : 'min'} value={v === PRESENT ? '' : v} onChange={(e) => set(r.enrollment_id, e.target.value)} />
                </div>
              </li>
            )
          })}
        </ul>
      </Card>
      <div className="flex justify-end">
        <Button type="submit" loading={mark.isPending}>
          Save attendance
        </Button>
      </div>
    </form>
  )
}

export function AttendanceDialog({ kind, target, onOpenChange }: { kind: LiveKind; target: { id: string; title: string } | null; onOpenChange: (o: boolean) => void }) {
  const q = useLiveAttendance(kind, target?.id)
  const d = q.data
  return (
    <Dialog open={!!target} onOpenChange={onOpenChange}>
      <DialogContent title="Attendance" description={target?.title} className="max-w-2xl">
        {q.error ? (
          <ErrorState message={(q.error as Error).message} onRetry={() => void q.refetch()} />
        ) : !d || !target ? (
          <div className="grid gap-2" aria-busy="true">
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
          </div>
        ) : !d.started ? (
          <EmptyState icon={<CalendarClock />} title="Not started yet" body="Attendance can be marked once it has started." />
        ) : (
          <div className="animate-reveal">
            <AttendanceForm
              key={q.dataUpdatedAt}
              kind={kind}
              id={target.id}
              rows={d.items}
              duration={d.duration_min}
              presentMin={d.present_min}
              hasMeeting={d.has_meeting}
              onDone={() => onOpenChange(false)}
            />
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------- one session
function SessionDialog({ groupId, session, canPlan, onOpenChange }: { groupId: string; session: LiveSessionRow | null; canPlan: boolean; onOpenChange: (o: boolean) => void }) {
  const update = useUpdateSession(groupId)
  const [link, setLink] = useState(session?.join_url ?? '')
  const [start, setStart] = useState(session ? toLocalInput(session.starts_at) : '')
  const [length, setLength] = useState(String(session?.duration_min ?? 60))
  if (!session) return null
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const body: SessionPatch = {}
    if (link.trim() !== session.join_url) body.join_url = link.trim()
    if (canPlan && start && fromLocalInput(start) !== new Date(session.starts_at).toISOString()) body.starts_at = fromLocalInput(start)
    if (canPlan && Number(length) !== session.duration_min) body.duration_min = Number(length)
    if (!Object.keys(body).length) return onOpenChange(false)
    update.mutate(
      { id: session.id, body },
      {
        onSuccess: () => (toast.success('Session saved'), onOpenChange(false)),
        onError: err,
      },
    )
  }
  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent title="Edit session" description={session.title}>
        <form className="grid gap-4" onSubmit={submit}>
          <Field label="Meeting link" hint="Learners see it from shortly before the start until the end.">
            {(p) => <Input {...p} type="url" inputMode="url" placeholder="https://" value={link} onChange={(e) => setLink(e.target.value)} />}
          </Field>
          {canPlan ? (
            <div className="grid gap-3 sm:grid-cols-[1fr_8rem]">
              <Field label="Starts" hint="In your time zone.">
                {(p) => <Input {...p} type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} required />}
              </Field>
              <Field label="Minutes">{(p) => <Input {...p} type="number" min={5} max={720} value={length} onChange={(e) => setLength(e.target.value)} required />}</Field>
            </div>
          ) : null}
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

function SessionItem({
  s,
  groupId,
  canPlan,
  teams,
  onEdit,
  onAttendance,
  onUpload,
}: {
  s: LiveSessionRow
  groupId: string
  canPlan: boolean
  teams: boolean
  onEdit: () => void
  onAttendance: () => void
  onUpload: () => void
}) {
  const update = useUpdateSession(groupId)
  const meeting = useMeetingNow('session')
  const cancelled = s.status === 'cancelled'
  const started = new Date(s.starts_at) <= new Date()
  return (
    <li className="flex flex-wrap items-start gap-3 px-4 py-3">
      <div className={`min-w-0 flex-1 ${cancelled ? 'opacity-60' : ''}`}>
        <p className="text-sm font-medium">{s.title}</p>
        <p className="text-xs text-muted tabular">{sessionWhen(s.starts_at, s.ends_at)}</p>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {cancelled ? <Badge tone="danger">Cancelled</Badge> : null}
          {!cancelled && !s.join_url ? <Badge tone="warning">No link yet</Badge> : null}
          {s.join_url ? (
            <Badge tone="outline">
              <Link2 className="size-3" aria-hidden /> {s.provider === 'teams' ? 'Teams meeting' : 'Link added'}
            </Badge>
          ) : null}
          {s.marked ? (
            <Badge tone="primary">
              {s.present} of {s.marked} present
            </Badge>
          ) : null}
          <RecordingBadge state={s.recording_state} />
        </div>
      </div>
      <Menu>
        <MenuTrigger asChild>
          <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${s.title}`}>
            <MoreHorizontal />
          </Button>
        </MenuTrigger>
        <MenuContent>
          <MenuItem onSelect={onEdit} disabled={cancelled}>
            <Link2 /> {canPlan ? 'Edit time or link' : 'Edit link'}
          </MenuItem>
          {teams && !s.join_url && !cancelled ? (
            <MenuItem
              onSelect={() =>
                meeting.mutate(s.id, {
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
          {canPlan ? (
            <>
              <MenuSeparator />
              {cancelled ? (
                <MenuItem
                  onSelect={() =>
                    update.mutate(
                      { id: s.id, body: { status: 'scheduled' } },
                      {
                        onSuccess: () => toast.success('Session restored'),
                        onError: err,
                      },
                    )
                  }
                >
                  <Undo2 /> Restore session
                </MenuItem>
              ) : (
                <MenuItem
                  disabled={started}
                  onSelect={() =>
                    update.mutate(
                      { id: s.id, body: { status: 'cancelled' } },
                      {
                        onSuccess: () => toast.success('Session cancelled'),
                        onError: err,
                      },
                    )
                  }
                >
                  <CalendarX /> Cancel session
                </MenuItem>
              )}
            </>
          ) : null}
        </MenuContent>
      </Menu>
    </li>
  )
}

/** A group's sessions: plan them from the timetable, then run each one. */
export function GroupSessions({ groupId }: { groupId: string }) {
  const q = useGroupSessions(groupId)
  const plan = usePlanSessions(groupId)
  const upload = useRecordingUpload('session')
  const [editing, setEditing] = useState<LiveSessionRow | null>(null)
  const [attendance, setAttendance] = useState<{
    id: string
    title: string
  } | null>(null)
  const d = q.data
  const runPlan = () =>
    plan.mutate(undefined, {
      onSuccess: (r) => {
        const parts = [r.created && `${r.created} added`, r.moved && `${r.moved} moved`, r.cancelled && `${r.cancelled} cancelled`].filter(Boolean)
        toast.success(parts.length ? `Sessions planned: ${parts.join(', ')}` : 'Sessions are up to date')
        if (r.skipped.length) toast.warning(`No teaching day for: ${r.skipped.join(', ')}`)
      },
      onError: err,
    })
  return (
    <section aria-labelledby={`sessions-${groupId}`} className="grid gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 id={`sessions-${groupId}`} className="text-sm font-semibold">
            Live sessions
          </h3>
          {d ? <p className="text-xs text-muted">{d.teams_connected ? 'Teams meetings are created for you.' : 'Teams is not connected: add a meeting link to each session.'}</p> : null}
        </div>
        {d?.can_plan ? (
          <Button size="sm" variant="secondary" loading={plan.isPending} onClick={runPlan}>
            <CalendarClock /> {d.items.length ? 'Re-plan from timetable' : 'Plan sessions'}
          </Button>
        ) : null}
      </div>
      {upload.element}
      {q.error ? (
        <ErrorState message={(q.error as Error).message} onRetry={() => void q.refetch()} />
      ) : !d ? (
        <div className="grid gap-2" aria-busy="true">
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
        </div>
      ) : !d.items.length ? (
        <EmptyState
          icon={<CalendarClock />}
          title="No sessions yet"
          body={d.can_plan ? "Plan them from the group's timetable: one per live component, on the group's day." : 'A cohort manager plans them from the timetable.'}
        />
      ) : (
        <Card className="overflow-hidden animate-reveal">
          <ul className="stagger divide-y divide-border">
            {d.items.map((s) => (
              <SessionItem
                key={s.id}
                s={s}
                groupId={groupId}
                canPlan={d.can_plan}
                teams={d.teams_connected}
                onEdit={() => setEditing(s)}
                onAttendance={() => setAttendance({ id: s.id, title: s.title })}
                onUpload={() => upload.pick(s.id)}
              />
            ))}
          </ul>
        </Card>
      )}
      {editing ? <SessionDialog key={editing.id} groupId={groupId} session={editing} canPlan={!!d?.can_plan} onOpenChange={(o) => !o && setEditing(null)} /> : null}
      <AttendanceDialog kind="session" target={attendance} onOpenChange={(o) => !o && setAttendance(null)} />
    </section>
  )
}
