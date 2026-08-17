import { cn } from '@/lib/utils'

export interface ChartSlice {
  label: string
  value: number
  color: string
}

function polarToCartesian(cx: number, cy: number, r: number, angle: number) {
  const rad = ((angle - 90) * Math.PI) / 180
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) }
}

function arcPath(cx: number, cy: number, r: number, start: number, end: number) {
  const s = polarToCartesian(cx, cy, r, end)
  const e = polarToCartesian(cx, cy, r, start)
  const large = end - start > 180 ? 1 : 0
  return `M ${s.x} ${s.y} A ${r} ${r} 0 ${large} 0 ${e.x} ${e.y}`
}

export function DonutChart({
  slices,
  totalLabel,
}: {
  slices: ChartSlice[]
  totalLabel?: string
}) {
  const total = slices.reduce((sum, slice) => sum + slice.value, 0)
  const cx = 60
  const cy = 60
  const r = 42
  const gap = 7

  let cursor = 0
  const visible = slices.filter((slice) => slice.value > 0)
  const arcs =
    total <= 0
      ? []
      : visible.map((slice) => {
          const sweep = (slice.value / total) * 360
          const start = cursor
          const end = cursor + sweep
          cursor = end
          return { ...slice, start, end, sweep, full: sweep >= 359.99 }
        })

  return (
    <div className="flex h-full min-h-0 w-full items-center gap-4 overflow-hidden">
      <svg
        viewBox="0 0 120 120"
        className="aspect-square h-[min(100%,8.25rem)] w-auto shrink-0 text-foreground"
        aria-hidden
      >
        <circle
          cx={cx}
          cy={cy}
          r={r}
          fill="none"
          className="stroke-muted/80"
          strokeWidth={11}
        />
        {arcs.map((arc) =>
          arc.full ? (
            <circle
              key={arc.label}
              cx={cx}
              cy={cy}
              r={r}
              fill="none"
              stroke={arc.color}
              strokeWidth={11}
            />
          ) : (
            <path
              key={arc.label}
              d={arcPath(
                cx,
                cy,
                r,
                arc.sweep > gap + 4 ? arc.start + gap / 2 : arc.start,
                arc.sweep > gap + 4 ? arc.end - gap / 2 : arc.end,
              )}
              fill="none"
              stroke={arc.color}
              strokeWidth={11}
              strokeLinecap="round"
            />
          ),
        )}
        <circle cx={cx} cy={cy} r={30} className="fill-card" />
        <text
          x={cx}
          y={cy + 1}
          textAnchor="middle"
          dominantBaseline="middle"
          fill="currentColor"
          fontSize="18"
          fontWeight="600"
        >
          {totalLabel ?? total}
        </text>
      </svg>
      <ul className="min-w-0 flex-1 space-y-2">
        {slices.map((slice) => (
          <li key={slice.label} className="flex items-center justify-between gap-3">
            <span className="flex min-w-0 items-center gap-2">
              <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: slice.color }} />
              <span className="truncate text-[12.5px] text-muted-foreground">{slice.label}</span>
            </span>
            <span className="text-[12.5px] tabular-nums font-medium">{slice.value}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function BarChart({
  bars,
}: {
  bars: { label: string; value: number }[]
}) {
  const max = Math.max(1, ...bars.map((bar) => bar.value))

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="flex min-h-0 flex-1 items-end gap-3">
        {bars.map((bar) => {
          const pct = bar.value > 0 ? Math.max(8, (bar.value / max) * 100) : 0
          return (
            <div key={bar.label} className="group flex h-full min-w-0 flex-1 flex-col items-center">
              <p
                className={cn(
                  'mb-1 h-4 text-[11px] tabular-nums',
                  bar.value > 0 ? 'font-medium text-foreground' : 'text-muted-foreground/45',
                )}
              >
                {bar.value}
              </p>
              <div className="relative flex min-h-0 w-full flex-1 items-end justify-center">
                <div className="absolute inset-x-[22%] bottom-0 top-0 rounded-t-md bg-[#dbeafe] dark:bg-[#1e3a5f]/50" />
                {bar.value > 0 ? (
                  <div
                    className="relative z-[1] w-[56%] max-w-10 rounded-t-md bg-[#3b82f6] transition-opacity duration-200 group-hover:opacity-80"
                    style={{ height: `${pct}%` }}
                  />
                ) : null}
              </div>
            </div>
          )
        })}
      </div>
      <div className="mt-2 flex gap-3 border-t border-border/80 pt-2">
        {bars.map((bar) => (
          <p
            key={bar.label}
            className="min-w-0 flex-1 text-center text-[11px] font-medium text-muted-foreground"
          >
            {bar.label}
          </p>
        ))}
      </div>
    </div>
  )
}
