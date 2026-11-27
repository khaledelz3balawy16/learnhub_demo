import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'

// Programs (M18): console programs, cohorts, groups, closures and staff roles.
// Query keys: ['console', 'programs', …] and ['console', 'roles', …].

const P = ['console', 'programs'] as const

export const CALENDARS: Record<string, string> = {
  'england-and-wales': 'England and Wales',
  scotland: 'Scotland',
  'northern-ireland': 'Northern Ireland',
}

export const COHORT_STATUS: Record<string, string> = {
  planned: 'Planned',
  open: 'Open for enrolment',
  running: 'Running',
  finished: 'Finished',
  cancelled: 'Cancelled',
}
/** The status changes the server allows from each status (apps.delivery.services.TRANSITIONS). */
export const COHORT_NEXT: Record<string, string[]> = {
  planned: ['open', 'cancelled'],
  open: ['planned', 'running', 'cancelled'],
  running: ['finished'],
  finished: [],
  cancelled: [],
}

export { WEEKDAYS } from '@/lib/schedule'

// ---------------------------------------------------------------- programs
/** Pages of programs (keyset). Every page also says what the signed-in staff member may
 * do (can_build, can_manage) and the provider's default bank holiday calendar. */
export function usePrograms(q: string) {
  return useInfiniteQuery({
    queryKey: [...P, 'list', q],
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET('/api/v1/console/programs', {
          params: {
            query: { q: q || undefined, cursor: pageParam || undefined },
          },
        }),
      ),
    initialPageParam: '',
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    placeholderData: keepPreviousData,
  })
}
export type ProgramRow = NonNullable<ReturnType<typeof usePrograms>['data']>['pages'][number]['items'][number]

export function useProgram(id?: string) {
  return useQuery({
    queryKey: [...P, 'detail', id],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/console/programs/{program_id}', {
          params: { path: { program_id: id! } },
        }),
      ),
    enabled: !!id,
  })
}
export type ProgramDetail = NonNullable<ReturnType<typeof useProgram>['data']>

/** Creates the program in the studio (needs programs.build) and returns its id. */
export function useCreateProgram() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (title: string) => unwrap(api.POST('/api/v1/studio/programs', { body: { title } })),
    onSuccess: () => Promise.all([qc.invalidateQueries({ queryKey: [...P, 'list'] }), qc.invalidateQueries({ queryKey: ['studio', 'courses'] })]),
  })
}

// ---------------------------------------------------------------- cohorts
export function useCreateCohort(programId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; start_date: string; calendar: string | null; capacity: number | null }) =>
      unwrap(
        api.POST('/api/v1/console/programs/{program_id}/cohorts', {
          params: { path: { program_id: programId } },
          body,
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: P }),
  })
}

export function useCohort(id?: string) {
  return useQuery({
    queryKey: [...P, 'cohort', id],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/console/program-cohorts/{cohort_id}', {
          params: { path: { cohort_id: id! } },
        }),
      ),
    enabled: !!id,
  })
}
export type CohortDetail = NonNullable<ReturnType<typeof useCohort>['data']>
export type CohortGroup = CohortDetail['groups'][number]

/** Every cohort change can move dates, counts or lists on the program page too. */
function useCohortDone(cohortId: string) {
  const qc = useQueryClient()
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: [...P, 'cohort', cohortId] }),
      qc.invalidateQueries({ queryKey: [...P, 'detail'] }),
      qc.invalidateQueries({ queryKey: [...P, 'list'] }),
    ])
}

export function useUpdateCohort(cohortId: string) {
  const done = useCohortDone(cohortId)
  return useMutation({
    mutationFn: (body: { name?: string; start_date?: string; calendar?: string; capacity?: number | null; status?: string }) =>
      unwrap(
        api.PATCH('/api/v1/console/program-cohorts/{cohort_id}', {
          params: { path: { cohort_id: cohortId } },
          body,
        }),
      ),
    onSuccess: done,
  })
}

export function useSetModuleStart(cohortId: string) {
  const done = useCohortDone(cohortId)
  return useMutation({
    mutationFn: (v: { moduleKey: string; startsOn: string | null }) =>
      unwrap(
        api.PUT('/api/v1/console/program-cohorts/{cohort_id}/modules/{module_key}/start', {
          params: { path: { cohort_id: cohortId, module_key: v.moduleKey } },
          body: { starts_on: v.startsOn },
        }),
      ),
    onSuccess: done,
  })
}

// ---------------------------------------------------------------- groups
export type GroupBody = {
  name?: string
  weekday?: number | null
  starts_at?: string | null
  ends_at?: string | null
  capacity?: number | null
  tutor_id?: string | null
  status?: string
}

export function useCreateGroup(cohortId: string) {
  const done = useCohortDone(cohortId)
  return useMutation({
    mutationFn: (body: GroupBody) =>
      unwrap(
        api.POST('/api/v1/console/program-cohorts/{cohort_id}/groups', {
          params: { path: { cohort_id: cohortId } },
          body,
        }),
      ),
    onSuccess: done,
  })
}

export function useUpdateGroup(cohortId: string) {
  const done = useCohortDone(cohortId)
  return useMutation({
    mutationFn: (v: { id: string; body: GroupBody }) =>
      unwrap(
        api.PATCH('/api/v1/console/program-groups/{group_id}', {
          params: { path: { group_id: v.id } },
          body: v.body,
        }),
      ),
    onSuccess: done,
  })
}

export function useDeleteGroup(cohortId: string) {
  const done = useCohortDone(cohortId)
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.DELETE('/api/v1/console/program-groups/{group_id}', {
          params: { path: { group_id: id } },
        }),
      ),
    onSuccess: done,
  })
}

export function useGroupMembers(groupId?: string) {
  return useInfiniteQuery({
    queryKey: [...P, 'members', groupId],
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET('/api/v1/console/program-groups/{group_id}/members', {
          params: {
            path: { group_id: groupId! },
            query: { cursor: pageParam || undefined },
          },
        }),
      ),
    initialPageParam: '',
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: !!groupId,
  })
}

export function useAddMembers(cohortId: string, groupId: string) {
  const qc = useQueryClient()
  const done = useCohortDone(cohortId)
  return useMutation({
    mutationFn: (emails: string[]) =>
      unwrap(
        api.POST('/api/v1/console/program-groups/{group_id}/members', {
          params: { path: { group_id: groupId } },
          body: { emails },
        }),
      ),
    onSuccess: () => Promise.all([done(), qc.invalidateQueries({ queryKey: [...P, 'members'] })]),
  })
}

export function useRemoveMember(cohortId: string, groupId: string) {
  const qc = useQueryClient()
  const done = useCohortDone(cohortId)
  return useMutation({
    mutationFn: (enrollmentId: string) =>
      unwrap(
        api.DELETE('/api/v1/console/program-groups/{group_id}/members/{enrollment_id}', {
          params: {
            path: { group_id: groupId, enrollment_id: enrollmentId },
          },
        }),
      ),
    onSuccess: () => Promise.all([done(), qc.invalidateQueries({ queryKey: [...P, 'members', groupId] })]),
  })
}

export function useTutors(q: string) {
  return useQuery({
    queryKey: [...P, 'tutors', q],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/console/program-tutors', {
          params: { query: { q: q || undefined } },
        }),
      ),
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  })
}

// ---------------------------------------------------------------- closures and holidays
export function useProviderClosures() {
  return useQuery({
    queryKey: [...P, 'closures'],
    queryFn: () => unwrap(api.GET('/api/v1/console/program-closures')),
  })
}

/** Closures move dates in one cohort (or, provider-wide, in all of them). */
export function useAddClosure() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { cohort_id: string | null; starts_on: string; ends_on: string; reason: string }) => unwrap(api.POST('/api/v1/console/program-closures', { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: P }),
  })
}

export function useDeleteClosure() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.DELETE('/api/v1/console/program-closures/{closure_id}', {
          params: { path: { closure_id: id } },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: P }),
  })
}

export function useSyncHolidays() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/console/program-holidays/sync')),
    onSuccess: () => qc.invalidateQueries({ queryKey: P }),
  })
}

// ---------------------------------------------------------------- staff roles
const R = ['console', 'roles'] as const

export function useStaffRoles() {
  return useQuery({
    queryKey: [...R, 'list'],
    queryFn: () => unwrap(api.GET('/api/v1/console/roles')),
  })
}
export type StaffRole = NonNullable<ReturnType<typeof useStaffRoles>['data']>['roles'][number]

export function useRoleMembers(roleId?: string) {
  return useQuery({
    queryKey: [...R, 'members', roleId],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/console/roles/{role_id}/members', {
          params: { path: { role_id: roleId! } },
        }),
      ),
    enabled: !!roleId,
  })
}

/** Roles change who can do what: the program screens re-check their permission flags too. */
function useRolesDone() {
  const qc = useQueryClient()
  return () => Promise.all([qc.invalidateQueries({ queryKey: R }), qc.invalidateQueries({ queryKey: P })])
}

type RoleBody = { name?: string; description?: string; permissions?: string[] }

export function useCreateRole() {
  const done = useRolesDone()
  return useMutation({
    mutationFn: (body: RoleBody) => unwrap(api.POST('/api/v1/console/roles', { body })),
    onSuccess: done,
  })
}

export function useUpdateRole() {
  const done = useRolesDone()
  return useMutation({
    mutationFn: (v: { id: string; body: RoleBody }) =>
      unwrap(
        api.PATCH('/api/v1/console/roles/{role_id}', {
          params: { path: { role_id: v.id } },
          body: v.body,
        }),
      ),
    onSuccess: done,
  })
}

export function useDeleteRole() {
  const done = useRolesDone()
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.DELETE('/api/v1/console/roles/{role_id}', {
          params: { path: { role_id: id } },
        }),
      ),
    onSuccess: done,
  })
}

export function useAddRoleMember(roleId: string) {
  const done = useRolesDone()
  return useMutation({
    mutationFn: (email: string) =>
      unwrap(
        api.POST('/api/v1/console/roles/{role_id}/members', {
          params: { path: { role_id: roleId } },
          body: { email },
        }),
      ),
    onSuccess: done,
  })
}

export function useRemoveRoleMember(roleId: string) {
  const done = useRolesDone()
  return useMutation({
    mutationFn: (userId: string) =>
      unwrap(
        api.DELETE('/api/v1/console/roles/{role_id}/members/{user_id}', {
          params: { path: { role_id: roleId, user_id: userId } },
        }),
      ),
    onSuccess: done,
  })
}

// ---------------------------------------------------------------- program settings and KSBs (M19)
export const OTJ_TARGETS: Record<string, string> = {
  none: 'No target',
  hours_per_week: 'Hours per teaching week',
  total_hours: 'Total hours over the cohort',
}
export const KSB_KINDS: Record<string, string> = {
  knowledge: 'Knowledge',
  skill: 'Skill',
  behaviour: 'Behaviour',
}

export function useProgramSettings(programId?: string) {
  return useQuery({
    queryKey: [...P, 'settings', programId],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/console/programs/{program_id}/settings', {
          params: { path: { program_id: programId! } },
        }),
      ),
    enabled: !!programId,
  })
}
export type ProgramSettings = NonNullable<ReturnType<typeof useProgramSettings>['data']>

export type ProgramSettingsBody = Partial<components['schemas']['ConsoleProgramSettingsIn']>

/** The standard drives the KSB map, so both refresh after a change. */
export function useSaveProgramSettings(programId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: ProgramSettingsBody) =>
      unwrap(
        api.PUT('/api/v1/console/programs/{program_id}/settings', {
          params: { path: { program_id: programId } },
          body: { clear_ksb_standard: false, ...body },
        }),
      ),
    onSuccess: (data) => {
      qc.setQueryData([...P, 'settings', programId], data)
      return qc.invalidateQueries({ queryKey: [...P, 'ksb-map', programId] })
    },
  })
}

const K = ['console', 'ksb'] as const

export function useKsbStandards(q: string) {
  return useQuery({
    queryKey: [...K, 'list', q],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/console/ksb-standards', {
          params: { query: { q: q || undefined } },
        }),
      ),
    placeholderData: keepPreviousData,
  })
}

export function useKsbStandard(id?: string | null) {
  return useQuery({
    queryKey: [...K, 'detail', id],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/console/ksb-standards/{standard_id}', {
          params: { path: { standard_id: id! } },
        }),
      ),
    enabled: !!id,
  })
}

/** A new or grown standard changes the lists, its detail and any program map showing it. */
function useKsbDone() {
  const qc = useQueryClient()
  return () => Promise.all([qc.invalidateQueries({ queryKey: K }), qc.invalidateQueries({ queryKey: [...P, 'ksb-map'] })])
}

export function useFetchStandard() {
  const done = useKsbDone()
  return useMutation({
    mutationFn: (code: string) => unwrap(api.POST('/api/v1/console/ksb-imports/fetch', { body: { code } })),
    onSuccess: done,
  })
}

export function useUploadStandard() {
  const done = useKsbDone()
  return useMutation({
    mutationFn: (standard: Record<string, unknown>) => unwrap(api.POST('/api/v1/console/ksb-imports/upload', { body: { standard } })),
    onSuccess: done,
  })
}

export function useCreateCustomStandard() {
  const done = useKsbDone()
  return useMutation({
    mutationFn: (body: { code: string; title: string }) => unwrap(api.POST('/api/v1/console/ksb-standards', { body })),
    onSuccess: done,
  })
}

export function useAddKsbItem(standardId: string) {
  const done = useKsbDone()
  return useMutation({
    mutationFn: (body: { kind: string; text: string }) =>
      unwrap(
        api.POST('/api/v1/console/ksb-standards/{standard_id}/items', {
          params: { path: { standard_id: standardId } },
          body,
        }),
      ),
    onSuccess: done,
  })
}

export function useKsbMap(programId?: string) {
  return useQuery({
    queryKey: [...P, 'ksb-map', programId],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/console/programs/{program_id}/ksb-map', {
          params: { path: { program_id: programId! } },
        }),
      ),
    enabled: !!programId,
  })
}
export type KsbMap = NonNullable<ReturnType<typeof useKsbMap>['data']>

/** One component's KSBs. Optimistic: the matrix ticks at once and rolls back on error. */
export function useSetKsbMap(programId: string) {
  const qc = useQueryClient()
  const key = [...P, 'ksb-map', programId]
  return useMutation({
    mutationFn: (v: { lectureKey: string; itemIds: string[] }) =>
      unwrap(
        api.PUT('/api/v1/console/programs/{program_id}/ksb-map/{lecture_key}', {
          params: {
            path: { program_id: programId, lecture_key: v.lectureKey },
          },
          body: { item_ids: v.itemIds },
        }),
      ),
    onMutate: async (v) => {
      await qc.cancelQueries({ queryKey: key })
      const before = qc.getQueryData<KsbMap>(key)
      if (before)
        qc.setQueryData<KsbMap>(key, {
          ...before,
          components: before.components.map((c) => (c.lecture_key === v.lectureKey ? { ...c, item_ids: v.itemIds } : c)),
        })
      return { before }
    },
    onError: (_e, _v, ctx) => ctx?.before && qc.setQueryData(key, ctx.before),
  })
}

// ---------------------------------------------------------------- off-the-job approvals (M19)
const O = ['console', 'otj'] as const

export function useOtjPending() {
  return useInfiniteQuery({
    queryKey: [...O, 'pending'],
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET('/api/v1/console/otj-pending', {
          params: { query: { cursor: pageParam || undefined } },
        }),
      ),
    initialPageParam: '',
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  })
}
export type OtjPending = NonNullable<ReturnType<typeof useOtjPending>['data']>['pages'][number]['items'][number]

export function useDecideOtj() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string; approve: boolean; note: string }) =>
      unwrap(
        api.POST('/api/v1/console/otj/{entry_id}/decide', {
          params: { path: { entry_id: v.id } },
          body: { approve: v.approve, note: v.note },
        }),
      ),
    onSuccess: () => Promise.all([qc.invalidateQueries({ queryKey: O }), qc.invalidateQueries({ queryKey: [...P, 'record'] })]),
  })
}

export function useLearnerRecord(enrollmentId?: string | null) {
  return useQuery({
    queryKey: [...P, 'record', enrollmentId],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/console/program-enrollments/{enrollment_id}/record', {
          params: { path: { enrollment_id: enrollmentId! } },
        }),
      ),
    enabled: !!enrollmentId,
  })
}

// ---------------------------------------------------------------- live sessions and workshops (M20)
// Keys: [...P, 'sessions', groupId], [...P, 'attendance', kind, id], [...P, 'workshops', …].

export function useMeetingsStatus() {
  return useQuery({
    queryKey: ['console', 'meetings-status'],
    queryFn: () => unwrap(api.GET('/api/v1/console/meetings/status')),
    staleTime: 5 * 60_000,
  })
}

export function useGroupSessions(groupId?: string | null) {
  return useQuery({
    queryKey: [...P, 'sessions', groupId],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/console/program-groups/{group_id}/sessions', {
          params: { path: { group_id: groupId! } },
        }),
      ),
    enabled: !!groupId,
  })
}
export type LiveSessionRow = NonNullable<ReturnType<typeof useGroupSessions>['data']>['items'][number]

export function usePlanSessions(groupId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/api/v1/console/program-groups/{group_id}/sessions/plan', {
          params: { path: { group_id: groupId } },
        }),
      ),
    onSuccess: () => Promise.all([qc.invalidateQueries({ queryKey: [...P, 'sessions', groupId] }), qc.invalidateQueries({ queryKey: [...P, 'teaching'] })]),
  })
}

export type SessionPatch = Partial<components['schemas']['ConsoleLiveSessionPatchIn']>
export function useUpdateSession(groupId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string; body: SessionPatch }) =>
      unwrap(
        api.PATCH('/api/v1/console/program-sessions/{session_id}', {
          params: { path: { session_id: v.id } },
          body: v.body,
        }),
      ),
    onSuccess: () => Promise.all([qc.invalidateQueries({ queryKey: [...P, 'sessions', groupId] }), qc.invalidateQueries({ queryKey: [...P, 'teaching'] })]),
  })
}

export type LiveKind = 'session' | 'workshop'

/** Create (or move) the Teams meeting now. */
export function useMeetingNow(kind: LiveKind) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      kind === 'session'
        ? unwrap(
            api.POST('/api/v1/console/program-sessions/{session_id}/teams', {
              params: { path: { session_id: id } },
            }),
          )
        : unwrap(
            api.POST('/api/v1/console/program-workshops/{workshop_id}/teams', {
              params: { path: { workshop_id: id } },
            }),
          ),
    onSuccess: () =>
      qc.invalidateQueries({
        queryKey: kind === 'session' ? [...P, 'sessions'] : [...P, 'workshops'],
      }),
  })
}

export function useLiveAttendance(kind: LiveKind, id?: string | null) {
  return useQuery({
    queryKey: [...P, 'attendance', kind, id],
    queryFn: () => (kind === 'session' ? unwrap(api.GET('/api/v1/console/program-sessions/{session_id}/attendance', { params: { path: { session_id: id! } } })) : unwrap(api.GET('/api/v1/console/program-workshops/{workshop_id}/attendance', { params: { path: { workshop_id: id! } } }))),
    enabled: !!id,
  })
}
export type AttendanceRow = NonNullable<ReturnType<typeof useLiveAttendance>['data']>['items'][number]

/** Marks change the counts on the list and every learner record (OTJ, CPD). */
function useAfterAttendance(kind: LiveKind, id: string) {
  const qc = useQueryClient()
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: [...P, 'attendance', kind, id] }),
      qc.invalidateQueries({
        queryKey: kind === 'session' ? [...P, 'sessions'] : [...P, 'workshops'],
      }),
      qc.invalidateQueries({ queryKey: [...P, 'record'] }),
    ])
}

export function useMarkAttendance(kind: LiveKind, id: string) {
  const after = useAfterAttendance(kind, id)
  return useMutation({
    mutationFn: (marks: { enrollment_id: string; minutes?: number | null }[]) => (kind === 'session' ? unwrap(api.PUT('/api/v1/console/program-sessions/{session_id}/attendance', { params: { path: { session_id: id } }, body: { marks } })) : unwrap(api.PUT('/api/v1/console/program-workshops/{workshop_id}/attendance', { params: { path: { workshop_id: id } }, body: { marks } }))),
    onSuccess: after,
  })
}

export function useSyncAttendance(kind: LiveKind, id: string) {
  const after = useAfterAttendance(kind, id)
  return useMutation({
    mutationFn: () => (kind === 'session' ? unwrap(api.POST('/api/v1/console/program-sessions/{session_id}/attendance/sync', { params: { path: { session_id: id } } })) : unwrap(api.POST('/api/v1/console/program-workshops/{workshop_id}/attendance/sync', { params: { path: { workshop_id: id } } }))),
    onSuccess: after,
  })
}

/** Step 1 of a recording upload: the API makes the video and returns a TUS ticket. */
export function startRecordingUpload(kind: LiveKind, id: string, file: File) {
  const body = { filename: file.name, size_bytes: file.size }
  return kind === 'session'
    ? unwrap(
        api.POST('/api/v1/console/program-sessions/{session_id}/recording', {
          params: { path: { session_id: id } },
          body,
        }),
      )
    : unwrap(
        api.POST('/api/v1/console/program-workshops/{workshop_id}/recording', {
          params: { path: { workshop_id: id } },
          body,
        }),
      )
}

export function useWorkshops(programId?: string) {
  return useInfiniteQuery({
    queryKey: [...P, 'workshops', programId ?? 'all'],
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET('/api/v1/console/program-workshops', {
          params: {
            query: {
              program_id: programId || undefined,
              cursor: pageParam || undefined,
            },
          },
        }),
      ),
    initialPageParam: '',
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  })
}
export type WorkshopRow = NonNullable<ReturnType<typeof useWorkshops>['data']>['pages'][number]['items'][number]
export type WorkshopBody = components['schemas']['ConsoleWorkshopIn']
export type WorkshopPatch = Partial<components['schemas']['ConsoleWorkshopPatchIn']>

export function useSaveWorkshop() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (v: { id: null; body: WorkshopBody } | { id: string; body: WorkshopPatch }) => {
      if (v.id)
        await unwrap(
          api.PATCH('/api/v1/console/program-workshops/{workshop_id}', {
            params: { path: { workshop_id: v.id } },
            body: v.body,
          }),
        )
      else
        await unwrap(
          api.POST('/api/v1/console/program-workshops', {
            body: v.body as WorkshopBody,
          }),
        )
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: [...P, 'workshops'] }),
  })
}

/** The groups the signed-in tutor teaches (console Teaching page). */
export function useMyTeaching() {
  return useQuery({
    queryKey: [...P, 'teaching'],
    queryFn: () => unwrap(api.GET('/api/v1/console/program-teaching')),
  })
}

// ---------------------------------------------------------------- offers (M21)
export function useProgramOffers(programId?: string) {
  return useQuery({
    queryKey: [...P, 'offers', programId],
    queryFn: () => unwrap(api.GET('/api/v1/console/programs/{program_id}/offers', { params: { path: { program_id: programId! } } })),
    enabled: !!programId,
  })
}
export type ProgramOffers = NonNullable<ReturnType<typeof useProgramOffers>['data']>
export type ProgramOfferBody = components['schemas']['ConsoleProgramOfferIn']

/** Add an offer, or change one (what and how it is taught stay fixed once created). */
export function useSaveProgramOffer(programId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (v: { id?: string; body: ProgramOfferBody }) => {
      if (v.id) {
        const { tier_id, token_price, instalments_max, is_active } = v.body
        await unwrap(api.PATCH('/api/v1/console/program-offers/{offer_id}', { params: { path: { offer_id: v.id } }, body: { tier_id, token_price, instalments_max, is_active } }))
      } else {
        await unwrap(api.POST('/api/v1/console/programs/{program_id}/offers', { params: { path: { program_id: programId } }, body: v.body }))
      }
    },
    // the course page shows the offers too
    onSuccess: () => Promise.all([qc.invalidateQueries({ queryKey: [...P, 'offers', programId] }), qc.invalidateQueries({ queryKey: ['course'] })]),
  })
}
