import type { Theme } from './types'

/** The number of categorical slots; past it the hues repeat. */
export const SLOTS = 8

/** The opacity of the baseline's marks, stronger on the dark surface, where faded hues dull. */
export const GHOST: Record<Theme, number> = { light: 0.3, dark: 0.4 }

// The chart tokens of the dataviz palette, light and dark. The categorical slots are assigned in
// this order, which keeps neighbours apart under colour-vision deficiencies; it is validated as
// a set, so slots are never reordered or generated.
export const CATEGORICAL: Record<Theme, readonly string[]> = {
  light: ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'],
  dark: ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'],
}

// `tick` is the axis labels' ink, at least 4.5:1 on the surface.
export const INK: Record<Theme, { surface: string, primary: string, secondary: string, muted: string, tick: string, grid: string, baseline: string }> = {
  light: { surface: '#fcfcfb', primary: '#0b0b0b', secondary: '#52514e', muted: '#898781', tick: '#73716c', grid: '#e1e0d9', baseline: '#c3c2b7' },
  dark: { surface: '#1a1a19', primary: '#f0efec', secondary: '#c3c2b7', muted: '#898781', tick: '#898781', grid: '#2c2c2a', baseline: '#383835' },
}

const FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'

/**
 * The least room a y axis's labels take, in px. It is a floor, which keeps the plot areas of the
 * charts stacked on a page aligned while their labels fit it; a wider label still shifts its chart,
 * since separate views line up by floors and clips, not by construction.
 */
export const Y_LABEL_EXTENT = 48

/**
 * The Vega-Lite config of a theme: recessive hairline axes, text in ink, never in series colour,
 * on the surface colour, which an exported image keeps.
 */
export function config(theme: Theme) {
  const ink = INK[theme]
  const text = { labelColor: ink.secondary, titleColor: ink.secondary, labelFontSize: 11, titleFontSize: 11, titleFontWeight: 'normal' }
  return {
    background: ink.surface,
    font: FONT,
    view: { stroke: null },
    axis: { ...text, labelColor: ink.tick, domainColor: ink.baseline, tickColor: ink.baseline, gridColor: ink.grid, gridWidth: 1, domainWidth: 1, tickSize: 4, labelPadding: 4 },
    axisX: { grid: false },
    axisY: { domain: false, ticks: false, titlePadding: 8, minExtent: Y_LABEL_EXTENT },
    legend: { ...text, orient: 'top', direction: 'horizontal', symbolStrokeWidth: 2, columnPadding: 12, labelLimit: 220 },
    header: { labelColor: ink.primary, labelFontSize: 12, labelAnchor: 'start', labelPadding: 6, title: null },
    title: { color: ink.secondary, fontSize: 12, fontWeight: 'normal', anchor: 'start', offset: 8 },
    line: { strokeWidth: 2, strokeCap: 'round', strokeJoin: 'round' },
  }
}
