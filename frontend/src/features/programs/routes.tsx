/** Programs (M18): console routes and navigation.
 *
 * In app/router.tsx, /console children: ...programsConsoleRoutes (before the '*' route).
 * In pages/console/ConsoleShell.tsx consoleNav: ...programsConsoleNav.
 * Each page is its own lazy chunk.
 */
import { ArrowLeftRight, ClipboardCheck, GraduationCap, KeyRound, Presentation, School } from 'lucide-react'
import { lazy, Suspense, type ComponentType, type ReactNode } from 'react'
import type { RouteObject } from 'react-router-dom'

import { PageSpinner } from '@/app/guards'
import type { NavSection } from '@/components/layout/WorkspaceLayout'

const named = <K extends string>(load: () => Promise<Record<K, ComponentType>>, name: K) => lazy(() => load().then((m) => ({ default: m[name] })))
const page = (el: ReactNode) => <Suspense fallback={<PageSpinner />}>{el}</Suspense>

const ProgramsPage = named(() => import('@/pages/console/programs/ProgramsPage'), 'ConsoleProgramsPage')
const ProgramPage = named(() => import('@/pages/console/programs/ProgramPage'), 'ConsoleProgramPage')
const CohortPage = named(() => import('@/pages/console/programs/CohortPage'), 'ConsoleCohortPage')
const OtjApprovalsPage = named(() => import('@/pages/console/programs/OtjApprovalsPage'), 'ConsoleOtjApprovalsPage')
const TeachingPage = named(() => import('@/pages/console/programs/TeachingPage'), 'ConsoleTeachingPage')
const WorkshopsPage = named(() => import('@/pages/console/programs/WorkshopsPage'), 'ConsoleWorkshopsPage')
const SeatSwapsPage = named(() => import('@/pages/console/programs/SeatSwapsPage'), 'ConsoleSeatSwapsPage')
const RolesPage = named(() => import('@/pages/console/programs/RolesPage'), 'ConsoleRolesPage')

export const programsConsoleRoutes: RouteObject[] = [
  {
    path: 'programs',
    element: page(<ProgramsPage />),
    handle: { title: 'Programs · Console', art: 'curriculum' },
  },
  {
    path: 'programs/:programId',
    element: page(<ProgramPage />),
    handle: { title: 'Program · Console', art: 'curriculum' },
  },
  {
    path: 'cohorts/:cohortId',
    element: page(<CohortPage />),
    handle: { title: 'Cohort · Console', art: 'timetable' },
  },
  {
    path: 'otj',
    element: page(<OtjApprovalsPage />),
    handle: { title: 'Hours to approve · Console', art: 'checklist' },
  },
  {
    path: 'teaching',
    element: page(<TeachingPage />),
    handle: { title: 'My teaching · Console', art: 'timetable' },
  },
  {
    path: 'workshops',
    element: page(<WorkshopsPage />),
    handle: { title: 'Workshops · Console', art: 'timetable' },
  },
  {
    path: 'seat-swaps',
    element: page(<SeatSwapsPage />),
    handle: { title: 'Seat swaps · Console', art: 'seats' },
  },
  {
    path: 'roles',
    element: page(<RolesPage />),
    handle: { title: 'Staff roles · Console', art: 'orgchart' },
  },
]

export const programsConsoleNav: NavSection[] = [
  {
    title: 'Programs',
    items: [
      { to: '/console/programs', label: 'Programs', Icon: GraduationCap },
      { to: '/console/teaching', label: 'My teaching', Icon: School },
      { to: '/console/workshops', label: 'Workshops', Icon: Presentation },
      { to: '/console/otj', label: 'Hours to approve', Icon: ClipboardCheck },
      { to: '/console/seat-swaps', label: 'Seat swaps', Icon: ArrowLeftRight },
      { to: '/console/roles', label: 'Staff roles', Icon: KeyRound },
    ],
  },
]
