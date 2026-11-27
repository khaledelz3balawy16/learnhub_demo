import { useQueryClient } from '@tanstack/react-query'
import { Building2, Check, CheckCircle2, Loader2 } from 'lucide-react'
import { type FormEvent, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Field, Input, NativeSelect } from '@/components/ui/input'
import { ErrorState, PageHeader } from '@/components/ui/misc'
import { Skeleton } from '@/components/ui/skeleton'
import { useCurrencies } from '@/features/commerce/api'
import { useCompanySignup, useSeatSetup } from '@/features/corporate/programSeats'
import { SeatOrderBuilder } from '@/features/corporate/SeatOrderBuilder'
import { useWorkspace } from '@/features/identity/workspace'
import { cn } from '@/lib/cn'
import { Link } from '@/lib/router'

const STEPS = ['Your company', 'Your order', 'Payment', 'Ready']

function Stepper({ at }: { at: number }) {
  return (
    <ol className="mb-6 flex flex-wrap gap-x-5 gap-y-2" aria-label="Setup steps">
      {STEPS.map((s, i) => (
        <li key={s} className="flex items-center gap-2 text-sm" aria-current={i === at ? 'step' : undefined}>
          <span
            className={cn(
              'flex size-6 items-center justify-center rounded-full border text-xs font-semibold transition-colors duration-200',
              i < at ? 'border-primary bg-primary text-on-primary' : i === at ? 'border-primary text-primary' : 'border-border text-muted',
            )}
          >
            {i < at ? <Check className="size-3.5" aria-hidden /> : i + 1}
          </span>
          <span className={i === at ? 'font-medium text-text' : 'text-muted'}>{s}</span>
        </li>
      ))}
    </ol>
  )
}

function CompanyForm({ onCreated }: { onCreated: (orgId: string) => void }) {
  const currencies = useCurrencies()
  const signup = useCompanySignup()
  const [name, setName] = useState('')
  const [currency, setCurrency] = useState('GBP')
  const submit = (e: FormEvent) => {
    e.preventDefault()
    signup.mutate({ name: name.trim(), currency }, { onSuccess: (r) => onCreated(r.org_id), onError: (err) => toast.error((err as Error).message) })
  }
  return (
    <Card className="max-w-xl p-5 animate-reveal">
      <form className="grid gap-4" onSubmit={submit}>
        <Field label="Company name">{(p) => <Input {...p} required minLength={2} maxLength={200} value={name} onChange={(e) => setName(e.target.value)} autoComplete="organization" />}</Field>
        <Field label="Pay in" hint="Your seat prices and invoices use this currency.">
          {(p) => (
            <NativeSelect {...p} value={currency} onChange={(e) => setCurrency(e.target.value)}>
              {(currencies.data ?? [{ code: 'GBP', name: 'Pound sterling', exponent: 2 }]).map((c) => (
                <option key={c.code} value={c.code}>
                  {c.code} · {c.name}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        <p className="text-sm text-muted">You'll be the company's owner. Next you choose the programs and seats; your workspace opens once the order is paid.</p>
        <div>
          <Button type="submit" loading={signup.isPending} disabled={name.trim().length < 2}>
            <Building2 /> Create company
          </Button>
        </div>
      </form>
    </Card>
  )
}

/** /business/start (M22, D8 and D9): create the company, build and pay the first order, then
 * the workspace opens. A company still being set up is sent here by the workspace guard. */
export function CompanyStartPage() {
  const qc = useQueryClient()
  const { org, memberships, switchTo } = useWorkspace()
  const [params] = useSearchParams()
  const paid = params.get('paid') === '1'
  const settingUp = memberships.find((m) => m.onboarding_state !== 'active' && ['owner', 'admin'].includes(m.role))
  const current = settingUp && org?.org_id === settingUp.org_id
  // the company being set up becomes the selected space, so the setup calls reach it
  useEffect(() => {
    if (settingUp && !current) switchTo(settingUp.org_id)
  }, [settingUp, current, switchTo])
  // only a company being set up has a setup to read: an open workspace never lands on a skeleton
  const setup = useSeatSetup(paid, !!current)
  const open = !!current && setup.data?.onboarding_state === 'active'
  useEffect(() => {
    if (open) void qc.refetchQueries({ queryKey: ['me'], type: 'all' }) // the guard now lets the workspace open
  }, [open, qc])
  // back from Stripe and the webhook has landed: the selected company is open now
  const justOpened = paid && !settingUp && org?.onboarding_state === 'active' && org.role !== 'manager'

  const created = async (orgId: string) => {
    await qc.refetchQueries({ queryKey: ['me'], type: 'all' })
    switchTo(orgId)
  }

  let body
  let step = 0
  if (open || justOpened) {
    step = 3
    body = (
      <Card className="max-w-xl p-6 text-center animate-reveal">
        <CheckCircle2 className="mx-auto mb-3 size-10 text-success" aria-hidden />
        <h2 className="text-lg font-semibold">Payment received. Your workspace is open.</h2>
        <p className="mt-1 text-sm text-muted">Next, give your seats to the people who will learn.</p>
        <Button asChild className="mt-4">
          <Link to="/business/program-seats">Give seats to your team</Link>
        </Button>
      </Card>
    )
  } else if (!settingUp) {
    body = <CompanyForm onCreated={(id) => void created(id)} />
  } else if (!current || setup.isLoading) {
    step = 1
    body = <Skeleton className="h-64" />
  } else if (setup.error) {
    step = 1
    body = <ErrorState message={(setup.error as Error).message} onRetry={() => void setup.refetch()} />
  } else if (paid && setup.data?.draft?.status === 'pending') {
    step = 2
    body = (
      <Card className="max-w-xl p-6 text-center animate-reveal" role="status" aria-live="polite">
        <Loader2 className="mx-auto mb-3 size-8 animate-spin text-primary" aria-hidden />
        <h2 className="text-lg font-semibold">Confirming your payment…</h2>
        <p className="mt-1 text-sm text-muted">This usually takes a few seconds. You can leave this page; we'll open your workspace when it lands.</p>
      </Card>
    )
  } else if (setup.data) {
    step = 1
    body = <SeatOrderBuilder setup={setup.data} />
  }

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title={setup.data && current ? `Set up ${setup.data.org_name}` : 'Train your team'}
        description="Choose programs or single modules, live or recorded, and how many seats. Pay by card and your company workspace opens."
      />
      <Stepper at={step} />
      {body}
    </div>
  )
}
