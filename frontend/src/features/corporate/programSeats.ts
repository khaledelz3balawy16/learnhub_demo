/** Program seats for companies (M22): signup, the order being built, checkout, seats,
 * swaps and the line manager view. Company queries are keyed by the org id, so switching
 * company never shows another company's cached data. */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { currentOrgId } from '@/lib/workspace'

type S = components['schemas']
export type SeatSetup = S['SeatSetupOut']
export type SeatCatalogue = S['SeatCatalogueOut']
export type SeatProgram = S['SeatProgramOut']
export type SeatOrder = S['SeatOrderOut']
export type SeatLine = S['SeatLineOut']
export type SeatHolder = S['SeatHolderOut']
export type SeatSwap = S['SeatSwapOut']
export type SeatTeamRow = S['SeatTeamRowOut']
export type DraftLine = S['SeatDraftLineIn']
export type ConsoleSeatSwap = S['ConsoleSeatSwapOut']

const key = (...parts: unknown[]) => ['program-seats', currentOrgId(), ...parts]

export function useCompanySignup() {
  return useMutation({ mutationFn: (body: S['SeatSignupIn']) => unwrap(api.POST('/api/v1/corporate/program-seats/signup', { body })) })
}

/** The company being set up: its state and the order being built. While a payment is on its
 * way back from Stripe (`poll`), it asks again every few seconds until the webhook has landed. */
export function useSeatSetup(poll = false, enabled = true) {
  return useQuery({
    queryKey: key('setup'),
    queryFn: () => unwrap(api.GET('/api/v1/corporate/program-seats/setup')),
    enabled,
    refetchInterval: (q) => (poll && q.state.data?.onboarding_state !== 'active' ? 3000 : false),
  })
}

export function useSeatCatalogue() {
  return useQuery({ queryKey: key('catalogue'), queryFn: () => unwrap(api.GET('/api/v1/corporate/program-seats/catalogue')), staleTime: 60_000 })
}

export function useSaveDraft() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (lines: DraftLine[]) => unwrap(api.PUT('/api/v1/corporate/program-seats/draft', { body: { lines } })),
    onSuccess: (data) => qc.setQueryData(key('setup'), data),
  })
}

export function useSeatCheckout() {
  return useMutation({ mutationFn: () => unwrap(api.POST('/api/v1/corporate/program-seats/draft/checkout')) })
}

export function useSeatOrders() {
  return useQuery({ queryKey: key('orders'), queryFn: () => unwrap(api.GET('/api/v1/corporate/program-seats/orders')) })
}

export function useSeatHolders(lineId: string | null) {
  return useQuery({
    queryKey: key('holders', lineId),
    queryFn: () => unwrap(api.GET('/api/v1/corporate/program-seats/lines/{line_id}/holders', { params: { path: { line_id: lineId! } } })),
    enabled: !!lineId,
  })
}

export function useSeatSwaps(open = true) {
  return useQuery({ queryKey: key('swaps', open), queryFn: () => unwrap(api.GET('/api/v1/corporate/program-seats/swaps', { params: { query: { open } } })) })
}

export function useSeatTeam(cursor?: string) {
  return useQuery({
    queryKey: key('team', cursor ?? ''),
    queryFn: () => unwrap(api.GET('/api/v1/corporate/program-seats/team', { params: { query: { cursor } } })),
    placeholderData: (prev) => prev,
  })
}

/** A seat changed hands: the line's holders, the seat counts, the swaps and the team. */
function seatsChanged(qc: ReturnType<typeof useQueryClient>) {
  return Promise.all(['holders', 'orders', 'swaps', 'team'].map((k) => qc.invalidateQueries({ queryKey: key(k) })))
}

export function useGiveSeat() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: S['SeatAllocateIn']) => unwrap(api.POST('/api/v1/corporate/program-seats/allocate', { body })),
    onSuccess: () => seatsChanged(qc),
  })
}

export function useReleaseSeat() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => unwrap(api.POST('/api/v1/corporate/program-seats/allocations/{allocation_id}/release', { params: { path: { allocation_id: id } } })),
    onSuccess: () => seatsChanged(qc),
  })
}

export function useRequestSwap() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string } & S['SeatSwapIn']) =>
      unwrap(api.POST('/api/v1/corporate/program-seats/allocations/{allocation_id}/swap', { params: { path: { allocation_id: id } }, body })),
    onSuccess: () => Promise.all(['holders', 'swaps'].map((k) => qc.invalidateQueries({ queryKey: key(k) }))),
  })
}

export function useDecideSwap() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string } & S['SeatDecideIn']) =>
      unwrap(api.POST('/api/v1/corporate/program-seats/swaps/{swap_id}/decide', { params: { path: { swap_id: id } }, body })),
    onSuccess: () => Promise.all(['holders', 'swaps'].map((k) => qc.invalidateQueries({ queryKey: key(k) }))),
  })
}

export function useCancelSwap() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => unwrap(api.POST('/api/v1/corporate/program-seats/swaps/{swap_id}/cancel', { params: { path: { swap_id: id } } })),
    onSuccess: () => Promise.all(['holders', 'swaps'].map((k) => qc.invalidateQueries({ queryKey: key(k) }))),
  })
}

// ---------------------------------------------------------------- console (provider step)
export function useConsoleSeatSwaps(waiting: boolean) {
  return useQuery({
    queryKey: ['console', 'seat-swaps', waiting],
    queryFn: () => unwrap(api.GET('/api/v1/console/seat-swaps', { params: { query: { waiting, limit: 100 } } })),
  })
}

export function useConsoleDecideSwap() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string } & S['ConsoleSeatSwapDecideIn']) =>
      unwrap(api.POST('/api/v1/console/seat-swaps/{swap_id}/decide', { params: { path: { swap_id: id } }, body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['console', 'seat-swaps'] }),
  })
}
