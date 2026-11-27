/** Build a company's program seat order (M22, D8 and D10): pick a program or one of its
 * modules, live in an intake or recorded, and how many seats (at least the program's
 * minimum). Prices come from the server; the browser only sends ids and seat counts. */
import { CalendarDays, CreditCard, GraduationCap, Minus, Plus, ShoppingBag, Trash2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'

import type { ApiError } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardHeader } from '@/components/ui/card'
import { Field, Input, NativeSelect } from '@/components/ui/input'
import { EmptyState, ErrorState } from '@/components/ui/misc'
import { Skeleton } from '@/components/ui/skeleton'
import { money, shortDate } from '@/lib/format'

import { type DraftLine, type SeatProgram, type SeatSetup, useSaveDraft, useSeatCatalogue, useSeatCheckout } from './programSeats'

const MODE: Record<string, string> = { live: 'Live in a cohort', recorded: 'Recorded, self-paced' }

function AddLine({ program, onAdd }: { program: SeatProgram; onAdd: (l: DraftLine) => void }) {
  const [offerId, setOfferId] = useState(program.offers[0]?.id ?? '')
  const offer = program.offers.find((o) => o.id === offerId)
  const [cohort, setCohort] = useState(program.intakes[0]?.id ?? '')
  const [seats, setSeats] = useState(String(program.min_seats))
  const live = offer?.mode === 'live'
  const n = Number(seats)
  const intake = program.intakes.find((i) => i.id === cohort)
  const tooMany = live && intake?.places_left != null && n > intake.places_left
  const valid = !!offer && n >= program.min_seats && n <= 500 && (!live || (!!cohort && !tooMany))
  return (
    <form
      className="grid gap-3 sm:grid-cols-[minmax(0,1.6fr)_minmax(0,1.2fr)_7rem_auto] sm:items-end"
      onSubmit={(e) => {
        e.preventDefault()
        if (offer) onAdd({ offer_id: offer.id, cohort_id: live ? cohort : null, seats: n })
      }}
    >
      <Field label="What">
        {(p) => (
          <NativeSelect {...p} value={offerId} onChange={(e) => setOfferId(e.target.value)}>
            {program.offers.map((o) => (
              <option key={o.id} value={o.id}>
                {o.module_title ?? 'Whole program'} · {o.mode === 'live' ? 'live' : 'recorded'}
              </option>
            ))}
          </NativeSelect>
        )}
      </Field>
      {live ? (
        <Field label="Intake" error={tooMany ? `${intake?.places_left} places left` : undefined}>
          {(p) =>
            program.intakes.length ? (
              <NativeSelect {...p} value={cohort} onChange={(e) => setCohort(e.target.value)}>
                {program.intakes.map((i) => (
                  <option key={i.id} value={i.id} disabled={i.places_left === 0}>
                    {i.name}, starts {shortDate(i.start_date)}
                    {i.places_left != null ? ` (${i.places_left} left)` : ''}
                  </option>
                ))}
              </NativeSelect>
            ) : (
              <p {...p} className="rounded-md border border-dashed border-border px-3 py-2 text-sm text-muted">
                No intakes open yet
              </p>
            )
          }
        </Field>
      ) : (
        <div className="hidden sm:block" aria-hidden />
      )}
      <Field label="Seats" error={n && n < program.min_seats ? `At least ${program.min_seats}` : undefined}>
        {(p) => <Input {...p} type="number" inputMode="numeric" min={program.min_seats} max={500} value={seats} onChange={(e) => setSeats(e.target.value)} />}
      </Field>
      <Button type="submit" variant="secondary" disabled={!valid}>
        <Plus /> Add
      </Button>
    </form>
  )
}

/** The catalogue on the left, the order on the right; "Pay by card" saves it and opens Stripe. */
export function SeatOrderBuilder({ setup }: { setup: SeatSetup }) {
  const cat = useSeatCatalogue()
  const save = useSaveDraft()
  const pay = useSeatCheckout()
  const [lines, setLines] = useState<DraftLine[]>(() =>
    (setup.draft?.lines ?? []).map((l) => ({ offer_id: l.offer_id, cohort_id: l.cohort_id, seats: l.seats })),
  )
  const offers = useMemo(() => {
    const m = new Map<string, { program: SeatProgram; offer: SeatProgram['offers'][number] }>()
    for (const program of cat.data?.programs ?? []) for (const offer of program.offers) m.set(offer.id, { program, offer })
    return m
  }, [cat.data])
  const cur = setup.currency
  const exp = setup.exponent
  const total = lines.reduce((sum, l) => sum + (offers.get(l.offer_id)?.offer.unit_minor ?? 0) * l.seats, 0)
  const busy = save.isPending || pay.isPending

  const add = (l: DraftLine) =>
    setLines((ls) => {
      const same = ls.findIndex((x) => x.offer_id === l.offer_id && x.cohort_id === l.cohort_id)
      return same >= 0 ? ls.map((x, i) => (i === same ? { ...x, seats: Math.min(x.seats + l.seats, 500) } : x)) : [...ls, l]
    })
  const setSeats = (i: number, seats: number) => setLines((ls) => ls.map((x, j) => (j === i ? { ...x, seats } : x)))

  const checkout = async () => {
    try {
      await save.mutateAsync(lines)
      const { checkout_url } = await pay.mutateAsync()
      window.location.assign(checkout_url)
    } catch (e) {
      const err = e as ApiError
      // prices moved since the order was built: saving it again picks up today's prices
      if (err.code === 'prices_changed') await save.mutateAsync(lines).catch(() => undefined)
      toast.error(err.message)
    }
  }

  if (cat.error) return <ErrorState message={(cat.error as Error).message} onRetry={() => void cat.refetch()} />
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-start">
      <div className="grid gap-4">
        {!cat.data ? (
          [0, 1].map((i) => <Skeleton key={i} className="h-40" />)
        ) : !cat.data.programs.length ? (
          <EmptyState icon={<GraduationCap />} title="No programs on sale yet" body="Your training provider hasn't put any programs on sale. Please check back soon." />
        ) : (
          <div className="stagger grid gap-4">
            {cat.data.programs.map((p) => (
              <Card key={p.id} className="p-5">
                <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h3 className="font-semibold tracking-tight break-words">{p.title}</h3>
                    <p className="text-sm text-muted">At least {p.min_seats} seats for each item.</p>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {[...new Set(p.offers.map((o) => o.mode))].map((m) => (
                      <Badge key={m} tone={m === 'live' ? 'info' : 'neutral'}>
                        {MODE[m]}
                      </Badge>
                    ))}
                  </div>
                </div>
                <ul className="mb-4 grid gap-1 text-sm">
                  {p.offers.map((o) => (
                    <li key={o.id} className="flex justify-between gap-3">
                      <span className="min-w-0 break-words text-muted">
                        {o.module_title ?? 'Whole program'}, {o.mode === 'live' ? 'live' : 'recorded'}
                      </span>
                      <span className="shrink-0 tabular font-medium">{money(o.unit_minor, cur, exp)} a seat</span>
                    </li>
                  ))}
                </ul>
                <AddLine program={p} onAdd={add} />
              </Card>
            ))}
          </div>
        )}
      </div>

      <Card className="lg:sticky lg:top-20">
        <CardHeader title="Your order" description="Card payment. Your workspace opens as soon as it is paid." />
        <div className="grid gap-3 p-5">
          {!lines.length ? (
            <p className="flex items-center gap-2 text-sm text-muted">
              <ShoppingBag className="size-4" /> Add a program or a module to start.
            </p>
          ) : (
            <ul className="stagger grid gap-3" aria-label="Order lines">
              {lines.map((l, i) => {
                const found = offers.get(l.offer_id)
                const intake = found?.program.intakes.find((x) => x.id === l.cohort_id)
                const least = found?.program.min_seats ?? 1
                return (
                  <li key={`${l.offer_id}-${l.cohort_id}`} className="grid gap-1.5 border-b border-border pb-3 last:border-0 last:pb-0">
                    <div className="flex items-start justify-between gap-2">
                      <span className="min-w-0 text-sm font-medium break-words">
                        {found ? `${found.program.title}${found.offer.module_title ? `: ${found.offer.module_title}` : ''}` : 'No longer on sale'}
                      </span>
                      <Button size="icon" variant="ghost" aria-label="Remove from order" onClick={() => setLines((ls) => ls.filter((_, j) => j !== i))}>
                        <Trash2 />
                      </Button>
                    </div>
                    <span className="flex items-center gap-1.5 text-xs text-muted">
                      {intake ? (
                        <>
                          <CalendarDays className="size-3.5" /> {intake.name}, {shortDate(intake.start_date)}
                        </>
                      ) : (
                        'Recorded'
                      )}
                    </span>
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1" role="group" aria-label="Seats">
                        <Button size="icon" variant="secondary" aria-label="One seat fewer" disabled={l.seats <= least} onClick={() => setSeats(i, l.seats - 1)}>
                          <Minus />
                        </Button>
                        <span className="w-10 text-center tabular text-sm" aria-live="polite">
                          {l.seats}
                        </span>
                        <Button size="icon" variant="secondary" aria-label="One seat more" disabled={l.seats >= 500} onClick={() => setSeats(i, l.seats + 1)}>
                          <Plus />
                        </Button>
                      </div>
                      <span className="tabular text-sm font-medium">{found ? money(found.offer.unit_minor * l.seats, cur, exp) : '—'}</span>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
          <div className="flex items-center justify-between border-t border-border pt-3">
            <span className="text-sm text-muted">Total</span>
            <span className="text-lg font-semibold tabular">{money(total, cur, exp)}</span>
          </div>
          <Button onClick={() => void checkout()} loading={busy} disabled={!lines.length || lines.some((l) => !offers.has(l.offer_id))}>
            <CreditCard /> Pay by card
          </Button>
          <p className="text-xs text-muted">You'll pay on Stripe's secure page. Prices are checked again before you pay.</p>
        </div>
      </Card>
    </div>
  )
}
