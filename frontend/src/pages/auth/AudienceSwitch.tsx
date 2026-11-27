import { Building2, GraduationCap } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'

import { cn } from '@/lib/cn'
import { safeNext } from '@/lib/next'
import { Link } from '@/lib/router'

export type Audience = 'learner' | 'org'

/** Who is signing in: `?as=org` is an organisation (company managers and admins), anything
 * else a learner. One account system serves both; only the wording and where you land differ. */
export function useAudience(): { audience: Audience; next: string; nextParam: string | null } {
  const [params] = useSearchParams()
  const audience: Audience = params.get('as') === 'org' ? 'org' : 'learner'
  const nextParam = params.get('next')
  return { audience, nextParam, next: nextParam ? safeNext(nextParam) : audience === 'org' ? ORG_HOME[0] : safeNext(null) }
}

// where an organisation lands: the workspace after log-in (it sends new companies to set-up)
const ORG_HOME = ['/business', '/business/start'] as const
export const orgSignupNext = ORG_HOME[1]

const OPTIONS = [
  { value: 'learner', label: 'Learner', Icon: GraduationCap },
  { value: 'org', label: 'Organisation', Icon: Building2 },
] as const

/** Two-way switch at the top of the log-in and sign-up pages. Links, so the choice lives in the
 * URL and the header's "For organisations" button can open the right side directly. */
export function AudienceSwitch({ path }: { path: '/login' | '/signup' }) {
  const [params] = useSearchParams()
  const { audience } = useAudience()
  const href = (value: Audience) => {
    const q = new URLSearchParams()
    if (value === 'org') q.set('as', 'org')
    const next = params.get('next')
    if (next) q.set('next', next)
    const s = q.toString()
    return s ? `${path}?${s}` : path
  }
  return (
    <nav aria-label={path === '/login' ? 'Log in as' : 'Sign up as'} className="mb-8 grid grid-cols-2 gap-1 rounded-lg border border-border bg-surface-2/70 p-1">
      {OPTIONS.map(({ value, label, Icon }) => {
        const active = audience === value
        return (
          <Link
            key={value}
            to={href(value)}
            replace
            aria-current={active ? 'page' : undefined}
            className={cn(
              'flex items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-[color,background-color,box-shadow] duration-200 focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none motion-reduce:transition-none',
              active ? 'bg-primary-soft text-primary-soft-text shadow-sm' : 'text-muted hover:bg-surface hover:text-text',
            )}
          >
            <Icon className="size-4" aria-hidden />
            {label}
          </Link>
        )
      })}
    </nav>
  )
}
