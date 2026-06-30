export const queryKeys = {
  health: ['health'] as const,
  sessions: ['sessions'] as const,
  reports: ['reports'] as const,
  status: (botId: string) => ['status', botId] as const,
  report: (botId: string) => ['report', botId] as const,
}
