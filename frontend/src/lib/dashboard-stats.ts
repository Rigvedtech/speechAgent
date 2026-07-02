import type { ReportSummary } from '@/types/api'

/** Minimum overall average treated as a pass on the dashboard KPI. */
export const DASHBOARD_PASS_SCORE = 6

export interface DashboardKpis {
  completed7d: number
  avgScore7d: number | null
  passRate7d: number | null
  endedEarly7d: number
  totalCompleted: number
  completedFully: number
  endedEarly: number
}

export const COMPLETED_FULLY_REASON = 'completed_all_questions'

export function isCompletedFully(report: ReportSummary): boolean {
  return report.stopped_reason === COMPLETED_FULLY_REASON
}

export function formatFinishedBreakdownHint(kpis: Pick<DashboardKpis, 'completedFully' | 'endedEarly'>): string {
  return `${kpis.completedFully} completed fully · ${kpis.endedEarly} ended early`
}

export function reportsWithinDays(reports: ReportSummary[], days: number): ReportSummary[] {
  const cutoff = Date.now() - days * 24 * 60 * 60 * 1000
  return reports.filter((r) => {
    if (!r.completed_at) return false
    return new Date(r.completed_at).getTime() >= cutoff
  })
}

export function computeDashboardKpis(reports: ReportSummary[]): DashboardKpis {
  const recent = reportsWithinDays(reports, 7)
  const scores = recent
    .map((r) => r.overall_average)
    .filter((s): s is number => s != null)

  const avgScore7d =
    scores.length > 0 ? scores.reduce((sum, s) => sum + s, 0) / scores.length : null

  const passRate7d =
    scores.length > 0
      ? (scores.filter((s) => s >= DASHBOARD_PASS_SCORE).length / scores.length) * 100
      : null

  const endedEarly7d = recent.filter(
    (r) => r.stopped_reason && r.stopped_reason !== COMPLETED_FULLY_REASON,
  ).length

  const completedFully = reports.filter(isCompletedFully).length
  const endedEarly = reports.filter(
    (r) => r.stopped_reason && r.stopped_reason !== COMPLETED_FULLY_REASON,
  ).length

  return {
    completed7d: recent.length,
    avgScore7d,
    passRate7d,
    endedEarly7d,
    totalCompleted: reports.length,
    completedFully,
    endedEarly,
  }
}

export const STOPPED_LABELS: Record<string, string> = {
  completed_all_questions: 'Completed',
  low_recent_average: 'Ended early',
  abuse: 'Policy violation',
  manual: 'Manual',
}
