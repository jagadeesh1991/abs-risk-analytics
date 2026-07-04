/* 4-step upload wizard: file -> column mapping -> validation -> import. */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useApp } from '../state/AppContext'
import type { FieldSpecInfo, ValidationIssue, ValidationReport } from '../types'

interface UploadInfo {
  upload_id: string
  filename: string
  sheets: string[]
  columns: string[]
  rows: string[][]
  suggested_mapping: Record<string, string>
}

interface ImportResult {
  ok: boolean
  portfolio_id: number
  portfolio_name: string
  snapshots: { as_of_date: string; rows: number }[]
}

const STEPS = ['1 · File', '2 · Map columns', '3 · Validate', '4 · Import']

export default function Upload() {
  const { portfolios, reload } = useApp()
  const [step, setStep] = useState(0)
  const [schema, setSchema] = useState<FieldSpecInfo[]>([])
  const [info, setInfo] = useState<UploadInfo | null>(null)
  const [sheet, setSheet] = useState<string>('')
  const [headerRow, setHeaderRow] = useState(0)
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [targetId, setTargetId] = useState<'new' | number>('new')
  const [newName, setNewName] = useState('')
  const [assetClass, setAssetClass] = useState('auto')
  const [asOfDate, setAsOfDate] = useState('')
  const [report, setReport] = useState<ValidationReport | null>(null)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [drag, setDrag] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api<FieldSpecInfo[]>('/api/uploads/schema').then(setSchema).catch(() => {})
  }, [])

  const body = useMemo(() => ({
    mapping,
    sheet: sheet || null,
    header_row: headerRow,
    as_of_date: asOfDate || null,
    asset_class: assetClass,
    portfolio_id: targetId === 'new' ? null : targetId,
    new_portfolio_name: targetId === 'new' ? newName : null,
    new_portfolio_asset_class: targetId === 'new' ? assetClass : null,
  }), [mapping, sheet, headerRow, asOfDate, assetClass, targetId, newName])

  const doUpload = async (file: File) => {
    setBusy(true); setError(null)
    try {
      const form = new FormData()
      form.append('file', file)
      const r = await api<UploadInfo>('/api/uploads', { method: 'POST', body: form })
      setInfo(r)
      setMapping(r.suggested_mapping)
      setSheet(r.sheets[0] ?? '')
      setHeaderRow(0)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const rePreview = async (nextSheet: string, nextHeader: number) => {
    if (!info) return
    setBusy(true); setError(null)
    try {
      const r = await api<Omit<UploadInfo, 'upload_id' | 'filename' | 'sheets'> & { sheets: string[] }>(
        `/api/uploads/${info.upload_id}/preview`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sheet: nextSheet || null, header_row: nextHeader }) })
      setInfo({ ...info, columns: r.columns, rows: r.rows })
      setMapping(r.suggested_mapping)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const applySavedMapping = async (pid: number) => {
    try {
      const r = await api<{ mapping: Record<string, string> | null }>(`/api/uploads/mappings/${pid}`)
      if (r.mapping && info) {
        const valid = Object.fromEntries(
          Object.entries(r.mapping).filter(([col]) => info.columns.includes(col)))
        if (Object.keys(valid).length > 0) setMapping((m) => ({ ...m, ...valid }))
      }
    } catch { /* no saved mapping */ }
  }

  const doValidate = async () => {
    if (!info) return
    setBusy(true); setError(null)
    try {
      const r = await api<ValidationReport>(`/api/uploads/${info.upload_id}/validate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      })
      setReport(r)
      setStep(2)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const doImport = async () => {
    if (!info) return
    setBusy(true); setError(null)
    try {
      const r = await api<ImportResult>(`/api/uploads/${info.upload_id}/import`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      })
      setResult(r)
      setStep(3)
      await reload()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const mappedFields = new Set(Object.values(mapping))
  const requiredMissing = schema.filter((f) => f.required && !mappedFields.has(f.name))
  const asOfNeeded = !mappedFields.has('as_of_date') && !asOfDate
  const targetInvalid = targetId === 'new' && !newName.trim()

  const issueList = (issues: ValidationIssue[]) => issues.map((iss, i) => (
    <div key={i} className={`issue ${iss.kind}`}>
      <span className="tag">{iss.kind}</span>
      <span>
        <b>{iss.field}</b> — {iss.message}
        {iss.sample_rows.length > 0 && <span style={{ color: 'var(--muted)' }}> (rows {iss.sample_rows.join(', ')}…)</span>}
      </span>
    </div>
  ))

  return (
    <>
      <div className="page-header">
        <h1>Upload Loan Tape</h1>
        <span className="sub">CSV or Excel → canonical schema → dashboards</span>
      </div>
      <div className="wizard-steps">
        {STEPS.map((s, i) => (
          <div key={s} className={`wizard-step${i === step ? ' active' : i < step ? ' done' : ''}`}>{s}</div>
        ))}
      </div>
      {error && <div className="issue error"><span className="tag">error</span><span>{error}</span></div>}

      {step === 0 && (
        <div className="card">
          <div className="dropzone"
            onClick={() => fileInput.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault(); setDrag(false)
              const f = e.dataTransfer.files[0]
              if (f) void doUpload(f)
            }}
            {...(drag ? { className: 'dropzone drag' } : {})}>
            {busy ? 'Reading file…' : info
              ? <><b>{info.filename}</b> — {info.columns.length} columns detected. Click to replace.</>
              : <>Drop a CSV / Excel loan tape here, or click to browse</>}
          </div>
          <input ref={fileInput} type="file" accept=".csv,.tsv,.txt,.xlsx,.xlsm,.xltx" hidden
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void doUpload(f) }} />

          {info && (
            <>
              <div className="form-row">
                {info.sheets.length > 1 && (
                  <div className="filter-field">
                    <label>Sheet</label>
                    <select value={sheet} onChange={(e) => { setSheet(e.target.value); void rePreview(e.target.value, headerRow) }}>
                      {info.sheets.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </div>
                )}
                <div className="filter-field">
                  <label>Header row (0-based)</label>
                  <input type="number" min={0} max={50} value={headerRow}
                    onChange={(e) => { const h = Number(e.target.value); setHeaderRow(h); void rePreview(sheet, h) }} />
                </div>
              </div>
              <div className="preview-table-wrap">
                <table className="preview-table">
                  <thead><tr>{info.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
                  <tbody>
                    {info.rows.slice(0, 8).map((r, i) => (
                      <tr key={i}>{r.map((v, j) => <td key={j}>{v}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="wizard-actions">
                <span />
                <button className="btn primary" onClick={() => setStep(1)}>Continue to mapping →</button>
              </div>
            </>
          )}
        </div>
      )}

      {step === 1 && info && (
        <div className="card">
          <div className="card-title">Where should this tape go?</div>
          <div className="form-row">
            <div className="filter-field">
              <label>Portfolio</label>
              <select value={targetId === 'new' ? 'new' : String(targetId)}
                onChange={(e) => {
                  const v = e.target.value
                  if (v === 'new') { setTargetId('new') } else {
                    const pid = Number(v)
                    setTargetId(pid)
                    void applySavedMapping(pid)
                  }
                }}>
                <option value="new">＋ Create new portfolio</option>
                {portfolios.map((p) => <option key={p.id} value={p.id}>{p.name} (add snapshot)</option>)}
              </select>
            </div>
            {targetId === 'new' && (
              <>
                <div className="filter-field">
                  <label>New portfolio name</label>
                  <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="e.g. Auto Pool 2026-A" />
                </div>
                <div className="filter-field">
                  <label>Asset class</label>
                  <select value={assetClass} onChange={(e) => setAssetClass(e.target.value)}>
                    <option value="auto">Auto</option>
                    <option value="mortgage">Mortgage</option>
                    <option value="consumer">Consumer</option>
                  </select>
                </div>
              </>
            )}
            {!mappedFields.has('as_of_date') && (
              <div className="filter-field">
                <label>As-of date for the whole file</label>
                <input type="date" value={asOfDate} onChange={(e) => setAsOfDate(e.target.value)} />
              </div>
            )}
          </div>

          <div className="card-title" style={{ marginTop: 10 }}>Map file columns to canonical fields</div>
          <div className="card-sub">
            Auto-detected matches are pre-filled.
            {requiredMissing.length > 0
              ? <span style={{ color: 'var(--amber)' }}> Still required: {requiredMissing.map((f) => f.label).join(', ')}</span>
              : <span style={{ color: 'var(--green)' }}> All required fields mapped ✓</span>}
          </div>
          <div className="mapping-grid">
            {info.columns.map((col) => (
              <div className="mapping-row" key={col}>
                <span className="col-name" title={col}>{col}</span>
                <select className={mapping[col] ? 'mapped' : ''} value={mapping[col] ?? ''}
                  onChange={(e) => setMapping((m) => {
                    const next = { ...m }
                    if (e.target.value) next[col] = e.target.value
                    else delete next[col]
                    return next
                  })}>
                  <option value="">— ignore —</option>
                  {schema.map((f) => (
                    <option key={f.name} value={f.name}
                      disabled={mappedFields.has(f.name) && mapping[col] !== f.name}>
                      {f.label}{f.required ? ' *' : ''}
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>
          <div className="wizard-actions">
            <button className="btn" onClick={() => setStep(0)}>← Back</button>
            <button className="btn primary" onClick={doValidate}
              disabled={busy || requiredMissing.length > 0 || asOfNeeded || targetInvalid}>
              {busy ? 'Validating…' : 'Validate →'}
            </button>
          </div>
        </div>
      )}

      {step === 2 && report && (
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Validation {report.ok ? 'passed' : 'failed'}</div>
              <div className="card-sub">
                {report.row_count.toLocaleString()} rows ·
                ${(report.total_balance / 1e6).toFixed(1)}M total balance
              </div>
            </div>
            <span className={`badge${report.ok ? ' ok' : ''}`}>
              {report.errors.length} errors · {report.warnings.length} warnings
            </span>
          </div>
          {report.errors.length === 0 && report.warnings.length === 0 && (
            <div className="issue" style={{ border: '1px solid rgba(52,211,153,0.4)' }}>
              <span className="tag" style={{ color: 'var(--green)' }}>clean</span>
              <span>No issues found — ready to import.</span>
            </div>
          )}
          {issueList(report.errors)}
          {issueList(report.warnings)}
          <div className="wizard-actions">
            <button className="btn" onClick={() => setStep(1)}>← Fix mapping</button>
            <button className="btn primary" onClick={doImport} disabled={!report.ok || busy}>
              {busy ? 'Importing…' : 'Import →'}
            </button>
          </div>
        </div>
      )}

      {step === 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="card-title">Reference data & template</div>
          <div className="card-sub">
            Download existing portfolios as CSV to see the expected layout, extend them with
            new loans or reporting periods, and upload them back. The history export stacks
            every as-of date — re-uploading it recreates all snapshots at once.
          </div>
          <div style={{ marginTop: 12 }}>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 14 }}>
              <a className="btn primary" href="/api/uploads/template" download>
                ⇩ Blank template (canonical columns)
              </a>
            </div>
            <table className="data-table">
              <thead>
                <tr><th>Portfolio</th><th>Snapshots</th><th>Download</th></tr>
              </thead>
              <tbody>
                {portfolios.map((p) => (
                  <tr key={p.id}>
                    <td style={{ textAlign: 'left' }}>{p.name}</td>
                    <td>{p.snapshot_count} ({p.latest_as_of ?? '—'} latest)</td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <a className="btn" style={{ padding: '4px 10px', marginRight: 8 }}
                        href={`/api/portfolios/${p.id}/export?scope=latest`} download>
                        Latest snapshot
                      </a>
                      <a className="btn" style={{ padding: '4px 10px' }}
                        href={`/api/portfolios/${p.id}/export?scope=history`} download>
                        Full history
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {step === 3 && result && (
        <div className="card" style={{ textAlign: 'center', padding: '50px 20px' }}>
          <h2 style={{ color: 'var(--green)' }}>✓ Imported into “{result.portfolio_name}”</h2>
          <p style={{ color: 'var(--muted)' }}>
            {result.snapshots.map((s) => `${s.as_of_date} (${s.rows.toLocaleString()} loans)`).join(' · ')}
          </p>
          <div style={{ marginTop: 20, display: 'flex', gap: 12, justifyContent: 'center' }}>
            <Link className="btn primary" to="/">View dashboards</Link>
            <button className="btn" onClick={() => {
              setStep(0); setInfo(null); setReport(null); setResult(null); setMapping({})
            }}>Upload another tape</button>
          </div>
        </div>
      )}
    </>
  )
}
