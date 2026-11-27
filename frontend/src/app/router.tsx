import { BookOpen, Building2, ClipboardCheck, CreditCard, DollarSign, FileBarChart, GraduationCap, HeartHandshake, LayoutDashboard, LifeBuoy, MessageSquare, Network, Plug, ShieldCheck, UserPlus, Users, Wallet } from 'lucide-react'
import { lazy, Suspense, type ReactNode } from 'react'
import { createBrowserRouter, Outlet } from 'react-router-dom'

import { BusinessLayout } from '@/components/layout/BusinessLayout'
import { LearnerLayout } from '@/components/layout/LearnerLayout'
import { PublicLayout } from '@/components/layout/PublicLayout'
import { SiteRoot } from '@/components/layout/SiteRoot'
import { type NavSection, WorkspaceLayout } from '@/components/layout/WorkspaceLayout'
import { corporateBusinessNav, corporateBusinessRoutes, corporateConsoleRoutes, corporateLearnerRoutes } from '@/features/corporate/routes'
import { programsConsoleRoutes } from '@/features/programs/routes'
import { inclusionConsoleRoutes } from '@/features/inclusion/routes'
import { NotFoundPage } from '@/pages/StatusPages'

import { PageSpinner, RequireAuth, RequireManager, RequireRole } from './guards'

// Every page is its own chunk: visitors download the marketplace only.
const named = <K extends string>(load: () => Promise<Record<K, React.ComponentType>>, name: K) =>
  lazy(() => load().then((m) => ({ default: m[name] })))
const HomePage = named(() => import('@/pages/HomePage'), 'HomePage')
const CoursesPage = named(() => import('@/pages/CoursesPage'), 'CoursesPage')
const CoursePage = named(() => import('@/pages/CoursePage'), 'CoursePage')
const MyLearningPage = named(() => import('@/pages/MyLearningPage'), 'MyLearningPage')
const DesignPage = named(() => import('@/pages/DesignPage'), 'DesignPage')
const LoginPage = named(() => import('@/pages/auth/LoginPage'), 'LoginPage')
const SignupPage = named(() => import('@/pages/auth/SignupPage'), 'SignupPage')
const VerifyEmailPage = named(() => import('@/pages/auth/VerifyEmailPage'), 'VerifyEmailPage')
const ForgotPasswordPage = named(() => import('@/pages/auth/ForgotPasswordPage'), 'ForgotPasswordPage')
const ResetPasswordPage = named(() => import('@/pages/auth/ResetPasswordPage'), 'ResetPasswordPage')
const CartPage = named(() => import('@/pages/shop/CartPage'), 'CartPage')
const CheckoutSuccessPage = named(() => import('@/pages/shop/CheckoutSuccessPage'), 'CheckoutSuccessPage')
const PlansPage = named(() => import('@/pages/shop/PlansPage'), 'PlansPage')
const WishlistPage = named(() => import('@/pages/shop/WishlistPage'), 'WishlistPage')
const OrdersPage = named(() => import('@/pages/shop/OrdersPage'), 'OrdersPage')
const PlayerPage = named(() => import('@/pages/learn/PlayerPage'), 'PlayerPage')
const ProgramRecordPage = named(() => import('@/pages/learner/ProgramRecordPage'), 'ProgramRecordPage')
const ProgramSessionsPage = named(() => import('@/pages/learner/ProgramSessionsPage'), 'ProgramSessionsPage')
const CertificatesPage = named(() => import('@/pages/learner/CertificatesPage'), 'CertificatesPage')
const AchievementsPage = named(() => import('@/pages/learner/AchievementsPage'), 'AchievementsPage')
const InclusionPage = named(() => import('@/pages/learner/InclusionPage'), 'InclusionPage')
const CompanyInclusionResultsPage = named(() => import('@/pages/business/InclusionResultsPage'), 'CompanyInclusionResultsPage')
const RequiredTrainingPage = named(() => import('@/pages/learner/RequiredTrainingPage'), 'RequiredTrainingPage')
const NotificationsPage = named(() => import('@/pages/learner/NotificationsPage'), 'NotificationsPage')
const AccountPage = named(() => import('@/pages/learner/AccountPage'), 'AccountPage')
const SupportPage = named(() => import('@/pages/learner/SupportPages'), 'SupportPage')
const TicketPage = named(() => import('@/pages/learner/SupportPages'), 'TicketPage')
const VerifyPage = named(() => import('@/pages/VerifyPage'), 'VerifyPage')
const PrivacyPage = named(() => import('@/pages/legal/LegalPages'), 'PrivacyPage')
const TermsPage = named(() => import('@/pages/legal/LegalPages'), 'TermsPage')
const WalletPage = named(() => import('@/pages/b2c/WalletPage'), 'WalletPage')
const TokenBuyPage = named(() => import('@/pages/b2c/TokenBuyPage'), 'TokenBuyPage')
const TokenResultPage = named(() => import('@/pages/b2c/TokenResultPage'), 'TokenResultPage')
const SubscriptionPage = named(() => import('@/pages/b2c/SubscriptionPage'), 'SubscriptionPage')
const PackagesPage = named(() => import('@/pages/b2c/PackagesPage'), 'PackagesPage')
const CheckoutReviewPage = named(() => import('@/pages/b2c/CheckoutReviewPage'), 'CheckoutReviewPage')
const ComplianceDashboard = named(() => import('@/pages/business/ComplianceDashboard'), 'ComplianceDashboard')
const MatrixPage = named(() => import('@/pages/business/MatrixPage'), 'MatrixPage')
const RequirementsPage = named(() => import('@/pages/business/RequirementsPage'), 'RequirementsPage')
const ReportsPage = named(() => import('@/pages/business/ReportsPage'), 'ReportsPage')
const PeoplePage = named(() => import('@/pages/business/PeoplePage'), 'PeoplePage')
const PersonPage = named(() => import('@/pages/business/PersonPage'), 'PersonPage')
const UnitsPage = named(() => import('@/pages/business/UnitsPage'), 'UnitsPage')
const HrSystemPage = named(() => import('@/pages/business/HrSystemPage'), 'HrSystemPage')
const InvitesPage = named(() => import('@/pages/business/InvitesPage'), 'InvitesPage')
const LibraryPage = named(() => import('@/pages/business/LibraryPage'), 'LibraryPage')
const AssignPage = named(() => import('@/pages/business/AssignPage'), 'AssignPage')
const BillingPage = named(() => import('@/pages/business/BillingPage'), 'BillingPage')
const CompanySettingsPage = named(() => import('@/pages/business/CompanySettingsPage'), 'CompanySettingsPage')
const CompanyStartPage = named(() => import('@/pages/business/CompanyStartPage'), 'CompanyStartPage')
const InvitePage = named(() => import('@/pages/InvitePage'), 'InvitePage')
const TeachPage = named(() => import('@/pages/studio/TeachPage'), 'TeachPage')
const InstructorInvitePage = named(() => import('@/pages/studio/InstructorInvitePage'), 'InstructorInvitePage')
const StudioDashboard = named(() => import('@/pages/studio/StudioDashboard'), 'StudioDashboard')
const StudioCoursesPage = named(() => import('@/pages/studio/StudioCoursesPage'), 'StudioCoursesPage')
const CourseBuilderPage = named(() => import('@/pages/studio/CourseBuilderPage'), 'CourseBuilderPage')
const StudentsPage = named(() => import('@/pages/studio/StudentsPage'), 'StudentsPage')
const GradingPage = named(() => import('@/pages/studio/GradingPage'), 'GradingPage')
const QuestionsPage = named(() => import('@/pages/studio/QuestionsPage'), 'QuestionsPage')
const RevenuePage = named(() => import('@/pages/studio/RevenuePage'), 'RevenuePage')
const PayoutsPage = named(() => import('@/pages/studio/PayoutsPage'), 'PayoutsPage')
const ConsoleShell = named(() => import('@/pages/console/ConsoleShell'), 'ConsoleShell')
const ConsoleDashboardPage = named(() => import('@/pages/console/DashboardPage'), 'ConsoleDashboardPage')
const ConsoleCoursesPage = named(() => import('@/pages/console/CoursesPage'), 'ConsoleCoursesPage')
const ConsoleInstructorsPage = named(() => import('@/pages/console/InstructorsPage'), 'ConsoleInstructorsPage')
const ConsoleStudentsPage = named(() => import('@/pages/console/StudentsPage'), 'ConsoleStudentsPage')
const ConsoleSalesPage = named(() => import('@/pages/console/SalesPage'), 'ConsoleSalesPage')
const ConsoleSubscriptionsPage = named(() => import('@/pages/console/SubscriptionsPage'), 'ConsoleSubscriptionsPage')
const ConsolePricingPage = named(() => import('@/pages/console/PricingPage'), 'ConsolePricingPage')
const ConsolePromotionsPage = named(() => import('@/pages/console/PromotionsPage'), 'ConsolePromotionsPage')
const ConsoleCommissionsPage = named(() => import('@/pages/console/CommissionsPage'), 'ConsoleCommissionsPage')
const ConsolePayoutsPage = named(() => import('@/pages/console/PayoutsPage'), 'ConsolePayoutsPage')
const ConsoleReportsPage = named(() => import('@/pages/console/ReportsPage'), 'ConsoleReportsPage')
const ConsoleApprovalsPage = named(() => import('@/pages/console/ApprovalsPage'), 'ConsoleApprovalsPage')
const ConsoleReviewsPage = named(() => import('@/pages/console/ReviewsPage'), 'ConsoleReviewsPage')
const ConsoleCommunicationsPage = named(() => import('@/pages/console/CommunicationsPage'), 'ConsoleCommunicationsPage')
const ConsoleCertificatesPage = named(() => import('@/pages/console/CertificatesPage'), 'ConsoleCertificatesPage')
const ConsoleCompaniesPage = named(() => import('@/pages/console/CompaniesPage'), 'ConsoleCompaniesPage')
const ConsoleSettingsPage = named(() => import('@/pages/console/SettingsPage'), 'ConsoleSettingsPage')
const ConsoleAuditPage = named(() => import('@/pages/console/AuditPage'), 'ConsoleAuditPage')
const ConsoleTokenPricingPage = named(() => import('@/pages/console/b2c/TokenPricingPage'), 'TokenPricingPage')
const ConsoleWalletsPage = named(() => import('@/pages/console/b2c/AdminWalletPage'), 'AdminWalletPage')
const ConsolePackagesPage = named(() => import('@/pages/console/b2c/AdminPackagesPage'), 'AdminPackagesPage')

const page = (el: ReactNode) => <Suspense fallback={<PageSpinner />}>{el}</Suspense>

const businessNav: NavSection[] = [
  { items: [{ to: '/business', label: 'Overview', Icon: LayoutDashboard, end: true }] },
  {
    title: 'Compliance',
    items: [
      { to: '/business/matrix', label: 'Training matrix', Icon: ClipboardCheck },
      { to: '/business/requirements', label: 'Requirements', Icon: ShieldCheck },
      { to: '/business/reports', label: 'Reports', Icon: FileBarChart },
    ],
  },
  {
    title: 'People',
    items: [
      { to: '/business/people', label: 'People', Icon: Users },
      { to: '/business/units', label: 'Locations & teams', Icon: Network },
      { to: '/business/invites', label: 'Invitations', Icon: UserPlus },
      { to: '/business/inclusion', label: 'Inclusion results', Icon: HeartHandshake },
    ],
  },
  {
    title: 'Learning',
    items: [
      { to: '/business/library', label: 'Course library', Icon: BookOpen },
      { to: '/business/assign', label: 'Assign training', Icon: GraduationCap },
    ],
  },
  ...corporateBusinessNav,
  {
    title: 'Company',
    items: [
      { to: '/business/billing', label: 'Billing', Icon: CreditCard },
      { to: '/business/hr-system', label: 'HR system', Icon: Plug },
      { to: '/business/settings', label: 'Settings', Icon: Building2 },
      { to: '/support', label: 'B2B support', Icon: LifeBuoy },
    ],
  },
]

const studioNav: NavSection[] = [
  { items: [{ to: '/studio', label: 'Dashboard', Icon: LayoutDashboard, end: true }, { to: '/studio/courses', label: 'My courses', Icon: BookOpen }] },
  { title: 'Learners', items: [{ to: '/studio/students', label: 'Students', Icon: Users }, { to: '/studio/grading', label: 'Assignments', Icon: ClipboardCheck }, { to: '/studio/questions', label: 'Q&A and reviews', Icon: MessageSquare }] },
  { title: 'Money', items: [{ to: '/studio/revenue', label: 'Sales & earnings', Icon: DollarSign }, { to: '/studio/payouts', label: 'Payouts', Icon: Wallet }] },
]

// SiteRoot applies the console's platform settings to every page: name, favicon, site
// banner, maintenance page and "guest browsing off" (components/layout/SiteRoot.tsx).
export const router = createBrowserRouter([{ element: <SiteRoot />, children: [
  {
    element: <PublicLayout />,
    children: [
      { path: '/', element: page(<HomePage />), handle: { title: 'Online courses and team training' } },
      { path: '/courses', element: page(<CoursesPage />), handle: { title: 'Browse courses' } },
      { path: '/courses/:slug', element: page(<CoursePage />), handle: { title: 'Course' } },
      // component showcase with sample data: local development only, never in the client build
      ...(import.meta.env.DEV ? [{ path: '/design', element: page(<DesignPage />) }] : []),
      { path: '/plans', element: page(<PlansPage />), handle: { title: 'Plans' } },
      { path: '/verify', element: page(<VerifyPage />), handle: { title: 'Verify a certificate' } },
      { path: '/verify/:code', element: page(<VerifyPage />), handle: { title: 'Verify a certificate' } },
      { path: '/privacy', element: page(<PrivacyPage />), handle: { title: 'Privacy policy' } },
      { path: '/terms', element: page(<TermsPage />), handle: { title: 'Terms of use' } },
      { path: '/cart', element: <RequireAuth>{page(<CartPage />)}</RequireAuth>, handle: { title: 'Your cart' } },
      { path: '/checkout/success', element: <RequireAuth>{page(<CheckoutSuccessPage />)}</RequireAuth>, handle: { title: 'Thank you' } },
      {
        element: (
          <RequireAuth>
            <LearnerLayout />
          </RequireAuth>
        ),
        children: [
          { path: '/learn', element: page(<MyLearningPage />), handle: { title: 'My learning' } },
          { path: '/learn/certificates', element: page(<CertificatesPage />), handle: { title: 'My certificates', art: 'guilloche' } },
          { path: '/learn/achievements', element: page(<AchievementsPage />), handle: { title: 'Achievements', art: 'honeycomb' } },
          { path: '/learn/inclusion', element: page(<InclusionPage />), handle: { title: 'Inclusion test', art: 'spectrum' } },
          { path: '/learn/required', element: page(<RequiredTrainingPage />), handle: { title: 'Required training', art: 'checklist' } },
          { path: '/learn/:slug/record', element: page(<ProgramRecordPage />), handle: { title: 'My record', art: 'curriculum' } },
          { path: '/learn/:slug/sessions', element: page(<ProgramSessionsPage />), handle: { title: 'Live sessions', art: 'timetable' } },
          { path: '/notifications', element: page(<NotificationsPage />), handle: { title: 'Notifications', art: 'signal' } },
          { path: '/wishlist', element: page(<WishlistPage />), handle: { title: 'Wishlist' } },
          { path: '/account/orders', element: page(<OrdersPage />), handle: { title: 'Orders', art: 'ribbons' } },
          { path: '/wallet', element: page(<WalletPage />), handle: { title: 'Token wallet', art: 'coins' } },
          { path: '/wallet/buy', element: page(<TokenBuyPage />), handle: { title: 'Buy tokens', art: 'coins' } },
          { path: '/wallet/result', element: page(<TokenResultPage />), handle: { title: 'Confirming payment', art: 'coins' } },
          { path: '/subscription', element: page(<SubscriptionPage />), handle: { title: 'Unlimited plan', art: 'ribbons' } },
          { path: '/packages', element: page(<PackagesPage />), handle: { title: 'Course bundles', art: 'ribbons' } },
          { path: '/checkout/review', element: page(<CheckoutReviewPage />), handle: { title: 'Review your order', art: 'ribbons' } },
          { path: '/account', element: page(<AccountPage />), handle: { title: 'Account', art: 'dials' } },
          { path: '/teach', element: page(<TeachPage />), handle: { title: 'Teach on LearnHub', art: 'blueprint' } },
          { path: '/teach/invite/:token', element: page(<InstructorInvitePage />), handle: { title: 'Instructor invitation', art: 'blueprint' } },
          { path: '/support', element: page(<SupportPage />), handle: { title: 'Help and support', art: 'bubbles' } },
          { path: '/support/:id', element: page(<TicketPage />), handle: { title: 'Support request', art: 'bubbles' } },
          { path: '/business/start', element: page(<CompanyStartPage />), handle: { title: 'Set up your company', art: 'seats' } },
          ...corporateLearnerRoutes,
        ],
      },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
  // the player is full-screen: its own header, no site footer
  { path: '/learn/:slug/*', element: <RequireAuth>{page(<PlayerPage />)}</RequireAuth>, handle: { title: 'Learning' } },
  { path: '/login', element: page(<LoginPage />), handle: { title: 'Log in' } },
  { path: '/signup', element: page(<SignupPage />), handle: { title: 'Sign up' } },
  { path: '/account/verify-email/:key', element: page(<VerifyEmailPage />), handle: { title: 'Confirm your email' } },
  { path: '/account/password/reset', element: page(<ForgotPasswordPage />), handle: { title: 'Reset your password' } },
  { path: '/account/password/reset/key/:key', element: page(<ResetPasswordPage />), handle: { title: 'Choose a new password' } },
  { path: '/invite/:token', element: page(<InvitePage />), handle: { title: 'Invitation' } },
  {
    path: '/business',
    element: (
      <RequireAuth>
        <RequireManager>
          <BusinessLayout sections={businessNav} />
        </RequireManager>
      </RequireAuth>
    ),
    children: [
      { index: true, element: page(<ComplianceDashboard />), handle: { title: 'Company overview' } },
      { path: 'matrix', element: page(<MatrixPage />), handle: { title: 'Training matrix' } },
      { path: 'requirements', element: page(<RequirementsPage />), handle: { title: 'Requirements', art: 'checklist' } },
      { path: 'reports', element: page(<ReportsPage />), handle: { title: 'Reports', art: 'chartgrid' } },
      { path: 'people', element: page(<PeoplePage />), handle: { title: 'People', art: 'orgchart' } },
      { path: 'inclusion', element: page(<CompanyInclusionResultsPage />), handle: { title: 'Inclusion results', art: 'spectrum' } },
      { path: 'people/:memberId', element: page(<PersonPage />), handle: { title: 'Person', art: 'orgchart' } },
      { path: 'units', element: page(<UnitsPage />), handle: { title: 'Locations and teams', art: 'floorplan' } },
      { path: 'hr-system', element: page(<HrSystemPage />), handle: { title: 'HR system', art: 'handover' } },
      { path: 'invites', element: page(<InvitesPage />), handle: { title: 'Invitations', art: 'orgchart' } },
      { path: 'library', element: page(<LibraryPage />), handle: { title: 'Course library', art: 'mosaic' } },
      { path: 'assign', element: page(<AssignPage />), handle: { title: 'Assign training', art: 'mosaic' } },
      { path: 'billing', element: page(<BillingPage />), handle: { title: 'Billing', art: 'ribbons' } },
      { path: 'settings', element: page(<CompanySettingsPage />), handle: { title: 'Company settings', art: 'dials' } },
      ...corporateBusinessRoutes,
      { path: '*', element: <NotFoundPage art={false} /> },
    ],
  },
  {
    path: '/studio',
    element: (
      <RequireAuth>
        <RequireRole allowed="instructor">
          <WorkspaceLayout area="Instructor" sections={studioNav} art="blueprint" />
        </RequireRole>
      </RequireAuth>
    ),
    children: [
      { index: true, element: page(<StudioDashboard />), handle: { title: 'Instructor dashboard' } },
      { path: 'courses', element: page(<StudioCoursesPage />), handle: { title: 'My courses · Studio' } },
      // the builder's tabs are paths, so the curriculum can show its own artwork
      { path: 'courses/:courseId', element: page(<CourseBuilderPage />), handle: { title: 'Course builder · Studio' } },
      { path: 'courses/:courseId/curriculum', element: page(<CourseBuilderPage />), handle: { title: 'Curriculum · Studio', art: 'storyboard' } },
      { path: 'courses/:courseId/:tab', element: page(<CourseBuilderPage />), handle: { title: 'Course builder · Studio' } },
      { path: 'students', element: page(<StudentsPage />), handle: { title: 'Students · Studio' } },
      { path: 'grading', element: page(<GradingPage />), handle: { title: 'Assignments · Studio' } },
      { path: 'questions', element: page(<QuestionsPage />), handle: { title: 'Q&A and reviews · Studio' } },
      { path: 'revenue', element: page(<RevenuePage />), handle: { title: 'Sales and earnings · Studio', art: 'coins' } },
      { path: 'payouts', element: page(<PayoutsPage />), handle: { title: 'Payouts · Studio', art: 'coins' } },
      { path: '*', element: <NotFoundPage art={false} /> },
    ],
  },
  {
    path: '/console',
    element: (
      <RequireAuth>
        <RequireRole allowed="staff">{page(<ConsoleShell />)}</RequireRole>
      </RequireAuth>
    ),
    children: [
      { index: true, element: page(<ConsoleDashboardPage />), handle: { title: 'Console' } },
      { path: 'courses', element: page(<ConsoleCoursesPage />), handle: { title: 'Courses · Console', art: 'mosaic' } },
      { path: 'instructors', element: page(<ConsoleInstructorsPage />), handle: { title: 'Instructors · Console', art: 'orgchart' } },
      { path: 'students', element: page(<ConsoleStudentsPage />), handle: { title: 'Students · Console', art: 'orgchart' } },
      { path: 'sales', element: page(<ConsoleSalesPage />), handle: { title: 'Sales · Console', art: 'coins' } },
      { path: 'subscriptions', element: page(<ConsoleSubscriptionsPage />), handle: { title: 'Subscriptions · Console', art: 'coins' } },
      { path: 'pricing', element: page(<ConsolePricingPage />), handle: { title: 'Pricing · Console', art: 'coins' } },
      { path: 'promotions', element: page(<ConsolePromotionsPage />), handle: { title: 'Promotions · Console', art: 'coins' } },
      { path: 'commissions', element: page(<ConsoleCommissionsPage />), handle: { title: 'Commissions · Console', art: 'coins' } },
      { path: 'payouts', element: page(<ConsolePayoutsPage />), handle: { title: 'Payouts · Console', art: 'coins' } },
      { path: 'reports', element: page(<ConsoleReportsPage />), handle: { title: 'Reports · Console', art: 'chartgrid' } },
      { path: 'approvals', element: page(<ConsoleApprovalsPage />), handle: { title: 'Approvals · Console', art: 'stamp' } },
      { path: 'reviews', element: page(<ConsoleReviewsPage />), handle: { title: 'Reviews · Console', art: 'bubbles' } },
      { path: 'communications', element: page(<ConsoleCommunicationsPage />), handle: { title: 'Communications · Console', art: 'bubbles' } },
      { path: 'certificates', element: page(<ConsoleCertificatesPage />), handle: { title: 'Certificates · Console', art: 'guilloche' } },
      { path: 'companies', element: page(<ConsoleCompaniesPage />), handle: { title: 'Companies · Console', art: 'contours' } },
      { path: 'settings', element: page(<ConsoleSettingsPage />), handle: { title: 'Settings · Console', art: 'dials' } },
      { path: 'audit', element: page(<ConsoleAuditPage />), handle: { title: 'Audit log · Console' } },
      ...corporateConsoleRoutes,
      ...programsConsoleRoutes,
      ...inclusionConsoleRoutes,
      { path: 'token-pricing', element: page(<ConsoleTokenPricingPage />), handle: { title: 'Token pricing · Console', art: 'coins' } },
      { path: 'wallets', element: page(<ConsoleWalletsPage />), handle: { title: 'Token wallets · Console', art: 'coins' } },
      { path: 'packages', element: page(<ConsolePackagesPage />), handle: { title: 'Packages · Console', art: 'ribbons' } },
      { path: '*', element: <NotFoundPage art={false} /> },
    ],
  },
  { path: '*', element: <Outlet /> },
]}])
