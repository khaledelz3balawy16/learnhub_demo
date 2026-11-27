import { AlertTriangle, ChevronRight, HeartHandshake, Search, ShieldCheck, Users } from 'lucide-react'
import { useEffect, useState } from 'react'

import { ApiError } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { CountUp } from '@/components/ui/count-up'
import { Input, NativeSelect } from '@/components/ui/input'
import { EmptyState, ErrorState, PageHeader, StatCard } from '@/components/ui/misc'
import { Skeleton } from '@/components/ui/skeleton'
import { DetailSheet, InfoRow, LoadMore, useParam } from '@/features/console/ui'
import { type InclusionDetail, type ResultsScope, useInclusionResult, useInclusionResults } from '@/features/inclusion/api'
import { cn } from '@/lib/cn'
import { shortDate } from '@/lib/format'
import { useFill } from '@/lib/motion'
import { Link } from '@/lib/router'

const COPY = {
  console: {
    forbidden: 'Only admins can see inclusion results',
    empty: 'Learners find the inclusion test under My learning. Their answers show here.',
    privacy: 'Private: only admins can see this.',
  },
  company: {
    forbidden: "Only your company's owners and admins can see inclusion results",
    empty: 'When your people take the inclusion test under My learning, their latest answers show here.',
    privacy: "Private: only your company's owners and admins, and the provider's admins, can see this.",
  },
}

/** Inclusion results: each learner's latest answers, the sections that flag them, and every
 * answer on demand. In the console: every learner (platform admins). In the company workspace:
 * the company's current members (its owners and admins). Every opened result is audit-logged. */
export function InclusionResultsView({ scope }: { scope: ResultsScope }) {
  const copy = COPY[scope]
  const [q, setQ] = useParam('q')
  const [flagged, setFlagged] = useParam('flagged')
  const [section, setSection] = useParam('section')
  const [openId, setOpenId] = useParam('open')
  const [term, setTerm] = useState(q)
  useEffect(() => {
    const t = setTimeout(() => term !== q && setQ(term.trim()), 300)
    return () => clearTimeout(t)
  }, [term, q, setQ])
  const res = useInclusionResults(scope, { q, flagged: flagged === 'yes' || flagged === 'no' ? flagged : '', section })
  const first = res.data?.pages[0]
  const rows = res.data?.pages.flatMap((p) => p.items) ?? []

  if (res.error instanceof ApiError && res.error.status === 403)
    return <EmptyState icon={<ShieldCheck />} title={copy.forbidden} body="The answers are private health information, so only a few people can see them." />

  return (
    <div className="grid gap-6">
      <PageHeader
        title="Inclusion results"
        description="Each learner's latest answers. A flag is not a diagnosis: it is a prompt to check in."
        actions={
          scope === 'console' ? (
            <Button variant="secondary" asChild>
              <Link to="/console/inclusion/questions">Edit questions</Link>
            </Button>
          ) : undefined
        }
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <StatCard label="Learners who answered" value={first ? <CountUp value={first.summary.learners} /> : '–'} icon={<Users />} />
        <StatCard label="May need support" value={first ? <CountUp value={first.summary.flagged} /> : '–'} icon={<AlertTriangle />} tone="warning" hint="At least one section at or above its flag" />
      </div>
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b border-border p-3 sm:p-4">
          <div className="min-w-48 flex-1">
            <Input icon={<Search />} value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Search by name or email" aria-label="Search learners" />
          </div>
          <NativeSelect aria-label="Flags" value={flagged} onChange={(e) => setFlagged(e.target.value)} className="w-auto">
            <option value="">Everyone</option>
            <option value="yes">May need support</option>
            <option value="no">No flags</option>
          </NativeSelect>
          <NativeSelect aria-label="Flagged in section" value={section} onChange={(e) => setSection(e.target.value)} className="w-auto max-w-full">
            <option value="">Any section</option>
            {(first?.sections ?? []).map((s) => (
              <option key={s.id} value={s.id}>
                Flagged in {s.title}
              </option>
            ))}
          </NativeSelect>
        </div>
        {res.error ? (
          <ErrorState message={(res.error as Error).message} onRetry={() => void res.refetch()} />
        ) : !res.data ? (
          <div className="grid gap-2 p-4" aria-busy="true">
            {Array.from({ length: 5 }, (_, i) => (
              <Skeleton key={i} className="h-14" />
            ))}
          </div>
        ) : !rows.length ? (
          <EmptyState
            icon={<HeartHandshake />}
            title={q || flagged || section ? 'Nobody matches' : 'No answers yet'}
            body={q || flagged || section ? 'Try other filters.' : copy.empty}
          />
        ) : (
          <>
            <ul className={cn('stagger divide-y divide-border animate-reveal', res.isPlaceholderData && 'opacity-60')}>
              {rows.map((r) => {
                const flags = r.scores.filter((s) => s.flagged)
                return (
                  <li key={r.attempt_id}>
                    <button
                      type="button"
                      onClick={() => setOpenId(r.attempt_id)}
                      className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-2/60 focus-visible:bg-surface-2 focus-visible:outline-none sm:px-5"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium">{r.name}</p>
                        <p className="truncate text-xs text-muted">
                          {r.email} · sent {shortDate(r.submitted_at)}
                        </p>
                        {flags.length ? (
                          <p className="mt-1.5 flex flex-wrap gap-1">
                            {flags.map((s) => (
                              <Badge key={s.section_id} tone="warning">
                                {s.title}
                              </Badge>
                            ))}
                          </p>
                        ) : null}
                      </div>
                      {flags.length ? <Badge tone="warning" dot>{flags.length} {flags.length === 1 ? 'flag' : 'flags'}</Badge> : <Badge tone="success">No flags</Badge>}
                      <ChevronRight className="size-4 shrink-0 text-subtle" />
                    </button>
                  </li>
                )
              })}
            </ul>
            <LoadMore shown={rows.length} noun={rows.length === 1 ? 'learner' : 'learners'} hasMore={!!res.hasNextPage} loading={res.isFetchingNextPage} onMore={() => void res.fetchNextPage()} />
          </>
        )}
      </Card>
      <DetailSheet open={!!openId} onOpenChange={(o) => !o && setOpenId('')} title="Inclusion answers" description={copy.privacy}>
        {openId ? <ResultDetail scope={scope} attemptId={openId} onPick={setOpenId} /> : null}
      </DetailSheet>
    </div>
  )
}

function ResultDetail({ scope, attemptId, onPick }: { scope: ResultsScope; attemptId: string; onPick: (id: string) => void }) {
  const q = useInclusionResult(scope, attemptId)
  if (q.error) return <ErrorState message={(q.error as Error).message} onRetry={() => void q.refetch()} />
  if (!q.data)
    return (
      <div className="grid gap-3" aria-busy="true">
        <Skeleton className="h-24" />
        <Skeleton className="h-40" />
      </div>
    )
  const d = q.data
  return (
    <div className="grid animate-reveal gap-5">
      <div>
        <p className="text-lg font-semibold">{d.name}</p>
        <p className="text-sm text-muted">{d.email}</p>
      </div>
      <div>
        <InfoRow label="Sent">{shortDate(d.submitted_at)}{d.is_latest ? ' (latest)' : ''}</InfoRow>
        <InfoRow label="Agreed to the note">{shortDate(d.consented_at)}</InfoRow>
        <InfoRow label="Sections flagged">{d.flag_count}</InfoRow>
      </div>
      {d.history.length > 1 ? (
        <div>
          <p className="mb-2 text-sm font-semibold">Earlier answers</p>
          <div className="flex flex-wrap gap-2">
            {d.history.map((h) => (
              <Button key={h.attempt_id} size="sm" variant={h.attempt_id === d.attempt_id ? 'primary' : 'secondary'} onClick={() => onPick(h.attempt_id)} aria-current={h.attempt_id === d.attempt_id ? 'true' : undefined}>
                {shortDate(h.submitted_at)}
                {h.flag_count ? ` · ${h.flag_count} ${h.flag_count === 1 ? 'flag' : 'flags'}` : ''}
              </Button>
            ))}
          </div>
        </div>
      ) : null}
      <ol className="stagger grid gap-3">
        {d.groups.map((g) => (
          <li key={`${d.attempt_id}-${g.section_id}`}>
            <Group group={g} />
          </li>
        ))}
      </ol>
    </div>
  )
}

function Group({ group: g }: { group: InclusionDetail['groups'][number] }) {
  const [open, setOpen] = useState(g.flagged)
  const fill = useFill(g.max ? (g.score / g.max) * 100 : 0, true)
  const mark = g.threshold != null && g.max ? Math.min(100, (g.threshold / g.max) * 100) : null
  return (
    <Card className={cn('overflow-hidden', g.flagged && 'border-warning/50')}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="grid w-full gap-2 p-4 text-left focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none"
      >
        <span className="flex items-start justify-between gap-3">
          <span className="text-sm font-semibold">{g.title}</span>
          <span className="flex shrink-0 items-center gap-2">
            {g.flagged ? <Badge tone="warning">May need support</Badge> : null}
            <span className="text-sm font-semibold tabular">
              {g.score}
              <span className="font-normal text-muted"> / {g.max}</span>
            </span>
          </span>
        </span>
        <span className="relative block h-2 rounded-full bg-surface-2" role="img" aria-label={`Score ${g.score} of ${g.max}${g.threshold != null ? `, flag at ${g.threshold}` : ''}`}>
          <span className={cn('absolute inset-y-0 left-0 rounded-full transition-[width] duration-300 ease-out', g.flagged ? 'bg-warning' : 'bg-primary')} style={{ width: `${fill}%` }} />
          {mark != null ? <span className="absolute -top-1 -bottom-1 w-0.5 rounded bg-text/60" style={{ left: `${mark}%` }} /> : null}
        </span>
        <span className="text-xs text-muted">{g.threshold != null ? `Flags at ${g.threshold} or more` : 'This section doesn’t flag anyone'} · {open ? 'Hide answers' : 'Show answers'}</span>
      </button>
      {open ? (
        <ol className="animate-reveal divide-y divide-border border-t border-border">
          {g.answers.map((a) => (
            <li key={a.key} className="flex flex-col gap-1.5 px-4 py-2.5 text-sm sm:flex-row sm:items-start sm:justify-between sm:gap-4">
              <span className="min-w-0">{a.text}</span>
              <Badge tone={a.value >= a.max && a.max > 0 ? 'warning' : a.value === 0 ? 'neutral' : 'primary'} className="shrink-0 self-start">
                {a.label}
              </Badge>
            </li>
          ))}
        </ol>
      ) : null}
    </Card>
  )
}
