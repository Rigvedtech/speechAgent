import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppShell } from '@/layouts/AppShell'
import { MarketingShell } from '@/layouts/MarketingShell'
import { PublicShell } from '@/layouts/PublicShell'
import { CodingShell } from '@/layouts/CodingShell'
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
  { path: '/register', element: <RegisterOrgPage /> },
  {
    path: '/feedback',
    element: <PublicShell />,
    children: [
      { index: true, element: <Navigate to="/" replace /> },
      { path: ':botId', element: <CandidateFeedbackPage /> },
    ],
  },
  // Candidate coding link — no login, no recruiter navbar
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
        element: <AppShell />,
        children: [
          { path: 'dashboard', element: <DashboardPage /> },
          { path: 'interviews/new', element: <NewInterviewPage /> },
          // Must be before interviews/:botId so "scheduled" is not treated as a bot id
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
          { path: 'settings/ats', element: <AtsSettingsPage /> },
          { path: '*', element: <Navigate to="/dashboard" replace /> },
        ],
      },
    ],
  },
])
