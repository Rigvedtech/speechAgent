import { useQuery } from '@tanstack/react-query'
import { getBotStatus } from '@/lib/api'
import { ApiError } from '@/lib/api-client'
import { queryKeys } from '@/lib/query-keys'
import type { StatusResponse } from '@/types/api'

export function useBotStatus(botId: string, enabled = true) {
  return useQuery<StatusResponse>({
    queryKey: queryKeys.status(botId),
    queryFn: () => getBotStatus(botId),
    enabled: Boolean(botId) && enabled,
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data) return 2500
      if (data.interview_ended || !data.is_active) return false
      return 2500
    },
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status === 404) return false
      return failureCount < 5
    },
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
  })
}
