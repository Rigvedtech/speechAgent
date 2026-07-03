import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppShell } from '@/layouts/AppShell'
import { PublicShell } from '@/layouts/PublicShell'
import { DashboardPage } from '@/pages/DashboardPage'
import { NewInterviewPage } from '@/pages/NewInterviewPage'
import { LiveSessionPage } from '@/pages/LiveSessionPage'
import { ReportPage } from '@/pages/ReportPage'
import { ReportsHistoryPage } from '@/pages/ReportsHistoryPage'
import { CandidateFeedbackPage } from '@/pages/CandidateFeedbackPage'

export const router = createBrowserRouter([
  {
    path: '/feedback',
    element: <PublicShell />,
    children: [
      { index: true, element: <Navigate to="/" replace /> },
      { path: ':botId', element: <CandidateFeedbackPage /> },
    ],
  },
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'interviews/new', element: <NewInterviewPage /> },
      { path: 'interviews/:botId', element: <LiveSessionPage /> },
      { path: 'interviews/:botId/report', element: <ReportPage /> },
      { path: 'reports', element: <ReportsHistoryPage /> },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
])
