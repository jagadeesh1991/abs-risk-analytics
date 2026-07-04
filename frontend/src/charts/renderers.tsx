/* Payload-type -> visual renderers. The frontend half of the chart registry:
   any backend chart declaring one of these chart types renders automatically. */
import { useEffect, useState } from 'react'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import EChart, { BASE_TEXT, PALETTE } from './EChart'
import DataTable from '../components/DataTable'
import { KpiGrid } from '../components/KpiCards'
import { axisFormatter, fmtValue } from '../format'
import type { ValueFormat } from '../types'
import usStates from '../assets/us-states.json'

const STATE_NAMES: Record<string, string> = {
  AL: 'Alabama', AK: 'Alaska', AZ: 'Arizona', AR: 'Arkansas', CA: 'California', CO: 'Colorado',
  CT: 'Connecticut', DE: 'Delaware', FL: 'Florida', GA: 'Georgia', HI: 'Hawaii', ID: 'Idaho',
  IL: 'Illinois', IN: 'Indiana', IA: 'Iowa', KS: 'Kansas', KY: 'Kentucky', LA: 'Louisiana',
  ME: 'Maine', MD: 'Maryland', MA: 'Massachusetts', MI: 'Michigan', MN: 'Minnesota',
  MS: 'Mississippi', MO: 'Missouri', MT: 'Montana', NE: 'Nebraska', NV: 'Nevada',
  NH: 'New Hampshire', NJ: 'New Jersey', NM: 'New Mexico', NY: 'New York', NC: 'North Carolina',
  ND: 'North Dakota', OH: 'Ohio', OK: 'Oklahoma', OR: 'Oregon', PA: 'Pennsylvania',
  RI: 'Rhode Island', SC: 'South Carolina', SD: 'South Dakota', TN: 'Tennessee', TX: 'Texas',
  UT: 'Utah', VT: 'Vermont', VA: 'Virginia', WA: 'Washington', WV: 'West Virginia',
  WI: 'Wisconsin', WY: 'Wyoming', DC: 'District of Columbia', PR: 'Puerto Rico',
}

const GRID = { left: 55, right: 20, top: 36, bottom: 40, containLabel: false }
const AXIS_LINE = { lineStyle: { color: '#1e2c47' } }
const SPLIT_LINE = { lineStyle: { color: '#16223a' } }
const TOOLTIP_STYLE = {
  backgroundColor: '#121c2e', borderColor: '#1e2c47', textStyle: { color: '#d9e2f2', fontSize: 12 },
}

/* eslint-disable @typescript-eslint/no-explicit-any */

function LineChart({ p, height }: { p: any; height?: number }) {
  const fmt = axisFormatter(p.yFormat ?? 'number')
  const hasGhosts = p.series.some((s: any) => s.ghost)
  const series: any[] = []
  if (p.band) {
    // shaded corridor: invisible base + (high - low) stacked area
    series.push({
      name: '_low', type: 'line', data: p.band.low, stack: '_band', symbol: 'none',
      lineStyle: { opacity: 0 }, silent: true, tooltip: { show: false },
    })
    series.push({
      name: p.band.name, type: 'line', stack: '_band', symbol: 'none',
      data: p.band.high.map((h: number, i: number) => h - p.band.low[i]),
      lineStyle: { opacity: 0 }, areaStyle: { color: 'rgba(79,143,247,0.14)' },
      tooltip: { show: false },
    })
  }
  for (const s of p.series) {
    series.push({
      name: s.name, type: 'line', data: s.data, showSymbol: false, smooth: 0.2,
      stack: p.stacked ? 'total' : undefined,
      areaStyle: p.area ? { opacity: 0.4 } : undefined,
      lineStyle: s.ghost
        ? { width: 1, color: '#3d4c66', type: s.name === 'Median' ? 'dashed' : 'solid' }
        : { width: hasGhosts ? 3 : 2 },
      itemStyle: s.ghost ? { color: '#3d4c66' } : undefined,
      emphasis: s.ghost ? { disabled: true } : undefined,
    })
  }
  const option: EChartsOption = {
    tooltip: {
      trigger: 'axis', ...TOOLTIP_STYLE,
      valueFormatter: (v) => (v == null ? '—' : fmt(Number(v))),
    },
    legend: {
      textStyle: BASE_TEXT, top: 0, type: 'scroll',
      data: [...(p.band ? [p.band.name] : []), ...p.series.map((s: any) => s.name)],
    },
    grid: { ...GRID, top: 34 },
    xAxis: {
      type: 'category', data: p.x.map(String), axisLine: AXIS_LINE, axisLabel: BASE_TEXT,
      name: p.xLabel, nameLocation: 'middle', nameGap: 28, nameTextStyle: BASE_TEXT,
    },
    yAxis: {
      type: 'value', splitLine: SPLIT_LINE,
      axisLabel: { ...BASE_TEXT, formatter: (v: number) => fmt(v) },
    },
    series,
  }
  return <EChart option={option} height={height} />
}

function BarChart({ p, height }: { p: any; height?: number }) {
  const fmt = axisFormatter(p.yFormat ?? 'number')
  const option: EChartsOption = {
    tooltip: { trigger: 'axis', ...TOOLTIP_STYLE, valueFormatter: (v) => (v == null ? '—' : fmt(Number(v))) },
    legend: p.series.length > 1 ? { textStyle: BASE_TEXT, top: 0, type: 'scroll' } : undefined,
    grid: { ...GRID, top: p.series.length > 1 ? 34 : GRID.top },
    xAxis: { type: 'category', data: p.x, axisLine: AXIS_LINE, axisLabel: { ...BASE_TEXT, interval: 'auto' } },
    yAxis: { type: 'value', splitLine: SPLIT_LINE, axisLabel: { ...BASE_TEXT, formatter: (v: number) => fmt(v) } },
    series: p.series.map((s: any) => ({
      name: s.name, type: 'bar', data: s.data, barMaxWidth: 26,
      stack: p.stacked ? 'total' : undefined,
      itemStyle: p.stacked ? undefined : { borderRadius: [3, 3, 0, 0] },
    })),
  }
  return <EChart option={option} height={height} />
}

function PyramidChart({ p, height }: { p: any; height?: number }) {
  const fmt = (v: number) => fmtValue(Math.abs(v), (p.format ?? 'number') as ValueFormat)
  const option: EChartsOption = {
    tooltip: {
      trigger: 'axis', ...TOOLTIP_STYLE,
      valueFormatter: (v) => (v == null ? '—' : fmt(Number(v))),
    },
    legend: { textStyle: BASE_TEXT, top: 0 },
    grid: { left: 70, right: 20, top: 34, bottom: 30 },
    xAxis: {
      type: 'value', axisLine: AXIS_LINE, splitLine: SPLIT_LINE,
      axisLabel: { ...BASE_TEXT, formatter: (v: number) => fmt(v) },
    },
    yAxis: { type: 'category', data: p.categories, axisLine: AXIS_LINE, axisLabel: BASE_TEXT },
    series: [
      { name: p.left.name, type: 'bar', stack: 'pyr', barMaxWidth: 22,
        data: p.left.data.map((v: number) => -v) },
      { name: p.right.name, type: 'bar', stack: 'pyr', barMaxWidth: 22, data: p.right.data },
    ],
  }
  return <EChart option={option} height={height} />
}

function PieChart({ p, height }: { p: any; height?: number }) {
  const fmt = (v: number) => fmtValue(v, (p.format ?? 'number') as ValueFormat)
  const option: EChartsOption = {
    tooltip: { ...TOOLTIP_STYLE, formatter: (params: any) => `${params.name}: ${fmt(params.value)} (${params.percent}%)` },
    legend: { textStyle: BASE_TEXT, bottom: 0, type: 'scroll' },
    series: [{
      type: 'pie', radius: ['48%', '72%'], center: ['50%', '46%'],
      data: p.items, label: { color: '#8093b0', fontSize: 11 },
      itemStyle: { borderColor: '#121c2e', borderWidth: 2 },
    }],
  }
  return <EChart option={option} height={height} />
}

function HeatmapChart({ p, height }: { p: any; height?: number }) {
  const values = p.cells.map((c: number[]) => c[2])
  const isPct = p.format === 'percent'
  const sign = (v: number) => (p.diverging && v > 0 ? '+' : '')
  const fmt = (v: number) => (isPct ? `${sign(v)}${(v * 100).toFixed(1)}%` : fmtValue(v, p.format))
  const absMax = Math.max(...values.map((v: number) => Math.abs(v)), 0.0001)
  const visualMap = p.diverging
    ? { min: -absMax, max: absMax, inRange: { color: ['#2dd4bf', '#12233d', '#ef4444'] } }
    : { min: 0, max: Math.max(...values, 0.0001), inRange: { color: ['#12233d', '#1d4ed8', '#2dd4bf', '#f59e0b'] } }
  const option: EChartsOption = {
    tooltip: {
      ...TOOLTIP_STYLE,
      formatter: (params: any) =>
        `${p.yLabels[params.value[1]]} → ${p.xLabels[params.value[0]]}: <b>${fmt(params.value[2])}</b>`,
    },
    grid: { left: 80, right: 20, top: 10, bottom: 70 },
    xAxis: { type: 'category', data: p.xLabels, axisLine: AXIS_LINE, axisLabel: BASE_TEXT, splitArea: { show: false } },
    yAxis: { type: 'category', data: p.yLabels, inverse: true, axisLine: AXIS_LINE, axisLabel: BASE_TEXT },
    visualMap: {
      ...visualMap, calculable: false, orient: 'horizontal', left: 'center', bottom: 0,
      textStyle: BASE_TEXT, formatter: (v: any) => fmt(Number(v)),
    },
    series: [{
      type: 'heatmap', data: p.cells,
      label: {
        show: true, fontSize: 10, color: '#d9e2f2',
        formatter: (params: any) => (Math.abs(params.value[2]) > 0.0005 ? fmt(params.value[2]) : ''),
      },
      itemStyle: { borderColor: '#0b1220', borderWidth: 2 },
    }],
  }
  return <EChart option={option} height={height} />
}

function TreemapChart({ p, height }: { p: any; height?: number }) {
  const fmt = (v: number) => fmtValue(v, (p.format ?? 'number') as ValueFormat)
  const option: EChartsOption = {
    tooltip: { ...TOOLTIP_STYLE, formatter: (params: any) => `${params.name}: ${fmt(params.value)}` },
    series: [{
      type: 'treemap', roam: false, nodeClick: 'zoomToNode',
      breadcrumb: { show: true, itemStyle: { color: '#16223a', textStyle: { color: '#8093b0' } } },
      label: { fontSize: 12 },
      upperLabel: { show: true, height: 22, fontSize: 12, color: '#fff' },
      itemStyle: { borderColor: '#0b1220', borderWidth: 1, gapWidth: 1 },
      levels: [
        { itemStyle: { gapWidth: 3 } },
        { colorSaturation: [0.3, 0.6], itemStyle: { gapWidth: 1, borderColorSaturation: 0.6 } },
      ],
      data: p.children,
    }],
  }
  return <EChart option={option} height={height} />
}

function BoxChart({ p, height }: { p: any; height?: number }) {
  const isPct = p.format === 'percent'
  const fmt = (v: number) => (isPct ? `${(v * 100).toFixed(1)}%` : fmtValue(v, p.format))
  const option: EChartsOption = {
    tooltip: {
      ...TOOLTIP_STYLE,
      formatter: (params: any) => {
        const [, min, q1, med, q3, max] = params.value
        return `${params.name}<br/>max ${fmt(max)}<br/>q3 ${fmt(q3)}<br/><b>median ${fmt(med)}</b><br/>q1 ${fmt(q1)}<br/>min ${fmt(min)}`
      },
    },
    grid: GRID,
    xAxis: { type: 'category', data: p.categories, axisLine: AXIS_LINE, axisLabel: BASE_TEXT },
    yAxis: { type: 'value', splitLine: SPLIT_LINE, axisLabel: { ...BASE_TEXT, formatter: (v: number) => fmt(v) } },
    series: [{
      type: 'boxplot', data: p.data,
      itemStyle: { color: 'rgba(79,143,247,0.25)', borderColor: '#4f8ff7' },
    }],
  }
  return <EChart option={option} height={height} />
}

function WaterfallChart({ p, height }: { p: any; height?: number }) {
  const fmt = (v: number) => fmtValue(v, (p.format ?? 'currency') as ValueFormat)
  const names: string[] = p.items.map((i: any) => i.name)
  const base: number[] = []
  const bars: { value: number; itemStyle: { color: string } }[] = []
  let running = 0
  for (const item of p.items) {
    if (item.kind === 'start' || item.kind === 'end') {
      base.push(0)
      bars.push({ value: item.value, itemStyle: { color: '#4f8ff7' } })
      running = item.value
    } else if (item.value >= 0) {
      base.push(running)
      bars.push({ value: item.value, itemStyle: { color: '#34d399' } })
      running += item.value
    } else {
      running += item.value
      base.push(running)
      bars.push({ value: -item.value, itemStyle: { color: '#ef4444' } })
    }
  }
  const option: EChartsOption = {
    tooltip: {
      ...TOOLTIP_STYLE, trigger: 'axis',
      formatter: (params: any) => {
        const i = params[params.length - 1].dataIndex
        return `${names[i]}: <b>${fmt(p.items[i].value)}</b>`
      },
    },
    grid: { ...GRID, bottom: 60 },
    xAxis: { type: 'category', data: names, axisLine: AXIS_LINE, axisLabel: { ...BASE_TEXT, interval: 0, rotate: 18 } },
    yAxis: { type: 'value', splitLine: SPLIT_LINE, axisLabel: { ...BASE_TEXT, formatter: (v: number) => fmt(v) } },
    series: [
      { type: 'bar', stack: 'w', itemStyle: { color: 'transparent' }, emphasis: { itemStyle: { color: 'transparent' } }, data: base, tooltip: { show: false } },
      { type: 'bar', stack: 'w', data: bars, barMaxWidth: 42, itemStyle: { borderRadius: 3 } },
    ],
  }
  return <EChart option={option} height={height} />
}

function SankeyChart({ p, height }: { p: any; height?: number }) {
  const fmt = (v: number) => fmtValue(v, (p.format ?? 'currency') as ValueFormat)
  const option: EChartsOption = {
    tooltip: {
      ...TOOLTIP_STYLE,
      formatter: (params: any) => params.dataType === 'edge'
        ? `${params.data.source} → ${params.data.target}: <b>${fmt(params.data.value)}</b>`
        : params.name,
    },
    series: [{
      type: 'sankey',
      data: p.nodes,
      links: p.links,
      left: 10, right: 130, top: 12, bottom: 12,
      nodeWidth: 14, nodeGap: 14,
      label: { color: '#d9e2f2', fontSize: 11 },
      lineStyle: { color: 'gradient', curveness: 0.5, opacity: 0.35 },
      itemStyle: { borderWidth: 0 },
      emphasis: { focus: 'adjacency' },
    }],
  }
  return <EChart option={option} height={height} />
}

function FunnelChart({ p, height }: { p: any; height?: number }) {
  const fmt = (v: number) => fmtValue(v, (p.format ?? 'number') as ValueFormat)
  const option: EChartsOption = {
    tooltip: { ...TOOLTIP_STYLE, formatter: (params: any) => `${params.name}: <b>${fmt(params.value)}</b>` },
    series: [{
      type: 'funnel',
      sort: 'descending',
      left: '8%', right: '8%', top: 10, bottom: 10,
      gap: 3,
      label: { show: true, position: 'inside', color: '#fff', fontSize: 11.5,
               formatter: (params: any) => `${params.name}\n${fmt(params.value)}` },
      itemStyle: { borderColor: '#0b1220', borderWidth: 1 },
      data: p.items,
    }],
  }
  return <EChart option={option} height={height} />
}

function RadarChart({ p, height }: { p: any; height?: number }) {
  const option: EChartsOption = {
    tooltip: TOOLTIP_STYLE,
    legend: { textStyle: BASE_TEXT, bottom: 0, type: 'scroll' },
    radar: {
      indicator: p.indicators,
      radius: '62%',
      center: ['50%', '46%'],
      axisName: { color: '#8093b0', fontSize: 11 },
      splitLine: { lineStyle: { color: '#1e2c47' } },
      splitArea: { areaStyle: { color: ['rgba(30,44,71,0.15)', 'rgba(30,44,71,0.05)'] } },
      axisLine: { lineStyle: { color: '#1e2c47' } },
    },
    series: [{
      type: 'radar',
      data: p.series.map((s: any) => ({
        name: s.name, value: s.values,
        areaStyle: { opacity: 0.12 }, lineStyle: { width: 2 },
      })),
    }],
  }
  return <EChart option={option} height={height} />
}

let mapRegistered = false
function MapChart({ p, height }: { p: any; height?: number }) {
  const [ready, setReady] = useState(mapRegistered)
  useEffect(() => {
    if (!mapRegistered) {
      echarts.registerMap('USA', usStates as any)
      mapRegistered = true
      setReady(true)
    }
  }, [])
  if (!ready) return null

  const data = p.data.map((d: any) => ({ name: STATE_NAMES[d.name] ?? d.name, value: d.value }))
  const values = data.map((d: any) => d.value)
  const fmt = (v: number) => fmtValue(v, (p.format ?? 'number') as ValueFormat)
  const option: EChartsOption = {
    tooltip: {
      ...TOOLTIP_STYLE,
      formatter: (params: any) =>
        `${params.name}: <b>${params.value != null && !Number.isNaN(params.value) ? fmt(params.value) : 'no loans'}</b>`,
    },
    visualMap: {
      min: Math.min(...values, 0), max: Math.max(...values, 0.0001),
      orient: 'horizontal', left: 'center', bottom: 0, calculable: true,
      textStyle: BASE_TEXT, formatter: (v: any) => fmt(Number(v)),
      inRange: { color: ['#12233d', '#1d4ed8', '#2dd4bf', '#f59e0b'] },
    },
    series: [{
      type: 'map', map: 'USA', roam: false,
      center: [-98.5, 38.5], zoom: 1.15, aspectScale: 0.8,
      label: { show: false },
      emphasis: { label: { show: true, color: '#fff', fontSize: 11 }, itemStyle: { areaColor: '#2dd4bf' } },
      itemStyle: { borderColor: '#0b1220', areaColor: '#141d30' },
      data,
    }],
  }
  return <EChart option={option} height={height} />
}

function KpisInline({ p }: { p: any }) {
  return <KpiGrid items={p.items} inline />
}

export default function ChartRenderer({ payload, height, exportName }: {
  payload: any
  height?: number
  exportName?: string
}) {
  switch (payload.type) {
    case 'line': return <LineChart p={payload} height={height} />
    case 'bar': return <BarChart p={payload} height={height} />
    case 'pyramid': return <PyramidChart p={payload} height={height} />
    case 'pie': return <PieChart p={payload} height={height} />
    case 'heatmap': return <HeatmapChart p={payload} height={height} />
    case 'treemap': return <TreemapChart p={payload} height={height} />
    case 'box': return <BoxChart p={payload} height={height} />
    case 'waterfall': return <WaterfallChart p={payload} height={height} />
    case 'map': return <MapChart p={payload} height={height} />
    case 'sankey': return <SankeyChart p={payload} height={height} />
    case 'funnel': return <FunnelChart p={payload} height={height} />
    case 'radar': return <RadarChart p={payload} height={height} />
    case 'table': return <DataTable columns={payload.columns} rows={payload.rows} exportName={exportName} />
    case 'kpis': return <KpisInline p={payload} />
    default:
      return <div className="chart-status">Unknown chart type “{String(payload.type)}” — is the frontend renderer registered?</div>
  }
}

export { PALETTE }
