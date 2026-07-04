import ChartCard from '../components/ChartCard'
import FilterBar from '../components/FilterBar'

export default function Performance() {
  return (
    <>
      <div className="page-header">
        <h1>Credit Performance</h1>
        <span className="sub">Delinquency development, vintage seasoning and roll rates</span>
      </div>
      <FilterBar />
      <div className="grid">
        <div className="col-12"><ChartCard chartId="delinquency_trend" height={320} /></div>
        <div className="col-7" style={{ gridColumn: 'span 7' }}>
          <ChartCard chartId="vintage_curves" height={340} />
        </div>
        <div className="col-5" style={{ gridColumn: 'span 5' }}>
          <ChartCard chartId="roll_rate_matrix" height={340} />
        </div>
        <div className="col-12"><ChartCard chartId="loss_surface" height={340} /></div>
      </div>
    </>
  )
}
