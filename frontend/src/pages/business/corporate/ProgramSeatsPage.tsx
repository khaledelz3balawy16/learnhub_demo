import { Armchair, ArrowLeftRight, CalendarDays, Check, ShoppingCart, Undo2, UserPlus, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'

import { Avatar } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardHeader } from '@/components/ui/card'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Field, Textarea } from '@/components/ui/input'
import { PageHeader } from '@/components/ui/misc'
import { Progress } from '@/components/ui/progress'
import { Table, Td, Th, Tr } from '@/components/ui/table'
import {
  type SeatHolder,
  type SeatLine,
  type SeatSwap,
  useCancelSwap,
  useDecideSwap,
  useGiveSeat,
  useReleaseSeat,
  useRequestSwap,
  useSeatHolders,
  useSeatOrders,
  useSeatSwaps,
} from '@/features/corporate/programSeats'
import { PersonPicker, QueryBlock, StatusBadge } from '@/features/corporate/ui'
import { cn } from '@/lib/cn'
import { money, shortDate } from '@/lib/format'
import { Link } from '@/lib/router'

const ORDER_STATUS = {
  draft: { label: 'Being built', tone: 'neutral' },
  pending: { label: 'Waiting for payment', tone: 'warning' },
  paid: { label: 'Paid', tone: 'success' },
  expired: { label: 'Not paid', tone: 'neutral' },
} as const
const HOLDER_STATUS = {
  active: { label: 'Has the seat', tone: 'success' },
  released: { label: 'Released', tone: 'neutral' },
  swapped: { label: 'Swapped', tone: 'neutral' },
} as const
const SWAP_STATUS = {
  pending_company: { label: 'Waiting for your company', tone: 'warning' },
  pending_provider: { label: 'Waiting for the provider', tone: 'info' },
  approved: { label: 'Approved', tone: 'success' },
  rejected: { label: 'Not approved', tone: 'danger' },
  cancelled: { label: 'Cancelled', tone: 'neutral' },
} as const

const lineTitle = (l: SeatLine) => `${l.program_title}${l.module_title ? `: ${l.module_title}` : ''}`

function LineCard({ line, selected, onSelect }: { line: SeatLine; selected: boolean; onSelect: () => void }) {
  const free = line.seats - line.used
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        'grid gap-3 rounded-xl border bg-surface p-4 text-left transition-[border-color,box-shadow] duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
        selected ? 'border-primary shadow-md' : 'border-border hover:shadow-sm',
      )}
    >
      <span className="line-clamp-2 font-semibold break-words">{lineTitle(line)}</span>
      <span className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
        <Badge tone={line.mode === 'live' ? 'info' : 'neutral'}>{line.mode === 'live' ? 'Live' : 'Recorded'}</Badge>
        {line.cohort_name ? (
          <span className="inline-flex items-center gap-1">
            <CalendarDays className="size-3.5" /> {line.cohort_name}
            {line.cohort_start ? `, ${shortDate(line.cohort_start)}` : ''}
          </span>
        ) : null}
      </span>
      <Progress value={line.seats ? Math.round((line.used / line.seats) * 100) : 0} label={`${line.used} of ${line.seats} seats given`} />
      <span className="flex justify-between text-sm">
        <span className="text-muted">
          {line.used} of {line.seats} given
        </span>
        <span className={free ? 'font-medium text-success' : 'text-muted'}>{free} free</span>
      </span>
    </button>
  )
}

function GiveSeat({ line, holders }: { line: SeatLine; holders: string[] }) {
  const [open, setOpen] = useState(false)
  const give = useGiveSeat()
  const full = line.used >= line.seats
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button size="sm" onClick={() => setOpen(true)} disabled={full} title={full ? 'No free seats left' : undefined}>
        <UserPlus /> Give a seat
      </Button>
      <DialogContent title={`Give a seat: ${lineTitle(line)}`} description={line.cohort_name ? `They join ${line.cohort_name} in the group with the most room.` : 'They can start straight away.'}>
        <PersonPicker
          label="Who should get it?"
          exclude={holders}
          disabled={give.isPending}
          onPick={(p) =>
            give.mutate(
              { line_id: line.id, user_id: p.user_id },
              {
                onSuccess: () => {
                  toast.success(`${p.name || p.email} has a seat`)
                  setOpen(false)
                },
                onError: (e) => toast.error((e as Error).message),
              },
            )
          }
        />
      </DialogContent>
    </Dialog>
  )
}

function SwapDialog({ holder, holders, onClose }: { holder: SeatHolder; holders: string[]; onClose: () => void }) {
  const swap = useRequestSwap()
  const [to, setTo] = useState<{ user_id: string; name: string; email: string } | null>(null)
  const [reason, setReason] = useState('')
  const needsReason = holder.past_cutoff && reason.trim().length < 10
  const send = () =>
    to &&
    swap.mutate(
      { id: holder.id, to_user_id: to.user_id, reason: reason.trim() },
      {
        onSuccess: (s) => {
          toast.success(s.status === 'pending_provider' ? 'Swap sent to your training provider' : 'Swap sent for your company to approve')
          onClose()
        },
        onError: (e) => toast.error((e as Error).message),
      },
    )
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title={`Swap ${holder.name}'s seat`} description="Your company and then your training provider approve the swap. Their progress stays on record.">
        <div className="grid gap-4">
          {to ? (
            <div className="flex items-center justify-between gap-2 rounded-lg border border-border p-3">
              <span className="flex min-w-0 items-center gap-2.5">
                <Avatar name={to.name || to.email} size="sm" />
                <span className="min-w-0 truncate text-sm font-medium">{to.name || to.email}</span>
              </span>
              <Button size="sm" variant="ghost" onClick={() => setTo(null)}>
                Change
              </Button>
            </div>
          ) : (
            <PersonPicker label="Who should take the seat?" exclude={holders} onPick={setTo} />
          )}
          <Field label={holder.past_cutoff ? 'Why does the seat need to move?' : 'Reason (optional)'} hint={holder.past_cutoff ? 'This seat is past the swap cut-off, so a reason is needed.' : undefined}>
            {(p) => <Textarea {...p} rows={3} maxLength={2000} value={reason} onChange={(e) => setReason(e.target.value)} />}
          </Field>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button onClick={send} loading={swap.isPending} disabled={!to || needsReason}>
              <ArrowLeftRight /> Request swap
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function Holders({ line }: { line: SeatLine }) {
  const q = useSeatHolders(line.id)
  const release = useReleaseSeat()
  const [swapping, setSwapping] = useState<SeatHolder | null>(null)
  const active = (q.data?.items ?? []).filter((h) => h.status === 'active').map((h) => h.user_id)
  return (
    <Card>
      <CardHeader title={lineTitle(line)} description="People with one of these seats" action={<GiveSeat line={line} holders={active} />} />
      <QueryBlock query={{ ...q, data: q.data?.items }} empty={{ icon: <Armchair />, title: 'No seats given yet', body: 'Give a seat to someone in your company to start them.' }}>
        {(items) => (
          <Table>
            <thead>
              <tr>
                <Th>Person</Th>
                <Th className="hidden sm:table-cell">Progress</Th>
                <Th className="hidden md:table-cell">Status</Th>
                <Th className="w-24">
                  <span className="sr-only">Actions</span>
                </Th>
              </tr>
            </thead>
            <tbody className="stagger">
              {items.map((h) => (
                <Tr key={h.id}>
                  <Td>
                    <span className="flex min-w-0 items-center gap-2.5">
                      <Avatar name={h.name} size="sm" />
                      <span className="min-w-0">
                        <span className="block truncate font-medium">{h.name}</span>
                        <span className="block truncate text-xs text-muted">{h.email}</span>
                      </span>
                    </span>
                  </Td>
                  <Td className="hidden w-40 sm:table-cell">
                    <Progress value={h.progress_pct} label={`${Math.round(h.progress_pct)}% done`} />
                  </Td>
                  <Td className="hidden md:table-cell">
                    {h.open_swap_id ? <Badge tone="warning">Swap waiting</Badge> : <StatusBadge map={HOLDER_STATUS} status={h.status} />}
                  </Td>
                  <Td>
                    {h.status === 'active' ? (
                      <span className="flex justify-end gap-1">
                        <Button size="icon" variant="ghost" aria-label={`Swap ${h.name}'s seat`} title="Swap seat" disabled={!!h.open_swap_id} onClick={() => setSwapping(h)}>
                          <ArrowLeftRight />
                        </Button>
                        {q.data?.can_release && !h.started ? (
                          <Button
                            size="icon"
                            variant="ghost"
                            aria-label={`Take back ${h.name}'s seat`}
                            title="Take back (not started yet)"
                            disabled={release.isPending || !!h.open_swap_id}
                            onClick={() => release.mutate(h.id, { onSuccess: () => toast.success('Seat taken back'), onError: (e) => toast.error((e as Error).message) })}
                          >
                            <Undo2 />
                          </Button>
                        ) : null}
                      </span>
                    ) : null}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </QueryBlock>
      {swapping ? <SwapDialog holder={swapping} holders={active} onClose={() => setSwapping(null)} /> : null}
    </Card>
  )
}

function SwapRow({ s }: { s: SeatSwap }) {
  const decide = useDecideSwap()
  const cancel = useCancelSwap()
  const done = (msg: string) => ({ onSuccess: () => toast.success(msg), onError: (e: unknown) => toast.error((e as Error).message) })
  return (
    <li className="grid gap-2 border-b border-border px-5 py-4 last:border-0 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
      <div className="min-w-0">
        <p className="text-sm font-medium break-words">
          {s.from_name} → {s.to_name}
        </p>
        <p className="text-xs text-muted break-words">
          {s.program_title}
          {s.module_title ? `: ${s.module_title}` : ''} · asked by {s.requested_by_name}
          {s.after_cutoff ? ' · past the cut-off' : ''}
        </p>
        {s.reason ? <p className="mt-1 text-sm break-words">“{s.reason}”</p> : null}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge map={SWAP_STATUS} status={s.status} />
        {s.can_decide ? (
          <>
            <Button size="sm" onClick={() => decide.mutate({ id: s.id, approve: true, note: '' }, done('Swap approved. It now goes to your training provider.'))} loading={decide.isPending}>
              <Check /> Approve
            </Button>
            <Button size="sm" variant="secondary" onClick={() => decide.mutate({ id: s.id, approve: false, note: '' }, done('Swap turned down'))} disabled={decide.isPending}>
              <X /> Turn down
            </Button>
          </>
        ) : null}
        {s.can_cancel ? (
          <Button size="sm" variant="ghost" onClick={() => cancel.mutate(s.id, done('Swap cancelled'))} loading={cancel.isPending}>
            Cancel
          </Button>
        ) : null}
      </div>
    </li>
  )
}

/** /business/program-seats (M22): the company's program seat orders, who holds each seat,
 * seat swaps waiting for someone, and "Buy more seats". */
export function ProgramSeatsPage() {
  const [params] = useSearchParams()
  const orders = useSeatOrders()
  const swaps = useSeatSwaps(true)
  const lines = (orders.data?.items ?? []).filter((o) => o.status === 'paid').flatMap((o) => o.lines)
  const [selected, setSelected] = useState<string | null>(null)
  const line = lines.find((l) => l.id === selected) ?? lines[0]
  const waiting = (orders.data?.items ?? []).some((o) => o.status === 'pending')
  const paid = params.get('paid') === '1'
  const refetch = orders.refetch
  useEffect(() => {
    if (!paid || !waiting) return
    const t = setInterval(() => void refetch(), 3000) // the webhook lands a moment after Stripe sends you back
    return () => clearInterval(t)
  }, [paid, waiting, refetch])
  const buy = orders.data?.can_buy ? (
    <Button asChild>
      <Link to="/business/program-seats/buy">
        <ShoppingCart /> Buy more seats
      </Link>
    </Button>
  ) : undefined

  return (
    <>
      <PageHeader title="Program seats" description="Give seats to your people, swap them, and see what you have bought." actions={buy} />
      {paid && waiting ? (
        <Card className="mb-4 p-4 text-sm" role="status">
          Confirming your payment. Your new seats appear here in a moment.
        </Card>
      ) : null}
      {swaps.data?.items.length ? (
        <Card className="mb-5 animate-reveal">
          <CardHeader title="Seat swaps waiting" description="Swaps need your company's approval, then your training provider's." />
          <ul className="stagger mt-2">
            {swaps.data.items.map((s) => (
              <SwapRow key={s.id} s={s} />
            ))}
          </ul>
        </Card>
      ) : null}
      <QueryBlock query={{ ...orders, data: orders.data ? lines : undefined }} empty={{ icon: <Armchair />, title: 'No program seats yet', body: 'Buy seats on a program or a module, then give them to your people.', action: buy }}>
        {() => (
          <div className="grid gap-5">
            <div className="stagger grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {lines.map((l) => (
                <LineCard key={l.id} line={l} selected={l.id === line?.id} onSelect={() => setSelected(l.id)} />
              ))}
            </div>
            {line ? <Holders key={line.id} line={line} /> : null}
            <Card>
              <CardHeader title="Orders" />
              <Table>
                <thead>
                  <tr>
                    <Th>Date</Th>
                    <Th className="hidden sm:table-cell">Items</Th>
                    <Th>Total</Th>
                    <Th>Status</Th>
                  </tr>
                </thead>
                <tbody>
                  {(orders.data?.items ?? []).map((o) => (
                    <Tr key={o.id}>
                      <Td className="whitespace-nowrap">{shortDate(o.paid_at ?? o.created_at)}</Td>
                      <Td className="hidden sm:table-cell">{o.lines.reduce((n, l) => n + l.seats, 0)} seats</Td>
                      <Td className="tabular">{money(o.total_minor, o.currency, orders.data?.exponent)}</Td>
                      <Td>
                        <StatusBadge map={ORDER_STATUS} status={o.status} />
                      </Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            </Card>
          </div>
        )}
      </QueryBlock>
    </>
  )
}
