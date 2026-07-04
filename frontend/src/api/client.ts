import type { FilterState } from '../types'

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch { /* not json */ }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export function filterQuery(filters: FilterState, params?: Record<string, string>): string {
  const q = new URLSearchParams()
  if (filters.portfolioId != null) q.set('portfolio_id', String(filters.portfolioId))
  if (filters.asOf) q.set('as_of', filters.asOf)
  if (filters.assetClass) q.set('asset_class', filters.assetClass)
  if (filters.vintage != null) q.set('vintage', String(filters.vintage))
  if (filters.ficoBand) q.set('fico_band', filters.ficoBand)
  if (filters.state) q.set('state', filters.state)
  for (const [k, v] of Object.entries(params ?? {})) if (v) q.set(k, v)
  const s = q.toString()
  return s ? `?${s}` : ''
}
