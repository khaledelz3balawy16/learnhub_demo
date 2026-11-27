/** Corporate packages: routes and navigation, ready for the integrator to plug in.
 *
 * Every page is its own lazy chunk. The paths match the URLs the backend sends Stripe
 * back to (/business/purchases?success=1, /business/packages, /business/live-bookings).
 *
 * In app/router.tsx:
 *   - /business children:  ...corporateBusinessRoutes  (before the '*' route)
 *   - /console children:   ...corporateConsoleRoutes   (before the '*' route)
 *   - LearnerLayout children: ...corporateLearnerRoutes
 *   - businessNav:  ...corporateBusinessNav  (after 'Learning')
 * In pages/console/ConsoleShell.tsx consoleNav: ...corporateConsoleNav
 */
import { BarChart3, Building2, CalendarDays, GraduationCap, LayoutDashboard, Package, Receipt, Armchair, Undo2, Users, Video } from 'lucide-react'
import { lazy, Suspense, type ComponentType, type ReactNode } from 'react'
import type { RouteObject } from 'react-router-dom'

import type { NavSection } from '@/components/layout/WorkspaceLayout'
import { PageSpinner } from '@/app/guards'

const named = <K extends string>(load: () => Promise<Record<K, ComponentType>>, name: K) => lazy(() => load().then((m) => ({ default: m[name] })))
const page = (el: ReactNode) => <Suspense fallback={<PageSpinner />}>{el}</Suspense>

const CorporateOverviewPage = named(() => import('@/pages/business/corporate/CorporateOverviewPage'), 'CorporateOverviewPage')
const PackagesPage = named(() => import('@/pages/business/corporate/PackagesPage'), 'PackagesPage')
const PurchasesPage = named(() => import('@/pages/business/corporate/PurchasesPage'), 'PurchasesPage')
const SeatsPage = named(() => import('@/pages/business/corporate/SeatsPage'), 'SeatsPage')
const ProgramSeatsPage = named(() => import('@/pages/business/corporate/ProgramSeatsPage'), 'ProgramSeatsPage')
const BuySeatsPage = named(() => import('@/pages/business/corporate/BuySeatsPage'), 'BuySeatsPage')
const TeamPage = named(() => import('@/pages/business/TeamPage'), 'TeamPage')
const LiveTrainingPage = named(() => import('@/pages/business/corporate/LiveTrainingPage'), 'LiveTrainingPage')
const CancellationsPage = named(() => import('@/pages/business/corporate/CancellationsPage'), 'CancellationsPage')
const MyLiveTrainingPage = named(() => import('@/features/corporate/MyLiveTrainingPage'), 'MyLiveTrainingPage')
const ConsolePackages = named(() => import('@/pages/console/corporate/CorporatePackagesPage'), 'ConsoleCorporatePackagesPage')
const ConsoleLive = named(() => import('@/pages/console/corporate/CorporateLivePage'), 'ConsoleCorporateLivePage')
const ConsoleCases = named(() => import('@/pages/console/corporate/CorporateCasesPage'), 'ConsoleCorporateCasesPage')
const ConsoleReports = named(() => import('@/pages/console/corporate/CorporateReportsPage'), 'ConsoleCorporateReportsPage')

/** Children of /business (company owner, admin or manager; buying is admin-only inside). */
export const corporateBusinessRoutes: RouteObject[] = [
  { path: 'corporate', element: page(<CorporateOverviewPage />), handle: { title: 'Company training', art: 'seats' } },
  { path: 'packages', element: page(<PackagesPage />), handle: { title: 'Course packages', art: 'seats' } },
  { path: 'purchases', element: page(<PurchasesPage />), handle: { title: 'Purchases', art: 'ribbons' } },
  { path: 'seats', element: page(<SeatsPage />), handle: { title: 'Course seats', art: 'seats' } },
  // M22: program seats and the line manager view
  { path: 'program-seats', element: page(<ProgramSeatsPage />), handle: { title: 'Program seats', art: 'seats' } },
  { path: 'program-seats/buy', element: page(<BuySeatsPage />), handle: { title: 'Buy program seats', art: 'seats' } },
  { path: 'team', element: page(<TeamPage />), handle: { title: 'My team', art: 'orgchart' } },
  { path: 'live-bookings', element: page(<LiveTrainingPage />), handle: { title: 'Short-course live training', art: 'timetable' } },
  { path: 'cancellations', element: page(<CancellationsPage />), handle: { title: 'Refunds and changes', art: 'ribbons' } },
]

/** Inside LearnerLayout (any signed-in user; shows only their own live training). */
export const corporateLearnerRoutes: RouteObject[] = [{ path: '/learn/live', element: page(<MyLiveTrainingPage />), handle: { title: 'My live training', art: 'timetable' } }]

/** Children of /console (staff). */
export const corporateConsoleRoutes: RouteObject[] = [
  { path: 'corporate', element: page(<ConsolePackages />), handle: { title: 'Company packages', art: 'seats' } },
  { path: 'corporate/live', element: page(<ConsoleLive />), handle: { title: 'Short-course live training', art: 'timetable' } },
  { path: 'corporate/cases', element: page(<ConsoleCases />), handle: { title: 'Refunds and departures', art: 'ribbons' } },
  { path: 'corporate/reports', element: page(<ConsoleReports />), handle: { title: 'Company reports', art: 'chartgrid' } },
]

export const corporateBusinessNav: NavSection[] = [
  {
    title: 'Company training',
    items: [
      { to: '/business/corporate', label: 'Overview', Icon: LayoutDashboard },
      { to: '/business/packages', label: 'Course packages', Icon: Package },
      { to: '/business/program-seats', label: 'Program seats', Icon: GraduationCap },
      { to: '/business/team', label: 'My team', Icon: Users },
      { to: '/business/seats', label: 'Course seats', Icon: Armchair },
      { to: '/business/live-bookings', label: 'Short-course live training', Icon: Video },
      { to: '/business/purchases', label: 'Purchases', Icon: Receipt },
      { to: '/business/cancellations', label: 'Refunds and changes', Icon: Undo2 },
    ],
  },
]

export const corporateConsoleNav: NavSection[] = [
  {
    title: 'Companies',
    items: [
      { to: '/console/corporate', label: 'Company packages', Icon: Building2, end: true },
      { to: '/console/corporate/live', label: 'Short-course live training', Icon: CalendarDays },
      { to: '/console/corporate/cases', label: 'Refunds and departures', Icon: Undo2 },
      { to: '/console/corporate/reports', label: 'Company reports', Icon: BarChart3 },
    ],
  },
]
