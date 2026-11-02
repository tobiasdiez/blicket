// The drawing of the Sankey diagram, in a chunk of its own that sankey.ts loads when it draws the
// first diagram: each panel's graph, laid out by the rules of sankey_graph.ts, the links and node
// bars that d3-sankey-diagram draws, and around them the legend, the unit, the panel and node
// labels, the tooltips and the export menu, in SVG that exports as it is.
import { sankeyDiagram, type LayoutLink, type LayoutNode } from 'd3-sankey-diagram'
import { select } from 'd3-selection'
import { Handler } from 'vega-tooltip'
import type { Row } from '../lib/table'
import { legendGrid } from './encodings'
import { SPACING } from './layout'
import { diagramHeight, HEADER, headerHeight, MENU_ROOM, PANEL_LABEL, panelGrid, ROW_GAP, sankeyChannels, unitLine, type SankeyChannels } from './sankey'
import {
  backward,
  caption,
  clamped,
  comparisons,
  drawable,
  fitRows,
  labelBox,
  labelLines,
  labelSides,
  layOut,
  leastWidth,
  LINE_STEP,
  linkOpacity,
  linkTooltip,
  nodeTooltip,
  placeLabels,
  ribbonPath,
  sankeyGraphs,
  type Box,
  type Emphasis,
  type Flow,
  type FlowChange,
  type Graphs,
  type Metrics,
  type Panel,
  type Placed,
  type Side,
} from './sankey_graph'
import { background, exportMenu, svgElement, svgText } from './svg_export'
import { FONT, INK } from './theme'
import type { PlotArgs, Theme } from './types'

// Room around a diagram, in px: at its sides, where the layout narrows the box further for loops
// that turn back beyond the nodes, and above and below.
const SIDE_MARGIN = 4
const INSET = 12
const COMPACT_INSET = 4
const TEXT_SIZE = 11 // px, the header's and the node labels' text, as the other charts' axis titles
const PANEL_TITLE_SIZE = 12 // px, a panel's label, as the other charts' panel headers
const BASELINE = 14 // px from the top of a panel's label to its baseline
const LABEL_GAP = 4 // px between a node and its label
const EMPTY = 20 // px, the least height of a row of panels, which a panel's note takes
// The opacity of a legend entry of a colour value that the legend leaves out or no flow has.
const LEGEND_FADED = 0.4
// The tooltip's element, which vega-tooltip makes, and the room it keeps from the window's edges.
const TOOLTIP = 'vg-tooltip-element'
const TOOLTIP_EDGE = 4
// A touch that moves less than this many px is a tap.
const TAP = 10
// A diagram at most this many px narrower than its least width is drawn as wide as there is room.
const SCROLL_SLACK = 16

/**
 * The header over the diagrams, into `svg`, `width` wide: the legend of the colour values, whose
 * entries `pick` on a click, those that `present` holds, then the unit of the links' width; the
 * legend's entries by value.
 */
function drawHeader(svg: SVGSVGElement, title: string | null, entries: Graphs['legend'], present: Set<string>, unit: string | null, width: number, theme: Theme, pick: (label: string) => void, signal: AbortSignal): Map<string, SVGGElement> {
  const ink = INK[theme]
  const text = { 'font-size': TEXT_SIZE, 'fill': ink.secondary }
  const legend = new Map<string, SVGGElement>()
  const height = headerHeight(entries.map(entry => entry.label), unit !== null, width)
  if (title !== null && entries.length) {
    const { columns, entryWidth } = legendGrid(entries.map(entry => entry.label), width)
    svg.append(svgText(title, { x: 0, y: HEADER.title, ...text }))
    entries.forEach((entry, i) => {
      const [x, y] = [(i % columns) * entryWidth, HEADER.legendTop + Math.floor(i / columns) * HEADER.legendRow]
      const group = svgElement('g')
      // A box over the entry and the gap after it, so that a click anywhere on it picks it.
      group.append(svgElement('rect', { x, 'y': y - HEADER.legendRow / 2, 'width': entryWidth, 'height': HEADER.legendRow, 'fill': 'transparent' }))
      group.append(svgElement('rect', { x, 'y': y - 5, 'width': 10, 'height': 10, 'rx': 2, 'fill': entry.color }))
      group.append(svgText(entry.label, { 'x': x + 16, y, 'dy': '0.35em', ...text }))
      if (present.has(entry.label)) {
        group.setAttribute('cursor', 'pointer')
        group.addEventListener('click', () => pick(entry.label), { signal })
      }
      svg.append(group)
      legend.set(entry.label, group)
    })
  }
  if (unit !== null) svg.append(svgText(unit, { x: 0, y: height - HEADER.gap - HEADER.unitBaseline, ...text }))
  svg.setAttribute('height', String(height))
  return legend
}

/**
 * The library's drawing of `placed` into `group`: the links in their flows' colours, the links
 * turned back under the others, and the node bars, without the library's titles and labels; the
 * links that run rightwards drawn as ribbons instead of the library's arcs, which leave wedges
 * where a wide link turns tightly. The element of each link and node.
 */
function drawGraph(group: SVGGElement, placed: Placed, theme: Theme): { links: { element: SVGElement, link: LayoutLink }[], nodes: { element: SVGElement, node: LayoutNode }[] } {
  const diagram = sankeyDiagram()
    .nodeTitle(() => '')
    .linkTitle(() => '')
    .linkColor(link => placed.flows.get(link)?.color ?? null)
    .linkImportance(link => (backward(link) ? -1 : link.dy))
  const selection = select(group).datum(placed.graph)
  selection.call(diagram)
  for (const element of group.querySelectorAll('title, .node-title, .node-value, .link .label')) element.remove()
  for (const body of group.querySelectorAll('.node-body')) body.setAttribute('fill', INK[theme].secondary)
  const links: { element: SVGElement, link: LayoutLink }[] = []
  const nodes: { element: SVGElement, node: LayoutNode }[] = []
  selection.selectAll<LayoutLink>('.link').each(function (link) {
    if (!backward(link)) this.querySelector('path')!.setAttribute('d', ribbonPath(link.points, link.dy))
    links.push({ element: this, link })
  })
  selection.selectAll<LayoutNode>('.node').each(function (node) {
    nodes.push({ element: this, node })
  })
  return { links, nodes }
}

/**
 * The labels of a panel's nodes, `width` wide, placed by `placeLabels` in the order of the nodes'
 * size, on the sides `labelSides` names, a long one beside its bar in two lines or else three,
 * clear of each other and of the other nodes' bars; a label that fits nowhere is left out, and the
 * tooltip names its node all the same. The lines are measured once, the boxes on each side worked
 * out from that, and each label set once, where it goes.
 */
function drawLabels(group: SVGGElement, nodes: LayoutNode[], width: number, theme: Theme): void {
  const ink = INK[theme]
  const bars = new Map<LayoutNode, Box>(nodes.map(node => [node, { x: node.x0, y: node.y0, width: node.x1 - node.x0, height: Math.max(1, node.y1 - node.y0) }]))
  const sorted = nodes.toSorted((a, b) => b.value - a.value)
  const wraps = sorted.map(node => [labelLines(node.id), labelLines(node.id, 3)] as const)
  const { lengths, metrics } = measured(group, wraps.flat(2))
  const labels = sorted.map((node, i) => {
    const [two, three] = wraps[i]!
    const tried = labelSides(node).flatMap((side): [Side, string[]][] => (side === 'right' || side === 'left') && three.length > two.length ? [[side, two], [side, three]] : [[side, two]])
    const places = tried.map(([side, lines]) => labelBox(side, node, lines.length, Math.max(...lines.map(line => lengths.get(line)!)), LABEL_GAP, width, metrics))
    return { tried, places, label: { boxes: places.map(place => place?.box ?? null), bars: nodes.filter(other => other !== node).map(other => bars.get(other)!) } }
  })
  placeLabels(labels.map(({ label }) => label)).forEach((chosen, i) => {
    if (chosen === null) return
    const [, lines] = labels[i]!.tried[chosen]!
    const { x, y, anchor, first } = labels[i]!.places[chosen]!
    const text = svgElement('text', {
      'y': y,
      'text-anchor': anchor,
      'font-size': TEXT_SIZE,
      'fill': ink.primary,
      // A halo in the surface colour keeps the label legible over the links.
      'stroke': ink.surface,
      'stroke-width': 3,
      'stroke-linejoin': 'round',
      'paint-order': 'stroke',
      'pointer-events': 'none',
    })
    text.append(...lines.map((line, k) => Object.assign(svgElement('tspan', { x, dy: `${k ? LINE_STEP : first}em` }), { textContent: line })))
    group.append(text)
  })
}

/** The length of each of `lines` in the labels' text, and how far its glyphs reach, measured in `group` at once. */
function measured(group: SVGGElement, lines: string[]): { lengths: Map<string, number>, metrics: Metrics } {
  const distinct = [...new Set(lines)]
  const probe = svgElement('text', { 'font-size': TEXT_SIZE, 'visibility': 'hidden' })
  const spans = distinct.map(line => Object.assign(svgElement('tspan'), { textContent: line }))
  probe.append(...spans)
  const glyphs = svgElement('text', { 'font-size': TEXT_SIZE, 'visibility': 'hidden' })
  glyphs.textContent = 'Hg'
  group.append(probe, glyphs)
  const lengths = new Map(distinct.map((line, i) => [line, spans[i]!.getComputedTextLength()]))
  const box = glyphs.getBBox()
  probe.remove()
  glyphs.remove()
  return { lengths, metrics: { size: TEXT_SIZE, ascent: -box.y, descent: box.y + box.height } }
}

/**
 * Highlights an element under the pointer and shows its tooltip: `tip` makes the tooltip's content,
 * `enter` and `leave` highlight it and clear the highlight.
 */
type Interactive = (element: SVGElement, tip: () => Record<string, string>, enter: () => void, leave: () => void) => void

/**
 * Tooltips in the other charts' look, kept within the window: under a mouse while it is over an
 * element; for a tap of a finger or pen, until the next touch elsewhere or a scroll. A touch that
 * moves, as a swipe does, shows nothing. They and their listeners go with `signal`.
 */
function tooltips(theme: Theme, signal: AbortSignal): Interactive {
  const handler = new Handler({ theme })
  const show = (event: MouseEvent, value: Record<string, string> | null) => {
    handler.call(null, event, null as never, value)
    const element = document.getElementById(TOOLTIP)
    if (!value || !element) return
    // Under the pointer it must not take the pointer's events, or it would flicker.
    element.style.pointerEvents = 'none'
    // Where vega-tooltip put it, and its full size, at the window's left edge, where nothing
    // squeezes it.
    const placed = element.getBoundingClientRect()
    element.style.left = '0px'
    const { width, height } = element.getBoundingClientRect()
    element.style.left = `${clamped(placed.left, width, window.innerWidth, TOOLTIP_EDGE)}px`
    element.style.top = `${clamped(placed.top, height, window.innerHeight, TOOLTIP_EDGE)}px`
  }
  let tapped: { element: SVGElement, leave: () => void } | null = null
  let pressed: { id: number, x: number, y: number } | null = null
  const hide = (event: MouseEvent) => {
    if (!tapped) return
    tapped.leave()
    tapped = null
    show(event, null)
  }
  document.addEventListener('pointerdown', (event) => {
    if (tapped && !tapped.element.contains(event.target as Node)) hide(event)
  }, { capture: true, signal })
  // A scroll, of the page or of the diagram's box, moves the content from under the tooltip.
  document.addEventListener('scroll', () => {
    if (tapped) hide(new MouseEvent('scroll'))
  }, { capture: true, signal })
  signal.addEventListener('abort', () => show(new MouseEvent('abort'), null))
  return (element, tip, enter, leave) => {
    const on = { signal }
    element.addEventListener('pointerenter', (event) => {
      if (event.pointerType === 'mouse') enter()
    }, on)
    element.addEventListener('pointermove', (event) => {
      if (event.pointerType === 'mouse') show(event, tip())
    }, on)
    element.addEventListener('pointerleave', (event) => {
      if (event.pointerType !== 'mouse') return
      show(event, null)
      leave()
    }, on)
    element.addEventListener('pointerdown', (event) => {
      if (event.pointerType !== 'mouse') pressed = { id: event.pointerId, x: event.clientX, y: event.clientY }
    }, on)
    element.addEventListener('pointercancel', () => {
      pressed = null
    }, on)
    element.addEventListener('pointerup', (event) => {
      if (event.pointerType === 'mouse' || pressed?.id !== event.pointerId) return
      const moved = Math.hypot(event.clientX - pressed.x, event.clientY - pressed.y)
      pressed = null
      if (moved > TAP) return
      hide(event)
      tapped = { element, leave }
      enter()
      show(event, tip())
    }, on)
  }
}

/** A drawn link, with the path its opacity goes on and the panel it is in. */
interface DrawnLink {
  path: SVGPathElement
  link: LayoutLink
  flow: Flow
  panel: Panel
}

/** What the panels share as they are drawn. */
interface Context {
  args: PlotArgs
  ch: SankeyChannels
  compared: Map<Row, FlowChange> | null
  emphasis: Emphasis
  /** The links drawn so far, of every panel. */
  drawn: DrawnLink[]
  paint: () => void
  interactive: Interactive
}

/**
 * A panel's diagram into `group`, `width` wide: the graph with its tooltips and highlights, and
 * the node labels unless the chart is compact; a note when the panel has no flow to draw.
 */
function drawPanel(group: SVGGElement, panel: Panel, placed: Placed | undefined, width: number, context: Context): void {
  const { args, ch, emphasis, paint } = context
  if (!placed) {
    group.append(svgText('Nothing to draw', { 'x': 0, 'y': BASELINE, 'font-size': TEXT_SIZE, 'fill': INK[args.theme].muted }))
    return
  }
  const { links, nodes } = drawGraph(group, placed, args.theme)
  for (const { element, link } of links) {
    const flow = placed.flows.get(link)!
    context.drawn.push({ path: element.querySelector('path')!, link, flow, panel })
    context.interactive(element, () => linkTooltip(flow, ch, args.unit, context.compared?.get(flow.row) ?? null), () => {
      emphasis.link = link
      paint()
    }, () => {
      emphasis.link = null
      paint()
    })
  }
  for (const { element, node } of nodes) {
    context.interactive(element, () => nodeTooltip(node.id, panel.flows, args.unit), () => {
      emphasis.node = { node, panel }
      paint()
    }, () => {
      emphasis.node = null
      paint()
    })
  }
  if (!args.compact) drawLabels(group, placed.graph.nodes, width, args.theme)
}

/**
 * The box the diagrams scroll sideways in when they need more room than `available`: a region
 * the keyboard can scroll, with a fade at its right edge while more is to the right.
 */
function scrollBox(box: HTMLElement, width: number, available: number, surface: string, signal: AbortSignal): HTMLElement {
  const frame = document.createElement('div')
  frame.className = 'relative'
  const scroller = document.createElement('div')
  scroller.className = 'overflow-x-auto'
  frame.append(scroller)
  box.append(frame)
  if (width <= available) return scroller
  scroller.setAttribute('role', 'region')
  scroller.setAttribute('aria-label', 'Sankey diagram, scrolls sideways')
  scroller.tabIndex = 0
  const fade = document.createElement('div')
  fade.className = 'pointer-events-none absolute inset-y-0 right-0 w-8'
  fade.style.background = `linear-gradient(to left, ${surface}, transparent)`
  frame.append(fade)
  const update = () => {
    fade.hidden = scroller.scrollLeft + scroller.clientWidth >= scroller.scrollWidth - 1
  }
  scroller.addEventListener('scroll', update, { signal })
  requestAnimationFrame(update)
  return scroller
}

/**
 * The chart of `graphs` into `box`, whose width is `available`: the header over a box that scrolls
 * sideways when the diagrams need more room than a narrow page has, the diagrams in a grid of
 * panels with their labels, each row as high as what it draws, and the export menu.
 */
function drawChart(box: HTMLElement, available: number, args: PlotArgs, ch: SankeyChannels, graphs: Graphs, signal: AbortSignal): void {
  const ink = INK[args.theme]
  // A diagram more than a few px too narrow for its labels is drawn wider, in a box that scrolls
  // sideways.
  const least = leastWidth(graphs.panels)
  const width = args.compact || least - available <= SCROLL_SLACK ? Math.max(1, available) : least
  const emphasis: Emphasis = { focus: null, link: null, node: null }
  const drawn: DrawnLink[] = []
  const present = new Set(graphs.panels.flatMap(panel => panel.flows.map(flow => flow.type)))
  let legend = new Map<string, SVGGElement>()
  const paint = () => {
    for (const { path, link, flow, panel } of drawn) path.setAttribute('fill-opacity', String(linkOpacity(link, flow, panel, emphasis, args.theme)))
    for (const [label, entry] of legend) {
      const shown = present.has(label) && (emphasis.focus === null || emphasis.focus === label)
      entry.setAttribute('opacity', String(shown ? 1 : LEGEND_FADED))
    }
  }

  const parts: SVGSVGElement[] = []
  const unit = unitLine(ch, args.unit)
  if (!args.compact && (graphs.legend.length || unit !== null)) {
    const header = svgElement('svg', { 'width': Math.max(1, available), 'font-family': FONT, 'aria-hidden': 'true' })
    header.append(background(ink.surface))
    box.append(header)
    const pick = (label: string) => {
      emphasis.focus = emphasis.focus === label ? null : label
      paint()
    }
    legend = drawHeader(header, ch.color?.name ?? null, graphs.legend, present, unit, Math.max(1, available), args.theme, pick, signal)
    parts.push(header)
  }

  const scroller = scrollBox(box, width, available, ink.surface, signal)
  const flows = `the flows between ${ch.source.name} and ${ch.target.name}, ${ch.value}${args.unit ? ` in ${args.unit}` : ''}`
  const svg = svgElement('svg', { 'width': width, 'font-family': FONT, 'role': 'img', 'aria-label': `Sankey diagram of ${flows}; the numbers are in the Data tab` })
  svg.append(background(ink.surface))
  scroller.append(svg)
  parts.push(svg)

  const height = diagramHeight(args)
  const { columns, panelWidth } = panelGrid(graphs.panels.length, width)
  const inset = args.compact ? COMPACT_INSET : INSET
  const placed = new Map(layOut(graphs.panels, [[SIDE_MARGIN, inset], [panelWidth - SIDE_MARGIN, height - inset]], args.state.y === 'shared').map(p => [p.panel, p]))
  const context: Context = { args, ch, compared: comparisons(args), emphasis, drawn, paint, interactive: tooltips(args.theme, signal) }
  const groups = graphs.panels.map((panel) => {
    const group = svgElement('g')
    svg.append(group)
    drawPanel(group, panel, placed.get(panel), panelWidth, context)
    return group
  })
  paint()
  fitPanels(svg, groups, graphs.panels, placed, { columns, panelWidth, height, width, labelled: args.state.splits.length > 0, compact: !!args.compact, ink: ink.primary })
  if (!args.compact) exportMenu(box, parts, ink.surface, args.name, signal)
}

/**
 * The panels' places: in a grid of `columns`, each row as high as what its diagrams draw (a compact
 * chart keeps the height of its box, that of the cards), each panel's label above it; and the
 * height of `svg`.
 */
function fitPanels(svg: SVGSVGElement, groups: SVGGElement[], panels: Panel[], placed: Map<Panel, Placed>, layout: { columns: number, panelWidth: number, height: number, width: number, labelled: boolean, compact: boolean, ink: string }): void {
  const { columns, panelWidth, height, width, labelled, compact, ink } = layout
  const bounds = panels.map((panel, i): [number, number] | null => {
    if (!placed.has(panel)) return null
    if (compact) return [0, height]
    const drawnBox = groups[i]!.getBBox()
    return [drawnBox.y, drawnBox.y + drawnBox.height]
  })
  const rows = Array.from({ length: Math.ceil(bounds.length / columns) }, (_, row) => bounds.slice(row * columns, (row + 1) * columns))
  const label = labelled ? PANEL_LABEL : 0
  const fitted = fitRows(rows, label, ROW_GAP, EMPTY)
  panels.forEach((panel, i) => {
    const row = fitted.rows[Math.floor(i / columns)]!
    const x = (i % columns) * (panelWidth + SPACING)
    if (label) svg.append(svgText(panel.label, { 'x': x, 'y': row.top + BASELINE, 'font-size': PANEL_TITLE_SIZE, 'fill': ink }))
    groups[i]!.setAttribute('transform', `translate(${x},${row.top + label - (placed.has(panel) ? row.shift : 0)})`)
  })
  svg.setAttribute('height', String(fitted.height))
  svg.setAttribute('viewBox', `0 0 ${width} ${fitted.height}`)
}

/**
 * Draw the chart of `args` into `el`: the legend of the colour values, which fades the other
 * values' links on a click, and the unit of the links' width; a diagram per panel in a grid with
 * its label above, the link scale shared by the panels or each panel's own as the y toggle says;
 * the node labels; and a caption that counts the rows not drawn. Links and nodes have tooltips; a
 * hovered link stands out, a hovered node fades the links of its panel not on it. A compact chart
 * has no legend, unit, labels or export menu, and its card's caption says the rest, but for a
 * chart with nothing to draw. Returns what removes the chart's listeners and tooltip.
 */
export function draw({ el, ...args }: PlotArgs & { el: HTMLElement }): () => void {
  const ch = sankeyChannels(args)
  const graphs = sankeyGraphs(args)
  el.replaceChildren()
  const box = document.createElement('div')
  box.className = 'relative'
  el.append(box)
  const controller = new AbortController()
  try {
    const shown = drawable(graphs)
    if (shown) {
      if (!args.compact) box.style.paddingTop = `${MENU_ROOM}px`
      drawChart(box, el.clientWidth, args, ch, graphs, controller.signal)
    }
    const text = caption(graphs)
    if (text && (!args.compact || !shown)) box.append(Object.assign(document.createElement('p'), { className: 'mt-2 text-sm text-muted', textContent: text }))
  }
  catch (error) {
    controller.abort()
    throw error
  }
  return () => controller.abort()
}
