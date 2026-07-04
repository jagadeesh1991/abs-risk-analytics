export interface ParamOption {
  value: string
  label: string
}

export interface ParamSpec {
  label: string
  default: string
  options: ParamOption[]
}

export interface ChartSpec {
  id: string
  title: string
  category: string
  chart_type: string
  description: string
  needs_history: boolean
  params: Record<string, ParamSpec>
}

export interface SnapshotInfo {
  as_of_date: string
  row_count: number
  total_balance: number
  source: string
}

export interface Portfolio {
  id: number
  name: string
  asset_class: string
  description: string
  snapshot_count: number
  snapshots: SnapshotInfo[]
  latest_as_of: string | null
  latest_balance: number
}

export interface FilterState {
  portfolioId: number | null
  asOf: string | null
  assetClass: string | null
  vintage: number | null
  ficoBand: string | null
  state: string | null
}

export interface FilterOptions {
  as_of_dates: string[]
  asset_classes: string[]
  vintages: number[]
  fico_bands: string[]
  states: string[]
}

export type ValueFormat = 'currency' | 'percent' | 'number' | 'score' | 'text'

export interface ChartResponse {
  chart_id: string
  title: string
  payload: Record<string, unknown> & { empty?: boolean; message?: string }
}

export interface FieldSpecInfo {
  name: string
  label: string
  dtype: string
  required: boolean
  description: string
  asset_classes: string[]
}

export interface ValidationIssue {
  field: string
  kind: 'error' | 'warning'
  message: string
  count: number
  sample_rows: number[]
}

export interface ValidationReport {
  ok: boolean
  errors: ValidationIssue[]
  warnings: ValidationIssue[]
  row_count: number
  total_balance: number
}
