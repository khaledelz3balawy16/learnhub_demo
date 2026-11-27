import { CloudDownload, FileUp, Layers, ListChecks, Plus, Search, X } from 'lucide-react'
import { type ChangeEvent, type FormEvent, useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardHeader } from '@/components/ui/card'
import { Field, Input, NativeSelect, Textarea } from '@/components/ui/input'
import { EmptyState, ErrorState } from '@/components/ui/misc'
import { Skeleton } from '@/components/ui/skeleton'
import { useDebounced } from '@/features/org/ui'
import {
  KSB_KINDS,
  type KsbMap,
  OTJ_TARGETS,
  type ProgramSettings,
  useAddKsbItem,
  useCreateCustomStandard,
  useFetchStandard,
  useKsbMap,
  useKsbStandards,
  useProgramSettings,
  useSaveProgramSettings,
  useSetKsbMap,
  useUploadStandard,
} from '@/features/programs/api'
import { cn } from '@/lib/cn'

const err = (e: unknown) => toast.error((e as Error).message)
const MAX_UPLOAD = 2_000_000 // bytes: a standard is a few dozen KB

// ---------------------------------------------------------------- choosing a standard
function ChooseStandard({ programId }: { programId: string }) {
  const [q, setQ] = useState('')
  const list = useKsbStandards(useDebounced(q))
  const save = useSaveProgramSettings(programId)
  const fetchStd = useFetchStandard()
  const upload = useUploadStandard()
  const custom = useCreateCustomStandard()
  const [code, setCode] = useState('')
  const [own, setOwn] = useState({ code: '', title: '' })
  const choose = (id: string) => save.mutate({ ksb_standard_id: id }, { onSuccess: () => toast.success('Standard chosen'), onError: err })
  const onFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (file.size > MAX_UPLOAD) return toast.error('That file is too big for a standard.')
    let json: Record<string, unknown>
    try {
      json = JSON.parse(await file.text())
    } catch {
      return toast.error("That file isn't JSON.")
    }
    upload.mutate(json, { onSuccess: (r) => (toast.success(`Standard saved: ${r.added} KSBs added`), choose(r.id)), onError: err })
  }
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader title="Choose a standard" description="Standards already in your library." />
        <div className="grid gap-3 px-5 pb-5">
          <Input icon={<Search />} placeholder="Search by code or title" aria-label="Search standards" value={q} onChange={(e) => setQ(e.target.value)} />
          {list.error ? (
            <ErrorState message={(list.error as Error).message} onRetry={() => void list.refetch()} />
          ) : !list.data ? (
            <Skeleton className="h-24" />
          ) : !list.data.length ? (
            <EmptyState icon={<ListChecks />} title="No standards yet" body="Fetch one by its code, upload its file or write your own." />
          ) : (
            <ul className="stagger grid gap-2">
              {list.data.map((s) => (
                <li key={s.id} className="flex items-center gap-3 rounded-lg border border-border p-3 text-sm">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">
                      {s.code} {s.version ? <span className="text-muted">v{s.version}</span> : null}
                    </p>
                    <p className="truncate text-muted">{s.title}</p>
                  </div>
                  <Badge tone="neutral">{s.item_count} KSBs</Badge>
                  <Button size="sm" variant="secondary" loading={save.isPending && save.variables?.ksb_standard_id === s.id} onClick={() => choose(s.id)}>
                    Use
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>
      <div className="grid content-start gap-4">
        <Card>
          <CardHeader title="Add an apprenticeship standard" description="Fetch it by its code from Skills England, or upload its JSON file." />
          <div className="grid gap-3 px-5 pb-5">
            <form
              className="flex flex-wrap items-end gap-2"
              onSubmit={(e: FormEvent) => {
                e.preventDefault()
                fetchStd.mutate(code.trim(), { onSuccess: (r) => (toast.success(`Standard fetched: ${r.added} KSBs added`), setCode(''), choose(r.id)), onError: err })
              }}
            >
              <div className="min-w-0 flex-1">
                <Field label="Standard code">{(p) => <Input {...p} placeholder="ST0272" value={code} onChange={(e) => setCode(e.target.value)} minLength={3} maxLength={20} required />}</Field>
              </div>
              <Button type="submit" loading={fetchStd.isPending}>
                <CloudDownload /> Fetch
              </Button>
            </form>
            <label className="inline-flex w-fit cursor-pointer items-center gap-2 rounded-md border border-dashed border-border-strong px-3 py-2 text-sm font-medium transition-colors hover:bg-surface-2 focus-within:ring-2 focus-within:ring-primary">
              <FileUp className="size-4" aria-hidden /> {upload.isPending ? 'Uploading…' : 'Upload a standard file (.json)'}
              <input type="file" accept="application/json,.json" className="sr-only" onChange={(e) => void onFile(e)} disabled={upload.isPending} />
            </label>
          </div>
        </Card>
        <Card>
          <CardHeader title="Write your own set" description="For programs that aren't apprenticeships. You add the KSBs next." />
          <form
            className="grid gap-3 px-5 pb-5 sm:grid-cols-[8rem_1fr_auto] sm:items-end"
            onSubmit={(e: FormEvent) => {
              e.preventDefault()
              custom.mutate({ code: own.code.trim(), title: own.title.trim() }, { onSuccess: (r) => (setOwn({ code: '', title: '' }), choose(r.id)), onError: err })
            }}
          >
            <Field label="Code">{(p) => <Input {...p} placeholder="MBA-1" value={own.code} onChange={(e) => setOwn({ ...own, code: e.target.value })} minLength={2} maxLength={40} required />}</Field>
            <Field label="Title">{(p) => <Input {...p} value={own.title} onChange={(e) => setOwn({ ...own, title: e.target.value })} minLength={3} maxLength={300} required />}</Field>
            <Button type="submit" loading={custom.isPending}>
              <Plus /> Create
            </Button>
          </form>
        </Card>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- the map
function AddKsb({ standardId }: { standardId: string }) {
  const add = useAddKsbItem(standardId)
  const [kind, setKind] = useState('knowledge')
  const [text, setText] = useState('')
  return (
    <form
      className="grid gap-3 sm:grid-cols-[10rem_1fr_auto] sm:items-end"
      onSubmit={(e) => {
        e.preventDefault()
        add.mutate({ kind, text: text.trim() }, { onSuccess: () => (toast.success('KSB added'), setText('')), onError: err })
      }}
    >
      <Field label="Type">
        {(p) => (
          <NativeSelect {...p} value={kind} onChange={(e) => setKind(e.target.value)}>
            {Object.entries(KSB_KINDS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </NativeSelect>
        )}
      </Field>
      <Field label="Description">{(p) => <Textarea {...p} rows={1} value={text} onChange={(e) => setText(e.target.value)} minLength={3} maxLength={4000} required />}</Field>
      <Button type="submit" loading={add.isPending}>
        <Plus /> Add KSB
      </Button>
    </form>
  )
}

function Matrix({ programId, map }: { programId: string; map: KsbMap }) {
  const set = useSetKsbMap(programId)
  const std = map.standard!
  const covered = new Map<string, number>()
  for (const c of map.components) for (const id of c.item_ids) covered.set(id, (covered.get(id) ?? 0) + 1)
  const toggle = (lectureKey: string, current: string[], id: string) =>
    set.mutate({ lectureKey, itemIds: current.includes(id) ? current.filter((x) => x !== id) : [...current, id] }, { onError: err })
  const uncovered = std.items.filter((i) => !covered.get(i.id))
  return (
    <div className="grid gap-4">
      <Card className="p-4">
        <p className="text-sm font-medium">Coverage</p>
        <p className="mt-0.5 text-sm text-muted">
          {std.items.length - uncovered.length} of {std.items.length} KSBs are linked to at least one component.
          {uncovered.length ? ` Not linked yet: ${uncovered.map((i) => i.code).join(', ')}.` : ''}
        </p>
      </Card>
      {!map.components.length ? (
        <EmptyState icon={<Layers />} title="No components yet" body="Build the program's weeks and components in the studio first." />
      ) : (
        <Card className="overflow-hidden">
          <ul className="divide-y divide-border">
            {map.components.map((c, ci) => {
              const head = ci === 0 || map.components[ci - 1]!.week !== c.week ? `${c.module ? `${c.module} · ` : ''}${c.week}` : null
              return (
                <li key={c.lecture_key} className="grid gap-2 px-4 py-3">
                  {head ? <p className="text-xs font-semibold tracking-wide text-muted uppercase">{head}</p> : null}
                  <p className="text-sm font-medium">{c.title}</p>
                  <div className="flex flex-wrap gap-1.5" role="group" aria-label={`KSBs for ${c.title}`}>
                    {std.items.map((i) => {
                      const on = c.item_ids.includes(i.id)
                      return (
                        <button
                          key={i.id}
                          type="button"
                          aria-pressed={on}
                          aria-label={`${i.code}: ${i.text}`}
                          title={i.text}
                          disabled={!map.can_build}
                          onClick={() => toggle(c.lecture_key, c.item_ids, i.id)}
                          className={cn(
                            'rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors duration-150 disabled:cursor-default',
                            on ? 'border-primary bg-primary text-on-primary' : 'border-border text-muted hover:border-primary/50 hover:text-text',
                          )}
                        >
                          {i.code}
                        </button>
                      )
                    })}
                  </div>
                </li>
              )
            })}
          </ul>
        </Card>
      )}
    </div>
  )
}

export function ProgramKsbs({ programId }: { programId: string }) {
  const settings = useProgramSettings(programId)
  const map = useKsbMap(programId)
  const save = useSaveProgramSettings(programId)
  const error = settings.error ?? map.error
  if (error) return <ErrorState message={(error as Error).message} onRetry={() => void (settings.refetch(), map.refetch())} />
  if (!settings.data || !map.data) return <Skeleton className="h-64" />
  if (!map.data.standard) return map.data.can_build ? <ChooseStandard programId={programId} /> : <EmptyState icon={<ListChecks />} title="No KSB standard yet" body="Someone who builds programs can choose one." />
  const std = map.data.standard
  return (
    <div className="grid gap-4 animate-reveal">
      <Card className="flex flex-wrap items-center gap-3 p-4">
        <ListChecks className="size-5 text-primary" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="font-semibold">
            {std.code} {std.version ? <span className="font-normal text-muted">v{std.version}</span> : null}
          </p>
          <p className="text-sm text-muted">
            {std.title} · {std.items.length} KSBs · {std.source === 'custom' ? 'Your own set' : 'Apprenticeship standard'}
          </p>
        </div>
        {map.data.can_build ? (
          <Button variant="ghost" size="sm" loading={save.isPending} onClick={() => window.confirm('Choose a different standard? Links to this one stop counting.') && save.mutate({ clear_ksb_standard: true }, { onError: err })}>
            <X /> Change standard
          </Button>
        ) : null}
      </Card>
      {map.data.can_build && std.source === 'custom' ? (
        <Card className="p-4">
          <AddKsb standardId={std.id} />
        </Card>
      ) : null}
      <Matrix programId={programId} map={map.data} />
    </div>
  )
}

// ---------------------------------------------------------------- settings
function SettingsForm({ programId, s }: { programId: string; s: ProgramSettings }) {
  const save = useSaveProgramSettings(programId)
  const [mode, setMode] = useState(s.otj_target_mode)
  const [value, setValue] = useState(String(s.otj_target_value || ''))
  const [amber, setAmber] = useState(String(s.otj_amber_pct))
  const [cap, setCap] = useState(String(s.otj_daily_cap_min / 60))
  const [minSeats, setMinSeats] = useState(String(s.min_seats_per_line))
  const [cutoff, setCutoff] = useState(s.swap_cutoff_mode)
  const [cutoffAt, setCutoffAt] = useState(String(s.swap_cutoff_value || ''))
  const submit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate(
      {
        otj_target_mode: mode,
        otj_target_value: Number(value) || 0,
        otj_amber_pct: Number(amber),
        otj_daily_cap_min: Math.round(Number(cap) * 60),
        min_seats_per_line: Number(minSeats),
        swap_cutoff_mode: cutoff,
        swap_cutoff_value: cutoff === 'none' ? 0 : Number(cutoffAt),
      },
      { onSuccess: () => toast.success('Settings saved'), onError: err },
    )
  }
  const off = !s.can_build
  return (
    <form className="grid max-w-2xl gap-5" onSubmit={submit}>
      <Card>
        <CardHeader title="Off-the-job hours" description="The target sets each learner's status: on track, behind or at risk." />
        <fieldset disabled={off} className="grid gap-4 px-5 pb-5 sm:grid-cols-2">
          <Field label="Target">
            {(p) => (
              <NativeSelect {...p} value={mode} onChange={(e) => setMode(e.target.value)}>
                {Object.entries(OTJ_TARGETS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label={mode === 'total_hours' ? 'Total hours' : 'Hours per week'}>
            {(p) => <Input {...p} type="number" inputMode="decimal" min={0} step="0.5" value={value} onChange={(e) => setValue(e.target.value)} disabled={mode === 'none'} required={mode !== 'none'} />}
          </Field>
          <Field label="At risk below (% of expected)" hint="Between this and 100% a learner is 'behind'.">
            {(p) => <Input {...p} type="number" inputMode="numeric" min={1} max={100} value={amber} onChange={(e) => setAmber(e.target.value)} required />}
          </Field>
          <Field label="Most a learner can log in a day (hours)">
            {(p) => <Input {...p} type="number" inputMode="decimal" min={0.25} max={24} step="0.25" value={cap} onChange={(e) => setCap(e.target.value)} required />}
          </Field>
        </fieldset>
      </Card>
      <Card>
        <CardHeader title="Company seats" description="Rules for companies that buy seats on this program." />
        <fieldset disabled={off} className="grid gap-4 px-5 pb-5 sm:grid-cols-2">
          <Field label="Fewest seats a company can order" hint="For each item: the whole program or one module.">
            {(p) => <Input {...p} type="number" inputMode="numeric" min={1} max={500} value={minSeats} onChange={(e) => setMinSeats(e.target.value)} required />}
          </Field>
          <Field label="Seat swaps need a reason after" hint="Before this, a company can swap a seat freely.">
            {(p) => (
              <NativeSelect {...p} value={cutoff} onChange={(e) => setCutoff(e.target.value)}>
                <option value="none">Never (no cut-off)</option>
                <option value="progress_pct">The learner reaches a progress %</option>
                <option value="week">A week of the cohort</option>
              </NativeSelect>
            )}
          </Field>
          {cutoff !== 'none' ? (
            <Field label={cutoff === 'week' ? 'Week number' : 'Progress (%)'}>
              {(p) => <Input {...p} type="number" inputMode="numeric" min={1} max={cutoff === 'week' ? 520 : 100} value={cutoffAt} onChange={(e) => setCutoffAt(e.target.value)} required />}
            </Field>
          ) : null}
        </fieldset>
      </Card>
      {off ? null : (
        <div className="flex justify-end">
          <Button type="submit" loading={save.isPending}>
            Save settings
          </Button>
        </div>
      )}
    </form>
  )
}

export function ProgramSettingsTab({ programId }: { programId: string }) {
  const q = useProgramSettings(programId)
  if (q.error) return <ErrorState message={(q.error as Error).message} onRetry={() => void q.refetch()} />
  if (!q.data) return <Skeleton className="h-64" />
  return <SettingsForm key={q.dataUpdatedAt} programId={programId} s={q.data} />
}
