import ChartCard from '../components/ChartCard'
import FilterBar from '../components/FilterBar'

export default function Distributions() {
  return (
    <>
      <div className="page-header">
        <h1>Distributions & Composition</h1>
        <span className="sub">How the pool is built: credit, collateral and balance mix</span>
      </div>
      <FilterBar />
      <div className="grid">
        <div className="col-6"><ChartCard chartId="hist_fico" /></div>
        <div className="col-6"><ChartCard chartId="hist_ltv" /></div>
        <div className="col-6"><ChartCard chartId="hist_balance" /></div>
        <div className="col-6"><ChartCard chartId="rate_by_fico_box" /></div>
        <div className="col-6"><ChartCard chartId="composition_treemap" height={340} /></div>
        <div className="col-6"><ChartCard chartId="balance_waterfall" height={340} /></div>
      </div>
    </>
  )
}
