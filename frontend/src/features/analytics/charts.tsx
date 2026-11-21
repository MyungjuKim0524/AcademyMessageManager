import { useState } from 'react'
import { Tooltip, Typography } from 'antd'

/**
 * Attendance state colours (validated with the dataviz palette script, light mode, all checks
 * PASS: CVD worst adjacent ΔE 10.2). Same hue families as the app's attendance tags; every use
 * also shows the state name and count in text, so colour is never the only signal.
 */
export const ATTENDANCE_COLORS = {
  PRESENT: '#389e0d',
  LATE: '#d4b106',
  ABSENT: '#cf1322',
  EXCUSED: '#722ed1',
} as const

export type Segment = { key: string; label: string; value: number; color: string }

const percent = (value: number, total: number) => `${((value / total) * 100).toFixed(1)}%`

/** One 100% stacked bar of the recorded attendance, with a labelled legend underneath. */
export function StackedBar({ segments, ariaLabel }: { segments: Segment[]; ariaLabel: string }) {
  const total = segments.reduce((sum, s) => sum + s.value, 0)
  if (total === 0) return null
  return (
    <div className="stacked-bar-figure">
      <div className="stacked-bar" role="img" aria-label={ariaLabel}>
        {segments.filter((s) => s.value > 0).map((s) => (
          <Tooltip key={s.key} title={`${s.label} ${s.value}건 (${percent(s.value, total)})`}>
            <div className="stacked-bar-segment" style={{ flexGrow: s.value, background: s.color }} />
          </Tooltip>
        ))}
      </div>
      <ul className="chart-legend">
        {segments.map((s) => (
          <li key={s.key}>
            <span className="chart-swatch" style={{ background: s.color }} aria-hidden />
            <span>{s.label}</span>
            <Typography.Text strong>{`${s.value}건`}</Typography.Text>
            <Typography.Text type="secondary">{percent(s.value, total)}</Typography.Text>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** `compare` = the class average % of the same session (drawn dashed, for a fair comparison). */
export type TrendPoint = { key: number; label: string; date: string; percent: number; detail: string; compare?: number | null }

const W = 640
const H = 220
const PAD = { top: 16, right: 20, bottom: 36, left: 44 }

/**
 * Percent-of-max over time for one student. The y axis is fixed at 0–100% so different
 * assessments are never stretched to look like a bigger change; x is the assessment order.
 * Points only (no line) when there are fewer than two, so one score is not read as a trend.
 */
export function TrendChart({ points, ariaLabel }: { points: TrendPoint[]; ariaLabel: string }) {
  const [hover, setHover] = useState<TrendPoint | null>(null)
  if (points.length === 0) return null
  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom
  const x = (i: number) => PAD.left + (points.length === 1 ? innerW / 2 : (innerW * i) / (points.length - 1))
  const y = (p: number) => PAD.top + innerH * (1 - p / 100)
  const line = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i)},${y(p.percent)}`).join(' ')
  const compared = points.map((p, i) => ({ i, value: p.compare })).filter((c): c is { i: number; value: number } => c.value != null)
  const compareLine = compared.map((c, n) => `${n === 0 ? 'M' : 'L'}${x(c.i)},${y(c.value)}`).join(' ')
  return (
    <div className="trend-chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={ariaLabel} preserveAspectRatio="xMidYMid meet">
        {[0, 50, 100].map((tick) => (
          <g key={tick}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(tick)} y2={y(tick)} className="trend-grid" />
            <text x={PAD.left - 8} y={y(tick)} className="trend-axis" textAnchor="end" dominantBaseline="middle">{`${tick}%`}</text>
          </g>
        ))}
        {compared.length > 1 && <path d={compareLine} className="trend-line" style={{ strokeDasharray: '6 4', opacity: 0.45 }} />}
        {compared.length === 1 && <circle cx={x(compared[0].i)} cy={y(compared[0].value)} r={3} className="trend-point" style={{ opacity: 0.45 }} />}
        {points.length > 1 && <path d={line} className="trend-line" />}
        {points.map((p, i) => (
          <g key={p.key}>
            <text x={x(i)} y={H - 12} className="trend-axis" textAnchor="middle">{p.date.slice(5)}</text>
            {/* Larger invisible hit target than the 8px mark. */}
            <circle cx={x(i)} cy={y(p.percent)} r={14} className="trend-hit" tabIndex={0} aria-label={p.detail}
              onMouseEnter={() => setHover(p)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(p)} onBlur={() => setHover(null)} />
            <circle cx={x(i)} cy={y(p.percent)} r={4} className="trend-point" pointerEvents="none" />
          </g>
        ))}
      </svg>
      {compared.length > 0 && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>실선: 학생 · 점선: 같은 회차 반 평균</Typography.Text>
      )}
      {hover && <div className="trend-tooltip" role="status">{hover.detail}</div>}
    </div>
  )
}
