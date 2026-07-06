import { createBrowserRouter, Navigate } from 'react-router-dom'
import { MarketingShell } from '@/layouts/MarketingShell'
import { LandingPage } from '@/pages/LandingPage'

export const router = createBrowserRouter([
  {
    element: <MarketingShell />,
    children: [
      { index: true, element: <LandingPage /> },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
])
