import ChartCard from '../components/ChartCard'
import FilterBar from '../components/FilterBar'

export default function Vintage() {
  return (
    <>
      <div className="page-header">
        <h1>Vintage & Cohort</h1>
        <span className="sub">How each origination cohort seasons and where the mix is shifting</span>
      </div>
      <FilterBar />
      <div className="grid">
        <div className="col-12"><ChartCard chartId="ghost_vintage" height={340} /></div>
        <div className="col-12"><ChartCard chartId="cohort_lifecycle" height={340} /></div>
        <div className="col-6"><ChartCard chartId="grouped_loss_by_fico" height={320} /></div>
        <div className="col-6"><ChartCard chartId="distribution_pyramid" height={320} /></div>
      </div>
    </>
  )
}
