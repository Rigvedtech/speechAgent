import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppShell } from '@/layouts/AppShell'
import { MarketingShell } from '@/layouts/MarketingShell'
import { PublicShell } from '@/layouts/PublicShell'
import { RequireAuth } from '@/components/auth/RequireAuth'
import { LandingPage } from '@/pages/LandingPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { NewInterviewPage } from '@/pages/NewInterviewPage'
import { ScheduledInterviewsPage } from '@/pages/ScheduledInterviewsPage'
import { LiveSessionPage } from '@/pages/LiveSessionPage'
import { ReportPage } from '@/pages/ReportPage'
import { ReportsHistoryPage } from '@/pages/ReportsHistoryPage'
import { CandidateFeedbackPage } from '@/pages/CandidateFeedbackPage'
import { LoginPage } from '@/pages/LoginPage'
import { RegisterOrgPage } from '@/pages/RegisterOrgPage'
import { TeamSettingsPage } from '@/pages/TeamSettingsPage'
import { AtsSettingsPage } from '@/pages/AtsSettingsPage'

export const router = createBrowserRouter([
  {
    element: <MarketingShell />,
    children: [{ index: true, element: <LandingPage /> }],
  },
  { path: '/login', element: <LoginPage /> },
  { path: '/register', element: <RegisterOrgPage /> },
  {
    path: '/feedback',
    element: <PublicShell />,
    children: [
      { index: true, element: <Navigate to="/" replace /> },
      { path: ':botId', element: <CandidateFeedbackPage /> },
    ],
  },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: 'dashboard', element: <DashboardPage /> },
          { path: 'interviews/new', element: <NewInterviewPage /> },
          // Must be before interviews/:botId so "scheduled" is not treated as a bot id
          { path: 'interviews/scheduled', element: <ScheduledInterviewsPage /> },
          { path: 'interviews/:botId', element: <LiveSessionPage /> },
          { path: 'interviews/:botId/report', element: <ReportPage /> },
          { path: 'reports', element: <ReportsHistoryPage /> },
          { path: 'settings/team', element: <TeamSettingsPage /> },
          { path: 'settings/ats', element: <AtsSettingsPage /> },
          { path: '*', element: <Navigate to="/dashboard" replace /> },
        ],
      },
    ],
  },
])
