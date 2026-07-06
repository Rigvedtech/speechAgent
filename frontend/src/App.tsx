import { useEffect, useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider, type createBrowserRouter } from 'react-router-dom'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000,
      refetchOnWindowFocus: true,
    },
  },
})

type AppRouter = ReturnType<typeof createBrowserRouter>

const LANDING_ONLY = import.meta.env.VITE_LANDING_ONLY === 'true'

export default function App() {
  const [router, setRouter] = useState<AppRouter | null>(null)

  useEffect(() => {
    let cancelled = false

    async function loadRouter() {
      const module = LANDING_ONLY
        ? await import('@/routes/router.landing')
        : await import('@/routes/router.app')

      if (!cancelled) {
        setRouter(module.router)
      }
    }

    void loadRouter()
    return () => {
      cancelled = true
    }
  }, [])

  if (!router) {
    return null
  }

  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}
