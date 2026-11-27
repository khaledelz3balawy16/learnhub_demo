import { KeyRound, Plus, ShieldCheck, Trash2, UserMinus, UserPlus, Users } from 'lucide-react'
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
import { type StaffRole, useAddRoleMember, useCreateRole, useDeleteRole, useRemoveRoleMember, useRoleMembers, useStaffRoles, useUpdateRole } from '@/features/programs/api'

const err = (e: unknown) => toast.error((e as Error).message)
type Perm = { code: string; label: string }

function RoleForm({ role, permissions, onSaved }: { role?: StaffRole; permissions: Perm[]; onSaved: (id: string) => void }) {
  const create = useCreateRole()
  const update = useUpdateRole()
  const [name, setName] = useState(role?.name ?? '')
  const [description, setDescription] = useState(role?.description ?? '')
  const [perms, setPerms] = useState<string[]>(role?.permissions ?? [])
  const toggle = (code: string) => setPerms((p) => (p.includes(code) ? p.filter((c) => c !== code) : [...p, code]))
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const body = { name: name.trim(), description: description.trim(), permissions: perms }
    if (role) update.mutate({ id: role.id, body }, { onSuccess: () => toast.success('Role saved'), onError: err })
    else create.mutate(body, { onSuccess: (r) => (toast.success('Role created'), onSaved(r.id)), onError: err })
  }
  return (
    <form className="grid gap-4" onSubmit={submit}>
      <Field label="Role name">{(p) => <Input {...p} value={name} onChange={(e) => setName(e.target.value)} minLength={2} maxLength={80} required />}</Field>
      <Field label="What it's for (optional)">{(p) => <Textarea {...p} rows={2} value={description} onChange={(e) => setDescription(e.target.value)} maxLength={300} />}</Field>
      <fieldset className="grid gap-2">
        <legend className="mb-1 text-sm font-medium">People with this role can</legend>
        {permissions.map((p) => (
          <label key={p.code} className="flex cursor-pointer items-start gap-3 rounded-md border border-border p-3 text-sm transition-colors hover:bg-surface-2 has-[:checked]:border-primary/40 has-[:checked]:bg-primary-soft/40">
            <input type="checkbox" className="mt-0.5 size-4 accent-[var(--primary)]" checked={perms.includes(p.code)} onChange={() => toggle(p.code)} />
            <span>{p.label}</span>
          </label>
        ))}
      </fieldset>
      <div className="flex justify-end">
        <Button type="submit" loading={create.isPending || update.isPending}>
          {role ? 'Save role' : 'Create role'}
        </Button>
      </div>
    </form>
  )
}

function Members({ role }: { role: StaffRole }) {
  const members = useRoleMembers(role.id)
  const add = useAddRoleMember(role.id)
  const remove = useRemoveRoleMember(role.id)
  const [email, setEmail] = useState('')
  const [removing, setRemoving] = useState<{ id: string; name: string } | null>(null)
  return (
    <section aria-label="People with this role" className="grid gap-3">
      <h3 className="text-sm font-semibold">People with this role</h3>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          add.mutate(email.trim(), { onSuccess: () => (toast.success('Role given'), setEmail('')), onError: err })
        }}
      >
        <div className="min-w-0 flex-1">
          <Field label="Staff email">{(p) => <Input {...p} type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />}</Field>
        </div>
        <Button type="submit" loading={add.isPending}>
          <UserPlus /> Give role
        </Button>
      </form>
      {members.error ? (
        <ErrorState message={(members.error as Error).message} onRetry={() => void members.refetch()} />
      ) : !members.data ? (
        <Skeleton className="h-24" />
      ) : !members.data.length ? (
        <EmptyState icon={<Users />} title="Nobody has this role yet" />
      ) : (
        <Card className="overflow-hidden">
          <ul className="stagger divide-y divide-border">
            {members.data.map((m) => (
              <li key={m.user_id} className="flex items-center gap-3 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{m.name}</p>
                  <p className="truncate text-xs text-muted">{m.email}</p>
                </div>
                <Button variant="ghost" size="icon-sm" aria-label={`Take the role away from ${m.name}`} onClick={() => setRemoving({ id: m.user_id, name: m.name })}>
                  <UserMinus />
                </Button>
              </li>
            ))}
          </ul>
        </Card>
      )}
      <ConfirmDialog
        open={!!removing}
        onOpenChange={(o) => !o && setRemoving(null)}
        title={`Take “${role.name}” away from ${removing?.name ?? ''}?`}
        confirmLabel="Take role away"
        loading={remove.isPending}
        onConfirm={() => removing && remove.mutate(removing.id, { onSuccess: () => (toast.success('Role taken away'), setRemoving(null)), onError: err })}
      />
    </section>
  )
}

export function ConsoleRolesPage() {
  const q = useStaffRoles()
  const del = useDeleteRole()
  const [openId, setOpenId] = useState<string | 'new' | null>(null)
  const [deleting, setDeleting] = useState<StaffRole | null>(null)
  const role = q.data?.roles.find((r) => r.id === openId)
  if (q.error instanceof ApiError && q.error.status === 403)
    return <EmptyState icon={<ShieldCheck />} title="You can't manage staff roles" body="Ask someone with the Admin role to give you access." />
  return (
    <div className="grid gap-6">
      <PageHeader
        title="Staff roles"
        description="Choose what each staff member can do. A person's permissions are all of their roles together."
        actions={
          <Button onClick={() => setOpenId('new')} disabled={!q.data}>
            <Plus /> New role
          </Button>
        }
      />
      {q.error ? (
        <ErrorState message={(q.error as Error).message} onRetry={() => void q.refetch()} />
      ) : !q.data ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-busy="true">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-36" />
          ))}
        </div>
      ) : (
        <ul className="stagger grid gap-4 animate-reveal sm:grid-cols-2 xl:grid-cols-3">
          {q.data.roles.map((r) => (
            <li key={r.id}>
              <Card className="flex h-full flex-col p-4">
                <div className="flex items-start justify-between gap-2">
                  <h2 className="font-semibold">{r.name}</h2>
                  {r.is_system ? <Badge tone="neutral">Built in</Badge> : null}
                </div>
                {r.description ? <p className="mt-1 text-sm text-muted">{r.description}</p> : null}
                <ul className="mt-3 flex flex-wrap gap-1.5">
                  {r.permissions.length ? (
                    r.permissions.map((code) => (
                      <li key={code}>
                        <Badge tone="primary">{q.data.permissions.find((p) => p.code === code)?.label.split(' (')[0] ?? code}</Badge>
                      </li>
                    ))
                  ) : (
                    <li className="text-sm text-muted">No permissions</li>
                  )}
                </ul>
                <div className="mt-auto flex items-center justify-between gap-2 pt-4">
                  <span className="text-xs text-muted tabular">
                    {r.member_count} {r.member_count === 1 ? 'person' : 'people'}
                  </span>
                  <div className="flex gap-1">
                    {!r.is_system ? (
                      <Button variant="ghost" size="icon-sm" aria-label={`Delete role ${r.name}`} onClick={() => setDeleting(r)}>
                        <Trash2 />
                      </Button>
                    ) : null}
                    <Button variant="secondary" size="sm" onClick={() => setOpenId(r.id)}>
                      <KeyRound /> Manage
                    </Button>
                  </div>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
      <DetailSheet open={!!openId} onOpenChange={(o) => !o && setOpenId(null)} title={role ? role.name : 'New role'} description={role ? 'Change what this role allows and who holds it.' : 'Pick what people with this role can do.'}>
        {q.data && openId ? (
          <div className="grid gap-6">
            <RoleForm key={openId} role={role} permissions={q.data.permissions} onSaved={(id) => setOpenId(id)} />
            {role ? <Members role={role} /> : null}
          </div>
        ) : null}
      </DetailSheet>
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={`Delete the role “${deleting?.name ?? ''}”?`}
        body="People keep any other roles they hold."
        confirmLabel="Delete role"
        loading={del.isPending}
        onConfirm={() => deleting && del.mutate(deleting.id, { onSuccess: () => (toast.success('Role deleted'), setDeleting(null)), onError: err })}
      />
    </div>
  )
}
