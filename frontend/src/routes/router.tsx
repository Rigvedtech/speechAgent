import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppShell } from '@/layouts/AppShell'
import { DashboardPage } from '@/pages/DashboardPage'
import { NewInterviewPage } from '@/pages/NewInterviewPage'
import { LiveSessionPage } from '@/pages/LiveSessionPage'
import { ReportPage } from '@/pages/ReportPage'
import { ReportsHistoryPage } from '@/pages/ReportsHistoryPage'

export const router = createBrowserRouter([
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
