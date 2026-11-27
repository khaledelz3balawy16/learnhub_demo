import { ArrowRight, Award, BookOpen, Building2, CalendarClock, CalendarDays, CheckCircle2, ClipboardList, Download, PlayCircle, Users } from 'lucide-react'
import type { ReactNode } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { CourseThumb } from '@/components/ui/course-thumb'
import { EmptyState, ErrorState } from '@/components/ui/misc'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { CountUp } from '@/components/ui/count-up'
import { useMyRequirementsAll } from '@/features/compliance/api'
import { useMe } from '@/features/identity/auth'
import { certificatePdfUrl, useMyCertificates, useMyCourses } from '@/features/learning/api'
import { relativeDate, shortDate } from '@/lib/format'
import { Link } from '@/lib/router'
import { dayRange } from '@/lib/schedule'

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
}

function PanelHead({ icon, title, to, label }: { icon: ReactNode; title: string; to: string; label: string }) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
      <h2 className="inline-flex items-center gap-2 text-[15px] font-semibold [&_svg]:size-4 [&_svg]:text-primary">
        {icon} {title}
      </h2>
      <Link to={to} aria-label={label} className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline">
        View all <ArrowRight className="size-3.5" />
      </Link>
    </div>
  )
}

/** Company deadlines that are still open, soonest first (from every company the learner is in). */
function UpcomingDeadlines() {
  const { data: me } = useMe()
  const orgs = me?.memberships ?? []
  const results = useMyRequirementsAll(orgs.map((m) => m.org_id))
  if (!orgs.length) return null
  const loading = results.some((r) => r.isLoading)
  const failed = results.filter((r) => r.isError)
  const due = results
    .flatMap((r) => r.data ?? [])
    .filter((r) => r.due_at && !['compliant', 'exempt'].includes(r.status))
    .sort((a, b) => a.due_at!.localeCompare(b.due_at!))
    .slice(0, 3)
  return (
    <Card className="overflow-hidden">
      <PanelHead icon={<CalendarClock />} title="Upcoming deadlines" to="/learn/required" label="View all required training" />
      {failed.length ? (
        // never say "up to date" when we couldn't check
        <div className="p-4">
          <ErrorState message="We couldn't load your deadlines." onRetry={() => failed.forEach((r) => void r.refetch())} />
        </div>
      ) : loading ? (
        <div className="grid gap-2 p-4">
          <Skeleton className="h-12 rounded-md" />
          <Skeleton className="h-12 rounded-md" />
        </div>
      ) : !due.length ? (
        <p className="flex animate-reveal items-center gap-2 px-4 py-5 text-sm text-muted">
          <CheckCircle2 className="size-4 text-success" /> Nothing due. You're up to date.
        </p>
      ) : (
        <ul className="stagger divide-y divide-border">
          {due.map((r) => {
            const late = new Date(r.due_at!) < new Date()
            return (
              <li key={r.status_id} className="flex items-start gap-3 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{r.requirement}</p>
                  <p className="truncate text-xs text-muted">{r.course_title}</p>
                </div>
                <Badge tone={late ? 'danger' : 'warning'} title={shortDate(r.due_at!)}>
                  {late ? 'Overdue' : `Due ${relativeDate(r.due_at!)}`}
                </Badge>
              </li>
            )
          })}
        </ul>
      )}
    </Card>
  )
}

function RecentCertificates() {
  const { data, isLoading, error, refetch } = useMyCertificates()
  const certs = (data ?? []).slice(0, 2)
  return (
    <Card className="overflow-hidden">
      <PanelHead icon={<Award />} title="My certificates" to="/learn/certificates" label="View all certificates" />
      {error ? (
        <div className="p-4">
          <ErrorState message="We couldn't load your certificates." onRetry={() => void refetch()} />
        </div>
      ) : isLoading ? (
        <div className="p-4">
          <Skeleton className="h-12 rounded-md" />
        </div>
      ) : !certs.length ? (
        <p className="animate-reveal px-4 py-5 text-sm text-muted">Finish a course to earn your first certificate.</p>
      ) : (
        <ul className="stagger divide-y divide-border">
          {certs.map((c) => (
            <li key={c.id} className="flex items-center gap-3 px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{c.course_title}</p>
                <p className="text-xs text-muted">Issued {shortDate(c.issued_at)}</p>
              </div>
              <Button size="sm" variant="secondary" asChild>
                <a href={certificatePdfUrl(c.id)} download aria-label={`Download the certificate for ${c.course_title}`}>
                  <Download /> Download
                </a>
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function Stats({ enrolled, completed, more }: { enrolled: number; completed: number; more: boolean }) {
  const { data: certs } = useMyCertificates()
  const stats: [string, number, boolean][] = [
    ['Courses', enrolled, more],
    ['Completed', completed, more],
    ['Certificates', certs?.length ?? 0, false],
  ]
  return (
    <Card className="grid grid-cols-3 divide-x divide-border py-4 text-center">
      {stats.map(([label, n, plus]) => (
        <div key={label} className="px-2">
          <p className="text-2xl font-semibold tracking-tight tabular">
            <CountUp value={n} />
            {plus ? '+' : ''}
          </p>
          <p className="mt-0.5 text-xs text-muted">{label}</p>
        </div>
      ))}
    </Card>
  )
}

export function MyLearningPage() {
  const { data: me } = useMe()
  const { data, isLoading, error, refetch, hasNextPage, fetchNextPage, isFetchingNextPage } = useMyCourses()
  const items = data?.pages.flatMap((p) => p.items) ?? []
  const current = items.find((i) => i.progress_pct > 0 && i.progress_pct < 100) ?? items[0]

  return (
    <>
      <p className="text-sm text-muted">
        {greeting()}, {me?.full_name?.split(' ')[0] || 'there'}
      </p>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-[26px]">Continue your learning</h1>

      {error ? (
        <ErrorState message={(error as Error).message} onRetry={() => void refetch()} />
      ) : isLoading ? (
        <div className="mt-6 grid gap-4">
          <Skeleton className="h-40 rounded-lg" />
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-64 rounded-lg" />
            ))}
          </div>
        </div>
      ) : !items.length ? (
        <Card className="mt-6">
          <EmptyState icon={<BookOpen />} title="No courses yet" body="Courses you buy, and training your company assigns, appear here." action={<Button asChild><Link to="/courses">Browse courses</Link></Button>} />
        </Card>
      ) : (
        <div className="mt-6 grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="min-w-0">
          {current ? (
            <Card className="flex animate-reveal flex-col gap-5 p-4 sm:flex-row sm:items-center sm:p-5">
              <CourseThumb src={current.thumbnail_url} title={current.title} className="sm:w-56" />
              <div className="min-w-0 flex-1">
                <Badge tone="primary">{current.progress_pct > 0 ? 'In progress' : 'Up next'}</Badge>
                <h2 className="mt-2 text-lg font-semibold tracking-tight">{current.title}</h2>
                <p className="text-sm text-muted">{current.instructors.join(', ')}</p>
                <div className="mt-4 flex items-center gap-3">
                  <Progress value={current.progress_pct} label="Progress" />
                  <span className="text-xs text-muted tabular">{Math.round(current.progress_pct)}%</span>
                </div>
              </div>
              <Button size="lg" asChild>
                <Link to={`/learn/${current.slug}`}>
                  <PlayCircle /> {current.progress_pct > 0 ? 'Continue' : 'Start'}
                </Link>
              </Button>
            </Card>
          ) : null}
          <h2 className="mt-10 mb-4 text-lg font-semibold tracking-tight">My courses</h2>
          <div className="stagger grid gap-4 sm:grid-cols-2 2xl:grid-cols-3">
            {items.map((c) => (
              <div key={c.enrollment_id} className="grid content-start gap-1.5">
              <Link to={`/learn/${c.slug}`} className="group rounded-lg border border-border bg-surface p-2.5 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow">
                <CourseThumb src={c.thumbnail_url} title={c.title} />
                <div className="px-1 pt-3 pb-1">
                  <h3 className="line-clamp-2 text-[15px] font-semibold group-hover:text-primary">{c.title}</h3>
                  {c.org_name ? (
                    <p className="mt-1 inline-flex items-center gap-1 text-xs text-muted">
                      <Building2 className="size-3.5" /> Assigned by {c.org_name}
                    </p>
                  ) : (
                    <p className="mt-1 text-xs text-muted">{c.instructors.join(', ')}</p>
                  )}
                  {c.group_name ? (
                    <p className="mt-1 flex items-center gap-1 text-xs text-muted">
                      <Users className="size-3.5 shrink-0" aria-hidden /> {c.group_name} · {c.cohort_name}
                    </p>
                  ) : null}
                  {c.next_week ? (
                    <p className="mt-1 flex items-center gap-1 text-xs text-muted tabular">
                      <CalendarDays className="size-3.5 shrink-0" aria-hidden /> Week {c.next_week.number}: {dayRange(c.next_week.starts_on, c.next_week.ends_on)}
                    </p>
                  ) : null}
                  <div className="mt-3 flex items-center gap-3">
                    <Progress value={c.progress_pct} tone={c.progress_pct >= 100 ? 'success' : 'primary'} label="Progress" />
                    <span className="text-xs text-muted tabular">{Math.round(c.progress_pct)}%</span>
                  </div>
                </div>
              </Link>
              {c.cohort_name ? (
                // programs: hours, KSBs, CPD and module certificates (a sibling: links can't nest)
                <Link to={`/learn/${c.slug}/record`} className="inline-flex items-center gap-1 justify-self-start px-1 text-xs font-medium text-primary hover:underline">
                  <ClipboardList className="size-3.5" aria-hidden /> My record
                </Link>
              ) : null}
              </div>
            ))}
          </div>
          {hasNextPage ? (
            <div className="mt-6 flex justify-center">
              <Button variant="secondary" loading={isFetchingNextPage} onClick={() => void fetchNextPage()}>
                Show more courses
              </Button>
            </div>
          ) : null}
          </div>
          <aside className="grid content-start gap-4" aria-label="Your progress">
            <Stats enrolled={items.length} completed={items.filter((i) => i.progress_pct >= 100).length} more={!!hasNextPage} />
            <UpcomingDeadlines />
            <RecentCertificates />
          </aside>
        </div>
      )}
    </>
  )
}
