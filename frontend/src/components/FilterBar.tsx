import { useApp } from '../state/AppContext'

export default function FilterBar() {
  const { portfolios, filters, options, setFilters, resetFilters } = useApp()

  return (
    <div className="filter-bar">
      <div className="filter-field">
        <label>Portfolio</label>
        <select value={filters.portfolioId ?? ''}
          onChange={(e) => setFilters({ portfolioId: e.target.value ? Number(e.target.value) : null })}>
          <option value="">All portfolios</option>
          {portfolios.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>
      <div className="filter-field">
        <label>As of</label>
        <select value={filters.asOf ?? ''}
          onChange={(e) => setFilters({ asOf: e.target.value || null })}>
          <option value="">Latest</option>
          {(options?.as_of_dates ?? []).slice().reverse().map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
      </div>
      <div className="filter-field">
        <label>Asset class</label>
        <select value={filters.assetClass ?? ''}
          onChange={(e) => setFilters({ assetClass: e.target.value || null })}>
          <option value="">All</option>
          {(options?.asset_classes ?? []).map((c) => (
            <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>
          ))}
        </select>
      </div>
      <div className="filter-field">
        <label>Vintage</label>
        <select value={filters.vintage ?? ''}
          onChange={(e) => setFilters({ vintage: e.target.value ? Number(e.target.value) : null })}>
          <option value="">All</option>
          {(options?.vintages ?? []).map((v) => <option key={v} value={v}>{v}</option>)}
        </select>
      </div>
      <div className="filter-field">
        <label>FICO band</label>
        <select value={filters.ficoBand ?? ''}
          onChange={(e) => setFilters({ ficoBand: e.target.value || null })}>
          <option value="">All</option>
          {(options?.fico_bands ?? []).map((b) => <option key={b} value={b}>{b}</option>)}
        </select>
      </div>
      <div className="filter-field">
        <label>State</label>
        <select value={filters.state ?? ''}
          onChange={(e) => setFilters({ state: e.target.value || null })}>
          <option value="">All</option>
          {(options?.states ?? []).map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      <button className="btn" onClick={resetFilters}>Reset</button>
    </div>
  )
}
