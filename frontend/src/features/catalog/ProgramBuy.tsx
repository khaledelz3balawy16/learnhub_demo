import { CalendarDays, Check, Coins, PlayCircle, Radio, Video } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Field, NativeSelect } from '@/components/ui/input'
import { Progress } from '@/components/ui/progress'
import type { useCourse } from '@/features/catalog/api'
import { Price } from '@/features/catalog/CourseCard'
import { useProgramCheckout, useUnlockProgramModule } from '@/features/commerce/api'
import { useMe } from '@/features/identity/auth'
import { cn } from '@/lib/cn'
import { useCurrency } from '@/lib/currency'
import { money, shortDate } from '@/lib/format'
import { Link, useNavigate } from '@/lib/router'

type Detail = NonNullable<ReturnType<typeof useCourse>['data']>
type Offer = Detail['offers'][number]
type Access = NonNullable<Detail['program_access']>

const WHOLE = 'program'
const MODE_LABEL: Record<string, string> = { live: 'Live in a cohort', recorded: 'Recorded, self-paced' }

/** Mirrors apps.commerce.programs.covers: does the learner already have what this offer sells? */
function covers(access: Detail['program_access'], o: Offer) {
  if (!access) return false
  if (o.mode === 'live' && !access.live) return false
  if (!o.module_key) return access.scope === 'program'
  return access.scope === 'program' || access.module_keys.includes(o.module_key)
}

function haveLabel(a: Access, modules: Detail['modules']) {
  const what = a.scope === 'program' ? 'The whole program' : a.module_keys.map((k) => modules.find((m) => m.module_key === k)?.title ?? 'A module').join(', ')
  return `${what} · ${a.live ? 'live in a cohort' : 'recorded'}`
}

function Choice({ options, value, onChange, label }: { options: { value: string; label: string; icon?: React.ReactNode }[]; value: string; onChange: (v: string) => void; label: string }) {
  return (
    <div role="group" aria-label={label} className="grid gap-1.5">
      <p className="text-sm font-medium">{label}</p>
      <div className="grid grid-cols-2 gap-1.5">
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            aria-pressed={value === o.value}
            onClick={() => onChange(o.value)}
            className={cn('flex min-w-0 items-center justify-center gap-1.5 rounded-md border px-2 py-2 text-[13px] font-medium transition-colors duration-150', value === o.value ? 'border-primary bg-primary-soft text-primary-soft-text' : 'border-border text-muted hover:bg-surface-2 hover:text-text')}
          >
            {o.icon}
            <span className="truncate">{o.label}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

/** Programs (M21, plan D5–D7, D10): buy the whole program or one module, live in a cohort or
 * recorded, paid in full or monthly; recorded modules can also be unlocked with tokens. */
export function ProgramBuy({ course, progress }: { course: Detail; progress: number | null }) {
  const { data: me } = useMe()
  const navigate = useNavigate()
  const location = useLocation()
  const { code } = useCurrency()
  const checkout = useProgramCheckout()
  const unlock = useUnlockProgramModule()
  const access = course.program_access ?? null
  const offers = course.offers
  const modes = useMemo(() => ['live', 'recorded'].filter((m) => offers.some((o) => o.mode === m)), [offers])
  const [mode, setMode] = useState(modes[0] ?? 'live')
  const ofMode = offers.filter((o) => o.mode === mode)
  const [scope, setScope] = useState(WHOLE)
  const offer = ofMode.find((o) => (o.module_key ?? WHOLE) === scope) ?? ofMode[0]
  const open = course.intakes.filter((i) => i.places_left !== 0)
  const [picked, setPicked] = useState<string | null>(null)
  const cohortId = access?.cohort_id && offer?.mode === 'live' ? access.cohort_id : (picked ?? open[0]?.id ?? null)
  const [months, setMonths] = useState(1)
  const [confirmTokens, setConfirmTokens] = useState(false)
  const remaining = offers.filter((o) => !covers(access, o))
  const fail = (e: unknown) => toast.error((e as Error).message)
  const needLogin = () => navigate(`/login?next=${encodeURIComponent(location.pathname)}`)

  const moduleTitle = (key: string | null) => (key ? (course.modules.find((m) => m.module_key === key)?.title ?? 'Module') : 'Whole program')
  const owned = offer ? covers(access, offer) : false
  const monthly = offer?.price && offer.instalments_max > 1 ? Math.min(Math.max(months, 1), offer.instalments_max) : 1
  const list = offer?.price?.list_minor ?? 0
  const per = monthly > 1 ? Math.ceil(list / monthly) : list
  const needsIntake = offer?.mode === 'live'
  const canBuy = !!offer?.price && !owned && (!needsIntake || !!cohortId)

  const buy = () =>
    offer &&
    checkout.mutate(
      { offerId: offer.id, currency: offer.price?.currency ?? code ?? 'GBP', cohortId: needsIntake ? cohortId : null, instalments: monthly },
      { onSuccess: (r) => (r.checkout_url ? window.location.assign(r.checkout_url) : navigate(`/checkout/success?order=${r.order_id}`)), onError: fail },
    )
  const spend = () =>
    offer &&
    unlock.mutate(offer.id, {
      onSuccess: () => {
        toast.success('Module unlocked. Enjoy it!')
        navigate(`/learn/${course.slug}`)
      },
      onError: fail,
      onSettled: () => setConfirmTokens(false),
    })

  return (
    <div className="grid gap-4">
      {access ? (
        <div>
          <p className="text-sm font-medium">You're enrolled</p>
          <p className="mt-0.5 text-xs text-muted">{haveLabel(access, course.modules)}</p>
          <Progress value={progress ?? 0} className="mt-3" label="Program progress" />
          <Button size="lg" className="mt-4 w-full" asChild>
            <Link to={`/learn/${course.slug}`}>
              <PlayCircle /> {(progress ?? 0) > 0 ? 'Continue learning' : 'Start learning'}
            </Link>
          </Button>
        </div>
      ) : null}

      {access?.paused ? (
        <p className="rounded-md bg-danger/10 px-3 py-2.5 text-[13px] text-danger">
          Your access is paused because a monthly payment didn't go through.{' '}
          <Link to="/account/orders" className="font-medium underline">
            Update your card
          </Link>
        </p>
      ) : access?.paying_monthly ? (
        <p className="text-xs text-muted">You're paying for this program monthly. You can add more once it is paid.</p>
      ) : !offers.length ? (
        <div className="grid gap-1.5">
          <p className="text-sm font-medium">Places are arranged by your training provider</p>
          <p className="text-sm text-muted">Learners join this program in a cohort and group. Ask your provider for a place.</p>
        </div>
      ) : access && !remaining.length ? null : (
        <div className={cn('grid gap-3.5', access && 'border-t border-border pt-4')}>
          {access ? <p className="text-sm font-semibold">Add to your learning</p> : null}
          {modes.length > 1 ? (
            <Choice
              label="How you learn"
              value={mode}
              onChange={(m) => {
                setMode(m)
                setScope(WHOLE)
                setMonths(1)
              }}
              options={modes.map((m) => ({ value: m, label: MODE_LABEL[m], icon: m === 'live' ? <Radio className="size-4 shrink-0" /> : <Video className="size-4 shrink-0" /> }))}
            />
          ) : (
            <Badge tone="neutral" className="justify-self-start">
              {MODE_LABEL[mode]}
            </Badge>
          )}
          {ofMode.length > 1 ? (
            <Field label="What you buy">
              {(p) => (
                <NativeSelect
                  {...p}
                  value={offer ? (offer.module_key ?? WHOLE) : WHOLE}
                  onChange={(e) => {
                    setScope(e.target.value)
                    setMonths(1)
                    setConfirmTokens(false)
                  }}
                >
                  {ofMode.map((o) => (
                    <option key={o.id} value={o.module_key ?? WHOLE}>
                      {moduleTitle(o.module_key)}
                      {covers(access, o) ? ' (you have this)' : ''}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
          ) : null}
          {needsIntake && !owned ? (
            access?.cohort_id ? (
              <p className="flex items-center gap-1.5 text-sm text-muted">
                <CalendarDays className="size-4" /> With your intake: {course.intakes.find((i) => i.id === access.cohort_id)?.name ?? 'your cohort'}
              </p>
            ) : course.intakes.length ? (
              <Field label="Intake" hint={open.length ? undefined : 'Every intake is full right now.'}>
                {(p) => (
                  <NativeSelect {...p} value={cohortId ?? ''} onChange={(e) => setPicked(e.target.value)}>
                    {course.intakes.map((i) => (
                      <option key={i.id} value={i.id} disabled={i.places_left === 0}>
                        {i.name} · starts {shortDate(i.start_date)}
                        {i.places_left === 0 ? ' · full' : i.places_left != null && i.places_left <= 5 ? ` · ${i.places_left} places left` : ''}
                      </option>
                    ))}
                  </NativeSelect>
                )}
              </Field>
            ) : (
              <p className="text-sm text-muted">No intakes are open right now. Check back soon.</p>
            )
          ) : null}
          {offer?.price && offer.instalments_max > 1 && !owned ? (
            <>
              <Choice
                label="How you pay"
                value={monthly > 1 ? 'monthly' : 'full'}
                onChange={(v) => setMonths(v === 'monthly' ? offer.instalments_max : 1)}
                options={[
                  { value: 'full', label: 'Pay in full' },
                  { value: 'monthly', label: 'Pay monthly' },
                ]}
              />
              {monthly > 1 && offer.instalments_max > 2 ? (
                <Field label="Number of monthly payments">
                  {(p) => (
                    <NativeSelect {...p} value={monthly} onChange={(e) => setMonths(Number(e.target.value))}>
                      {Array.from({ length: offer.instalments_max - 1 }, (_, i) => i + 2).map((n) => (
                        <option key={n} value={n}>
                          {n} payments
                        </option>
                      ))}
                    </NativeSelect>
                  )}
                </Field>
              ) : null}
            </>
          ) : null}

          {owned ? (
            <Badge tone="success" className="justify-self-start">
              <Check /> You have this
            </Badge>
          ) : offer?.price ? (
            <div aria-live="polite">
              {monthly > 1 ? (
                <>
                  <p className="text-3xl font-bold tracking-tight tabular">
                    {money(per, offer.price.currency, offer.price.exponent)}
                    <span className="ml-1 text-base font-medium text-muted">/ month</span>
                  </p>
                  <p className="mt-0.5 text-xs text-muted">
                    {monthly} payments · {money(per * monthly, offer.price.currency, offer.price.exponent)} in total
                  </p>
                </>
              ) : (
                <Price price={offer.price} className="text-3xl [&>span:first-child]:text-3xl [&>span:first-child]:font-bold" />
              )}
            </div>
          ) : null}

          {!owned && offer?.price ? (
            <Button size="lg" className="w-full" loading={checkout.isPending} disabled={!canBuy} onClick={() => (me ? buy() : needLogin())}>
              {needsIntake ? 'Book my place' : 'Buy now'}
            </Button>
          ) : null}
          {!owned && offer?.token_price ? (
            <div className={cn(offer.price && 'border-t border-border pt-3')}>
              {offer.price ? <p className="mb-2 text-xs font-medium text-muted">Or unlock this module with tokens</p> : null}
              {confirmTokens ? (
                <div className="grid grid-cols-2 gap-2">
                  <Button variant="secondary" onClick={() => setConfirmTokens(false)}>
                    Cancel
                  </Button>
                  <Button loading={unlock.isPending} onClick={spend}>
                    Spend {offer.token_price}
                  </Button>
                </div>
              ) : (
                <Button size="lg" variant="soft" className="w-full" onClick={() => (me ? setConfirmTokens(true) : needLogin())}>
                  <Coins /> Unlock with {offer.token_price} tokens
                </Button>
              )}
            </div>
          ) : null}
          {!owned ? (
            <p className="text-center text-xs text-muted">
              Secure checkout by Stripe{monthly > 1 ? '. If a monthly payment fails, you keep access for a short time while you update your card.' : ''}
            </p>
          ) : null}
        </div>
      )}
    </div>
  )
}

/** The intakes a live place can join, with dates and places left. */
export function ProgramIntakes({ intakes }: { intakes: Detail['intakes'] }) {
  if (!intakes.length) return null
  return (
    <section aria-labelledby="intakes">
      <h2 id="intakes" className="text-xl font-semibold tracking-tight">
        Intakes
      </h2>
      <p className="mt-1 text-sm text-muted">Live places study together in a cohort, in small groups with their own tutor.</p>
      <ul className="stagger mt-4 grid gap-3 sm:grid-cols-2">
        {intakes.map((i) => (
          <li key={i.id} className="flex min-w-0 items-start gap-3 rounded-lg border border-border bg-surface p-4">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-primary-soft text-primary-soft-text">
              <CalendarDays className="size-5" />
            </span>
            <div className="min-w-0">
              <p className="font-medium break-words">{i.name}</p>
              <p className="text-sm text-muted">
                {shortDate(i.start_date)}
                {i.end_date ? ` to ${shortDate(i.end_date)}` : ''}
              </p>
              <p className={cn('mt-1 text-xs font-medium', i.places_left === 0 ? 'text-danger' : 'text-muted')}>{i.places_left === 0 ? 'Full' : i.places_left == null ? 'Places available' : `${i.places_left} places left`}</p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}
