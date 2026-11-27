import { ArrowLeftRight, Check, X } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Field, Textarea } from '@/components/ui/input'
import { EmptyState, ErrorState, PageHeader } from '@/components/ui/misc'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { type ConsoleSeatSwap, useConsoleDecideSwap, useConsoleSeatSwaps } from '@/features/corporate/programSeats'
import { StatusBadge } from '@/features/corporate/ui'
import { shortDate } from '@/lib/format'

const STATUS = {
  approved: { label: 'Approved', tone: 'success' },
  rejected: { label: 'Rejected', tone: 'danger' },
  cancelled: { label: 'Cancelled', tone: 'neutral' },
  pending_provider: { label: 'Waiting', tone: 'warning' },
} as const

function Decide({ swap, approve, onClose }: { swap: ConsoleSeatSwap; approve: boolean; onClose: () => void }) {
  const decide = useConsoleDecideSwap()
  const [note, setNote] = useState('')
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        title={approve ? 'Approve this swap?' : 'Reject this swap?'}
        description={approve ? `${swap.to_name} gets the seat now. ${swap.from_name} loses access; their progress stays on record.` : 'Nothing changes. The company sees your note.'}
      >
        <div className="grid gap-4">
          <Field label="Note to the company (optional)">{(p) => <Textarea {...p} rows={3} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button
              variant={approve ? 'primary' : 'danger'}
              loading={decide.isPending}
              onClick={() =>
                decide.mutate(
                  { id: swap.id, approve, note: note.trim() },
                  {
                    onSuccess: () => {
                      toast.success(approve ? 'Seat moved' : 'Swap rejected')
                      onClose()
                    },
                    onError: (e) => toast.error((e as Error).message),
                  },
                )
              }
            >
              {approve ? <Check /> : <X />} {approve ? 'Approve' : 'Reject'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function SwapCard({ s, onDecide }: { s: ConsoleSeatSwap; onDecide?: (approve: boolean) => void }) {
  return (
    <Card className="grid gap-3 p-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
      <div className="grid min-w-0 gap-1.5">
        <p className="text-xs text-muted">
          {s.org_name} · {shortDate(s.created_at)}
        </p>
        <p className="font-medium break-words">
          {s.program_title}
          {s.module_title ? `: ${s.module_title}` : ''}
          <span className="text-sm font-normal text-muted"> · {s.mode === 'live' ? `live${s.cohort_name ? `, ${s.cohort_name}` : ''}` : 'recorded'}</span>
        </p>
        <p className="flex flex-wrap items-center gap-1.5 text-sm">
          <span className="break-all">{s.from_name}</span>
          <ArrowLeftRight className="size-3.5 text-muted" aria-label="to" />
          <span className="break-all">{s.to_name}</span>
        </p>
        <div className="max-w-xs">
          <Progress value={s.from_progress_pct} label={`${s.from_name} is ${Math.round(s.from_progress_pct)}% through`} />
        </div>
        {s.reason ? <p className="text-sm break-words">“{s.reason}”</p> : null}
        <p className="flex flex-wrap gap-1.5 text-xs text-muted">
          Asked by {s.requested_by_name}
          {s.company_by_name ? `, approved by ${s.company_by_name}` : ''}
          {s.after_cutoff ? <Badge tone="warning">Past the cut-off</Badge> : null}
        </p>
        {s.decision_note ? <p className="text-xs text-muted break-words">Note: {s.decision_note}</p> : null}
      </div>
      {onDecide ? (
        <div className="flex gap-2 sm:flex-col">
          <Button size="sm" onClick={() => onDecide(true)}>
            <Check /> Approve
          </Button>
          <Button size="sm" variant="secondary" onClick={() => onDecide(false)}>
            <X /> Reject
          </Button>
        </div>
      ) : (
        <StatusBadge map={STATUS} status={s.status} />
      )}
    </Card>
  )
}

/** Console › Seat swaps (M22, D11): the provider's step. Needs the "Approve company seat swaps"
 * permission (the server checks it). */
export function ConsoleSeatSwapsPage() {
  const [tab, setTab] = useState('waiting')
  const q = useConsoleSeatSwaps(tab === 'waiting')
  const [deciding, setDeciding] = useState<{ swap: ConsoleSeatSwap; approve: boolean } | null>(null)
  return (
    <>
      <PageHeader title="Seat swaps" description="Companies asking to move a program seat from one person to another. Their company has already approved." />
      <Tabs value={tab} onValueChange={setTab} className="mb-4">
        <TabsList>
          <TabsTrigger value="waiting">Waiting</TabsTrigger>
          <TabsTrigger value="decided">Decided</TabsTrigger>
        </TabsList>
      </Tabs>
      {q.error ? (
        <ErrorState message={(q.error as Error).message} onRetry={() => void q.refetch()} />
      ) : !q.data ? (
        <div className="grid gap-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      ) : !q.data.items.length ? (
        <EmptyState icon={<ArrowLeftRight />} title={tab === 'waiting' ? 'No swaps waiting' : 'No decided swaps yet'} body="When a company asks to move a seat, it shows here." />
      ) : (
        <div className="stagger grid gap-3 animate-reveal">
          {q.data.items.map((s) => (
            <SwapCard key={s.id} s={s} onDecide={tab === 'waiting' ? (approve) => setDeciding({ swap: s, approve }) : undefined} />
          ))}
        </div>
      )}
      {deciding ? <Decide swap={deciding.swap} approve={deciding.approve} onClose={() => setDeciding(null)} /> : null}
    </>
  )
}
