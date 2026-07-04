import ChartCard from '../components/ChartCard'
import FilterBar from '../components/FilterBar'
import KpiCards from '../components/KpiCards'

export default function Surveillance() {
  return (
    <>
      <div className="page-header">
        <h1>Surveillance</h1>
        <span className="sub">Scorecard with sparklines, historical corridors and early-warning deviations</span>
      </div>
      <FilterBar />
      <KpiCards />
      <div className="grid">
        <div className="col-12"><ChartCard chartId="percentile_band" height={300} /></div>
        <div className="col-6"><ChartCard chartId="delinq_composition" height={300} /></div>
        <div className="col-6"><ChartCard chartId="duration_mix" height={300} /></div>
        <div className="col-6"><ChartCard chartId="deviation_heatmap" height={320} /></div>
        <div className="col-6"><ChartCard chartId="dlq_fico_mob" height={320} /></div>
      </div>
    </>
  )
}
