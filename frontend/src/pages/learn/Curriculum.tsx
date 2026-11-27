import { CalendarOff, CheckCircle2, ChevronDown, Circle, Lock, PlayCircle } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import type { Player } from '@/features/learning/api'
import { cn } from '@/lib/cn'
import { Link } from '@/lib/router'
import { dayRange, dayWithWeekday } from '@/lib/schedule'

import { kindOf, lectureUrl, minutes } from './shared'

type Section = Player['sections'][number]

/** The course outline beside the player: where you are, what's done, what's next.
 * Programs (M18) group their weeks under modules, with the cohort's dates and days off. */
export function Curriculum({ player, current, onPick }: { player: Player; current?: string; onPick?: () => void }) {
  const holding = player.sections.find((s) => s.lectures.some((l) => l.key === current))?.id
  const thisWeek = player.current_section_id ?? undefined
  const [open, setOpen] = useState<Set<string>>(() => new Set(holding ? [holding] : thisWeek ? [thisWeek] : player.sections.slice(0, 1).map((s) => s.id)))
  const active = useRef<HTMLAnchorElement>(null)

  // follow the learner: opening the next section and keeping the current row in view
  useEffect(() => {
    if (holding) setOpen((prev) => (prev.has(holding) ? prev : new Set(prev).add(holding)))
  }, [holding])
  useEffect(() => {
    active.current?.scrollIntoView({ block: 'nearest' })
  }, [current])

  const program = player.kind === 'program'
  const toggle = (id: string) =>
    setOpen((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const renderSection = (s: Section, n: number) => {
    const done = s.lectures.filter((l) => l.completed).length
    const total = s.lectures.reduce((t, l) => t + l.duration_sec, 0)
    const isOpen = open.has(s.id)
    return (
      <section key={s.id}>
        <button type="button" onClick={() => toggle(s.id)} aria-expanded={isOpen} className="flex w-full items-start gap-3 bg-surface-2/60 px-4 py-3 text-left transition-colors hover:bg-surface-2">
          <span className="min-w-0 flex-1">
            <span className="flex flex-wrap items-center gap-x-2 text-[13px] font-semibold">
              {program ? `Week ${s.week_number ?? n + 1}` : `Section ${n + 1}`}: {s.title}
              {s.id === thisWeek ? <span className="rounded-full bg-primary px-1.5 py-px text-[10px] font-semibold tracking-wide text-on-primary uppercase">This week</span> : null}
            </span>
            <span className="mt-0.5 block text-xs text-muted tabular">
              {s.starts_on ? `${dayRange(s.starts_on, s.ends_on)} · ` : ''}
              {done} / {s.lectures.length}
              {total ? ` · ${minutes(total)}` : ''}
            </span>
          </span>
          <ChevronDown className={cn('mt-0.5 size-4 shrink-0 text-muted transition-transform duration-200', isOpen && 'rotate-180')} />
        </button>
        <div className={cn('grid transition-[grid-template-rows] duration-250 ease-out', isOpen ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]')}>
          <ul className="overflow-hidden">
            {s.days_off?.length ? (
              <li className="flex items-start gap-2 px-4 py-2 text-xs text-muted">
                <CalendarOff className="mt-px size-3.5 shrink-0" aria-hidden />
                <span>No teaching {s.days_off.map((d) => `${dayWithWeekday(d.date)} (${d.title})`).join(', ')}</span>
              </li>
            ) : null}
            {s.lectures.map((l) => {
              const here = l.key === current
              const { Icon, label } = kindOf(l.kind)
              return (
                <li key={l.key}>
                  <Link
                    ref={here ? active : undefined}
                    to={lectureUrl(player.slug, l.key)}
                    onClick={onPick}
                    aria-current={here ? 'page' : undefined}
                    tabIndex={isOpen ? undefined : -1}
                    className={cn('relative flex gap-3 px-4 py-2.5 text-sm transition-colors', here ? 'bg-primary-soft text-text' : 'hover:bg-surface-2')}
                  >
                    {here ? <span aria-hidden className="absolute inset-y-0 left-0 w-[3px] bg-primary" /> : null}
                    <span className="mt-0.5 shrink-0" aria-label={l.completed ? 'Completed' : l.locked ? 'Locked' : 'Not completed'}>
                      {l.completed ? <CheckCircle2 className="size-[18px] fill-success text-surface" /> : l.locked ? <Lock className="size-[18px] text-muted" /> : here ? <PlayCircle className="size-[18px] text-primary" /> : <Circle className="size-[18px] text-border-strong" />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className={cn('block leading-snug', here && 'font-medium')}>{l.title}</span>
                      <span className="mt-0.5 flex items-center gap-1.5 text-xs text-muted">
                        <Icon className="size-3.5" /> {label}
                        {l.duration_sec ? ` · ${minutes(l.duration_sec)}` : ''}
                      </span>
                      {l.locked && l.prerequisite_title ? <span className="mt-0.5 block text-xs text-muted">Finish “{l.prerequisite_title}” first</span> : null}
                    </span>
                  </Link>
                </li>
              )
            })}
          </ul>
        </div>
      </section>
    )
  }

  if (program && player.modules?.length) {
    return (
      <nav aria-label="Program content">
        {player.modules.map((m, mi) => {
          const weeks = player.sections.filter((s) => s.module_id === m.id)
          return (
            <section key={m.id} aria-labelledby={`module-${m.id}`} className="border-b border-border last:border-b-0">
              <header className="bg-surface px-4 pt-4 pb-2">
                <p className="text-[11px] font-semibold tracking-wide text-primary uppercase">Module {mi + 1}</p>
                <h3 id={`module-${m.id}`} className="text-sm font-semibold">{m.title}</h3>
                {m.starts_on ? <p className="mt-0.5 text-xs text-muted tabular">{dayRange(m.starts_on, m.ends_on)}</p> : null}
              </header>
              <div className="divide-y divide-border border-t border-border">{weeks.map((s) => renderSection(s, player.sections.indexOf(s)))}</div>
            </section>
          )
        })}
      </nav>
    )
  }

  return (
    <nav aria-label="Course content" className="divide-y divide-border">
      {player.sections.map(renderSection)}
    </nav>
  )
}
