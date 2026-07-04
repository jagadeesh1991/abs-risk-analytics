/* Per-asset-class deal structuring screens (ABS / CLO / RMBS): run the
   collateral projection + waterfall engine and view institutional analytics. */
import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import ChartRenderer from '../charts/renderers'
import { useApp } from '../state/AppContext'

export type DealType = 'abs' | 'clo' | 'rmbs'

interface TemplateInfo {
  label: string
  description: string
  defaults: {
    cpr: number; cdr: number; severity: number
    recovery_lag: number; curve_shift_bps: number; oc_trigger: number
  }
  pool: { name: string; balance: number; wac: number; wam: number; floating: boolean }
}

interface RunResponse {
  pool: { name: string; balance: number; wac: number; wam: number; floating: boolean }
  deal: { name: string; oc_trigger: number }
  oc_breached: boolean
  charts: Record<string, Record<string, unknown>>
}

interface FormState {
  cpr: number; cdr: number; severity: number; lag: number; shift: number; trigger: number
}

const TITLES: Record<DealType, string> = {
  abs: 'Auto ABS Structuring',
  clo: 'CLO Structuring',
  rmbs: 'RMBS Structuring',
}

function toForm(d: TemplateInfo['defaults']): FormState {
  return {
    cpr: +(d.cpr * 100).toFixed(2), cdr: +(d.cdr * 100).toFixed(2),
    severity: +(d.severity * 100).toFixed(0), lag: d.recovery_lag,
    shift: d.curve_shift_bps, trigger: d.oc_trigger,
  }
}

export default function Structuring({ dealType }: { dealType: DealType }) {
  const { portfolios } = useApp()
  const [template, setTemplate] = useState<TemplateInfo | null>(null)
  const [form, setForm] = useState<FormState | null>(null)
  const [portfolioId, setPortfolioId] = useState<string>('')
  const [result, setResult] = useState<RunResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = useCallback(async (f: FormState, pid: string) => {
    setBusy(true)
    setError(null)
    try {
      const r = await api<RunResponse>('/api/structuring/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          deal_type: dealType,
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
  }, [dealType])

  useEffect(() => {
    let cancelled = false
    setResult(null)
    setPortfolioId('')
    api<Record<DealType, TemplateInfo>>('/api/structuring/templates')
      .then((all) => {
        if (cancelled) return
        const tpl = all[dealType]
        setTemplate(tpl)
        const f = toForm(tpl.defaults)
        setForm(f)
        void run(f, '')
      })
      .catch((e) => { if (!cancelled) setError((e as Error).message) })
    return () => { cancelled = true }
  }, [dealType, run])

  if (!form || !template) {
    return <div className="chart-status" style={{ height: 300 }}>
      {error ?? <div className="spinner" />}
    </div>
  }

  const num = (key: keyof FormState, label: string, step = 0.5, min = 0, max = 100) => (
    <div className="filter-field">
      <label>{label}</label>
      <input type="number" step={step} min={min} max={max} value={form[key]}
        onChange={(e) => setForm((f) => f && ({ ...f, [key]: Number(e.target.value) }))} />
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
        <ChartRenderer payload={payload} height={height} exportName={`${dealType}_${id}`} />
      </div>
    )
  }

  return (
    <>
      <div className="page-header">
        <h1>{TITLES[dealType]}</h1>
        <span className="sub">{template.description}</span>
      </div>

      <div className="filter-bar">
        <div className="filter-field">
          <label>Collateral</label>
          <select value={portfolioId} onChange={(e) => setPortfolioId(e.target.value)}>
            <option value="">{template.pool.name} (${(template.pool.balance / 1e6).toFixed(0)}M)</option>
            {portfolios.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        {num('cpr', 'CPR %', 0.5, 0, 60)}
        {num('cdr', 'CDR %', 0.25, 0, 40)}
        {num('severity', 'Severity %', 5, 0, 100)}
        {num('lag', 'Recovery lag (m)', 1, 0, 36)}
        {num('shift', 'Curve shift (bps)', 25, -300, 300)}
        {num('trigger', 'OC trigger (x)', 0.01, 1, 1.3)}
        <button className="btn primary" disabled={busy} onClick={() => void run(form, portfolioId)}>
          {busy ? 'Running…' : 'Run waterfall'}
        </button>
      </div>

      {error && <div className="issue error"><span className="tag">error</span><span>{error}</span></div>}

      {result && (
        <>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 14, flexWrap: 'wrap' }}>
            <span className="badge">{result.deal.name}</span>
            <span className="badge">
              {result.pool.name}: ${(result.pool.balance / 1e6).toFixed(0)}M ·
              {result.pool.floating ? ' floating' : ` WAC ${(result.pool.wac * 100).toFixed(2)}%`} ·
              WAM {result.pool.wam}m
            </span>
            <span className={`badge${result.oc_breached ? '' : ' ok'}`}>
              {result.oc_breached ? '⚠ OC trigger breached — turbo active' : '✓ OC test passing'}
            </span>
          </div>
          <div className="grid">
            <div className="col-12">{chart('tranche_table', 'Tranche Results',
              'PV & duration from ±50bp reprice; yield is the IRR at par; MOIC on equity')}</div>
            <div className="col-4" style={{ gridColumn: 'span 4' }}>{chart('capital_stack', 'Capital Structure',
              'Tranche sizing over the collateral', 340)}</div>
            <div className="col-8" style={{ gridColumn: 'span 8' }}>{chart('paydown', 'Tranche Balance Paydown',
              'Outstanding balance by tranche', 340)}</div>
            <div className="col-6">{chart('oc', 'Overcollateralization Test', undefined, 300)}</div>
            <div className="col-6">{chart('credit_enhancement', 'Credit Enhancement', undefined, 300)}</div>
            <div className="col-6">{chart('collateral', 'Collateral Cash Flows',
              'Monthly collections by source', 300)}</div>
            <div className="col-6">{chart('debt_service', 'Liability Cash Flows',
              'Where the money goes: fees, coupons, principal, equity', 300)}</div>
            <div className="col-12">{chart('equity_grid', 'Equity PV Sensitivity', undefined, 320)}</div>
          </div>
        </>
      )}
    </>
  )
}
