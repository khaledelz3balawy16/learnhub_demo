import { InclusionResultsView } from '@/features/inclusion/ResultsView'

/** Company workspace > Inclusion results: the company's current members' latest answers
 * (owners and admins only; user decision 2026-11-25). */
export function CompanyInclusionResultsPage() {
  return <InclusionResultsView scope="company" />
}
