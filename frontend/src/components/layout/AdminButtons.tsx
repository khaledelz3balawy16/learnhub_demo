import { LayoutDashboard, Shield } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { useMe } from '@/features/identity/auth'
import { useWorkspace } from '@/features/identity/workspace'
import { Link, useNavigate } from '@/lib/router'

/** Header shortcuts to the admin areas (desktop; phones use the account menu): the platform
 * console for staff, and the company workspace for its owners, admins and managers. */
export function AdminButtons() {
  const { data: me } = useMe()
  const { org, memberships, switchTo } = useWorkspace()
  const navigate = useNavigate()
  if (!me) return null
  const managed = memberships.filter((m) => ['owner', 'admin', 'manager'].includes(m.role) && m.onboarding_state === 'active')
  // the company in use if they manage it, otherwise the first one they manage
  const company = managed.find((m) => m.org_id === org?.org_id) ?? managed[0]
  if (!me.is_staff && !company) return null
  return (
    <span className="mr-1 hidden items-center gap-1 lg:inline-flex">
      {company ? (
        <Button variant="secondary" size="sm" onClick={() => (switchTo(company.org_id), navigate('/business'))} title={`${company.name} dashboard`}>
          <LayoutDashboard /> Company dashboard
        </Button>
      ) : null}
      {me.is_staff ? (
        <Button variant="secondary" size="sm" asChild>
          <Link to="/console">
            <Shield /> Admin console
          </Link>
        </Button>
      ) : null}
    </span>
  )
}
