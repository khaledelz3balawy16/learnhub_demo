import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { currentOrgId } from '@/lib/workspace'

// The inclusion test. The learner's keys start with 'inclusion'; the console's with
// 'console-inclusion'. Types come from the API schema only (/sync-types).

type S = components['schemas']
export type InclusionMe = S['InclusionMeOut']
export type InclusionSection = S['InclusionSectionOut']
export type EditorSection = S['ConsoleInclusionSectionOut']
export type EditorQuestion = S['ConsoleInclusionQuestionOut']
export type InclusionOption = S['ConsoleInclusionOptionSchema']
export type InclusionResult = S['InclusionResultOut']
export type InclusionDetail = S['InclusionDetailOut']
/** console: every learner (platform admins); company: the current company's members (its owners and admins) */
export type ResultsScope = 'console' | 'company'
export type Answers = Record<string, number>

// ---------------------------------------------------------------- learner
export function useInclusionMe() {
  return useQuery({ queryKey: ['inclusion', 'me'], queryFn: () => unwrap(api.GET('/api/v1/inclusion/me')) })
}

/** Saves answers so far. Doesn't touch the cache: the page holds the answers while open. */
export function useSaveInclusionDraft() {
  return useMutation({
    mutationFn: (body: { answers: Answers; consent: boolean }) => unwrap(api.PUT('/api/v1/inclusion/me/draft', { body })),
  })
}

export function useSubmitInclusion() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { answers: Answers; consent: boolean }) => unwrap(api.POST('/api/v1/inclusion/me/submit', { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['inclusion', 'me'] }),
  })
}

// ---------------------------------------------------------------- console: editor
const EDITOR = ['console-inclusion', 'editor']

export function useInclusionEditor() {
  return useQuery({ queryKey: EDITOR, queryFn: () => unwrap(api.GET('/api/v1/console/inclusion/questions')) })
}

/** Every editor change: refresh the editor; a threshold or section change also changes flags
 * in the results; and what learners see changes too. */
function useEditorMutation<V, R>(fn: (v: V) => Promise<R>, opts: { results?: boolean } = {}) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: EDITOR })
      void qc.invalidateQueries({ queryKey: ['inclusion', 'me'] })
      if (opts.results) void qc.invalidateQueries({ queryKey: ['console-inclusion', 'results'] })
    },
  })
}

type SectionPatch = { title?: string; description?: string; flag_threshold?: number | null; is_active?: boolean }
type QuestionPatch = { text?: string; options?: InclusionOption[]; required?: boolean; is_active?: boolean }

export const useCreateInclusionSection = () =>
  useEditorMutation((body: { title: string; flag_threshold?: number | null }) => unwrap(api.POST('/api/v1/console/inclusion/sections', { body })), { results: true })

export const useUpdateInclusionSection = () =>
  useEditorMutation(
    ({ id, ...body }: SectionPatch & { id: string }) => unwrap(api.PATCH('/api/v1/console/inclusion/sections/{section_id}', { params: { path: { section_id: id } }, body })),
    { results: true },
  )

export const useDeleteInclusionSection = () =>
  useEditorMutation((id: string) => unwrap(api.DELETE('/api/v1/console/inclusion/sections/{section_id}', { params: { path: { section_id: id } } })), { results: true })

export const useOrderInclusionSections = () =>
  useEditorMutation((ids: string[]) => unwrap(api.PUT('/api/v1/console/inclusion/sections-order', { body: { ids } })))

export const useCreateInclusionQuestion = () =>
  useEditorMutation(({ sectionId, ...body }: { sectionId: string; text: string; options?: InclusionOption[]; required?: boolean }) =>
    unwrap(api.POST('/api/v1/console/inclusion/sections/{section_id}/questions', { params: { path: { section_id: sectionId } }, body })),
  )

export const useUpdateInclusionQuestion = () =>
  useEditorMutation(({ id, ...body }: QuestionPatch & { id: string }) =>
    unwrap(api.PATCH('/api/v1/console/inclusion/questions/{question_id}', { params: { path: { question_id: id } }, body })),
  )

export const useDeleteInclusionQuestion = () =>
  useEditorMutation((id: string) => unwrap(api.DELETE('/api/v1/console/inclusion/questions/{question_id}', { params: { path: { question_id: id } } })))

export const useOrderInclusionQuestions = () =>
  useEditorMutation(({ sectionId, ids }: { sectionId: string; ids: string[] }) =>
    unwrap(api.PUT('/api/v1/console/inclusion/sections/{section_id}/questions-order', { params: { path: { section_id: sectionId } }, body: { ids } })),
  )

// ---------------------------------------------------------------- results (console or company)
const resultsKey = (scope: ResultsScope) => (scope === 'console' ? ['console-inclusion', 'results'] : ['inclusion', 'company', currentOrgId() ?? '', 'results'])

export function useInclusionResults(scope: ResultsScope, filters: { q: string; flagged: '' | 'yes' | 'no'; section: string }) {
  return useInfiniteQuery({
    queryKey: [...resultsKey(scope), filters],
    queryFn: ({ pageParam }) => {
      const query = {
        q: filters.q || undefined,
        flagged: filters.flagged ? filters.flagged === 'yes' : undefined,
        section: filters.section || undefined,
        cursor: pageParam,
        limit: 30,
      }
      return scope === 'console'
        ? unwrap(api.GET('/api/v1/console/inclusion/results', { params: { query } }))
        : unwrap(api.GET('/api/v1/inclusion/company/results', { params: { query } }))
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    placeholderData: keepPreviousData,
  })
}

export function useInclusionResult(scope: ResultsScope, attemptId: string | null) {
  return useQuery({
    queryKey: [...resultsKey(scope), 'detail', attemptId],
    queryFn: () => {
      const params = { path: { attempt_id: attemptId! } }
      return scope === 'console'
        ? unwrap(api.GET('/api/v1/console/inclusion/results/{attempt_id}', { params }))
        : unwrap(api.GET('/api/v1/inclusion/company/results/{attempt_id}', { params }))
    },
    enabled: !!attemptId,
  })
}
