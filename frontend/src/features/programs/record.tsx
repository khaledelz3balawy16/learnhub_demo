import { Award, CheckCircle2, Circle, CircleDashed, CircleDot } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/misc'
import { Progress } from '@/components/ui/progress'
import { Ring } from '@/components/ui/ring'
import type { components } from '@/api/schema'
import { shortDate } from '@/lib/format'

// A program record (M19): shown to the learner (/learn/:slug/record) and to their tutor
// (console cohort page). Pure display: the data comes from the record endpoints.

type S = components['schemas']
type Otj = S['LearnerOtjSummaryOut']
type Ksb = S['LearnerKsbOut']
type Cpd = S['LearnerCpdOut']
type Cert = S['LearnerModuleCertificateOut']

/** "6 h 30 min" from minutes. */
export function hours(min: number) {
  const h = Math.floor(min / 60)
  const m = Math.round(min % 60)
  if (!h) return `${m} min`
  return m ? `${h} h ${m} min` : `${h} h`
}

const RAG: Record<string, { label: string; tone: 'success' | 'warning' | 'danger' }> = {
  on_track: { label: 'On track', tone: 'success' },
  behind: { label: 'Behind', tone: 'warning' },
  at_risk: { label: 'At risk', tone: 'danger' },
}

export function RagBadge({ rag }: { rag?: string | null }) {
  const r = rag ? RAG[rag] : undefined
  return r ? (
    <Badge tone={r.tone} dot>
      {r.label}
    </Badge>
  ) : (
    <Badge tone="neutral">No target</Badge>
  )
}

/** Off-the-job hours against the program target: a ring for the share of the expected-so-far. */
export function OtjPanel({ otj }: { otj: Otj }) {
  const pct = otj.expected_min ? Math.min(100, (otj.counted_min / otj.expected_min) * 100) : otj.target_min ? (otj.counted_min / otj.target_min) * 100 : 0
  const colour = otj.rag === 'at_risk' ? 'var(--danger)' : otj.rag === 'behind' ? 'var(--warning)' : 'var(--success)'
  return (
    <Card className="flex flex-wrap items-center gap-6 p-5">
      {otj.expected_min != null ? <Ring value={pct} size={112} stroke={10} label="of expected" color={colour} /> : null}
      <dl className="grid min-w-0 flex-1 grid-cols-2 gap-x-6 gap-y-3 text-sm">
        <div>
          <dt className="text-muted">Counted</dt>
          <dd className="text-lg font-semibold tabular">{hours(otj.counted_min)}</dd>
        </div>
        <div>
          <dt className="text-muted">Waiting for approval</dt>
          <dd className="text-lg font-semibold tabular">{hours(otj.pending_min)}</dd>
        </div>
        <div>
          <dt className="text-muted">Expected by now</dt>
          <dd className="font-medium tabular">{otj.expected_min != null ? hours(otj.expected_min) : '—'}</dd>
        </div>
        <div>
          <dt className="text-muted">Status</dt>
          <dd>
            <RagBadge rag={otj.rag} />
          </dd>
        </div>
      </dl>
    </Card>
  )
}

const KSB_STATUS: Record<string, { label: string; icon: typeof Circle; className: string }> = {
  met: { label: 'Met', icon: CheckCircle2, className: 'text-success' },
  in_progress: {
    label: 'In progress',
    icon: CircleDot,
    className: 'text-warning',
  },
  not_started: { label: 'Not started', icon: Circle, className: 'text-subtle' },
  not_mapped: {
    label: 'Not linked to any component yet',
    icon: CircleDashed,
    className: 'text-subtle',
  },
}

export function KsbGrid({ ksbs }: { ksbs: Ksb[] }) {
  if (!ksbs.length) return <EmptyState icon={<CircleDashed />} title="No KSBs for this program" body="The provider hasn't linked a standard yet." />
  const met = ksbs.filter((k) => k.status === 'met').length
  return (
    <div className="grid gap-3">
      <div className="flex items-center gap-3">
        <Progress value={(met / ksbs.length) * 100} tone="success" label="KSBs met" />
        <span className="shrink-0 text-sm text-muted tabular">
          {met} of {ksbs.length} met
        </span>
      </div>
      <ul className="stagger grid gap-2 sm:grid-cols-2">
        {ksbs.map((k) => {
          const s = KSB_STATUS[k.status] ?? KSB_STATUS.not_started!
          const Icon = s.icon
          return (
            <li key={k.id} className="flex gap-3 rounded-lg border border-border bg-surface p-3">
              <Icon className={`mt-0.5 size-[18px] shrink-0 ${s.className}`} aria-hidden />
              <div className="min-w-0 text-sm">
                <p className="font-semibold">
                  {k.code} <span className="sr-only">: {s.label}</span>
                </p>
                <p className="text-muted">{k.text}</p>
                <p className="mt-1 text-xs text-muted">
                  {s.label}
                  {k.total ? ` · ${k.done} of ${k.total} components` : ''}
                </p>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export function CpdList({ cpd }: { cpd: Cpd }) {
  if (!cpd.available_min) return <EmptyState icon={<Award />} title="No CPD set for this program" />
  return (
    <div className="grid gap-4">
      <p className="text-sm text-muted">
        <span className="text-2xl font-semibold text-text tabular">{hours(cpd.earned_min)}</span> of {hours(cpd.available_min)} earned
      </p>
      <ul className="stagger grid gap-3">
        {cpd.modules.map((m) => (
          <li key={m.module_key} className="grid gap-1.5">
            <div className="flex justify-between gap-3 text-sm">
              <span className="min-w-0 truncate font-medium">{m.title}</span>
              <span className="shrink-0 text-muted tabular">
                {hours(m.earned_min)} / {hours(m.available_min)}
              </span>
            </div>
            <Progress value={m.available_min ? (m.earned_min / m.available_min) * 100 : 0} label={`CPD for ${m.title}`} />
          </li>
        ))}
      </ul>
    </div>
  )
}

export function ModuleCertificates({ certificates }: { certificates: Cert[] }) {
  if (!certificates.length) return <EmptyState icon={<Award />} title="No module certificates yet" body="Finish every part of a module to get its certificate." />
  return (
    <ul className="stagger grid gap-3 sm:grid-cols-2">
      {certificates.map((c) => (
        <li key={c.module_key}>
          <Card className="flex gap-3 p-4">
            <Award className="size-6 shrink-0 text-primary" aria-hidden />
            <div className="min-w-0 text-sm">
              <p className="font-semibold">{c.module_title}</p>
              <p className="text-muted">
                Issued {shortDate(c.issued_at)}
                {c.cpd_min ? ` · ${hours(c.cpd_min)} CPD` : ''}
              </p>
              <p className="mt-1 font-mono text-xs text-muted">{c.verification_code}</p>
            </div>
          </Card>
        </li>
      ))}
    </ul>
  )
}
