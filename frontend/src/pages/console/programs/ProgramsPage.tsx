import { CalendarOff, GraduationCap, Plus, RefreshCw, Search } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { toast } from 'sonner'

import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardHeader } from '@/components/ui/card'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Field, Input } from '@/components/ui/input'
import { EmptyState, ErrorState, PageHeader } from '@/components/ui/misc'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, Td, Th, Tr } from '@/components/ui/table'
import { ConfirmDialog, StatusPill } from '@/features/console/ui'
import { useDebounced } from '@/features/org/ui'
import { useCreateProgram, usePrograms, useProviderClosures, useSyncHolidays } from '@/features/programs/api'
import { ClosureDialog, ClosureRows, useClosureActions } from '@/features/programs/ui'
import { shortDate } from '@/lib/format'
import { Link, useNavigate } from '@/lib/router'

const err = (e: unknown) => toast.error((e as Error).message)

function NewProgram({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const create = useCreateProgram()
  const navigate = useNavigate()
  const [title, setTitle] = useState('')
  const submit = (e: FormEvent) => {
    e.preventDefault()
    create.mutate(title.trim(), {
      onSuccess: (r) => {
        toast.success('Program created. Add its modules and weeks.')
        onOpenChange(false)
        setTitle('')
        navigate(`/studio/courses/${r.id}/curriculum`)
      },
      onError: err,
    })
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="New program" description="For example a professional certificate or an MBA. You'll add modules and weeks next.">
        <form className="grid gap-4" onSubmit={submit}>
          <Field label="Program name">{(p) => <Input {...p} value={title} onChange={(e) => setTitle(e.target.value)} minLength={3} maxLength={160} required autoFocus />}</Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending}>
              Create program
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function ProgramList({ list, term, q, setQ }: { list: ReturnType<typeof usePrograms>; term: string; q: string; setQ: (v: string) => void }) {
  const rows = list.data?.pages.flatMap((p) => p.items)
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-3 border-b border-border p-4">
        <div className="w-full sm:w-72">
          <Input icon={<Search />} placeholder="Search programs" aria-label="Search programs" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
      </div>
      {list.error ? (
        <ErrorState message={(list.error as Error).message} onRetry={() => void list.refetch()} />
      ) : !rows ? (
        <div className="grid gap-3 p-5" aria-busy="true">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <EmptyState icon={<GraduationCap />} title={term ? 'No programs match' : 'No programs yet'} body={term ? 'Try another name.' : 'Create a program, then open cohorts for it.'} />
      ) : (
        <div className="animate-reveal">
          <Table>
            <thead>
              <tr>
                <Th>Program</Th>
                <Th className="hidden sm:table-cell">Status</Th>
                <Th className="hidden md:table-cell text-right">Modules</Th>
                <Th className="hidden md:table-cell text-right">Weeks</Th>
                <Th className="text-right">Cohorts</Th>
              </tr>
            </thead>
            <tbody className="stagger">
              {rows.map((p) => (
                <Tr key={p.id} className="relative transition-colors hover:bg-surface-2">
                  <Td>
                    <Link to={`/console/programs/${p.id}`} className="font-medium after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-primary">
                      {p.title}
                    </Link>
                    <span className="block text-xs text-muted">Updated {shortDate(p.updated_at)}</span>
                  </Td>
                  <Td className="hidden sm:table-cell">{p.published ? <StatusPill status="published" /> : <StatusPill status="draft" />}</Td>
                  <Td className="hidden md:table-cell text-right tabular">{p.module_count}</Td>
                  <Td className="hidden md:table-cell text-right tabular">{p.week_count}</Td>
                  <Td className="text-right tabular">{p.cohort_count}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
          {list.hasNextPage ? (
            <div className="flex justify-center border-t border-border p-3">
              <Button variant="ghost" size="sm" loading={list.isFetchingNextPage} onClick={() => void list.fetchNextPage()}>
                Show more programs
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </Card>
  )
}

/** Days the provider is closed for every cohort, plus the GOV.UK bank holiday refresh. */
function ProviderClosures({ canManage }: { canManage: boolean }) {
  const closures = useProviderClosures()
  const sync = useSyncHolidays()
  const [adding, setAdding] = useState(false)
  const actions = useClosureActions()
  const [removing, setRemoving] = useState<string | null>(null)
  const forbidden = closures.error instanceof ApiError && closures.error.status === 403
  if (forbidden) return null
  return (
    <Card>
      <CardHeader
        className="flex-wrap pb-4"
        title="Closures and bank holidays"
        description="Weeks with no teaching day are skipped in every cohort. Bank holidays come from GOV.UK and refresh each month."
        action={
          canManage ? (
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" size="sm" loading={sync.isPending} onClick={() => sync.mutate(undefined, { onSuccess: (r) => toast.success(`${r.saved} bank holidays up to date`), onError: err })}>
                {sync.isPending ? null : <RefreshCw />} Refresh bank holidays
              </Button>
              <Button size="sm" onClick={() => setAdding(true)}>
                <Plus /> Add closure
              </Button>
            </div>
          ) : undefined
        }
      />
      {closures.error ? (
        <ErrorState message={(closures.error as Error).message} onRetry={() => void closures.refetch()} />
      ) : !closures.data ? (
        <div className="grid gap-2 p-5">
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
        </div>
      ) : closures.data.length === 0 ? (
        <EmptyState icon={<CalendarOff />} title="No provider-wide closures" body="Add one for times like the Christmas break." />
      ) : (
        <ClosureRows rows={closures.data} canManage={canManage} onRemove={(id) => setRemoving(id)} />
      )}
      <ClosureDialog open={adding} onOpenChange={setAdding} cohortId={null} />
      <ConfirmDialog
        open={!!removing}
        onOpenChange={(o) => !o && setRemoving(null)}
        title="Remove this closure?"
        body="Every cohort's week dates will be worked out again."
        confirmLabel="Remove closure"
        loading={actions.remove.isPending}
        onConfirm={() => removing && actions.remove.mutate(removing, { onSuccess: () => (toast.success('Closure removed'), setRemoving(null)), onError: err })}
      />
    </Card>
  )
}

export function ConsoleProgramsPage() {
  const [creating, setCreating] = useState(false)
  const [q, setQ] = useState('')
  const term = useDebounced(q)
  const list = usePrograms(term)
  const first = list.data?.pages[0]
  return (
    <div className="grid gap-6">
      <PageHeader
        title="Programs"
        description="Qualifications taught in cohorts: modules, dated weeks and learner groups."
        actions={
          first?.can_build ? (
            <Button onClick={() => setCreating(true)}>
              <Plus /> New program
            </Button>
          ) : undefined
        }
      />
      <ProgramList list={list} term={term} q={q} setQ={setQ} />
      {first ? <ProviderClosures canManage={first.can_manage} /> : null}
      {first?.can_build ? <NewProgram open={creating} onOpenChange={setCreating} /> : null}
    </div>
  )
}

