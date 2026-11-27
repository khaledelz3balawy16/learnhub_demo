import { Pencil, Plus, Tags } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Field, Input, Label, NativeSelect } from '@/components/ui/input'
import { EmptyState, ErrorState } from '@/components/ui/misc'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Table, Td, Th, Tr } from '@/components/ui/table'
import { type ProgramOffers as Offers, useProgramOffers, useSaveProgramOffer } from '@/features/programs/api'
import { money } from '@/lib/format'

type Offer = Offers['items'][number]
const WHOLE = 'program'
const MODE: Record<string, string> = { live: 'Live in a cohort', recorded: 'Recorded' }

function OfferDialog({ programId, data, offer, open, onOpenChange }: { programId: string; data: Offers; offer: Offer | null; open: boolean; onOpenChange: (o: boolean) => void }) {
  const save = useSaveProgramOffer(programId)
  const [what, setWhat] = useState(offer?.module_key ?? WHOLE)
  const [mode, setMode] = useState(offer?.mode ?? 'live')
  const [tier, setTier] = useState(offer ? (offer.tier_id ?? '') : (data.tiers[0]?.id ?? ''))
  const [tokens, setTokens] = useState(offer?.token_price ? String(offer.token_price) : '')
  const [months, setMonths] = useState(String(offer?.instalments_max ?? 1))
  const [active, setActive] = useState(offer?.is_active ?? true)
  const tokensAllowed = mode === 'recorded' && what !== WHOLE
  const monthlyAllowed = mode === 'live' && !!tier

  const submit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate(
      {
        id: offer?.id,
        body: {
          module_key: what === WHOLE ? null : what,
          mode,
          tier_id: tier || null,
          token_price: tokensAllowed && tokens ? Number(tokens) : null,
          instalments_max: monthlyAllowed ? Number(months) || 1 : 1,
          is_active: active,
        },
      },
      {
        onSuccess: () => {
          toast.success(offer ? 'Offer saved' : 'Offer added')
          onOpenChange(false)
        },
        onError: (err) => toast.error((err as Error).message),
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={offer ? 'Edit offer' : 'New offer'} description="How people can buy this program or one of its modules. Prices use the same tiers as courses.">
        <form className="grid gap-4" onSubmit={submit}>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="What">
              {(p) => (
                <NativeSelect {...p} value={what} onChange={(e) => setWhat(e.target.value)} disabled={!!offer}>
                  <option value={WHOLE}>Whole program</option>
                  {data.modules.map((m) => (
                    <option key={m.module_key} value={m.module_key}>
                      {m.title}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
            <Field label="How it is taught">
              {(p) => (
                <NativeSelect {...p} value={mode} onChange={(e) => setMode(e.target.value)} disabled={!!offer}>
                  <option value="live">Live in a cohort</option>
                  <option value="recorded">Recorded, self-paced</option>
                </NativeSelect>
              )}
            </Field>
          </div>
          <Field label="Price" hint={tokensAllowed ? 'Leave empty to sell this module for tokens only.' : undefined}>
            {(p) => (
              <NativeSelect {...p} value={tier} onChange={(e) => setTier(e.target.value)}>
                {tokensAllowed ? <option value="">No cash price</option> : null}
                {data.tiers.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} · {money(t.gbp_minor, 'GBP')}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            {tokensAllowed ? (
              <Field label="Token price (optional)">{(p) => <Input {...p} type="number" min={1} max={100000} inputMode="numeric" value={tokens} onChange={(e) => setTokens(e.target.value)} />}</Field>
            ) : null}
            {monthlyAllowed ? (
              <Field label="Monthly payments, up to" hint="1 means pay in full only.">
                {(p) => <Input {...p} type="number" min={1} max={24} inputMode="numeric" value={months} onChange={(e) => setMonths(e.target.value)} />}
              </Field>
            ) : null}
          </div>
          <div className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2.5">
            <Label htmlFor="offer-active">On sale</Label>
            <Switch id="offer-active" checked={active} onCheckedChange={setActive} />
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={save.isPending}>
              {offer ? 'Save' : 'Add offer'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** Console › Programs › program › Offers (M21): what is for sale, for how much, and how it is paid. */
export function ProgramOffers({ programId }: { programId: string }) {
  const q = useProgramOffers(programId)
  const [editing, setEditing] = useState<Offer | 'new' | null>(null)
  if (q.error) return <ErrorState message={(q.error as Error).message} onRetry={() => void q.refetch()} />
  if (!q.data) return <Skeleton className="h-48" />
  const d = q.data
  const title = (o: Offer) => (o.module_key ? (o.module_title ?? 'A module') : 'Whole program')
  const add = d.can_edit && d.published ? (
    <Button onClick={() => setEditing('new')}>
      <Plus /> New offer
    </Button>
  ) : undefined
  return (
    <div className="grid gap-3 animate-reveal">
      {!d.items.length ? (
        <EmptyState icon={<Tags />} title="Not for sale yet" body={d.published ? 'Add an offer to list this program in the catalogue: the whole program or a module, live or recorded.' : 'Publish the program in the studio first.'} action={add} />
      ) : (
        <>
          {add ? <div className="flex justify-end">{add}</div> : null}
          <Card className="overflow-hidden">
            <Table>
              <thead>
                <tr>
                  <Th>What</Th>
                  <Th className="hidden sm:table-cell">Taught</Th>
                  <Th>Price</Th>
                  <Th className="hidden md:table-cell">Monthly</Th>
                  <Th className="hidden sm:table-cell">Status</Th>
                  {d.can_edit ? <Th className="w-12"><span className="sr-only">Edit</span></Th> : null}
                </tr>
              </thead>
              <tbody className="stagger">
                {d.items.map((o) => (
                  <Tr key={o.id}>
                    <Td>
                      <span className="font-medium break-words">{title(o)}</span>
                      <span className="block text-xs text-muted sm:hidden">{MODE[o.mode]}</span>
                    </Td>
                    <Td className="hidden sm:table-cell">{MODE[o.mode]}</Td>
                    <Td className="tabular">
                      {o.gbp_minor != null ? money(o.gbp_minor, 'GBP') : null}
                      {o.token_price ? <span className="block text-xs text-muted">{o.token_price} tokens</span> : null}
                    </Td>
                    <Td className="hidden md:table-cell tabular">{o.instalments_max > 1 ? `Up to ${o.instalments_max}` : 'No'}</Td>
                    <Td className="hidden sm:table-cell">{o.is_active ? <Badge tone="success">On sale</Badge> : <Badge>Off</Badge>}</Td>
                    {d.can_edit ? (
                      <Td>
                        <Button size="icon" variant="ghost" aria-label={`Edit ${title(o)}, ${MODE[o.mode]}`} onClick={() => setEditing(o)}>
                          <Pencil />
                        </Button>
                      </Td>
                    ) : null}
                  </Tr>
                ))}
              </tbody>
            </Table>
          </Card>
        </>
      )}
      <p className="text-xs text-muted">Prices are shown in pounds. Buyers see them in their own currency, from the same price tiers as courses.</p>
      {editing ? <OfferDialog key={editing === 'new' ? 'new' : editing.id} programId={programId} data={d} offer={editing === 'new' ? null : editing} open onOpenChange={(o) => !o && setEditing(null)} /> : null}
    </div>
  )
}
