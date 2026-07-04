import ChartCard from '../components/ChartCard'
import FilterBar from '../components/FilterBar'

export default function Comparison() {
  return (
    <>
      <div className="page-header">
        <h1>Portfolio Comparison</h1>
        <span className="sub">Cross-issuer credit quality — best viewed with the portfolio filter on “All”</span>
      </div>
      <FilterBar />
      <div className="grid">
        <div className="col-12"><ChartCard chartId="issuer_matrix" /></div>
        <div className="col-12"><ChartCard chartId="issuer_trend" height={320} /></div>
        <div className="col-6"><ChartCard chartId="issuer_radar" height={360} /></div>
        <div className="col-6"><ChartCard chartId="issuer_rank" height={360} /></div>
      </div>
    </>
  )
}
