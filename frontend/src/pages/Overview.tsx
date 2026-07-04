import { useState } from 'react'
import { api } from '../api/client'
import ChartCard from '../components/ChartCard'
import FilterBar from '../components/FilterBar'
import KpiCards from '../components/KpiCards'
import { useApp } from '../state/AppContext'

export default function Overview() {
  const { hasData, loading, reload } = useApp()
  const [generating, setGenerating] = useState(false)

  const generateDemo = async () => {
    setGenerating(true)
    try {
      await api('/api/sample-data', { method: 'POST' })
      await reload()
    } finally {
      setGenerating(false)
    }
  }

  if (!loading && !hasData) {
    return (
      <div className="empty-hero">
        <h2>Welcome to Lord Abbett ABF</h2>
        <p>No loan tapes loaded yet. Generate realistic demo portfolios to explore every<br />
          dashboard, or upload your own CSV / Excel loan tape.</p>
        <button className="btn primary" onClick={generateDemo} disabled={generating}>
          {generating ? 'Generating…' : 'Generate demo data'}
        </button>
        <span style={{ margin: '0 12px', color: 'var(--muted)' }}>or</span>
        <a className="btn" href="/upload">Upload a loan tape</a>
      </div>
    )
  }

  return (
    <>
      <div className="page-header">
        <h1>Portfolio Overview</h1>
        <span className="sub">Headline pool metrics and composition</span>
      </div>
      <FilterBar />
      <KpiCards />
      <div className="grid">
        <div className="col-6"><ChartCard chartId="balance_by_asset_class" /></div>
        <div className="col-6"><ChartCard chartId="status_composition" /></div>
        <div className="col-12"><ChartCard chartId="balance_trend" /></div>
      </div>
    </>
  )
}
