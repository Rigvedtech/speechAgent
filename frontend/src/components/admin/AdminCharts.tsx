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
  const cx = 48
  const cy = 48
  const r = 34

  let cursor = 0
  const arcs =
    total <= 0
      ? []
      : slices
          .filter((slice) => slice.value > 0)
          .map((slice) => {
            const sweep = (slice.value / total) * 360
            const start = cursor
            const end = cursor + sweep
            cursor = end
            return { ...slice, start, end, full: sweep >= 359.99 }
          })

  return (
    <div className="flex items-center gap-4">
      <svg viewBox="0 0 96 96" className="h-[7.25rem] w-[7.25rem] shrink-0 text-foreground" aria-hidden>
        {total <= 0 ? (
          <circle cx={cx} cy={cy} r={r} fill="none" className="stroke-muted" strokeWidth={12} />
        ) : (
          arcs.map((arc) =>
            arc.full ? (
              <circle
                key={arc.label}
                cx={cx}
                cy={cy}
                r={r}
                fill="none"
                stroke={arc.color}
                strokeWidth={12}
              />
            ) : (
              <path
                key={arc.label}
                d={arcPath(cx, cy, r, arc.start, arc.end)}
                fill="none"
                stroke={arc.color}
                strokeWidth={12}
              />
            ),
          )
        )}
        <circle cx={cx} cy={cy} r={24} className="fill-card" />
        <text x={cx} y={cy + 4} textAnchor="middle" fill="currentColor" fontSize="13" fontWeight="600">
          {totalLabel ?? total}
        </text>
      </svg>
      <ul className="min-w-0 flex-1 space-y-1 text-[12.5px] leading-tight">
        {slices.map((slice) => (
          <li key={slice.label} className="flex items-center justify-between gap-3">
            <span className="flex min-w-0 items-center gap-2">
              <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: slice.color }} />
              <span className="truncate text-muted-foreground">{slice.label}</span>
            </span>
            <span className="tabular-nums font-medium">{slice.value}</span>
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
    <div>
      <div className="flex items-end gap-3 border-b border-border/70">
        {bars.map((bar) => {
          const height = bar.value > 0 ? Math.max(8, (bar.value / max) * 112) : 0
          return (
            <div key={bar.label} className="flex min-w-0 flex-1 flex-col items-center gap-1">
              <p className="h-4 text-[11px] tabular-nums text-muted-foreground">
                {bar.value > 0 ? bar.value : ''}
              </p>
              <div className="flex h-[112px] w-full items-end justify-center">
                {bar.value > 0 ? (
                  <div className="w-7 rounded-t-sm bg-foreground" style={{ height }} />
                ) : null}
              </div>
            </div>
          )
        })}
      </div>
      <div className="mt-1.5 flex gap-3">
        {bars.map((bar) => (
          <p key={bar.label} className="min-w-0 flex-1 text-center text-[11px] font-medium text-muted-foreground">
            {bar.label}
          </p>
        ))}
      </div>
    </div>
  )
}
