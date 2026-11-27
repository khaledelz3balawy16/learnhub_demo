import { Check, Coins, Lock, RefreshCw, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { ApiError } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogContent, DialogTrigger } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { useAccess, useUnlock, useWalletBalance, type UnlockScope } from '@/features/b2c/api'
import { count } from '@/lib/format'
import { Link } from '@/lib/router'

// keys are the access resolver's sources (backend apps/platform/access.py)
const SOURCE_LABEL: Record<string, string> = {
  legacy_purchase: 'You already own this',
  cash_package: 'Included in a package you bought',
  CHANGE_ME: 'Unlocked with tokens',
  CHANGE_ME: 'Unlocked with tokens',
  subscription: 'Included in your subscription',
  preview: 'Free preview',
  admin_grant: 'Granted by our team',
}

const SCOPE_NOUN: Record<UnlockScope, string> = { course: 'course', lecture: 'lecture', material: 'material' }

/** The single gate for paid B2C content. The server's access resolver decides whether to
 * show an unlock prompt at all — so a person who already has access (through a subscription,
 * a package, a legacy purchase or a previous unlock) is never asked to pay again. Spending is
 * confirmed explicitly and only ever committed by the server (no optimistic unlock). */
export function UnlockButton({
  scope,
  targetId,
  tokenPrice,
  title,
  size = 'md',
  className,
  skeletonClassName,
  onUnlocked,
}: {
  scope: UnlockScope
  targetId: string
  tokenPrice: number | null | undefined
  title?: string
  size?: 'sm' | 'md' | 'lg'
  className?: string
  /** Size of the placeholder while access loads (defaults to the button's size). */
  skeletonClassName?: string
  onUnlocked?: () => void
}) {
  const access = useAccess(scope, targetId)
  const balance = useWalletBalance()
  const unlock = useUnlock()
  const [open, setOpen] = useState(false)

  if (access.isLoading) return <Skeleton className={skeletonClassName ?? className ?? 'h-10 w-40 rounded-md'} />

  // Resolver is the authority: if access is granted, show how — never a purchase prompt.
  if (access.data?.allowed) {
    return (
      <Badge tone="success" className={className}>
        <Check /> {SOURCE_LABEL[access.data.source] ?? 'Unlocked'}
      </Badge>
    )
  }

  // Not accessible and no token price set → unlocking isn't offered for this item.
  if (tokenPrice == null || tokenPrice <= 0) {
    return (
      <Badge tone="neutral" className={className}>
        <Lock /> Locked
      </Badge>
    )
  }

  // never treat an unknown balance as 0: wait for it, or say it failed
  const known = balance.data != null
  const bal = balance.data?.balance ?? 0
  const affordable = known && bal >= tokenPrice
  const after = bal - tokenPrice

  const confirm = () => {
    unlock.mutate(
      { scope, targetId },
      {
        onSuccess: () => {
          toast.success(`${title ? `“${title}”` : `This ${SCOPE_NOUN[scope]}`} is unlocked.`)
          setOpen(false)
          onUnlocked?.()
        },
        onError: (e) => {
          // Already unlocked elsewhere (e.g. another tab): treat as success, refresh access.
          if (e instanceof ApiError && e.status === 409) {
            toast.success('Already unlocked.')
            setOpen(false)
            void access.refetch()
            onUnlocked?.()
            return
          }
          toast.error((e as Error).message)
        },
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size={size} className={className}>
          <Coins /> Unlock · {count(tokenPrice)} {tokenPrice === 1 ? 'token' : 'CHANGE_ME'}
        </Button>
      </DialogTrigger>
      <DialogContent title={`Unlock this ${SCOPE_NOUN[scope]}?`} description={title}>
        <div className="space-y-4">
          <div className="rounded-lg border border-border bg-surface-2/50 p-4">
            <Row label="Cost" value={`${count(tokenPrice)} tokens`} strong />
            {known ? <Row label="Your balance" value={`${count(bal)} tokens`} /> : null}
            {affordable ? <Row label="After unlocking" value={`${count(after)} tokens`} /> : null}
          </div>

          {!known ? (
            balance.isError ? (
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">
                <span>We couldn't load your token balance.</span>
                <Button size="sm" variant="secondary" loading={balance.isFetching} onClick={() => void balance.refetch()}>
                  <RefreshCw /> Try again
                </Button>
              </div>
            ) : (
              <Skeleton className="h-9 rounded-md" />
            )
          ) : affordable ? (
            <>
              <p className="flex items-start gap-2 text-sm text-muted">
                <Sparkles className="mt-0.5 size-4 shrink-0 text-primary" />
                Tokens are spent oldest-expiring first. This can't be undone, and you won't be asked to pay for it again.
              </p>
              <div className="flex justify-end gap-2">
                <DialogClose asChild>
                  <Button variant="secondary">Cancel</Button>
                </DialogClose>
                <Button onClick={confirm} loading={unlock.isPending}>
                  Confirm unlock
                </Button>
              </div>
            </>
          ) : (
            <>
              <p className="rounded-md bg-warning-soft px-3 py-2 text-sm text-warning">
                You need {count(tokenPrice - bal)} more {tokenPrice - bal === 1 ? 'token' : 'CHANGE_ME'} to unlock this.
              </p>
              <div className="flex justify-end gap-2">
                <DialogClose asChild>
                  <Button variant="secondary">Cancel</Button>
                </DialogClose>
                <Button asChild>
                  <Link to="/wallet/buy">
                    <Coins /> Buy tokens
                  </Link>
                </Button>
              </div>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="flex items-center justify-between py-1 text-sm">
      <span className="text-muted">{label}</span>
      <span className={strong ? 'font-semibold' : 'tabular-nums'}>{value}</span>
    </div>
  )
}
