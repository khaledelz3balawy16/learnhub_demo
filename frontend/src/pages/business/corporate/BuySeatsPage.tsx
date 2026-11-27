import { ArrowLeft } from 'lucide-react'

import { ErrorState, PageHeader } from '@/components/ui/misc'
import { Skeleton } from '@/components/ui/skeleton'
import { useSeatSetup } from '@/features/corporate/programSeats'
import { SeatOrderBuilder } from '@/features/corporate/SeatOrderBuilder'
import { Link } from '@/lib/router'

/** /business/program-seats/buy (M22): more program seats for an open workspace. The same order
 * builder the company signup uses; owners and admins only (the server checks). */
export function BuySeatsPage() {
  const setup = useSeatSetup()
  return (
    <>
      <PageHeader
        title="Buy program seats"
        description="Choose programs or single modules, live or recorded, and how many seats."
        back={
          <Link to="/business/program-seats" className="mb-2 inline-flex items-center gap-1 text-sm text-muted hover:text-text">
            <ArrowLeft className="size-4" /> Program seats
          </Link>
        }
      />
      {setup.error ? (
        <ErrorState message={(setup.error as Error).message} onRetry={() => void setup.refetch()} />
      ) : !setup.data ? (
        <Skeleton className="h-64" />
      ) : (
        <div className="animate-reveal">
          <SeatOrderBuilder setup={setup.data} />
        </div>
      )}
    </>
  )
}
