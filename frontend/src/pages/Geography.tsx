import ChartCard from '../components/ChartCard'
import FilterBar from '../components/FilterBar'

export default function Geography() {
  return (
    <>
      <div className="page-header">
        <h1>Geography</h1>
        <span className="sub">State-level concentration and performance</span>
      </div>
      <FilterBar />
      <div className="grid">
        <div className="col-12"><ChartCard chartId="geo_states" height={460} /></div>
        <div className="col-12"><ChartCard chartId="strat_table" initialParams={{ dimension: 'state' }} /></div>
      </div>
    </>
  )
}
