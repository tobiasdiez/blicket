// The rules of the Sankey diagram, without the DOM: each panel's graph from the rows, what the
// caption and the tooltips say, the order and the layout that d3-sankey-diagram gets, how far its
// loops reach past the box, which links stand out, where the rows of panels and the node labels
// go. sankey_diagram.ts draws with them; it and they load together, with the first diagram.
import { sankey, type Graph, type LayoutLink, type LayoutNode } from 'd3-sankey-diagram'
import { display, type Row } from '../lib/table'
import { CHANGE, changeRows, RELATIVE, ZERO } from './change'
import { written, yTitle } from './encodings'
import { asNumber, baselineValues, combinations, labelOf, rowKey, splitDimensions } from './layout'
import { sankeyChannels, type SankeyChannels } from './sankey'
import { seriesColors } from './theme'
import type { PlotArgs, Theme } from './types'

const NODE_WIDTH = 4 // px, the width of a node's bar
// A node label longer than this many characters is broken into two lines at a space.
const WRAP = 20
// The room kept free beside a node label and above and below it, in px.
const LABEL_PADDING = { x: 3, y: 1 }
// The least width of a diagram per layer of nodes, in px, which keeps their labels apart; the
// fourteen layers of a plastics model's flows take 854 px.
const LAYER_WIDTH = 61
// How often a panel is laid out again in a narrower box, at most, and the overhang it then leaves,
// in px; the narrowing takes at most this share of the box's width.
const NARROWINGS = 3
const SLACK = 0.5
const MAX_NARROWING = 0.5
// The opacity of the links, higher on the dark surface, where faded hues dull, and lower for the
// links turned back, which lie under the others; of a hovered link and the links on a hovered
// node; and of the links a hovered node is not on or the legend leaves out.
const LINK_OPACITY: Record<Theme, number> = { light: 0.6, dark: 0.75 }
const BACKWARD_OPACITY: Record<Theme, number> = { light: 0.35, dark: 0.45 }
const HOVERED = 0.9
const FADED = 0.15

/** A link of the diagram: a row with a positive value, between the display values of its ends. */
export interface Flow {
  source: string
  target: string
  /** The display value of the row's colour; empty without a colour dimension. */
  type: string
  value: number
  color: string
  row: Row
}

/** The diagram of a panel: its label, its nodes in display order, and its flows. */
export interface Panel {
  label: string
  nodes: string[]
  flows: Flow[]
}

/** What the diagram draws: a panel per split value present, and what it leaves out or colours. */
export interface Graphs {
  panels: Panel[]
  /** How many rows hold a negative value, which no link draws. */
  negative: number
  /** How many rows hold a positive value from a node to itself, which no link draws either. */
  loops: number
  /** How many rows hold an infinite value, which no link draws. */
  infinite: number
  /** The colour values in display order with their colours; empty without a colour dimension. */
  legend: { label: string, color: string }[]
}

/**
 * The graphs of the rows: per panel of the split values, in display order, a flow per row with a
 * positive value between two nodes, and the nodes they connect, in the display order of the source
 * values and then the target values. A row with no value, or 0, draws nothing, nor does one within
 * `ZERO` of the largest finite positive value of its panel, which is numerical noise; a negative
 * one, an infinite one and one from a node to itself, which the layout cannot place, are counted. The colour values take their
 * colours in display order, the same for every filter; without a colour dimension, every link takes
 * the first.
 */
export function sankeyGraphs(args: PlotArgs): Graphs {
  const ch = sankeyChannels(args)
  const splits = splitDimensions(args)
  const labels = ch.color ? ch.color.values.map(value => display(value, ch.color!)) : []
  const legend = seriesColors(labels.length, args.theme).map((color, i) => ({ label: labels[i]!, color }))
  const colors = new Map(legend.map(entry => [entry.label, entry.color]))
  const [first] = seriesColors(1, args.theme)
  const rows = new Map<string, Row[]>()
  for (const row of args.table) {
    const panel = labelOf(row, splits)
    const members = rows.get(panel)
    if (members) members.push(row)
    else rows.set(panel, [row])
  }
  const flows = new Map<string, Flow[]>()
  let [negative, loops, infinite] = [0, 0, 0]
  for (const [panel, members] of rows) {
    const values = members.map(row => asNumber(row[ch.value]))
    const noise = ZERO * values.reduce<number>((most, value) => (value !== null && Number.isFinite(value) ? Math.max(most, value) : most), 0)
    const drawn: Flow[] = []
    members.forEach((row, i) => {
      const value = values[i]!
      if (value === null || Math.abs(value) <= noise) return
      if (!Number.isFinite(value)) {
        infinite += 1
        return
      }
      if (value < 0) {
        negative += 1
        return
      }
      const source = display(row[ch.source.name] ?? null, ch.source)
      const target = display(row[ch.target.name] ?? null, ch.target)
      if (source === target) {
        loops += 1
        return
      }
      const type = ch.color ? display(row[ch.color.name] ?? null, ch.color) : ''
      drawn.push({ source, target, type, value, color: colors.get(type) ?? first!, row })
    })
    flows.set(panel, drawn)
  }
  const order = new Set([...ch.source.values.map(value => display(value, ch.source)), ...ch.target.values.map(value => display(value, ch.target))])
  const panels = combinations(splits).filter(label => flows.has(label)).map((label) => {
    const drawn = flows.get(label)!
    const ends = new Set(drawn.flatMap(flow => [flow.source, flow.target]))
    return { label, nodes: [...order].filter(name => ends.has(name)), flows: drawn }
  })
  return { panels, negative, loops, infinite, legend }
}

/** `n` things, `one` or `many` of them. */
const counted = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

/** What the caption under the diagram says of the rows it leaves out, or nothing. */
export function caption(graphs: Graphs): string {
  const left = [
    ...(graphs.negative ? [counted(graphs.negative, 'negative flow', 'negative flows')] : []),
    ...(graphs.loops ? [counted(graphs.loops, 'flow from a node to itself', 'flows from a node to itself')] : []),
    ...(graphs.infinite ? [counted(graphs.infinite, 'infinite flow', 'infinite flows')] : []),
  ]
  if (drawable(graphs)) return left.length ? `Not drawn: ${left.join(', ')}.` : ''
  return `No flow of this selection can be drawn${left.length ? `: ${left.join(', ')}` : ', none has a positive value'}.`
}

/** Whether a panel has a flow to draw. */
export function drawable(graphs: Graphs): boolean {
  return graphs.panels.some(panel => panel.flows.length)
}

/** A flow's comparison with the baseline: the baseline's value, the change and the relative change. */
export interface FlowChange {
  baseline: number | null
  change: number | null
  relative: number | null
}

/**
 * The comparison of each current row with the baseline's row of its dimension values, as the
 * change bars draw it; `null` without a baseline, or with no baseline row for the selection.
 */
export function comparisons(args: PlotArgs): Map<Row, FlowChange> | null {
  if (!args.baseline?.length) return null
  const ch = sankeyChannels(args)
  const dims = args.schema.dimensions
  const before = baselineValues(args.baseline, dims, ch.value)
  const changed = new Map(changeRows(args).map(row => [rowKey(row, dims), row]))
  return new Map(args.table.map((row) => {
    const key = rowKey(row, dims)
    const change = changed.get(key)
    return [row, { baseline: before.get(key) ?? null, change: asNumber(change?.[CHANGE]), relative: asNumber(change?.[RELATIVE]) }]
  }))
}

/**
 * A link's tooltip: its ends, its colour value and its value with the unit, and against a
 * baseline the baseline's value and the change, with the relative change.
 */
export function linkTooltip(flow: Flow, ch: SankeyChannels, unit: string | null, compared: FlowChange | null): Record<string, string> {
  const entries: Record<string, string> = { [`${ch.source.name} → ${ch.target.name}`]: `${flow.source} → ${flow.target}` }
  if (ch.color) entries[ch.color.name] = flow.type
  entries[yTitle(ch.value, unit)] = written(flow.value)
  if (compared) {
    const { change, relative } = compared
    entries.baseline = written(compared.baseline)
    entries.change = written(change, 'change') + (change === null || relative === null ? '' : ` (${written(relative, 'relative')})`)
  }
  return entries
}

/** A node's tooltip: its name as the title, and the totals of the flows drawn into it and out of it. */
export function nodeTooltip(name: string, flows: Flow[], unit: string | null): Record<string, string> {
  const total = (side: 'source' | 'target') => {
    const ends = flows.filter(flow => flow[side] === name)
    return written(ends.length ? ends.reduce((sum, flow) => sum + flow.value, 0) : null)
  }
  return { title: name, in: total('target'), out: total('source'), ...(unit ? { unit } : {}) }
}

/**
 * A node's label in at most `parts` lines: when it is long, broken at the spaces nearest the
 * points that cut it into equal parts, the first on a tie.
 */
export function labelLines(name: string, parts = 2): string[] {
  if (name.length <= WRAP) return [name]
  const cuts: number[] = []
  for (let k = 1; k < parts; k++) {
    const goal = (name.length * k) / parts
    const spaces = [...name.matchAll(/ /g)].map(match => match.index).filter(i => i > (cuts.at(-1) ?? -1))
    if (!spaces.length) break
    cuts.push(spaces.reduce((best, i) => (Math.abs(i - goal) < Math.abs(best - goal) ? i : best)))
  }
  return [-1, ...cuts].map((cut, i) => name.slice(cut + 1, cuts[i] ?? name.length))
}

/**
 * Where a node's label goes: beside its bar, right or left; or above or below it, centred on it,
 * or starting at the bar and running right or left.
 */
export type Side = 'right' | 'left' | 'above' | 'below' | 'above-right' | 'below-right' | 'above-left' | 'below-left'

/**
 * The sides a node's label is tried on, in order: right of a node that flows only leave or that
 * flows pass through, left of one that flows only enter, then the other side, then centred above
 * and below its bar, then above and below it running the way of the first side, then the other way.
 */
export function labelSides(node: Pick<LayoutNode, 'incoming' | 'outgoing'>): Side[] {
  const right = node.incoming.length === 0 || node.outgoing.length > 0
  return right
    ? ['right', 'left', 'above', 'below', 'above-right', 'below-right', 'above-left', 'below-left']
    : ['left', 'right', 'above', 'below', 'above-left', 'below-left', 'above-right', 'below-right']
}

/** A box in px. */
export interface Box {
  x: number
  y: number
  width: number
  height: number
}

/** The size of the labels' text, and how far a line's glyphs reach above and below its baseline, in px. */
export interface Metrics {
  size: number
  ascent: number
  descent: number
}

/** The step from one line of a label to the next, in em. */
export const LINE_STEP = 1.1

/**
 * A label's place on `side` of `node`'s bar, in `lines` lines `length` px wide, `gap` px from the
 * bar, in a panel `width` wide; `null` where it leaves the panel. Its anchor at `x` is the end it
 * starts from; `y` is the middle of the bar beside it, or the bar's top or bottom edge `gap` px
 * away above or below it, and `first` the first line's offset from `y`, in em: the lines centred
 * on `y`, ending above it, or starting below it. `box` is what its glyphs cover.
 */
export function labelBox(side: Side, node: Pick<LayoutNode, 'x0' | 'x1' | 'y0' | 'y1'>, lines: number, length: number, gap: number, width: number, metrics: Metrics): { box: Box, x: number, y: number, anchor: 'start' | 'end' | 'middle', first: number } | null {
  const [where, run] = side.split('-') as [string, string | undefined]
  const beside = where === 'right' || where === 'left'
  const middle = (node.x0 + node.x1) / 2
  const [x, anchor]: [number, 'start' | 'end' | 'middle'] = beside
    ? where === 'right' ? [node.x1 + gap, 'start'] : [node.x0 - gap, 'end']
    : run === 'right' ? [node.x0, 'start'] : run === 'left' ? [node.x1, 'end'] : [clamped(middle - length / 2, length, width, 0) + length / 2, 'middle']
  const from = anchor === 'start' ? x : anchor === 'end' ? x - length : x - length / 2
  if (from < 0 || from + length > width) return null
  const y = beside ? (node.y0 + node.y1) / 2 : where === 'above' ? node.y0 - gap : node.y1 + gap
  const first = beside ? 0.35 - ((lines - 1) * LINE_STEP) / 2 : where === 'above' ? -((lines - 1) * LINE_STEP + 0.25) : 0.8
  const top = y + first * metrics.size - metrics.ascent
  const bottom = y + (first + (lines - 1) * LINE_STEP) * metrics.size + metrics.descent
  return { box: { x: from, y: top, width: length, height: bottom - top }, x, y, anchor, first }
}

/** Whether two boxes come nearer than `LABEL_PADDING` to each other. */
export function near(a: Box, b: Box): boolean {
  const { x, y } = LABEL_PADDING
  return a.x - x < b.x + b.width && b.x - x < a.x + a.width && a.y - y < b.y + b.height && b.y - y < a.y + a.height
}

/** A node label to place: its box on each side it is tried on, `null` where it leaves the panel, and the bars it must keep clear of. */
export interface LabelPlaces {
  boxes: (Box | null)[]
  bars: Box[]
}

/**
 * Where the labels go, in their order, which puts the larger nodes' first: each on its first side
 * clear of its bars and of the labels placed. A label that fits nowhere takes a side that only one
 * placed label blocks, when that label can move to another of its sides clear of everything; a
 * label that still fits nowhere is left out. Per label, the index of its side, or `null`.
 */
export function placeLabels(labels: LabelPlaces[]): (number | null)[] {
  const chosen: (number | null)[] = labels.map(() => null)
  // Whether label `i`'s `box` is clear of its bars and of the placed labels but `ignore`.
  const clear = (i: number, box: Box | null, ignore: number[] = []): box is Box =>
    box !== null
    && !labels[i]!.bars.some(bar => near(bar, box))
    && !chosen.some((side, j) => side !== null && !ignore.includes(j) && near(labels[j]!.boxes[side]!, box))
  labels.forEach((label, i) => {
    const free = label.boxes.findIndex(box => clear(i, box))
    if (free >= 0) {
      chosen[i] = free
      return
    }
    for (const [side, box] of label.boxes.entries()) {
      if (!box || label.bars.some(bar => near(bar, box))) continue
      const blockers = chosen.flatMap((placed, j) => (placed !== null && near(labels[j]!.boxes[placed]!, box) ? [j] : []))
      if (blockers.length !== 1) continue
      const [j] = blockers as [number]
      const moved = labels[j]!.boxes.findIndex((other, m) => m !== chosen[j] && clear(j, other, [j]) && !near(other, box))
      if (moved < 0) continue
      chosen[j] = moved
      chosen[i] = side
      return
    }
  })
  return chosen
}

/**
 * How much flow the layout turns back for `nodes` and `flows` in this order. The layout breaks the
 * loops by a depth-first walk: from the first node without inflows, or the first node when every
 * node has some, then from the other nodes without inflows, then from any node not reached, each
 * in the order of `nodes`, and from each node along its flows in their order; a flow into a node
 * the walk came through is turned back.
 */
export function turnedBack(nodes: string[], flows: Flow[]): number {
  return [...walked(nodes, flows)].reduce((sum, flow) => sum + flow.value, 0)
}

/** The flows the layout turns back for `nodes` and `flows` in this order (see `turnedBack`). */
function walked(nodes: string[], flows: Flow[]): Set<Flow> {
  const out = new Map(nodes.map(id => [id, [] as Flow[]]))
  for (const flow of flows) out.get(flow.source)!.push(flow)
  const entered = new Set(flows.map(flow => flow.target))
  const walking = new Set<string>()
  const seen = new Set<string>()
  const back = new Set<Flow>()
  const walk = (id: string) => {
    seen.add(id)
    walking.add(id)
    for (const flow of out.get(id)!) {
      if (walking.has(flow.target)) back.add(flow)
      else if (!seen.has(flow.target)) walk(flow.target)
    }
    walking.delete(id)
  }
  for (const id of [...nodes.filter(node => !entered.has(node)), ...nodes]) {
    if (!seen.has(id)) walk(id)
  }
  return back
}

/**
 * How many layers the layout puts a panel's nodes in: one more than the longest chain of the flows
 * it does not turn back, a node's layer being after the layers of the nodes it takes flows from.
 */
export function layers(panel: Panel): number {
  const { nodes, flows } = walkOrder(panel)
  const back = walked(nodes, flows)
  const into = new Map(nodes.map(id => [id, [] as string[]]))
  for (const flow of flows) {
    if (!back.has(flow)) into.get(flow.target)!.push(flow.source)
  }
  const layer = new Map<string, number>()
  const of = (id: string): number => {
    const known = layer.get(id)
    if (known !== undefined) return known
    const found = Math.max(0, ...into.get(id)!.map(source => of(source) + 1))
    layer.set(id, found)
    return found
  }
  return nodes.length ? Math.max(...nodes.map(of)) + 1 : 0
}

/** The least width of a chart of `panels`, so that the labels of its widest graph stay apart. */
export function leastWidth(panels: Panel[]): number {
  return LAYER_WIDTH * Math.max(0, ...panels.filter(panel => panel.flows.length).map(layers))
}

/** The order of a panel's nodes and flows that the layout gets. */
interface Order {
  nodes: string[]
  flows: Flow[]
}

/**
 * The order the layout gets a panel's nodes and flows in. The flows go in the order of their
 * size, so that the layout's walk (see `turnedBack`) follows the main flows first; of the orders
 * of the nodes that start with a node without inflows, the rest in the order of their size, the one
 * that turns back the least flow is taken, so the flows turned back are the small ones that close
 * a loop, such as recycling, and not the main chain of a second source.
 */
export function walkOrder(panel: Panel): Order {
  const totals = new Map<string, [number, number]>(panel.nodes.map(id => [id, [0, 0]]))
  for (const flow of panel.flows) {
    totals.get(flow.source)![1] += flow.value
    totals.get(flow.target)![0] += flow.value
  }
  const size = (id: string) => Math.max(...totals.get(id)!)
  const bySize = panel.nodes.toSorted((a, b) => size(b) - size(a))
  const flows = panel.flows.toSorted((a, b) => b.value - a.value)
  const entered = new Set(flows.map(flow => flow.target))
  const starts = bySize.filter(id => !entered.has(id))
  const orders = (starts.length ? starts : bySize).map(first => [first, ...bySize.filter(id => id !== first)])
  const back = orders.map(order => turnedBack(order, flows))
  return { nodes: orders[back.indexOf(Math.min(...back))]!, flows }
}

/** A panel's graph after the layout, and the flow each of its links draws. */
export interface Placed {
  panel: Panel
  graph: Graph
  flows: Map<LayoutLink, Flow>
}

/** The box a diagram is laid out in: its corners, in px. */
export type Extent = [[number, number], [number, number]]

/** The layout of a panel's flows at `scale` px per unit, or fitted into `extent` when it is null. */
function place(panel: Panel, order: Order, extent: Extent, scale: number | null): { placed: Placed, scale: number } {
  const layout = sankey().nodeWidth(NODE_WIDTH).extent(extent).scale(scale)
  // The layout names a link between two nodes by its type, and an empty name can break it.
  const links = order.flows.map(flow => ({ source: flow.source, target: flow.target, type: flow.type || undefined, value: flow.value }))
  const graph = layout({ nodes: order.nodes.map(id => ({ id })), links })
  // The layout completes the objects it is given, so the i-th link is the i-th flow's.
  return { placed: { panel, graph, flows: new Map(graph.links.map((link, i) => [link, order.flows[i]!])) }, scale: layout.scale() ?? 0 }
}

/**
 * How far the links reach past the left and the right of `extent`, in px. The library lays out the
 * node bars within the extent, and a link turned back turns around beyond its last node: on an arc
 * whose radius is the smaller of the height it turns through over 2.1 and the mean radius at its
 * ends, or 5 px more than half its width without them, and whose outer edge lies half its width
 * further out; its width is at least 2 px.
 */
export function overhang(links: LayoutLink[], extent: Extent): [left: number, right: number] {
  let [left, right] = [0, 0]
  for (const link of links) {
    const half = Math.max(2, link.dy) / 2
    link.points.forEach((point, i) => {
      const next = link.points[i + 1]
      if (!next || (point.d ?? 'r') === (next.d ?? 'r')) return
      const radius = Math.min(Math.abs(next.y - point.y) / 2.1, ((point.ro ?? Number.NaN) + (next.ri ?? Number.NaN)) / 2 || 5 + half)
      if ((point.d ?? 'r') === 'r') right = Math.max(right, Math.max(point.x, next.x) + radius + half - extent[1][0])
      else left = Math.max(left, extent[0][0] - (Math.min(point.x, next.x) - radius - half))
    })
  }
  return [left, right]
}

/** `extent` narrowed by `left` and `right` px, together at most `MAX_NARROWING` of its width. */
export function narrowed(extent: Extent, [left, right]: [number, number]): Extent {
  const most = MAX_NARROWING * (extent[1][0] - extent[0][0])
  const share = left + right > most ? most / (left + right) : 1
  return [[extent[0][0] + left * share, extent[0][1]], [extent[1][0] - right * share, extent[1][1]]]
}

/**
 * The layout of each panel's graph in `extent`, a panel without flows left out. Each panel's flows
 * fill the height of its box; with `shared`, every panel is drawn at the scale of the one whose
 * flows need the least, so that a flow is as wide in every panel. Where the loops reach past the
 * sides of the box, the panel is laid out again in a box narrowed by as much more, up to
 * `NARROWINGS` times, until they reach no more than `SLACK` past it; shared panels are narrowed
 * alike, so that their columns stay in line.
 */
export function layOut(panels: Panel[], extent: Extent, shared: boolean): Placed[] {
  const drawn = panels.filter(panel => panel.flows.length)
  const orders = drawn.map(walkOrder)
  const first = drawn.map((panel, i) => place(panel, orders[i]!, extent, null))
  const together = shared && first.length > 1
  const scale = together ? Math.min(...first.map(fit => fit.scale)) : null
  let placed = first.map(fit => fit.placed)
  const narrowing = drawn.map((): [number, number] => [0, 0])
  // The shared scale needs every panel laid out again, whatever its loops.
  let again = together
  for (let pass = 0; pass < NARROWINGS; pass++) {
    // How far each panel's loops still reach past the box it was given, narrowed or not.
    const reach = placed.map(laidOut => overhang(laidOut.graph.links, extent))
    const most: [number, number] = [Math.max(0, ...reach.map(([left]) => left)), Math.max(0, ...reach.map(([, right]) => right))]
    const need = (i: number) => (together ? most : reach[i]!)
    const over = (i: number) => need(i).some(side => side > SLACK)
    if (!again && !drawn.some((_, i) => over(i))) break
    placed = placed.map((laidOut, i) => {
      if (!again && !over(i)) return laidOut
      const [left, right] = need(i)
      narrowing[i] = [narrowing[i]![0] + left, narrowing[i]![1] + right]
      return place(drawn[i]!, orders[i]!, narrowed(extent, narrowing[i]!), scale).placed
    })
    again = false
  }
  return placed
}

/** A curve from `from` to `to`, `offset` px below both, leaving and entering level. */
function curve(offset: number, from: { x: number, y: number }, to: { x: number, y: number }): string {
  const middle = (from.x + to.x) / 2
  return `C${middle},${from.y + offset} ${middle},${to.y + offset} ${to.x},${to.y + offset}`
}

/**
 * The outline of a link that runs rightwards from point to point: a band `dy` px wide, at least
 * 2 px, between two curves that leave and enter each point level, their control points halfway.
 * The library draws such a link with arcs, which leave wedges where a wide link turns tightly.
 */
export function ribbonPath(points: { x: number, y: number }[], dy: number): string {
  const half = Math.max(2, dy) / 2
  const [start] = points
  const end = points.at(-1)
  if (!start || !end) return ''
  const top = points.slice(1).map((point, i) => curve(-half, points[i]!, point))
  const bottom = points.slice(0, -1).toReversed().map((point, i, back) => curve(half, i ? back[i - 1]! : end, point))
  return `M${start.x},${start.y - half} ${top.join(' ')} L${end.x},${end.y + half} ${bottom.join(' ')} Z`
}

/** Whether the layout turned a link back: its path runs leftwards somewhere. */
export function backward(link: LayoutLink): boolean {
  return link.points.some(point => point.d === 'l')
}

/** What the legend picks and the pointer is over, which the links' opacity shows. */
export interface Emphasis {
  /** The colour value the legend picked, in every panel. */
  focus: string | null
  link: LayoutLink | null
  /** The hovered node, in its panel. */
  node: { node: LayoutNode, panel: Panel } | null
}

/**
 * The opacity of a link of `panel`: the theme's, lower for a link turned back; raised when it is
 * hovered or on a hovered node of its panel, faded when a hovered node of its panel is not on it or
 * the legend picked another colour value.
 */
export function linkOpacity(link: LayoutLink, flow: Flow, panel: Panel, emphasis: Emphasis, theme: Theme): number {
  const { node } = emphasis
  if (node && node.panel === panel) return link.source === node.node || link.target === node.node ? HOVERED : FADED
  if (emphasis.link === link) return HOVERED
  if (emphasis.focus !== null && flow.type !== emphasis.focus) return FADED
  return backward(link) ? BACKWARD_OPACITY[theme] : LINK_OPACITY[theme]
}

/**
 * Where rows of panels go: each row as high as the drawn bounds of its diagrams, `[low, high]` in
 * the diagrams' own coordinates (`null` for a panel without one), and at least `least`, under
 * labels `label` px high, `gap` px apart. Per row its top and how far its diagrams move up, so
 * that the room the layout leaves above and below them goes; and the height of all rows.
 */
export function fitRows(rows: ([number, number] | null)[][], label: number, gap: number, least: number): { rows: { top: number, shift: number }[], height: number } {
  let top = 0
  const fitted = rows.map((bounds) => {
    const drawn = bounds.filter(bound => bound !== null)
    const low = drawn.length ? Math.min(...drawn.map(([y]) => y)) : 0
    const high = drawn.length ? Math.max(...drawn.map(([, y]) => y)) : 0
    const row = { top, shift: low }
    top += label + Math.max(least, high - low) + gap
    return row
  })
  return { rows: fitted, height: Math.max(0, Math.ceil(top - gap)) }
}

/** The position along one axis that keeps a box of `size` within `[edge, viewport - edge]`. */
export function clamped(position: number, size: number, viewport: number, edge: number): number {
  return Math.max(edge, Math.min(position, viewport - edge - size))
}
