import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppShell } from '@/layouts/AppShell'
import { MarketingShell } from '@/layouts/MarketingShell'
import { PublicShell } from '@/layouts/PublicShell'
import { LandingPage } from '@/pages/LandingPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { NewInterviewPage } from '@/pages/NewInterviewPage'
import { LiveSessionPage } from '@/pages/LiveSessionPage'
import { ReportPage } from '@/pages/ReportPage'
import { ReportsHistoryPage } from '@/pages/ReportsHistoryPage'
import { CandidateFeedbackPage } from '@/pages/CandidateFeedbackPage'

export const router = createBrowserRouter([
  {
    element: <MarketingShell />,
    children: [{ index: true, element: <LandingPage /> }],
  },
  {
    path: '/feedback',
    element: <PublicShell />,
    children: [
      { index: true, element: <Navigate to="/" replace /> },
      { path: ':botId', element: <CandidateFeedbackPage /> },
    ],
  },
  {
    element: <AppShell />,
    children: [
      { path: 'dashboard', element: <DashboardPage /> },
      { path: 'interviews/new', element: <NewInterviewPage /> },
      { path: 'interviews/:botId', element: <LiveSessionPage /> },
      { path: 'interviews/:botId/report', element: <ReportPage /> },
      { path: 'reports', element: <ReportsHistoryPage /> },
      { path: '*', element: <Navigate to="/dashboard" replace /> },
    ],
  },
])
