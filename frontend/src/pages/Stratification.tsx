import ChartCard from '../components/ChartCard'
import FilterBar from '../components/FilterBar'

export default function Stratification() {
  return (
    <>
      <div className="page-header">
        <h1>Stratification</h1>
        <span className="sub">Pool cuts with weighted averages — switch the dimension on each table</span>
      </div>
      <FilterBar />
      <div className="grid">
        <div className="col-12"><ChartCard chartId="strat_table" /></div>
        <div className="col-12"><ChartCard chartId="strat_table" initialParams={{ dimension: 'vintage' }} /></div>
      </div>
    </>
  )
}
