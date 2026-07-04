import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'

export const PALETTE = ['#4f8ff7', '#2dd4bf', '#f59e0b', '#ef4444', '#a78bfa', '#34d399', '#f472b6', '#fbbf24', '#38bdf8', '#fb923c']

export const BASE_TEXT = { color: '#8093b0', fontSize: 11 }

export default function EChart({ option, height = 300 }: { option: EChartsOption; height?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)

  useEffect(() => {
    const chart = echarts.init(ref.current!)
    chartRef.current = chart
    const onResize = () => chart.resize()
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      chart.dispose()
      chartRef.current = null
    }
  }, [])

  useEffect(() => {
    chartRef.current?.setOption({ color: PALETTE, ...option }, true)
  }, [option])

  return <div ref={ref} style={{ height, width: '100%' }} />
}
