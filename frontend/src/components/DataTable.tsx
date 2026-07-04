import { fmtValue } from '../format'
import type { ValueFormat } from '../types'

interface Column { key: string; label: string; format: ValueFormat }
type Row = Record<string, string | number | null>

function toCsv(columns: Column[], rows: Row[]): string {
  const esc = (v: unknown) => {
    const s = v == null ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const head = columns.map((c) => esc(c.label)).join(',')
  const body = rows.map((r) => columns.map((c) => esc(r[c.key])).join(',')).join('\n')
  return `${head}\n${body}`
}

export default function DataTable({ columns, rows, exportName }: {
  columns: Column[]
  rows: Row[]
  exportName?: string
}) {
  const download = () => {
    const blob = new Blob([toCsv(columns, rows)], { type: 'text/csv' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${exportName ?? 'export'}.csv`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  return (
    <div>
      <div className="toolbar">
        <button className="btn" onClick={download}>Export CSV</button>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table className="data-table">
          <thead>
            <tr>{columns.map((c) => <th key={c.key}>{c.label}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                {columns.map((c) => (
                  <td key={c.key}>
                    {c.format === 'text' ? String(r[c.key] ?? '—') : fmtValue(r[c.key] as number, c.format)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
