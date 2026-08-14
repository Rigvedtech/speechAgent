import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppShell } from '@/layouts/AppShell'
import { AdminShell } from '@/layouts/AdminShell'
import { MarketingShell } from '@/layouts/MarketingShell'
import { PublicShell } from '@/layouts/PublicShell'
import { CodingShell } from '@/layouts/CodingShell'
import { RequireAuth, RequirePlatformAdmin, RequireTenant } from '@/components/auth/RequireAuth'
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
import { RequestAccessPage } from '@/pages/RequestAccessPage'
import { AccessRequestsPage } from '@/pages/AccessRequestsPage'
import { AdminOverviewPage } from '@/pages/AdminOverviewPage'
import { AdminOperatorsPage } from '@/pages/AdminOperatorsPage'
import { AdminOrganizationsPage } from '@/pages/AdminOrganizationsPage'
import { AdminOrganizationDetailPage } from '@/pages/AdminOrganizationDetailPage'
import { TeamSettingsPage } from '@/pages/TeamSettingsPage'
import { AtsSettingsPage } from '@/pages/AtsSettingsPage'
import { AtsBrowsePage } from '@/pages/AtsBrowsePage'
import { BulkUploadPage } from '@/pages/BulkUploadPage'
import { JobResumesPage } from '@/pages/JobResumesPage'
import { CodingPage } from '@/pages/CodingPage'
import { CodingDashboardPage } from '@/pages/CodingDashboardPage'
import { CandidateCodingPage } from '@/pages/CandidateCodingPage'

export const router = createBrowserRouter([
  {
    element: <MarketingShell />,
    children: [{ index: true, element: <LandingPage /> }],
  },
  { path: '/login', element: <LoginPage /> },
  { path: '/request-access', element: <RequestAccessPage /> },
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
    path: '/c',
    element: <CodingShell />,
    children: [
      { index: true, element: <Navigate to="/" replace /> },
      { path: ':token', element: <CandidateCodingPage /> },
    ],
  },
  {
    element: <RequireAuth />,
    children: [
      {
        path: 'admin',
        element: <RequirePlatformAdmin />,
        children: [
          {
            element: <AdminShell />,
            children: [
              { index: true, element: <AdminOverviewPage /> },
              { path: 'requests', element: <AccessRequestsPage /> },
              { path: 'organizations', element: <AdminOrganizationsPage /> },
              { path: 'organizations/:orgId', element: <AdminOrganizationDetailPage /> },
              { path: 'operators', element: <AdminOperatorsPage /> },
            ],
          },
        ],
      },
      {
        element: <RequireTenant />,
        children: [
          {
            element: <AppShell />,
            children: [
              { path: 'dashboard', element: <DashboardPage /> },
              { path: 'interviews/new', element: <NewInterviewPage /> },
              { path: 'interviews/scheduled', element: <ScheduledInterviewsPage /> },
              { path: 'interviews/by-id/:interviewId/coding', element: <CodingPage /> },
              { path: 'interviews/:botId/coding', element: <CodingPage /> },
              { path: 'interviews/:botId/report', element: <ReportPage /> },
              { path: 'interviews/:botId', element: <LiveSessionPage /> },
              { path: 'coding/demo/:demoToken', element: <CodingPage /> },
              { path: 'coding/demo', element: <CodingPage /> },
              { path: 'coding', element: <CodingDashboardPage /> },
              { path: 'reports', element: <ReportsHistoryPage /> },
              { path: 'ats/jobs', element: <AtsBrowsePage /> },
              { path: 'ats/jobs/:requestId', element: <AtsBrowsePage /> },
              { path: 'jobs/bulk-upload', element: <BulkUploadPage /> },
              { path: 'jobs/:jobId/resumes', element: <JobResumesPage /> },
              { path: 'settings/team', element: <TeamSettingsPage /> },
              { path: 'settings/access-requests', element: <Navigate to="/admin/requests" replace /> },
              { path: 'settings/ats', element: <AtsSettingsPage /> },
              { path: '*', element: <Navigate to="/dashboard" replace /> },
            ],
          },
        ],
      },
    ],
  },
])
