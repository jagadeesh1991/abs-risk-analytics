import { useEffect, useState } from 'react'
import { api, filterQuery } from '../api/client'
import { fmtValue } from '../format'
import { useApp } from '../state/AppContext'
import type { ChartResponse, ValueFormat } from '../types'

export interface KpiItem {
  label: string
  value: number | null
  format: ValueFormat
  spark?: number[]
  pctile?: number
}

function Spark({ data }: { data: number[] }) {
  const w = 84, h = 26
  const min = Math.min(...data), max = Math.max(...data)
  const range = max - min || 1
  const pts = data
    .map((v, i) => `${((i / (data.length - 1)) * (w - 2) + 1).toFixed(1)},${(h - 2 - ((v - min) / range) * (h - 6)).toFixed(1)}`)
    .join(' ')
  return (
    <svg width={w} height={h} style={{ display: 'block' }}>
      <polyline points={pts} fill="none" stroke="var(--accent)" strokeWidth="1.5" opacity="0.85" />
    </svg>
  )
}

export function KpiGrid({ items, inline = false }: { items: KpiItem[]; inline?: boolean }) {
  return (
    <div className="kpi-grid" style={inline ? { marginBottom: 0 } : undefined}>
      {items.map((item) => (
        <div className="kpi" key={item.label}>
          <div className="label">{item.label}</div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 8 }}>
            <div className="value">{fmtValue(item.value, item.format)}</div>
            {item.spark && item.spark.length >= 3 && <Spark data={item.spark} />}
          </div>
          {item.pctile != null && (
            <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 4 }}
              title="Percentile of the current value within this pool's own history">
              P{Math.round(item.pctile * 100)} vs trailing history
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

export default function KpiCards() {
  const { filters } = useApp()
  const [items, setItems] = useState<KpiItem[] | null>(null)

  useEffect(() => {
    let cancelled = false
    api<ChartResponse>(`/api/charts/kpi_summary${filterQuery(filters)}`)
      .then((r) => {
        if (cancelled) return
        setItems(r.payload.empty ? [] : (r.payload.items as KpiItem[]))
      })
      .catch(() => { if (!cancelled) setItems([]) })
    return () => { cancelled = true }
  }, [filters])

  if (items === null) {
    return <div className="kpi-grid">{Array.from({ length: 8 }).map((_, i) => (
      <div className="kpi" key={i}><div className="label">&nbsp;</div><div className="value">…</div></div>
    ))}</div>
  }
  if (items.length === 0) return null

  return <KpiGrid items={items} />
}
