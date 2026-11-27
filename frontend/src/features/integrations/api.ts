import { keepPreviousData, useInfiniteQuery, useMutation, useQueries, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { currentOrgId } from '@/lib/workspace'

// The HR system page (M17: Breathe HR). Every key starts with 'integrations' and carries
// the company id. Types come from the API schema only (/sync-types).

type S = components['schemas']
export type HrOverview = S['HrOverviewOut']
export type HrConnection = S['HrConnectionOut']
export type HrRun = S['HrRunOut']
export type HrPerson = S['HrPersonOut']
export type HrDepartment = S['HrDepartmentOut']
export type HrTrainingTitle = S['HrTrainingTitleOut']
export type HrTrainingRecord = S['HrTrainingRecordOut']
export type HrLeave = S['HrLeaveOut']
export type HrMemberLink = S['HrMemberLinkOut']
export type HrConnectInput = S['HrConnectIn']
export type HrFeature = 'departments' | 'managers' | 'training' | 'leave'

const key = (...parts: string[]) => ['integrations', currentOrgId() ?? '', ...parts]

const isActive = (run?: HrRun | null) => run?.status === 'queued' || run?.status === 'running'

export function useHrOverview() {
  return useQuery({
    queryKey: key('overview'),
    queryFn: () => unwrap(api.GET('/api/v1/integrations/hr')),
    // while a sync runs, check every 3 s so counts and the status update by themselves
    refetchInterval: (q) => (isActive(q.state.data?.latest_run) ? 3000 : false),
  })
}

export function useHrPeople(status: string, q: string, enabled = true) {
  return useInfiniteQuery({
    queryKey: key('people', status, q),
    queryFn: ({ pageParam }) => unwrap(api.GET('/api/v1/integrations/hr/people', { params: { query: { status: status || undefined, q: q || undefined, cursor: pageParam, limit: 50 } } })),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    placeholderData: keepPreviousData,
    enabled,
  })
}

export function useHrRuns(enabled = true) {
  return useQuery({ queryKey: key('runs'), queryFn: () => unwrap(api.GET('/api/v1/integrations/hr/runs')), enabled })
}

export function useHrDepartments(enabled = true) {
  return useQuery({ queryKey: key('departments'), queryFn: () => unwrap(api.GET('/api/v1/integrations/hr/departments')), enabled })
}

export function useHrTrainingTitles(enabled = true) {
  return useQuery({ queryKey: key('training', 'titles'), queryFn: () => unwrap(api.GET('/api/v1/integrations/hr/training/titles')), enabled })
}

export function useHrTrainingRecords(enabled = true) {
  return useQuery({ queryKey: key('training', 'records'), queryFn: () => unwrap(api.GET('/api/v1/integrations/hr/training/records')), enabled })
}

/** Approved leave for the people on one page: a single call, keyed by member. */
/** Leave for the people on screen: one cached request per loaded page of people, so
 *  "Show more" only fetches the new page and no request grows past one page of ids. */
export function useHrLeave(pages: string[][]) {
  return useQueries({
    queries: pages.map((memberIds) => {
      const ids = [...memberIds].sort()
      return {
        queryKey: key('leave', ids.join(',')),
        queryFn: () => unwrap(api.GET('/api/v1/integrations/hr/leave', { params: { query: { member_ids: ids } } })),
        enabled: ids.length > 0,
        staleTime: 5 * 60_000,
      }
    }),
    combine: (results) => new Map(results.flatMap((r) => r.data ?? []).map((r) => [r.member_id, r])),
  })
}

/** Is this member linked to the HR system (and on leave)? For the Person page badges. */
export function useHrMemberLink(memberId: string | undefined) {
  return useQuery({
    queryKey: key('member', memberId ?? ''),
    queryFn: () => unwrap(api.GET('/api/v1/integrations/hr/members/{member_id}', { params: { path: { member_id: memberId! } } })),
    enabled: !!memberId,
    staleTime: 5 * 60_000,
  })
}

// ---------------------------------------------------------------- writes
function invalidate(qc: QueryClient, ...prefixes: string[][]) {
  const org = currentOrgId() ?? ''
  return Promise.all(
    prefixes.map((p) =>
      qc.invalidateQueries({
        predicate: (q) => {
          const k = q.queryKey as unknown[]
          // integrations keys carry the org second; org/compliance keys carry it third
          return p[0] === 'integrations' ? k[0] === 'integrations' && k[1] === org && p.slice(1).every((part, i) => k[i + 2] === part) : p.every((part, i) => k[i] === part)
        },
      }),
    ),
  )
}

const ALL = ['integrations']

export function useHrConnect() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: HrConnectInput) => unwrap(api.POST('/api/v1/integrations/hr/connect', { body })),
    onSuccess: () => invalidate(qc, ALL),
  })
}

export function useHrValidate() {
  const qc = useQueryClient()
  return useMutation({ mutationFn: () => unwrap(api.POST('/api/v1/integrations/hr/validate')), onSuccess: () => invalidate(qc, ['integrations', 'overview']) })
}

export function useHrReplaceKey() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (apiKey: string) => unwrap(api.POST('/api/v1/integrations/hr/replace-key', { body: { api_key: apiKey } })),
    onSuccess: () => invalidate(qc, ['integrations', 'overview']),
  })
}

export function useHrFeatures() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (features: HrFeature[]) => unwrap(api.PATCH('/api/v1/integrations/hr/features', { body: { features } })),
    onSuccess: () => invalidate(qc, ['integrations', 'overview']),
  })
}

export function useHrPause() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (paused: boolean) => unwrap(api.POST('/api/v1/integrations/hr/pause', { body: { paused } })),
    onSuccess: () => invalidate(qc, ['integrations', 'overview']),
  })
}

export function useHrDisconnect() {
  const qc = useQueryClient()
  return useMutation({ mutationFn: () => unwrap(api.DELETE('/api/v1/integrations/hr')), onSuccess: () => invalidate(qc, ALL) })
}

/** A sync changes people, departments, training and leave, and through them units and
 * compliance; the overview polls until it ends, then refreshes the rest. */
export function useHrSync() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/integrations/hr/sync')),
    onSuccess: () => invalidate(qc, ['integrations', 'overview'], ['integrations', 'runs']),
  })
}

/** After a sync finishes: everything it may have changed. */
export function useAfterSync() {
  const qc = useQueryClient()
  return useCallback(() => invalidate(qc, ALL, ['org', 'people'], ['org', 'units'], ['compliance']), [qc])
}

export function useHrMatch() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { personId: string; memberId: string }) => unwrap(api.POST('/api/v1/integrations/hr/people/{person_id}/match', { params: { path: { person_id: v.personId } }, body: { member_id: v.memberId } })),
    // linking places them in their department and may import training: people, units, compliance
    onSuccess: () => invalidate(qc, ['integrations', 'people'], ['integrations', 'overview'], ['integrations', 'member'], ['integrations', 'training'], ['org', 'people'], ['org', 'units'], ['compliance']),
  })
}

export function useHrInvite() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { personId: string; role: string; unitId?: string | null; jobRoleId?: string | null }) =>
      unwrap(api.POST('/api/v1/integrations/hr/people/{person_id}/invite', { params: { path: { person_id: v.personId } }, body: { role: v.role, unit_id: v.unitId ?? null, job_role_id: v.jobRoleId ?? null } })),
    onSuccess: () => invalidate(qc, ['integrations', 'people'], ['integrations', 'overview'], ['org', 'invites'], ['org', 'company']),
  })
}

export function useHrIgnore() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { personId: string; undo?: boolean }) =>
      v.undo
        ? unwrap(api.POST('/api/v1/integrations/hr/people/{person_id}/reset', { params: { path: { person_id: v.personId } } }))
        : unwrap(api.POST('/api/v1/integrations/hr/people/{person_id}/ignore', { params: { path: { person_id: v.personId } } })),
    onSuccess: () => invalidate(qc, ['integrations', 'people'], ['integrations', 'overview'], ['integrations', 'member']),
  })
}

export function useHrLinkDepartment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { deptId: string; unitId?: string | null; create?: boolean }) =>
      unwrap(api.PUT('/api/v1/integrations/hr/departments/{dept_id}/unit', { params: { path: { dept_id: v.deptId } }, body: { unit_id: v.unitId ?? null, create: !!v.create } })),
    onSuccess: () => invalidate(qc, ['integrations', 'departments'], ['integrations', 'overview'], ['org', 'units'], ['org', 'people'], ['compliance']),
  })
}

export function useHrMapTraining() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { title: string; requirementId: string | null }) => unwrap(api.PUT('/api/v1/integrations/hr/training/map', { body: { title: v.title, requirement_id: v.requirementId } })),
    onSuccess: () => invalidate(qc, ['integrations', 'training'], ['integrations', 'overview'], ['compliance']),
  })
}

export const HR_FEATURES: { key: HrFeature; label: string; hint: string }[] = [
  { key: 'departments', label: 'Departments', hint: 'Place linked people in the team that matches their Breathe department.' },
  { key: 'managers', label: 'Line managers', hint: "Make each person's Breathe line manager a manager of that team." },
  { key: 'training', label: 'Training records', hint: 'Count training recorded in Breathe towards your requirements.' },
  { key: 'leave', label: 'Approved leave', hint: 'Show "On leave until …" to admins and managers.' },
]

export const HR_STATUS: Record<string, { label: string; tone: 'success' | 'warning' | 'neutral' | 'danger' | 'info' }> = {
  active: { label: 'Connected', tone: 'success' },
  attention: { label: 'Needs attention', tone: 'warning' },
  paused: { label: 'Paused', tone: 'neutral' },
  disabled: { label: 'Disconnected', tone: 'danger' },
}

export const PERSON_STATUS: Record<string, { label: string; tone: 'success' | 'warning' | 'neutral' | 'info' }> = {
  pending: { label: 'To review', tone: 'warning' },
  matched: { label: 'Linked', tone: 'success' },
  invited: { label: 'Invited', tone: 'info' },
  ignored: { label: 'Ignored', tone: 'neutral' },
}

export { isActive as isRunActive }
