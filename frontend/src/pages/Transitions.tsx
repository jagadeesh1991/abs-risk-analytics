import ChartCard from '../components/ChartCard'
import FilterBar from '../components/FilterBar'

export default function Transitions() {
  return (
    <>
      <div className="page-header">
        <h1>Transition Flows</h1>
        <span className="sub">How balance moves between delinquency states month over month</span>
      </div>
      <FilterBar />
      <div className="grid">
        <div className="col-12"><ChartCard chartId="sankey_flow" height={420} /></div>
        <div className="col-6"><ChartCard chartId="transition_trend" height={320} /></div>
        <div className="col-6"><ChartCard chartId="attrition_funnel" height={320} /></div>
      </div>
    </>
  )
}
