/* Generic chart container: fetches /api/charts/{id} with the global filters
   plus any chart-specific params, then renders via the chart-type registry. */
import { useEffect, useMemo, useState } from 'react'
import { api, filterQuery } from '../api/client'
import ChartRenderer from '../charts/renderers'
import { useApp } from '../state/AppContext'
import type { ChartResponse } from '../types'

export default function ChartCard({ chartId, height = 300, initialParams, className }: {
  chartId: string
  height?: number
  initialParams?: Record<string, string>
  className?: string
}) {
  const { filters, specs } = useApp()
  const spec = specs[chartId]
  const [params, setParams] = useState<Record<string, string>>(() => {
    const defaults: Record<string, string> = {}
    if (spec) for (const [k, v] of Object.entries(spec.params)) defaults[k] = v.default
    return { ...defaults, ...initialParams }
  })
  const [payload, setPayload] = useState<ChartResponse['payload'] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const query = useMemo(() => filterQuery(filters, params), [filters, params])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    api<ChartResponse>(`/api/charts/${chartId}${query}`)
      .then((r) => { if (!cancelled) setPayload(r.payload) })
      .catch((e) => { if (!cancelled) setError(e.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [chartId, query])

  const subtitle = (payload?.subtitle as string) ?? spec?.description

  return (
    <div className={`card ${className ?? ''}`}>
      <div className="card-header">
        <div>
          <div className="card-title">{spec?.title ?? chartId}</div>
          {subtitle && <div className="card-sub">{subtitle}</div>}
        </div>
        {spec && Object.keys(spec.params).length > 0 && (
          <div className="card-controls">
            {Object.entries(spec.params).map(([name, ps]) => (
              <select key={name} value={params[name] ?? ps.default}
                onChange={(e) => setParams((p) => ({ ...p, [name]: e.target.value }))}>
                {ps.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            ))}
          </div>
        )}
      </div>
      {loading ? (
        <div className="chart-status" style={{ height }}><div className="spinner" /></div>
      ) : error ? (
        <div className="chart-status error" style={{ height }}>{error}</div>
      ) : payload?.empty ? (
        <div className="chart-status" style={{ height }}>{String(payload.message ?? 'No data')}</div>
      ) : payload ? (
        <ChartRenderer payload={payload} height={height} exportName={chartId} />
      ) : null}
    </div>
  )
}
