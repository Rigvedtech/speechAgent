import { useQuery } from '@tanstack/react-query'
import { listSessions } from '@/lib/api'
import { queryKeys } from '@/lib/query-keys'

export function useActiveSessions() {
  return useQuery({
    queryKey: queryKeys.sessions,
    queryFn: listSessions,
    refetchInterval: 5000,
    retry: 2,
  })
}
