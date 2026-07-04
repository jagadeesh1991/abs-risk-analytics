/* Deal structuring: run the CPR/CDR collateral projection + waterfall engine
   against the demo pool or any uploaded portfolio, and view tranche results. */
import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import ChartRenderer from '../charts/renderers'
import { useApp } from '../state/AppContext'

interface RunResponse {
  pool: { name: string; balance: number; wac: number; wam: number }
  deal: { name: string; oc_trigger: number }
  oc_breached: boolean
  charts: Record<string, Record<string, unknown>>
}

const DEFAULTS = { cpr: 8, cdr: 2, severity: 40, lag: 6, shift: 0, trigger: 1.03 }

export default function Structuring() {
  const { portfolios } = useApp()
  const [form, setForm] = useState(DEFAULTS)
  const [portfolioId, setPortfolioId] = useState<string>('')
  const [result, setResult] = useState<RunResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = useCallback(async (f = form, pid = portfolioId) => {
    setBusy(true)
    setError(null)
    try {
      const r = await api<RunResponse>('/api/structuring/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cpr: f.cpr / 100, cdr: f.cdr / 100, severity: f.severity / 100,
          recovery_lag: f.lag, curve_shift_bps: f.shift, oc_trigger: f.trigger,
          portfolio_id: pid ? Number(pid) : null,
        }),
      })
      setResult(r)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }, [form, portfolioId])

  useEffect(() => { void run(DEFAULTS, '') }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const num = (key: keyof typeof DEFAULTS, label: string, step = 0.5, min = 0, max = 100) => (
    <div className="filter-field">
      <label>{label}</label>
      <input type="number" step={step} min={min} max={max} value={form[key]}
        onChange={(e) => setForm((f) => ({ ...f, [key]: Number(e.target.value) }))} />
    </div>
  )

  const chart = (id: string, title: string, sub?: string, height = 300) => {
    const payload = result?.charts[id]
    if (!payload) return null
    return (
      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">{title}</div>
            <div className="card-sub">{String(payload.subtitle ?? sub ?? '')}</div>
          </div>
        </div>
        <ChartRenderer payload={payload} height={height} exportName={id} />
      </div>
    )
  }

  return (
    <>
      <div className="page-header">
        <h1>Deal Structuring</h1>
        <span className="sub">Sequential-pay waterfall with OC trigger, priced off the SOFR curve</span>
      </div>

      <div className="filter-bar">
        <div className="filter-field">
          <label>Collateral</label>
          <select value={portfolioId} onChange={(e) => setPortfolioId(e.target.value)}>
            <option value="">Demo pool ($500M auto)</option>
            {portfolios.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        {num('cpr', 'CPR %', 0.5, 0, 60)}
        {num('cdr', 'CDR %', 0.5, 0, 40)}
        {num('severity', 'Severity %', 5, 0, 100)}
        {num('lag', 'Recovery lag (m)', 1, 0, 36)}
        {num('shift', 'Curve shift (bps)', 25, -300, 300)}
        {num('trigger', 'OC trigger (x)', 0.01, 1, 1.3)}
        <button className="btn primary" disabled={busy} onClick={() => void run()}>
          {busy ? 'Running…' : 'Run waterfall'}
        </button>
      </div>

      {error && <div className="issue error"><span className="tag">error</span><span>{error}</span></div>}

      {result && (
        <>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 14, flexWrap: 'wrap' }}>
            <span className="badge">
              {result.pool.name}: ${(result.pool.balance / 1e6).toFixed(0)}M ·
              WAC {(result.pool.wac * 100).toFixed(2)}% · WAM {result.pool.wam}m
            </span>
            <span className={`badge${result.oc_breached ? '' : ' ok'}`}>
              {result.oc_breached ? '⚠ OC trigger breached — turbo active' : '✓ OC test passing'}
            </span>
          </div>
          <div className="grid">
            <div className="col-12">{chart('tranche_table', 'Tranche Results',
              'PV and effective duration from a ±50bp parallel curve shift')}</div>
            <div className="col-6">{chart('paydown', 'Tranche Balance Paydown',
              'Outstanding balance by tranche', 320)}</div>
            <div className="col-6">{chart('oc', 'Overcollateralization Test', undefined, 320)}</div>
            <div className="col-12">{chart('collateral', 'Collateral Cash Flow Decomposition',
              'Monthly collections by source', 300)}</div>
          </div>
        </>
      )}
    </>
  )
}
