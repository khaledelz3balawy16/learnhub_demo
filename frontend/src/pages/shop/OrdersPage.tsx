import { ReceiptText, RotateCcw } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Dialog, DialogClose, DialogContent } from '@/components/ui/dialog'
import { Field, Textarea } from '@/components/ui/input'
import { EmptyState, ErrorState } from '@/components/ui/misc'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { useBillingPortal, useOrders, useRefund } from '@/features/commerce/api'
import { usePublicSettings } from '@/features/platform/api'

type Order = NonNullable<ReturnType<typeof useOrders>['data']>['pages'][number]['items'][number]
import { money, shortDate } from '@/lib/format'
import { Link } from '@/lib/router'

const STATUS: Record<string, { label: string; tone: 'success' | 'warning' | 'neutral' | 'danger' }> = {
  paid: { label: 'Paid', tone: 'success' },
  partially_refunded: { label: 'Partly refunded', tone: 'warning' },
  refunded: { label: 'Refunded', tone: 'neutral' },
}

const PLAN_STATUS: Record<string, string> = {
  pending: 'Waiting for the first payment',
  active: 'Paying monthly',
  past_due: 'Payment overdue',
  completed: 'Paid in full',
  cancelled: 'Payments stopped',
}

/** A program paid monthly (M21): how far along, and a warning while a payment is overdue. */
function Instalments({ plan, currency, exponent }: { plan: NonNullable<Order['instalments']>; currency: string; exponent: number }) {
  const portal = useBillingPortal()
  return (
    <div className="grid gap-2 border-t border-border px-5 py-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">
          {plan.paid_count} of {plan.count} monthly payments of {money(plan.amount_minor, currency, exponent)}
        </span>
        <Badge tone={plan.status === 'past_due' ? 'danger' : plan.status === 'completed' ? 'success' : 'neutral'}>{PLAN_STATUS[plan.status] ?? plan.status}</Badge>
      </div>
      <Progress value={(plan.paid_count / plan.count) * 100} label="Monthly payments made" />
      {plan.status === 'past_due' ? (
        <p className="text-[13px] text-danger">
          Your last payment didn't go through.{plan.grace_until ? ` Update your card by ${shortDate(plan.grace_until)} to keep your access.` : ''}{' '}
          <Button variant="link" size="sm" className="h-auto text-[13px] text-danger" loading={portal.isPending} onClick={() => portal.mutate(undefined, { onSuccess: (r) => window.location.assign(r.url), onError: (e) => toast.error((e as Error).message) })}>
            Update your card
          </Button>
        </p>
      ) : null}
    </div>
  )
}

export function OrdersPage() {
  const { data, isLoading, error, refetch, hasNextPage, fetchNextPage, isFetchingNextPage } = useOrders()
  const refund = useRefund()
  const refundDays = usePublicSettings().settings['payments.refund_window_days']
  const [target, setTarget] = useState<{ id: string; title: string } | null>(null)
  const [reason, setReason] = useState('')
  const orders = data?.pages.flatMap((p) => p.items) ?? []

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight sm:text-[26px]">Purchase history</h1>
      <p className="mt-1 text-sm text-muted">Receipts for courses you bought. Refunds are possible within {refundDays} days.</p>
      {error ? (
        <ErrorState message={(error as Error).message} onRetry={() => void refetch()} />
      ) : isLoading ? (
        <div className="mt-6 grid gap-3">
          <Skeleton className="h-40 rounded-lg" />
          <Skeleton className="h-40 rounded-lg" />
        </div>
      ) : !orders.length ? (
        <Card className="mt-6 animate-reveal">
          <EmptyState icon={<ReceiptText />} title="No purchases yet" body="Courses you buy will show up here with their receipts." action={<Button asChild><Link to="/courses">Browse courses</Link></Button>} />
        </Card>
      ) : (
        <ul className="stagger mt-6 grid gap-4">
          {orders.map((o) => {
            const s = STATUS[o.status] ?? { label: o.status, tone: 'neutral' as const }
            return (
              <li key={o.id}>
                <Card>
                  <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
                    <div>
                      <p className="text-sm font-semibold">{o.paid_at ? shortDate(o.paid_at) : shortDate(o.created_at)}</p>
                      <p className="font-mono text-xs text-muted">Order {o.id.slice(0, 8).toUpperCase()}</p>
                    </div>
                    <div className="flex items-center gap-3">
                      <Badge tone={s.tone} dot>
                        {s.label}
                      </Badge>
                      <span className="text-lg font-semibold tabular">{money(o.total_minor, o.currency, o.exponent)}</span>
                    </div>
                  </div>
                  <ul className="divide-y divide-border">
                    {o.items.map((i) => (
                      <li key={i.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm">
                        <span className="min-w-0 flex-1">
                          <Link to={`/learn`} className="font-medium break-words hover:text-primary">
                            {i.course_title}
                          </Link>
                          {i.offer_label ? <span className="block text-xs text-muted">{i.offer_label}</span> : null}
                        </span>
                        <span className="text-muted tabular">{money(i.gross_minor, o.currency, o.exponent)}</span>
                        {i.refunded_at ? (
                          <Badge>Refunded {shortDate(i.refunded_at)}</Badge>
                        ) : i.refundable ? (
                          <Button size="sm" variant="ghost" onClick={() => (setReason(''), setTarget({ id: i.id, title: i.course_title }))}>
                            <RotateCcw /> Refund
                          </Button>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                  {o.instalments ? <Instalments plan={o.instalments} currency={o.currency} exponent={o.exponent} /> : null}
                </Card>
              </li>
            )
          })}
        </ul>
      )}
      {hasNextPage ? (
        <Button variant="secondary" className="mt-4" loading={isFetchingNextPage} onClick={() => void fetchNextPage()}>
          Show older orders
        </Button>
      ) : null}

      <Dialog open={!!target} onOpenChange={(o) => !o && setTarget(null)}>
        <DialogContent title={`Refund “${target?.title ?? ''}”?`} description="The money goes back to the card you paid with (usually 5–10 days) and the course is removed from your learning.">
          <Field label="Reason (optional)" hint="Helps the instructor improve the course.">
            {(p) => <Textarea {...p} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} />}
          </Field>
          <div className="mt-5 flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="secondary">Keep the course</Button>
            </DialogClose>
            <Button
              variant="danger"
              loading={refund.isPending}
              onClick={() =>
                target &&
                refund.mutate(
                  { itemId: target.id, reason },
                  { onSuccess: () => (toast.success('Refund issued'), setTarget(null)), onError: (e) => toast.error((e as Error).message) },
                )
              }
            >
              Refund
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
