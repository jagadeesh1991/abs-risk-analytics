/* Global app state: portfolios, chart specs, filters, filter options. */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from '../api/client'
import type { ChartSpec, FilterOptions, FilterState, Portfolio } from '../types'

const EMPTY_FILTERS: FilterState = {
  portfolioId: null, asOf: null, assetClass: null, vintage: null, ficoBand: null, state: null,
}

interface AppState {
  portfolios: Portfolio[]
  specs: Record<string, ChartSpec>
  filters: FilterState
  options: FilterOptions | null
  loading: boolean
  hasData: boolean
  setFilters: (f: Partial<FilterState>) => void
  resetFilters: () => void
  reload: () => Promise<void>
}

const Ctx = createContext<AppState | null>(null)

export function AppProvider({ children }: { children: ReactNode }) {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([])
  const [specs, setSpecs] = useState<Record<string, ChartSpec>>({})
  const [filters, setFiltersState] = useState<FilterState>(EMPTY_FILTERS)
  const [options, setOptions] = useState<FilterOptions | null>(null)
  const [loading, setLoading] = useState(true)

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const [p, s] = await Promise.all([
        api<Portfolio[]>('/api/portfolios'),
        api<ChartSpec[]>('/api/charts'),
      ])
      setPortfolios(p)
      setSpecs(Object.fromEntries(s.map((c) => [c.id, c])))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void reload() }, [reload])

  // refetch filter options whenever the portfolio scope changes
  useEffect(() => {
    const q = filters.portfolioId != null ? `?portfolio_id=${filters.portfolioId}` : ''
    api<FilterOptions>(`/api/filters/options${q}`).then(setOptions).catch(() => setOptions(null))
  }, [filters.portfolioId, portfolios])

  const setFilters = useCallback((patch: Partial<FilterState>) => {
    setFiltersState((prev) => ({ ...prev, ...patch }))
  }, [])

  const resetFilters = useCallback(() => setFiltersState(EMPTY_FILTERS), [])

  const value = useMemo<AppState>(() => ({
    portfolios, specs, filters, options, loading,
    hasData: portfolios.some((p) => p.snapshot_count > 0),
    setFilters, resetFilters, reload,
  }), [portfolios, specs, filters, options, loading, setFilters, resetFilters, reload])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useApp(): AppState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useApp must be used inside AppProvider')
  return v
}
