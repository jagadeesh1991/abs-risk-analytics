import ChartCard from '../components/ChartCard'
import FilterBar from '../components/FilterBar'

export default function Prepayment() {
  return (
    <>
      <div className="page-header">
        <h1>Prepayment</h1>
        <span className="sub">Voluntary payoff speeds and the refi incentive</span>
      </div>
      <FilterBar />
      <div className="grid">
        <div className="col-12"><ChartCard chartId="cpr_trend" height={320} /></div>
        <div className="col-6"><ChartCard chartId="prepay_by_rate" /></div>
        <div className="col-6"><ChartCard chartId="prepay_by_fico" /></div>
      </div>
    </>
  )
}
