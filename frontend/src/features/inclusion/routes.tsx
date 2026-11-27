/** Inclusion test: console routes and navigation.
 *
 * In app/router.tsx, /console children: ...inclusionConsoleRoutes (before the '*' route).
 * In pages/console/ConsoleShell.tsx consoleNav: ...inclusionConsoleNav.
 * The learner page (/learn/inclusion) is a learner route in app/router.tsx.
 */
import { HeartHandshake, ListChecks } from 'lucide-react'
import { lazy, Suspense, type ComponentType, type ReactNode } from 'react'
import type { RouteObject } from 'react-router-dom'

import { PageSpinner } from '@/app/guards'
import type { NavSection } from '@/components/layout/WorkspaceLayout'

const named = <K extends string>(load: () => Promise<Record<K, ComponentType>>, name: K) => lazy(() => load().then((m) => ({ default: m[name] })))
const page = (el: ReactNode) => <Suspense fallback={<PageSpinner />}>{el}</Suspense>

const ResultsPage = named(() => import('@/pages/console/inclusion/InclusionResultsPage'), 'ConsoleInclusionResultsPage')
const QuestionsPage = named(() => import('@/pages/console/inclusion/InclusionQuestionsPage'), 'ConsoleInclusionQuestionsPage')

export const inclusionConsoleRoutes: RouteObject[] = [
  { path: 'inclusion/results', element: page(<ResultsPage />), handle: { title: 'Inclusion results · Console', art: 'spectrum' } },
  { path: 'inclusion/questions', element: page(<QuestionsPage />), handle: { title: 'Inclusion questions · Console', art: 'spectrum' } },
]

// admins only: the pages say so to anyone else (the API refuses them)
export const inclusionConsoleNav: NavSection[] = [
  {
    title: 'Learner support',
    items: [
      { to: '/console/inclusion/results', label: 'Inclusion results', Icon: HeartHandshake },
      { to: '/console/inclusion/questions', label: 'Inclusion questions', Icon: ListChecks },
    ],
  },
]
