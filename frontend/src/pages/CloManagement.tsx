/* CLO platform management: shelf-wide deal board + per-deal compliance,
   trustee reports and equity analytics — the manager's surveillance desk. */
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import ChartRenderer from '../charts/renderers'

interface DealRef { deal_id: string; name: string; status: string }

interface PlatformResponse {
  as_of: string
  deals: DealRef[]
  charts: Record<string, Record<string, unknown>>
}

interface DealResponse {
  as_of: string
  deal: {
    deal_id: string; name: string; status: string
    closing: string; reinvest_end: string; noncall_end: string; maturity: string
    failing: number
  }
  charts: Record<string, Record<string, unknown>>
}

interface ChartSlot { id: string; title: string; sub?: string; span: 4 | 6 | 8 | 12; height?: number }

const PLATFORM_LAYOUT: ChartSlot[] = [
  { id: 'deal_board', title: 'Deal Board', sub: 'Every deal on the shelf with its latest trustee metrics', span: 12 },
  { id: 'oc_cushion', title: 'Junior OC Cushion by Deal', span: 6, height: 300 },
  { id: 'warf_was', title: 'Risk vs Carry — WARF × WAS', span: 6, height: 300 },
  { id: 'industry', title: 'Platform Industry Exposure (Top 10)', span: 6, height: 300 },
  { id: 'rating', title: 'Platform Rating Distribution', span: 6, height: 300 },
  { id: 'overlap', title: 'Cross-Deal Obligor Overlap', span: 6 },
  { id: 'equity_ltm', title: 'Equity Cash-on-Cash by Deal (LTM)', span: 6, height: 300 },
]

const DEAL_LAYOUT: ChartSlot[] = [
  { id: 'stack', title: 'Capital Structure & Coverage', sub: 'Current balances after amortization; OC per class vs trigger', span: 12 },
  { id: 'compliance', title: 'Compliance Report', span: 12 },
  { id: 'warf_trend', title: 'WARF Trend', span: 4, height: 260 },
  { id: 'ccc_trend', title: 'Caa/CCC Bucket Trend', span: 4, height: 260 },
  { id: 'oc_trend', title: 'Junior OC Trend', span: 4, height: 260 },
  { id: 'obligors', title: 'Top 10 Obligors', span: 6 },
  { id: 'industry', title: 'Industry Concentration', span: 6, height: 340 },
  { id: 'payments', title: 'Payment Date History', span: 12 },
  { id: 'equity_cum', title: 'Cumulative Equity Distributions', span: 6, height: 300 },
  { id: 'equity_fwd', title: 'Projected Equity Distributions', span: 6, height: 300 },
  { id: 'paydown', title: 'Projected Tranche Paydown', span: 12, height: 320 },
]

export default function CloManagement() {
  const [platform, setPlatform] = useState<PlatformResponse | null>(null)
  const [dealId, setDealId] = useState<string>('')
  const [deal, setDeal] = useState<DealResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api<PlatformResponse>('/api/clo/platform')
      .then((r) => {
        setPlatform(r)
        if (r.deals.length) setDealId(r.deals[0].deal_id)
      })
      .catch((e) => setError((e as Error).message))
  }, [])

  useEffect(() => {
    if (!dealId) return
    setDeal(null)
    api<DealResponse>(`/api/clo/deals/${dealId}`)
      .then(setDeal)
      .catch((e) => setError((e as Error).message))
  }, [dealId])

  if (error) {
    return <div className="issue error"><span className="tag">error</span><span>{error}</span></div>
  }
  if (!platform) {
    return <div className="chart-status" style={{ height: 300 }}><div className="spinner" /></div>
  }

  const card = (charts: Record<string, Record<string, unknown>>, slot: ChartSlot, prefix: string) => {
    const payload = charts[slot.id]
    if (!payload) return null
    return (
      <div key={slot.id} className={`col-${slot.span}`}>
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">{slot.title}</div>
              <div className="card-sub">{String(payload.subtitle ?? slot.sub ?? '')}</div>
            </div>
          </div>
          <ChartRenderer payload={payload} height={slot.height ?? 300} exportName={`${prefix}_${slot.id}`} />
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="page-header">
        <h1>CLO Management</h1>
        <span className="sub">
          Shelf-wide surveillance: coverage tests, collateral quality, concentrations and
          equity performance across every deal · as of {platform.as_of}
        </span>
      </div>

      <ChartRenderer payload={platform.charts.kpis} />

      <div className="grid" style={{ marginTop: 14 }}>
        {PLATFORM_LAYOUT.map((slot) => card(platform.charts, slot, 'clo_platform'))}
      </div>

      <div className="page-header" style={{ marginTop: 28 }}>
        <h1>Deal Surveillance</h1>
        <span className="sub">Compliance, trustee reports and projections for a single deal</span>
      </div>

      <div className="filter-bar">
        <div className="filter-field">
          <label>Deal</label>
          <select value={dealId} onChange={(e) => setDealId(e.target.value)}>
            {platform.deals.map((d) => (
              <option key={d.deal_id} value={d.deal_id}>{d.name} — {d.status}</option>
            ))}
          </select>
        </div>
      </div>

      {!deal ? (
        <div className="chart-status" style={{ height: 200 }}><div className="spinner" /></div>
      ) : (
        <>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 14, flexWrap: 'wrap' }}>
            <span className="badge">{deal.deal.name}</span>
            <span className="badge">{deal.deal.status}</span>
            <span className="badge">Closed {deal.deal.closing}</span>
            <span className="badge">Reinvest end {deal.deal.reinvest_end}</span>
            <span className="badge">Non-call end {deal.deal.noncall_end}</span>
            <span className={`badge${deal.deal.failing ? ' fail' : ' ok'}`}>
              {deal.deal.failing ? `⚠ ${deal.deal.failing} test${deal.deal.failing > 1 ? 's' : ''} failing`
                : '✓ All tests passing'}
            </span>
          </div>
          <ChartRenderer payload={deal.charts.kpis} />
          <div className="grid" style={{ marginTop: 14 }}>
            {DEAL_LAYOUT.map((slot) => card(deal.charts, slot, `clo_${deal.deal.deal_id}`))}
          </div>
        </>
      )}
    </>
  )
}
