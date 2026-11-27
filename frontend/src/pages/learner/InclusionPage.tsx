import { ArrowLeft, ArrowRight, Check, CheckCircle2, HeartHandshake, Lock, RotateCcw, ShieldCheck } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardBody } from '@/components/ui/card'
import { EmptyState, ErrorState, PageHeader } from '@/components/ui/misc'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { Checkbox } from '@/components/ui/switch'
import { type Answers, type InclusionMe, useInclusionMe, useSaveInclusionDraft, useSubmitInclusion } from '@/features/inclusion/api'
import { cn } from '@/lib/cn'
import { shortDate } from '@/lib/format'
import { Link } from '@/lib/router'

type Stage = 'intro' | 'questions' | 'done'

/** Inclusion test: an optional questionnaire that helps the provider offer support. Learners
 * never see scores. Their answers go to the provider's admins and, for company learners, to the
 * company's owners and admins (user decision 2026-11-25), which the consent note says. */
export function InclusionPage() {
  const q = useInclusionMe()
  return (
    <>
      <PageHeader title="Inclusion test" description="A few short questions so we can support the way you learn best." />
      {q.error ? (
        <ErrorState message={q.error.message} onRetry={() => void q.refetch()} />
      ) : q.isPending ? (
        <div className="grid gap-4">
          <Skeleton className="h-40 rounded-xl" />
          <Skeleton className="h-72 rounded-xl" />
        </div>
      ) : !q.data.sections.length ? (
        <Card>
          <EmptyState icon={<HeartHandshake />} title="Nothing to answer right now" body="There are no questions at the moment. Please check back later." />
        </Card>
      ) : (
        <InclusionFlow key={q.data.last_submitted_at ?? 'new'} me={q.data} />
      )}
    </>
  )
}

function InclusionFlow({ me }: { me: InclusionMe }) {
  const [stage, setStage] = useState<Stage>(me.has_draft ? 'questions' : me.last_submitted_at ? 'done' : 'intro')
  const [consent, setConsent] = useState(me.consented)
  const [answers, setAnswers] = useState<Answers>(me.answers)
  const [step, setStep] = useState(0)

  const start = () => {
    setStep(0)
    setStage('questions')
  }

  if (stage === 'intro' || (stage === 'questions' && !consent))
    return <Intro consent={consent} setConsent={setConsent} retake={!!me.last_submitted_at} onStart={start} />
  if (stage === 'done') return <Done me={me} onRetake={() => setStage('intro')} />
  return (
    <Questions
      me={me}
      answers={answers}
      setAnswers={setAnswers}
      step={step}
      setStep={setStep}
      consent={consent}
      onDone={() => setStage('done')}
    />
  )
}

function Intro({ consent, setConsent, retake, onStart }: { consent: boolean; setConsent: (v: boolean) => void; retake: boolean; onStart: () => void }) {
  return (
    <Card className="animate-reveal overflow-hidden">
      <CardBody className="grid gap-5 sm:p-7">
        <div className="flex items-start gap-4">
          <span className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary-soft-text">
            <HeartHandshake className="size-6" />
          </span>
          <div>
            <h2 className="text-lg font-semibold">{retake ? 'Take the test again' : 'Before you start'}</h2>
            <p className="mt-1 text-sm text-muted">
              {retake ? 'We start from your last answers, so you only change what is different now.' : 'It takes about 10 minutes. There are no right or wrong answers.'}
            </p>
          </div>
        </div>
        <ul className="grid gap-3 text-sm">
          <li className="flex gap-3">
            <ShieldCheck className="mt-0.5 size-4 shrink-0 text-success" />
            <span>It is optional. You can stop at any time and come back later. We save your answers as you go.</span>
          </li>
          <li className="flex gap-3">
            <Lock className="mt-0.5 size-4 shrink-0 text-success" />
            <span>Our admin team can see your answers. If you learn through a company, its owners and admins can see them too. Tutors and other learners can't.</span>
          </li>
          <li className="flex gap-3">
            <Check className="mt-0.5 size-4 shrink-0 text-success" />
            <span>It is not a diagnosis. It helps us offer support, such as extra time, captions or check-ins.</span>
          </li>
        </ul>
        <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-border bg-surface-2/50 p-4 text-sm">
          <Checkbox checked={consent} onCheckedChange={(v) => setConsent(v === true)} className="mt-0.5" aria-describedby="inclusion-consent" />
          <span id="inclusion-consent">I agree that the admin team, and my company's owners and admins if I learn through a company, can see my answers and use them to plan support for me.</span>
        </label>
        <div>
          <Button size="lg" disabled={!consent} onClick={onStart}>
            {retake ? 'Start again' : 'Start'} <ArrowRight />
          </Button>
        </div>
      </CardBody>
    </Card>
  )
}

function Questions({
  me,
  answers,
  setAnswers,
  step,
  setStep,
  consent,
  onDone,
}: {
  me: InclusionMe
  answers: Answers
  setAnswers: (fn: (a: Answers) => Answers) => void
  step: number
  setStep: (n: number) => void
  consent: boolean
  onDone: () => void
}) {
  const sections = me.sections
  const section = sections[step]!
  const total = useMemo(() => sections.reduce((n, s) => n + s.questions.length, 0), [sections])
  const answered = sections.reduce((n, s) => n + s.questions.filter((qq) => answers[qq.id] != null).length, 0)
  const save = useSaveInclusionDraft()
  const submit = useSubmitInclusion()
  const [missing, setMissing] = useState<Set<string>>(new Set())
  const [savedAt, setSavedAt] = useState<string | null>(null)
  const top = useRef<HTMLDivElement>(null)

  // save a moment after the last change, so a quick run of clicks is one request. Saves run one
  // after another (never out of order), and none starts once the answers are being sent.
  const pending = useRef<Answers | null>(null)
  const timer = useRef<number>(undefined)
  const queue = useRef<Promise<unknown>>(Promise.resolve())
  const sending = useRef(false)
  const flush = useCallback(() => {
    window.clearTimeout(timer.current)
    if (!pending.current || sending.current) return
    const body = { answers: pending.current, consent }
    pending.current = null
    queue.current = queue.current.then(() =>
      save.mutateAsync(body).then(
        (r) => setSavedAt(r.saved_at),
        () => toast.error("We couldn't save your last answer. Check your connection."),
      ),
    )
  }, [consent, save])
  useEffect(() => () => window.clearTimeout(timer.current), [])

  const choose = (questionId: string, value: number) => {
    setAnswers((a) => {
      const next = { ...a, [questionId]: value }
      pending.current = next
      return next
    })
    setMissing((m) => {
      if (!m.has(questionId)) return m
      const n = new Set(m)
      n.delete(questionId)
      return n
    })
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(flush, 700)
  }

  const go = (n: number) => {
    flush()
    setStep(n)
    setMissing(new Set())
    top.current?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' })
  }

  const send = async () => {
    const gaps = sections.flatMap((s, i) => s.questions.filter((qq) => qq.required && answers[qq.id] == null).map((qq) => ({ i, id: qq.id })))
    if (gaps.length) {
      const first = gaps[0]!
      setStep(first.i)
      setMissing(new Set(gaps.filter((g) => g.i === first.i).map((g) => g.id)))
      toast.error(`Please answer ${gaps.length === 1 ? 'the last question' : `the ${gaps.length} questions left`}.`)
      top.current?.scrollIntoView({ block: 'start' })
      flush() // keep what they have answered so far
      return
    }
    // the submission carries every answer: drop the unsaved ones, wait for any save in flight
    window.clearTimeout(timer.current)
    pending.current = null
    sending.current = true
    await queue.current
    submit.mutate({ answers, consent }, { onSuccess: onDone, onError: (e) => ((sending.current = false), toast.error(e.message)) })
  }

  const last = step === sections.length - 1
  return (
    <div ref={top} className="grid scroll-mt-24 gap-5">
      <Card className="animate-reveal">
        <CardBody className="grid gap-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
            <p className="font-medium">
              Part {step + 1} of {sections.length}
            </p>
            <p className="text-muted tabular" aria-live="polite">
              {answered} of {total} answered
              {savedAt ? <span className="ml-2 text-subtle">· Saved</span> : null}
            </p>
          </div>
          <Progress value={(answered / total) * 100} label="Questions answered" />
          <ol className="flex flex-wrap gap-1.5" aria-label="Parts">
            {sections.map((s, i) => {
              const done = s.questions.every((qq) => answers[qq.id] != null)
              return (
                <li key={s.id}>
                  <button
                    type="button"
                    onClick={() => go(i)}
                    aria-current={i === step ? 'step' : undefined}
                    aria-label={`Part ${i + 1}: ${s.title}${done ? ', done' : ''}`}
                    className={cn(
                      'flex size-8 items-center justify-center rounded-full border text-xs font-semibold transition-colors duration-200 focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none',
                      i === step ? 'border-primary bg-primary text-on-primary' : done ? 'border-success/40 bg-success-soft text-success' : 'border-border text-muted hover:border-primary hover:text-text',
                    )}
                  >
                    {done && i !== step ? <Check className="size-3.5" /> : i + 1}
                  </button>
                </li>
              )
            })}
          </ol>
        </CardBody>
      </Card>

      <section key={section.id} aria-labelledby={`sec-${section.id}`} className="animate-reveal">
        <h2 id={`sec-${section.id}`} className="text-lg font-semibold">
          {section.title}
        </h2>
        {section.description ? <p className="mt-1 text-sm text-muted">{section.description}</p> : null}
        <p className="mt-1 text-sm text-muted">How often is this true for you?</p>
        <ol className="stagger mt-4 grid gap-3">
          {section.questions.map((qq, i) => (
            <li key={qq.id}>
              <fieldset className={cn('rounded-xl border bg-surface p-4 transition-colors duration-200 sm:p-5', missing.has(qq.id) ? 'border-danger/60' : 'border-border')}>
                <legend className="sr-only">{qq.text}</legend>
                <p className="flex gap-3 text-[15px] font-medium" aria-hidden>
                  <span className="text-subtle tabular">{i + 1}.</span>
                  <span>{qq.text}</span>
                </p>
                {missing.has(qq.id) ? <p className="mt-1 text-xs text-danger">Please choose an answer.</p> : null}
                <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {qq.options.map((o) => {
                    const on = answers[qq.id] === o.value
                    return (
                      <label
                        key={o.value}
                        className={cn(
                          'flex min-h-11 cursor-pointer items-center justify-center rounded-lg border px-3 py-2 text-center text-sm transition-[color,background-color,border-color,transform] duration-150 active:scale-[0.98] has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-primary motion-reduce:transition-none',
                          on ? 'border-primary bg-primary-soft font-medium text-primary-soft-text' : 'border-border hover:border-primary/50 hover:bg-surface-2',
                        )}
                      >
                        <input type="radio" name={qq.id} value={o.value} checked={on} onChange={() => choose(qq.id, o.value)} className="sr-only" />
                        {o.label}
                      </label>
                    )
                  })}
                </div>
              </fieldset>
            </li>
          ))}
        </ol>
      </section>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button variant="secondary" disabled={step === 0} onClick={() => go(step - 1)}>
          <ArrowLeft /> Back
        </Button>
        {last ? (
          <Button size="lg" loading={submit.isPending} onClick={() => void send()}>
            Send my answers <Check />
          </Button>
        ) : (
          <Button onClick={() => go(step + 1)}>
            Next part <ArrowRight />
          </Button>
        )}
      </div>
    </div>
  )
}

function Done({ me, onRetake }: { me: InclusionMe; onRetake: () => void }) {
  return (
    <Card className="animate-reveal">
      <CardBody className="grid gap-5 sm:p-7">
        <div className="flex items-start gap-4">
          <CheckCircle2 className="size-10 shrink-0 animate-pop text-success" />
          <div>
            <h2 className="text-lg font-semibold">Thank you. Your answers have been sent.</h2>
            <p className="mt-1 text-sm text-muted">
              {me.last_submitted_at ? `Sent on ${shortDate(me.last_submitted_at)}.` : null} They are used to plan support for you.
            </p>
          </div>
        </div>
        <p className="text-sm text-muted">Things change. If your situation is different now, take the test again and we'll use your new answers.</p>
        <p className="text-sm text-muted">
          Want to talk to someone sooner?{' '}
          <Link to="/support" className="font-medium text-primary hover:underline">
            Contact Help &amp; support
          </Link>
          .
        </p>
        <div>
          <Button variant="secondary" onClick={onRetake}>
            <RotateCcw /> Take it again
          </Button>
        </div>
      </CardBody>
    </Card>
  )
}
