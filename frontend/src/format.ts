import type { ValueFormat } from './types'

export function fmtCurrency(v: number, compact = true): string {
  if (!compact) return v.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
  const abs = Math.abs(v)
  if (abs >= 1e9) return `$${(v / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `$${(v / 1e6).toFixed(1)}M`
  if (abs >= 1e3) return `$${(v / 1e3).toFixed(0)}k`
  return `$${v.toFixed(0)}`
}

export function fmtPercent(v: number, digits = 2): string {
  return `${(v * 100).toFixed(digits)}%`
}

export function fmtNumber(v: number): string {
  return v.toLocaleString('en-US', { maximumFractionDigits: 0 })
}

export function fmtValue(v: number | null | undefined, format: ValueFormat): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  switch (format) {
    case 'currency': return fmtCurrency(v)
    case 'percent': return fmtPercent(v)
    case 'score': return v.toFixed(0)
    case 'number': return fmtNumber(v)
    default: return String(v)
  }
}

/** echarts axis/tooltip label formatter for a payload format */
export function axisFormatter(format: string): (v: number) => string {
  if (format === 'currency') return (v) => fmtCurrency(v)
  if (format === 'percent') return (v) => `${(v * 100).toFixed(1)}%`
  return (v) => fmtNumber(v)
}
