import { ArrowLeft, CalendarClock, CheckCircle2, Clock, PlayCircle, Presentation, Radio, Users, Video } from 'lucide-react'
import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { EmptyState, ErrorState, PageHeader } from '@/components/ui/misc'
import { Skeleton } from '@/components/ui/skeleton'
import { type MySession, type MyWorkshop, useBookWorkshop, useEnrollmentId, useMySessions, useMyWorkshops } from '@/features/learning/api'
import { hours } from '@/features/programs/record'
import { Link } from '@/lib/router'
import { sessionWhen } from '@/lib/schedule'

type Recording = NonNullable<MySession['recording']>

function RecordingDialog({ video, onOpenChange }: { video: { title: string; recording: Recording } | null; onOpenChange: (o: boolean) => void }) {
  return (
    <Dialog open={!!video} onOpenChange={onOpenChange}>
      <DialogContent title={video?.title ?? 'Recording'} description="Recording of the live session" className="max-w-3xl">
        {video?.recording.url ? (
          <iframe
            src={video.recording.url}
            title={`Recording: ${video.title}`}
            className="aspect-video w-full rounded-lg border-0"
            allow="accelerometer; gyroscope; encrypted-media; picture-in-picture; fullscreen"
            allowFullScreen
          />
        ) : (
          <EmptyState icon={<Video />} title="This recording isn't on the video service" body="Ask your tutor to upload it again." />
        )}
      </DialogContent>
    </Dialog>
  )
}

const live = (startsAt: string, endsAt: string, now = Date.now()) => new Date(startsAt).getTime() <= now && now <= new Date(endsAt).getTime()

function SessionRow({ s, early, present, onWatch }: { s: MySession; early: number; present: number; onWatch: () => void }) {
  const ended = new Date(s.ends_at).getTime() < Date.now()
  const cancelled = s.status === 'cancelled'
  return (
    <li className={`flex flex-wrap items-center gap-3 px-4 py-3 ${cancelled ? 'opacity-60' : ''}`}>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium break-words">{s.title}</p>
        <p className="text-xs text-muted tabular">{sessionWhen(s.starts_at, s.ends_at)}</p>
      </div>
      {cancelled ? (
        <Badge tone="danger">Cancelled</Badge>
      ) : s.join_url ? (
        <Button asChild size="sm">
          <a href={s.join_url} target="_blank" rel="noopener noreferrer">
            <Radio /> {live(s.starts_at, s.ends_at) ? 'Join now' : 'Join'}
          </a>
        </Button>
      ) : ended ? (
        <>
          {s.attended_min != null ? <Badge tone={s.attended_min >= present ? 'success' : 'neutral'}>{s.attended_min >= present ? `Attended ${hours(s.attended_min)}` : 'Missed'}</Badge> : null}
          {s.recording ? (
            <Button size="sm" variant="secondary" onClick={onWatch}>
              <PlayCircle /> Watch
            </Button>
          ) : null}
        </>
      ) : (
        <span className="text-xs text-muted">{s.has_link ? `Join opens ${early} min before` : 'Link coming soon'}</span>
      )}
    </li>
  )
}

function WorkshopCard({ w, enrollmentId, present, onWatch }: { w: MyWorkshop; enrollmentId: string; present: number; onWatch: () => void }) {
  const book = useBookWorkshop(enrollmentId)
  const started = new Date(w.starts_at).getTime() <= Date.now()
  const cancelled = w.status === 'cancelled'
  const full = w.spaces_left === 0 && !w.booked
  const act = (yes: boolean) =>
    book.mutate(
      { id: w.id, book: yes },
      {
        onSuccess: () => toast.success(yes ? 'Place booked' : 'Booking cancelled'),
        onError: (e) => toast.error((e as Error).message),
      },
    )
  return (
    <Card className={`grid min-w-0 gap-3 p-4 ${cancelled ? 'opacity-70' : ''}`}>
      <div>
        <h3 className="font-semibold break-words">{w.title}</h3>
        <p className="text-sm text-muted tabular">{sessionWhen(w.starts_at, w.ends_at)}</p>
        {w.description ? <p className="mt-2 line-clamp-3 text-sm whitespace-pre-line">{w.description}</p> : null}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {cancelled ? <Badge tone="danger">Cancelled</Badge> : null}
        {w.booked ? (
          <Badge tone="success">
            <CheckCircle2 className="size-3" aria-hidden /> Booked
          </Badge>
        ) : null}
        {w.spaces_left != null && !started ? <Badge tone={full ? 'warning' : 'outline'}>{full ? 'Full' : `${w.spaces_left} places left`}</Badge> : null}
        {w.expected_otj_min ? (
          <Badge tone="outline">
            <Clock className="size-3" aria-hidden /> {hours(w.expected_otj_min)} off-the-job
          </Badge>
        ) : null}
        {w.cpd_min ? <Badge tone="outline">{hours(w.cpd_min)} CPD</Badge> : null}
        {w.attended_min != null && w.attended_min >= present ? <Badge tone="success">Attended</Badge> : null}
      </div>
      <div className="flex flex-wrap gap-2">
        {cancelled ? null : w.join_url ? (
          <Button asChild size="sm">
            <a href={w.join_url} target="_blank" rel="noopener noreferrer">
              <Radio /> Join
            </a>
          </Button>
        ) : !started && !w.booked ? (
          <Button size="sm" disabled={full} loading={book.isPending} onClick={() => act(true)}>
            Book a place
          </Button>
        ) : !started && w.booked ? (
          <Button size="sm" variant="ghost" loading={book.isPending} onClick={() => act(false)}>
            Cancel booking
          </Button>
        ) : null}
        {w.recording ? (
          <Button size="sm" variant="secondary" onClick={onWatch}>
            <PlayCircle /> Watch the recording
          </Button>
        ) : null}
      </div>
    </Card>
  )
}

export function ProgramSessionsPage() {
  const { slug = '' } = useParams()
  const lookup = useEnrollmentId(slug)
  const id = lookup.enrollmentId
  const sessions = useMySessions(id)
  const workshops = useMyWorkshops(id)
  const [watching, setWatching] = useState<{
    title: string
    recording: Recording
  } | null>(null)
  const back = (
    <Link to={`/learn/${slug}`} className="inline-flex items-center gap-1 text-sm text-muted hover:text-text">
      <ArrowLeft className="size-4" aria-hidden /> Back to the program
    </Link>
  )
  if (lookup.notEnrolled)
    return (
      <EmptyState
        icon={<CalendarClock />}
        title="You're not on this program"
        action={
          <Button asChild>
            <Link to="/learn">My learning</Link>
          </Button>
        }
      />
    )
  const error = lookup.error ?? sessions.error ?? workshops.error
  if (error) return <ErrorState message={(error as Error).message} onRetry={() => void (lookup.refetch(), sessions.refetch(), workshops.refetch())} />
  if (!sessions.data || !workshops.data)
    return (
      <div className="grid gap-4" aria-busy="true">
        <Skeleton className="h-16" />
        <Skeleton className="h-48" />
        <Skeleton className="h-40" />
      </div>
    )
  const now = Date.now()
  const items = sessions.data.items
  const upcoming = items.filter((s) => new Date(s.ends_at).getTime() >= now)
  const past = items.filter((s) => new Date(s.ends_at).getTime() < now).reverse()
  const row = (s: MySession) => <SessionRow key={s.id} s={s} early={sessions.data.join_early_min} present={sessions.data.present_min} onWatch={() => s.recording && setWatching({ title: s.title, recording: s.recording })} />
  return (
    <div className="grid gap-8 animate-reveal">
      <PageHeader back={back} title="Live sessions" description={sessions.data.group_name ? `Your group: ${sessions.data.group_name}` : 'You are not in a group yet.'} />
      <section aria-labelledby="upcoming" className="grid gap-3">
        <h2 id="upcoming" className="text-base font-semibold">
          Coming up
        </h2>
        {upcoming.length ? (
          <Card className="overflow-hidden">
            <ul className="stagger divide-y divide-border">{upcoming.map(row)}</ul>
          </Card>
        ) : (
          <EmptyState
            icon={<CalendarClock />}
            title="No sessions coming up"
            body={sessions.data.group_name ? 'Your tutor adds them to the timetable.' : 'Sessions appear once your provider places you in a group.'}
          />
        )}
      </section>
      {past.length ? (
        <section aria-labelledby="past" className="grid gap-3">
          <h2 id="past" className="text-base font-semibold">
            Past sessions
          </h2>
          <Card className="overflow-hidden">
            <ul className="stagger divide-y divide-border">{past.map(row)}</ul>
          </Card>
        </section>
      ) : null}
      <section aria-labelledby="workshops" className="grid gap-3">
        <h2 id="workshops" className="flex items-center gap-2 text-base font-semibold">
          <Presentation className="size-4 text-primary" aria-hidden /> Workshops
        </h2>
        {workshops.data.items.length ? (
          <div className="stagger grid gap-3 md:grid-cols-2">
            {workshops.data.items.map((w) => (
              <WorkshopCard key={w.id} w={w} enrollmentId={id!} present={workshops.data.present_min} onWatch={() => w.recording && setWatching({ title: w.title, recording: w.recording })} />
            ))}
          </div>
        ) : (
          <EmptyState icon={<Users />} title="No workshops yet" body="Optional workshops for your program appear here. Book a place to join." />
        )}
      </section>
      <RecordingDialog video={watching} onOpenChange={(o) => !o && setWatching(null)} />
    </div>
  )
}
