import { ArrowDown, ArrowUp, ChevronDown, EyeOff, HeartHandshake, Pencil, Plus, ShieldCheck, Trash2, X } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { toast } from 'sonner'

import { ApiError } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Field, Input, Textarea } from '@/components/ui/input'
import { EmptyState, ErrorState, PageHeader } from '@/components/ui/misc'
import { Skeleton } from '@/components/ui/skeleton'
import { ConfirmDialog, DetailSheet } from '@/features/console/ui'
import {
  type EditorQuestion,
  type EditorSection,
  type InclusionOption,
  useCreateInclusionQuestion,
  useCreateInclusionSection,
  useDeleteInclusionQuestion,
  useDeleteInclusionSection,
  useInclusionEditor,
  useOrderInclusionQuestions,
  useOrderInclusionSections,
  useUpdateInclusionQuestion,
  useUpdateInclusionSection,
} from '@/features/inclusion/api'
import { cn } from '@/lib/cn'
import { Link } from '@/lib/router'

const err = (e: unknown) => toast.error((e as Error).message)
const move = <T,>(list: T[], i: number, by: -1 | 1) => {
  const next = [...list]
  const [x] = next.splice(i, 1)
  next.splice(i + by, 0, x!)
  return next
}

type Editing = { kind: 'section'; section?: EditorSection } | { kind: 'question'; section: EditorSection; question?: EditorQuestion }

/** Console > Inclusion questions: sections, their questions and answers, and when a section
 * flags a learner as "may need support". Admins only. */
export function ConsoleInclusionQuestionsPage() {
  const q = useInclusionEditor()
  const orderSections = useOrderInclusionSections()
  const [editing, setEditing] = useState<Editing | null>(null)
  const [open, setOpen] = useState<Set<string>>(new Set())
  const toggle = (id: string) => setOpen((s) => (s.has(id) ? new Set([...s].filter((x) => x !== id)) : new Set([...s, id])))

  if (q.error instanceof ApiError && q.error.status === 403)
    return <EmptyState icon={<ShieldCheck />} title="Only admins can edit the inclusion test" body="The answers are private health information, so this area is limited to the Admin role." />

  const sections = q.data?.sections ?? []
  return (
    <div className="grid gap-6">
      <PageHeader
        title="Inclusion questions"
        description="What learners are asked, and when a section flags someone as possibly needing support."
        actions={
          <>
            <Button variant="secondary" asChild>
              <Link to="/console/inclusion/results">See results</Link>
            </Button>
            <Button onClick={() => setEditing({ kind: 'section' })} disabled={!q.data}>
              <Plus /> New section
            </Button>
          </>
        }
      />
      <p className="-mt-2 rounded-lg bg-info-soft px-4 py-3 text-sm text-info">
        Changes apply to the next answers learners send. Answers already sent keep the wording the learner saw. A new flag level re-checks every learner straight away.
      </p>
      {q.error ? (
        <ErrorState message={(q.error as Error).message} onRetry={() => void q.refetch()} />
      ) : !q.data ? (
        <div className="grid gap-3" aria-busy="true">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-20 rounded-xl" />
          ))}
        </div>
      ) : !sections.length ? (
        <Card>
          <EmptyState icon={<HeartHandshake />} title="No sections yet" body="Add a section, then its questions." action={<Button onClick={() => setEditing({ kind: 'section' })}><Plus /> New section</Button>} />
        </Card>
      ) : (
        <ol className="stagger grid gap-3 animate-reveal">
          {sections.map((s, i) => (
            <li key={s.id}>
              <SectionCard
                section={s}
                expanded={open.has(s.id)}
                onToggle={() => toggle(s.id)}
                onEdit={() => setEditing({ kind: 'section', section: s })}
                onAddQuestion={() => setEditing({ kind: 'question', section: s })}
                onEditQuestion={(question) => setEditing({ kind: 'question', section: s, question })}
                onMove={(by) => orderSections.mutate(move(sections, i, by).map((x) => x.id), { onError: err })}
                first={i === 0}
                last={i === sections.length - 1}
              />
            </li>
          ))}
        </ol>
      )}
      <DetailSheet
        open={!!editing}
        onOpenChange={(o) => !o && setEditing(null)}
        title={editing?.kind === 'section' ? (editing.section ? 'Edit section' : 'New section') : editing?.question ? 'Edit question' : 'New question'}
        description={editing?.kind === 'question' ? editing.section.title : undefined}
      >
        {editing?.kind === 'section' ? (
          <SectionForm key={editing.section?.id ?? 'new'} section={editing.section} onDone={(id) => (setEditing(null), id && setOpen((s) => new Set([...s, id])))} />
        ) : editing?.kind === 'question' ? (
          <QuestionForm key={editing.question?.id ?? 'new'} section={editing.section} question={editing.question} defaults={q.data!.default_options} onDone={() => setEditing(null)} />
        ) : null}
      </DetailSheet>
    </div>
  )
}

function SectionCard({ section: s, expanded, onToggle, onEdit, onAddQuestion, onEditQuestion, onMove, first, last }: {
  section: EditorSection
  expanded: boolean
  onToggle: () => void
  onEdit: () => void
  onAddQuestion: () => void
  onEditQuestion: (q: EditorQuestion) => void
  onMove: (by: -1 | 1) => void
  first: boolean
  last: boolean
}) {
  const del = useDeleteInclusionSection()
  const delQ = useDeleteInclusionQuestion()
  const order = useOrderInclusionQuestions()
  const [confirm, setConfirm] = useState<{ kind: 'section' } | { kind: 'question'; q: EditorQuestion } | null>(null)
  const active = s.questions.filter((x) => x.is_active).length
  return (
    <Card className={cn('overflow-hidden', !s.is_active && 'opacity-75')}>
      <div className="flex flex-wrap items-center gap-3 px-4 py-3 sm:px-5">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={expanded}
          aria-controls={`sec-${s.id}`}
          className="flex min-w-0 flex-1 items-center gap-3 rounded-md text-left focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none"
        >
          <ChevronDown className={cn('size-4 shrink-0 text-muted transition-transform duration-200 motion-reduce:transition-none', expanded && 'rotate-180')} />
          <span className="min-w-0">
            <span className="block truncate font-semibold">{s.title}</span>
            <span className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted">
              <span className="tabular">
                {active} {active === 1 ? 'question' : 'questions'}, scored 0 to {s.max_score}
              </span>
              {s.flag_threshold != null ? <Badge tone="warning">Flags at {s.flag_threshold} or more</Badge> : <Badge>No flag</Badge>}
              {!s.is_active ? (
                <Badge tone="outline">
                  <EyeOff /> Hidden
                </Badge>
              ) : null}
            </span>
          </span>
        </button>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon-sm" aria-label={`Move ${s.title} up`} disabled={first} onClick={() => onMove(-1)}>
            <ArrowUp />
          </Button>
          <Button variant="ghost" size="icon-sm" aria-label={`Move ${s.title} down`} disabled={last} onClick={() => onMove(1)}>
            <ArrowDown />
          </Button>
          <Button variant="ghost" size="icon-sm" aria-label={`Edit ${s.title}`} onClick={onEdit}>
            <Pencil />
          </Button>
          <Button variant="ghost" size="icon-sm" aria-label={`Delete ${s.title}`} onClick={() => setConfirm({ kind: 'section' })}>
            <Trash2 />
          </Button>
        </div>
      </div>
      {expanded ? (
        <div id={`sec-${s.id}`} className="animate-reveal border-t border-border">
          {s.questions.length ? (
            <ol className="divide-y divide-border">
              {s.questions.map((qq, i) => (
                <li key={qq.id} className={cn('flex items-start gap-3 px-4 py-3 sm:px-5', !qq.is_active && 'opacity-60')}>
                  <span className="mt-0.5 w-6 shrink-0 text-xs text-subtle tabular">{i + 1}.</span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm">{qq.text}</p>
                    <p className="mt-1 flex flex-wrap gap-1.5 text-xs text-muted">
                      <span className="font-mono">{qq.key}</span>
                      <span>· {qq.options.map((o) => o.label).join(' / ')}</span>
                      {!qq.required ? <Badge>Optional</Badge> : null}
                      {!qq.is_active ? <Badge tone="outline">Hidden</Badge> : null}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-0.5">
                    <Button variant="ghost" size="icon-sm" aria-label={`Move question ${i + 1} up`} disabled={i === 0}
                      onClick={() => order.mutate({ sectionId: s.id, ids: move(s.questions, i, -1).map((x) => x.id) }, { onError: err })}>
                      <ArrowUp />
                    </Button>
                    <Button variant="ghost" size="icon-sm" aria-label={`Move question ${i + 1} down`} disabled={i === s.questions.length - 1}
                      onClick={() => order.mutate({ sectionId: s.id, ids: move(s.questions, i, 1).map((x) => x.id) }, { onError: err })}>
                      <ArrowDown />
                    </Button>
                    <Button variant="ghost" size="icon-sm" aria-label={`Edit question ${i + 1}`} onClick={() => onEditQuestion(qq)}>
                      <Pencil />
                    </Button>
                    <Button variant="ghost" size="icon-sm" aria-label={`Delete question ${i + 1}`} onClick={() => setConfirm({ kind: 'question', q: qq })}>
                      <Trash2 />
                    </Button>
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <p className="px-5 py-4 text-sm text-muted">No questions in this section yet.</p>
          )}
          <div className="border-t border-border px-4 py-3 sm:px-5">
            <Button variant="secondary" size="sm" onClick={onAddQuestion}>
              <Plus /> Add question
            </Button>
          </div>
        </div>
      ) : null}
      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={confirm?.kind === 'section' ? `Delete “${s.title}”?` : 'Delete this question?'}
        body={
          confirm?.kind === 'section'
            ? `Its ${s.questions.length} questions go too. Answers learners already sent keep their copy, but this section stops flagging anyone. To stop asking it for now, hide it instead.`
            : 'Learners stop seeing it. Answers already sent keep their copy. To stop asking it for now, hide it instead.'
        }
        confirmLabel="Delete"
        loading={del.isPending || delQ.isPending}
        onConfirm={() => {
          const done = { onSuccess: () => (toast.success('Deleted'), setConfirm(null)), onError: err }
          if (confirm?.kind === 'section') del.mutate(s.id, done)
          else if (confirm?.kind === 'question') delQ.mutate(confirm.q.id, done)
        }}
      />
    </Card>
  )
}

function SectionForm({ section, onDone }: { section?: EditorSection; onDone: (id?: string) => void }) {
  const create = useCreateInclusionSection()
  const update = useUpdateInclusionSection()
  const [title, setTitle] = useState(section?.title ?? '')
  const [description, setDescription] = useState(section?.description ?? '')
  const [flagOn, setFlagOn] = useState(section ? section.flag_threshold != null : true)
  const [threshold, setThreshold] = useState(String(section?.flag_threshold ?? 15))
  const [visible, setVisible] = useState(section?.is_active ?? true)
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const flag_threshold = flagOn ? Math.max(0, Math.round(Number(threshold) || 0)) : null
    if (section)
      update.mutate(
        { id: section.id, title: title.trim(), description: description.trim(), flag_threshold, is_active: visible },
        { onSuccess: () => (toast.success('Section saved'), onDone()), onError: err },
      )
    else create.mutate({ title: title.trim(), flag_threshold }, { onSuccess: (r) => (toast.success('Section added'), onDone(r.id)), onError: err })
  }
  return (
    <form className="grid gap-4" onSubmit={submit}>
      <Field label="Title">{(p) => <Input {...p} value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} required />}</Field>
      {section ? (
        <Field label="Note shown to learners (optional)">{(p) => <Textarea {...p} rows={2} value={description} onChange={(e) => setDescription(e.target.value)} maxLength={500} />}</Field>
      ) : null}
      <fieldset className="grid gap-3 rounded-lg border border-border p-4">
        <legend className="px-1 text-sm font-medium">Flag “may need support”</legend>
        <label className="flex cursor-pointer items-center gap-3 text-sm">
          <input type="checkbox" className="size-4 accent-[var(--primary)]" checked={flagOn} onChange={(e) => setFlagOn(e.target.checked)} />
          Flag learners in this section
        </label>
        {flagOn ? (
          <Field label={`Flag at this score or more${section ? ` (out of ${section.max_score})` : ''}`}>
            {(p) => <Input {...p} type="number" inputMode="numeric" min={0} max={1000} value={threshold} onChange={(e) => setThreshold(e.target.value)} required className="w-32" />}
          </Field>
        ) : (
          <p className="text-xs text-muted">Scores still show in the results, but nobody is flagged for this section.</p>
        )}
      </fieldset>
      {section ? (
        <label className="flex cursor-pointer items-center gap-3 text-sm">
          <input type="checkbox" className="size-4 accent-[var(--primary)]" checked={visible} onChange={(e) => setVisible(e.target.checked)} />
          Learners see this section
        </label>
      ) : null}
      <div className="flex justify-end">
        <Button type="submit" loading={create.isPending || update.isPending}>
          {section ? 'Save section' : 'Add section'}
        </Button>
      </div>
    </form>
  )
}

function QuestionForm({ section, question, defaults, onDone }: { section: EditorSection; question?: EditorQuestion; defaults: InclusionOption[]; onDone: () => void }) {
  const create = useCreateInclusionQuestion()
  const update = useUpdateInclusionQuestion()
  const [text, setText] = useState(question?.text ?? '')
  const [options, setOptions] = useState<{ label: string; value: string }[]>((question?.options ?? section.questions[0]?.options ?? defaults).map((o) => ({ label: o.label, value: String(o.value) })))
  const [required, setRequired] = useState(question?.required ?? true)
  const [visible, setVisible] = useState(question?.is_active ?? true)
  const setOpt = (i: number, patch: Partial<{ label: string; value: string }>) => setOptions((os) => os.map((o, j) => (j === i ? { ...o, ...patch } : o)))
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const opts = options.map((o) => ({ label: o.label.trim(), value: Math.round(Number(o.value)) }))
    if (question)
      update.mutate({ id: question.id, text: text.trim(), options: opts, required, is_active: visible }, { onSuccess: () => (toast.success('Question saved'), onDone()), onError: err })
    else create.mutate({ sectionId: section.id, text: text.trim(), options: opts, required }, { onSuccess: () => (toast.success('Question added'), onDone()), onError: err })
  }
  return (
    <form className="grid gap-4" onSubmit={submit}>
      <Field label="Question">{(p) => <Textarea {...p} rows={3} value={text} onChange={(e) => setText(e.target.value)} maxLength={500} required />}</Field>
      <fieldset className="grid gap-2">
        <legend className="mb-1 text-sm font-medium">Answers and their scores</legend>
        <p className="-mt-1 mb-1 text-xs text-muted">A higher score means more need for support. Scores are whole numbers from 0 to 10.</p>
        {options.map((o, i) => (
          <div key={i} className="flex items-center gap-2">
            <Input aria-label={`Answer ${i + 1}`} value={o.label} onChange={(e) => setOpt(i, { label: e.target.value })} maxLength={80} required className="min-w-0 flex-1" />
            <Input aria-label={`Score for answer ${i + 1}`} type="number" inputMode="numeric" min={0} max={10} value={o.value} onChange={(e) => setOpt(i, { value: e.target.value })} required className="w-20" />
            <Button type="button" variant="ghost" size="icon-sm" aria-label={`Remove answer ${i + 1}`} disabled={options.length <= 2} onClick={() => setOptions((os) => os.filter((_, j) => j !== i))}>
              <X />
            </Button>
          </div>
        ))}
        {options.length < 6 ? (
          <div>
            <Button type="button" variant="secondary" size="sm" onClick={() => setOptions((os) => [...os, { label: '', value: String(Math.min(10, Math.max(0, ...os.map((o) => Number(o.value) || 0)) + 1)) }])}>
              <Plus /> Add answer
            </Button>
          </div>
        ) : null}
      </fieldset>
      <label className="flex cursor-pointer items-center gap-3 text-sm">
        <input type="checkbox" className="size-4 accent-[var(--primary)]" checked={required} onChange={(e) => setRequired(e.target.checked)} />
        Learners must answer it
      </label>
      {question ? (
        <label className="flex cursor-pointer items-center gap-3 text-sm">
          <input type="checkbox" className="size-4 accent-[var(--primary)]" checked={visible} onChange={(e) => setVisible(e.target.checked)} />
          Learners see this question
        </label>
      ) : null}
      <div className="flex justify-end">
        <Button type="submit" loading={create.isPending || update.isPending}>
          {question ? 'Save question' : 'Add question'}
        </Button>
      </div>
    </form>
  )
}
