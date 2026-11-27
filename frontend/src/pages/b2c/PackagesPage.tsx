import { BookOpen, Check, CheckCircle2, Clock, Info, Package, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Card, CardBody } from '@/components/ui/card'
import { EmptyState, ErrorState, PageHeader } from '@/components/ui/misc'
import { Skeleton } from '@/components/ui/skeleton'
import { useCashPackages, useMoney } from '@/features/b2c/api'
import type { ReviewItem } from '@/pages/b2c/CheckoutReviewPage'
import { cn } from '@/lib/cn'
import { Link, useNavigate } from '@/lib/router'

// Stripe returns to /packages?bought=<id>: the page polls until the server shows the
// bundle's courses as owned, never assuming success from the return URL.
const CANCEL = '/packages'

/** Cash course bundles: pay once, keep the courses. A full-price alternative to unlocking
 * with tokens or subscribing. */
export function PackagesPage() {
  const [params] = useSearchParams()
  const bought = params.get('bought')
  const { data, isLoading, error, refetch, isFetching } = useCashPackages(bought)
  const navigate = useNavigate()
  const fmt = useMoney()

  const buy = (pkg: { id: string; name: string; amount_minor: number; currency: string; courses: { id: string }[] }) => {
    const item: ReviewItem = {
      kind: 'package',
      packageId: pkg.id,
      name: pkg.name,
      courseCount: pkg.courses.length,
      amountMinor: pkg.amount_minor,
      currency: pkg.currency,
      successPath: `/packages?bought=${pkg.id}`,
      cancelPath: CANCEL,
    }
    navigate('/checkout/review', { state: item })
  }

  return (
    <div className="relative isolate min-h-[70vh]">
      <div className="relative mx-auto max-w-5xl px-4 py-8 sm:px-6">
        <PageHeader title="Course bundles" description="Buy a themed set of courses together, in one payment." />
        {bought ? <BoughtBanner pkg={data?.find((p) => p.id === bought)} loaded={!!data} checking={isFetching} recheck={() => void refetch()} /> : null}

        {isLoading ? (
          <div className="grid gap-4 md:grid-cols-2">
            <Skeleton className="h-56 rounded-lg" />
            <Skeleton className="h-56 rounded-lg" />
          </div>
        ) : error ? (
          <ErrorState message="We couldn't load the bundles." onRetry={() => void refetch()} />
        ) : !data?.length ? (
          <EmptyState
            icon={<Package />}
            title="No bundles available"
            body="There aren't any course bundles right now. You can still unlock courses with tokens or subscribe."
            action={
              <Button asChild>
                <Link to="/courses">Browse courses</Link>
              </Button>
            }
          />
        ) : (
          <div className="stagger grid gap-5 md:grid-cols-2">
            {data.map((pkg) => (
              <Card key={pkg.id} className={cn('flex flex-col overflow-hidden transition-shadow hover:shadow-md', pkg.id === bought && 'ring-2 ring-primary')}>
                <div className="flex items-center gap-3 border-b border-border bg-primary-soft/30 px-5 py-4">
                  <span className="flex size-10 items-center justify-center rounded-xl bg-primary text-on-primary">
                    <Package className="size-5" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-bold">{pkg.name}</p>
                    <p className="text-xs text-muted">
                      {pkg.courses.length} {pkg.courses.length === 1 ? 'course' : 'courses'}
                    </p>
                  </div>
                  <p className="text-xl font-bold">{fmt(pkg.amount_minor, pkg.currency)}</p>
                </div>
                <CardBody className="flex flex-1 flex-col">
                  {pkg.description ? <p className="text-sm text-muted">{pkg.description}</p> : null}
                  <ul className="mt-3 space-y-1.5 text-sm">
                    {pkg.courses.map((c) => (
                      <li key={c.id} className="flex items-start gap-2">
                        <Check className="mt-0.5 size-4 shrink-0 text-success" />
                        <Link to={`/courses/${c.slug}`} className="hover:text-primary hover:underline">
                          {c.title}
                        </Link>
                      </li>
                    ))}
                  </ul>
                  {pkg.owned_count > 0 ? (
                    <p className="mt-3 flex items-center gap-2 rounded-md bg-primary-soft/40 px-3 py-2 text-xs text-primary-soft-text">
                      <Info className="size-3.5 shrink-0" />
                      {pkg.owned_count >= pkg.courses.length
                        ? 'You already have access to all of these (e.g. via your subscription).'
                        : `You already have ${pkg.owned_count} of these ${pkg.courses.length} courses.`}
                    </p>
                  ) : null}
                  <div className="mt-auto flex gap-2 pt-5">
                    {pkg.owned_count >= pkg.courses.length ? (
                      <Button className="flex-1" variant="secondary" disabled>
                        Already yours
                      </Button>
                    ) : (
                      <Button className="flex-1" onClick={() => buy(pkg)}>
                        <BookOpen /> Buy bundle
                      </Button>
                    )}
                  </div>
                </CardBody>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

/** After paying for a bundle: confirming, ready, or taking longer than usual. */
function BoughtBanner({ pkg, loaded, checking, recheck }: { pkg?: { name: string; owned_count: number; courses: unknown[] }; loaded: boolean; checking: boolean; recheck: () => void }) {
  const ready = !!pkg && pkg.owned_count >= pkg.courses.length
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    const t = setTimeout(() => setSlow(true), 60_000) // the polling above stops after about a minute
    return () => clearTimeout(t)
  }, [])
  if (ready)
    return (
      <Card className="mb-6 animate-reveal border-success/40">
        <CardBody className="flex items-start gap-3">
          <CheckCircle2 className="mt-0.5 size-5 shrink-0 animate-pop text-success" />
          <div>
            <p className="font-semibold">{pkg.name} is yours</p>
            <p className="text-sm text-muted">
              Payment confirmed and a receipt is on its way. The courses are in{' '}
              <Link to="/learn" className="font-medium text-primary hover:underline">My learning</Link>.
            </p>
          </div>
        </CardBody>
      </Card>
    )
  return (
    <Card className="mb-6 animate-reveal" role="status">
      <CardBody className="flex flex-wrap items-start gap-3">
        <Clock className={cn('mt-0.5 size-5 shrink-0 text-primary', !slow && 'animate-pulse')} />
        <div className="min-w-0 flex-1">
          <p className="font-semibold">{slow || (loaded && !pkg) ? 'This is taking longer than usual' : 'Confirming your payment…'}</p>
          <p className="text-sm text-muted">
            {slow || (loaded && !pkg) ? "If Stripe took your payment, your courses unlock shortly. You won't be charged twice." : 'This usually takes a few seconds. This page updates itself.'}
          </p>
        </div>
        {slow || (loaded && !pkg) ? (
          <Button variant="secondary" size="sm" loading={checking} onClick={recheck}>
            <RefreshCw /> Check again
          </Button>
        ) : null}
      </CardBody>
    </Card>
  )
}
