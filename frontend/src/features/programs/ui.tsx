import { CalendarOff, Trash2 } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Field, Input } from '@/components/ui/input'
import { dayRange } from '@/lib/schedule'
import type { components } from '@/api/schema'

import { useAddClosure, useDeleteClosure } from './api'

// ---------------------------------------------------------------- closures
type ClosureRow = components['schemas']['ConsoleCohortClosureOut']

export function useClosureActions() {
  return { add: useAddClosure(), remove: useDeleteClosure() }
}

export function ClosureRows({ rows, onRemove, canManage = true }: { rows: ClosureRow[]; onRemove: (id: string) => void; canManage?: boolean }) {
  return (
    <ul className="stagger divide-y divide-border">
      {rows.map((c) => (
        <li key={c.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
          <CalendarOff className="size-4 shrink-0 text-subtle" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{c.reason}</p>
            <p className="text-xs text-muted tabular">{dayRange(c.starts_on, c.ends_on)}</p>
          </div>
          {c.provider_wide ? <Badge tone="neutral">Every cohort</Badge> : null}
          {canManage ? (
            <Button variant="ghost" size="icon" aria-label={`Remove closure: ${c.reason}`} onClick={() => onRemove(c.id)}>
              <Trash2 />
            </Button>
          ) : null}
        </li>
      ))}
    </ul>
  )
}

/** Add a closure for one cohort, or (cohortId null) for every cohort. */
export function ClosureDialog({ open, onOpenChange, cohortId }: { open: boolean; onOpenChange: (o: boolean) => void; cohortId: string | null }) {
  const add = useAddClosure()
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [reason, setReason] = useState('')
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (to < from) return toast.error('The end date must be on or after the start date.')
    add.mutate(
      { cohort_id: cohortId, starts_on: from, ends_on: to, reason: reason.trim() },
      {
        onSuccess: () => {
          toast.success('Closure added. Week dates were worked out again.')
          onOpenChange(false)
          setFrom('')
          setTo('')
          setReason('')
        },
        onError: (e) => toast.error((e as Error).message),
      },
    )
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={cohortId ? 'Close this cohort for a while' : 'Close for every cohort'} description="A week with no teaching day left is skipped, and later weeks move on.">
        <form className="grid gap-4" onSubmit={submit}>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="From">{(p) => <Input {...p} type="date" value={from} onChange={(e) => setFrom(e.target.value)} required />}</Field>
            <Field label="To">{(p) => <Input {...p} type="date" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} required />}</Field>
          </div>
          <Field label="Reason" hint="Learners see this on their timetable.">
            {(p) => <Input {...p} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Christmas closure" minLength={2} maxLength={200} required />}
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={add.isPending}>
              Add closure
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
