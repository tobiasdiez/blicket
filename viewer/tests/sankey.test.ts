import { describe, expect, it } from 'vitest'
import { drawsBaseline, nothingToCompare, PLOT_TYPES } from '../app/plots'
import { comparable } from '../app/plots/change'
import { legendGrid } from '../app/plots/encodings'
import { diagramHeight, flowsChanged, HEADER, headerHeight, MENU_ROOM, PANEL_LABEL, panelGrid, reservedHeight, sankeyChannels } from '../app/plots/sankey'
import { backward, caption, clamped, comparisons, fitRows, labelBox, labelLines, labelSides, layers, layOut, leastWidth, linkOpacity, linkTooltip, narrowed, near, nodeTooltip, overhang, placeLabels, ribbonPath, sankeyGraphs, turnedBack, walkOrder, type Box, type Emphasis, type Extent, type Flow, type Panel, type Placed } from '../app/plots/sankey_graph'
import { CATEGORICAL } from '../app/plots/theme'
import { EXTENT, flows, stage } from './sankey-flows'

/** The pixels per unit of value of a laid-out panel. */
const linkScale = (placed: Placed) => placed.graph.links[0]!.dy / placed.graph.links[0]!.value
/** A panel's flows as their ends, colour value and value. */
const ends = (panel: Panel) => panel.flows.map(flow => [flow.source, flow.target, flow.type, flow.value])
/** A flow from `source` to `target` of `value`, without a colour or a row. */
const flowOf = (source: string, target: string, value: number): Flow => ({ source, target, type: '', value, color: '', row: {} })
/** A panel of the flows `edges`, its nodes in the order they first appear. */
function panelOf(edges: [string, string, number][]): Panel {
  return { label: '', nodes: [...new Set(edges.flatMap(([source, target]) => [source, target]))], flows: edges.map(edge => flowOf(...edge)) }
}

/** A node with `incoming` flows in and `outgoing` flows out, as label sides read it. */
const nodeOf = (incoming: number, outgoing: number) => ({ incoming: Array.from({ length: incoming }), outgoing: Array.from({ length: outgoing }) }) as Pick<Placed['graph']['nodes'][number], 'incoming' | 'outgoing'>
/** The opacity of each link of a laid-out panel. */
const opacities = (placed: Placed, emphasis: Emphasis) => placed.graph.links.map(link => linkOpacity(link, placed.flows.get(link)!, placed.panel, emphasis, 'light'))
/** A link that turns from the direction `d0` into `d1` at x 100, 100 px down, 30 px wide, its ends of radius 20. */
const turn = (d0: string, d1: string) => ({ dy: 30, points: [{ x: 100, y: 50, d: d0, ro: 20 }, { x: 100, y: 150, d: d1, ri: 20 }] }) as unknown as Placed['graph']['links'][number]

/** A label's box, 50 by 10 px, at `x` and `y`. */
const labelAt = (x: number, y: number): Box => ({ x, y, width: 50, height: 10 })

describe('the Sankey diagram', () => {
  it('draws a link per row with a positive value, a node per value of either end', () => {
    const graphs = sankeyGraphs(flows())
    expect(graphs.panels.map(panel => panel.label)).toEqual([''])
    const [panel] = graphs.panels
    // Production is a source and a target, one node; the nodes in display order, sources first.
    expect(panel!.nodes).toEqual(['Production', 'Use', 'End of life', 'Recycling', 'Landfill'])
    expect(ends(panel!)).toEqual([
      ['Production', 'Use', 'Use', 10],
      ['Production', 'Use', 'Recycling', 2],
      ['Use', 'End of life', 'End of life', 8],
      ['End of life', 'Recycling', 'Recycling', 3],
      ['End of life', 'Landfill', 'End of life', 5],
      ['Recycling', 'Production', 'Recycling', 3],
    ])
    // The missing and the zero value draw nothing; the negative one is counted.
    expect([graphs.negative, graphs.loops, caption(graphs)]).toEqual([1, 0, 'Not drawn: 1 negative flow.'])
  })

  it('puts the flows of each split value into a panel of its own, in display order', () => {
    const plotArgs = flows({ splits: ['Time'] })
    const graphs = sankeyGraphs({ ...plotArgs, table: plotArgs.table.toReversed() })
    expect(graphs.panels.map(panel => [panel.label, panel.flows.length])).toEqual([['2050', 6], ['2100', 6]])
    expect(graphs.panels[1]!.flows.find(flow => flow.source === 'Recycling')!.value).toBe(30)
    expect(caption(graphs)).toBe('Not drawn: 2 negative flows.')
  })

  it('colours the links by the display order of the colour values, the same for every selection', () => {
    for (const theme of ['light', 'dark'] as const) {
      const graphs = sankeyGraphs(flows({ theme }))
      // No flow has the first stage, Production; Use keeps the second slot.
      expect(graphs.legend).toEqual(stage.values.map((label, i) => ({ label, color: CATEGORICAL[theme][i] })))
      expect(graphs.panels[0]!.flows.map(flow => flow.color)).toEqual([1, 3, 2, 3, 2, 3].map(i => CATEGORICAL[theme][i]))
    }
    const plain = sankeyGraphs(flows({ color: false }))
    expect([plain.legend, new Set(plain.panels[0]!.flows.map(flow => [flow.type, flow.color].join()))]).toEqual([[], new Set([`,${CATEGORICAL.light[0]}`])])
  })

  it('leaves out a flow from a node to itself, which the layout cannot place, and counts it', () => {
    // Import, a node without inflows but its own, and Landfill flow to themselves.
    const plotArgs = flows({ extra: [['Import', 'Use', 'Use', 1], ['Import', 'Import', 'Production', 4], ['Landfill', 'Landfill', 'End of life', 2]] })
    const graphs = sankeyGraphs(plotArgs)
    expect([graphs.loops, graphs.panels[0]!.flows.some(flow => flow.source === flow.target), caption(graphs)]).toEqual([2, false, 'Not drawn: 1 negative flow, 2 flows from a node to itself.'])
    const [placed] = layOut(graphs.panels, EXTENT, false)
    expect(placed!.graph.nodes.map(node => node.id)).toContain('Import')
    for (const node of placed!.graph.nodes) expect([node.x0, node.x1, node.y0, node.y1].every(Number.isFinite)).toBe(true)
  })

  it('counts a value within a billionth of its panel\'s largest as 0, which is noise', () => {
    const graphs = sankeyGraphs(flows({ extra: [['Recycling', 'Use', 'Recycling', -1e-11], ['Use', 'Import', 'Use', 1e-12]] }))
    expect([graphs.negative, graphs.panels[0]!.flows.length, caption(graphs)]).toEqual([1, 6, 'Not drawn: 1 negative flow.'])
  })

  it('says when no flow of the selection can be drawn', () => {
    const plotArgs = flows()
    const negative = sankeyGraphs({ ...plotArgs, table: plotArgs.table.map(row => ({ ...row, value: row.value === null ? null : -1 })) })
    expect([negative.panels[0]!.flows, caption(negative)]).toEqual([[], 'No flow of this selection can be drawn: 8 negative flows.'])
    const missing = sankeyGraphs({ ...plotArgs, table: plotArgs.table.map(row => ({ ...row, value: null })) })
    expect(caption(missing)).toBe('No flow of this selection can be drawn, none has a positive value.')
  })

  it('needs a source, a target and a value', () => {
    expect(() => sankeyChannels({ ...flows(), mapping: { source: 'From', value: 'value' } })).toThrow('the plot maps no source, target or value')
    expect(() => sankeyChannels({ ...flows(), mapping: { source: 'From', target: 'Destination', value: 'value' } })).toThrow('the table has no dimension Destination')
  })

  it('lays out a graph with a loop in node, each link on its flow, the loop turned back', () => {
    const [placed] = layOut(sankeyGraphs(flows()).panels, EXTENT, true)
    for (const node of placed!.graph.nodes) {
      expect([node.x0 >= 24, node.x1 <= 576, node.y0 >= 12, node.y1 <= 468]).toEqual([true, true, true, true])
    }
    // Each link draws its flow: between its ends, of its colour value and its value.
    for (const link of placed!.graph.links) {
      const flow = placed!.flows.get(link)!
      expect([link.source.id, link.target.id, link.type ?? '', link.value]).toEqual([flow.source, flow.target, flow.type, flow.value])
    }
    const link = (source: string, target: string) => placed!.graph.links.find(l => l.source.id === source && l.target.id === target)!
    expect([backward(link('Production', 'Use')), link('Production', 'Use').target.x0 > link('Production', 'Use').source.x1]).toEqual([false, true])
    expect(backward(link('Recycling', 'Production'))).toBe(true)
  })

  it('turns back the least flow of the walks from each node without inflows', () => {
    // Two sources: imports into the market, the larger, and fossil feedstock into the chemicals that
    // the carbon loop through the atmosphere also feeds.
    const panel = panelOf([
      ['Imports', 'Market', 50], ['Fossil', 'Chemicals', 40], ['Chemicals', 'Polymers', 41], ['Polymers', 'Market', 41], ['Market', 'Use', 91],
      ['Use', 'Emissions', 60], ['Use', 'Exports', 31], ['Emissions', 'Atmosphere', 60], ['Atmosphere', 'Biomass', 1], ['Biomass', 'Chemicals', 1],
    ])
    const bySize = panel.flows.toSorted((a, b) => b.value - a.value)
    const fossilFirst = ['Fossil', ...panel.nodes.filter(node => node !== 'Fossil')]
    expect([turnedBack(panel.nodes, bySize), turnedBack(fossilFirst, bySize)]).toEqual([41, 1])
    expect(walkOrder(panel).nodes[0]).toBe('Fossil')
    const [placed] = layOut([panel], EXTENT, false)
    // The walk from the fossil feedstock is laid out: the chain runs forward, the carbon loop back.
    expect(placed!.graph.links.filter(backward).map(l => `${l.source.id} → ${l.target.id}`)).toEqual(['Biomass → Chemicals'])
  })

  it('shares the scale of the links across panels, or gives each panel its own', () => {
    const years = sankeyGraphs(flows({ splits: ['Time'] })).panels
    const own = layOut(years, EXTENT, false)
    expect(linkScale(own[0]!)).toBeCloseTo(10 * linkScale(own[1]!))
    const shared = layOut(years, EXTENT, true)
    expect([linkScale(shared[0]!), linkScale(shared[1]!)].map(value => value / linkScale(own[1]!))).toEqual([expect.closeTo(1), expect.closeTo(1)])
    // A panel without a positive flow is not laid out.
    expect(layOut([{ label: 'none', nodes: [], flows: [] }, ...years], EXTENT, true).map(placed => placed.panel.label)).toEqual(['2050', '2100'])
  })

  it('sizes a diagram alone, in panels and compact, and its panels in a grid', () => {
    const plotArgs = flows()
    expect([diagramHeight(plotArgs), diagramHeight({ ...plotArgs, state: { splits: ['Time'], y: 'shared' } }), diagramHeight({ ...plotArgs, compact: true })]).toEqual([480, 320, 204])
    expect([panelGrid(2, 800), panelGrid(13, 1000), panelGrid(2, 400), panelGrid(1, 300), panelGrid(1, 0)]).toEqual([
      { columns: 2, panelWidth: 392 },
      { columns: 2, panelWidth: 492 },
      { columns: 1, panelWidth: 400 },
      { columns: 1, panelWidth: 300 },
      { columns: 1, panelWidth: 120 },
    ])
    expect([legendGrid(stage.values as string[], 800).columns, legendGrid(stage.values as string[], 200).columns]).toEqual([4, 1])
  })

  it('fits each row of panels to what its diagrams draw, at least a note\'s height', () => {
    // Two rows: diagrams drawn from 40 to 400 and 60 to 420, then a diagram and a panel without one.
    const { rows, height } = fitRows([[[40, 400], [60, 420]], [[100, 200], null]], 24, 24, 20)
    expect(rows).toEqual([{ top: 0, shift: 40 }, { top: 24 + 380 + 24, shift: 100 }])
    expect(height).toBe(24 + 380 + 24 + 24 + 100)
    expect(fitRows([[null, null]], 0, 24, 20)).toEqual({ rows: [{ top: 0, shift: 0 }], height: 20 })
  })

  it('tries a label beside its node first, on the side its flows leave, then above and below', () => {
    const rightFirst = ['right', 'left', 'above', 'below', 'above-right', 'below-right', 'above-left', 'below-left']
    expect([labelSides(nodeOf(0, 2)), labelSides(nodeOf(1, 1)), labelSides(nodeOf(2, 0))]).toEqual([
      rightFirst,
      rightFirst,
      ['left', 'right', 'above', 'below', 'above-left', 'below-left', 'above-right', 'below-right'],
    ])
    // Each label on its first side clear of its bars and the labels placed, at least the padding away.
    expect(placeLabels([
      { boxes: [labelAt(10, 0), null, labelAt(10, -20)], bars: [{ x: 61, y: 0, width: 5, height: 5 }] },
      { boxes: [labelAt(10, -20), labelAt(10, 20)], bars: [] },
    ])).toEqual([2, 1])
    expect(placeLabels([{ boxes: [labelAt(10, 0)], bars: [{ x: 64, y: 0, width: 5, height: 5 }] }])).toEqual([0])
    // A label that fits nowhere moves the one label in its way, when that one has another side.
    expect(placeLabels([
      { boxes: [labelAt(0, 0), labelAt(0, 40)], bars: [] },
      { boxes: [labelAt(20, 5)], bars: [] },
    ])).toEqual([1, 0])
    // It is left out when that label has no other side, or when two are in its way.
    expect(placeLabels([{ boxes: [labelAt(0, 0)], bars: [] }, { boxes: [labelAt(20, 5)], bars: [] }])).toEqual([0, null])
    expect(placeLabels([])).toEqual([])
    expect(placeLabels([
      { boxes: [labelAt(0, 0), labelAt(0, 40)], bars: [] },
      { boxes: [labelAt(60, 0), labelAt(60, 40)], bars: [] },
      { boxes: [labelAt(30, 5)], bars: [] },
    ])).toEqual([0, 0, null])
    // Labels keep more room beside each other than above and below.
    const label = { x: 0, y: 0, width: 10, height: 10 }
    expect([near(label, { x: 12, y: 0, width: 5, height: 5 }), near(label, { x: 14, y: 0, width: 5, height: 5 })]).toEqual([true, false])
    expect([near(label, { x: 0, y: 10.5, width: 5, height: 5 }), near(label, { x: 0, y: 12, width: 5, height: 5 })]).toEqual([true, false])
  })

  it('keeps a tooltip within the window, its start in view when it is wider', () => {
    expect([clamped(-150, 200, 390, 4), clamped(300, 200, 390, 4), clamped(50, 200, 390, 4), clamped(10, 500, 390, 4)]).toEqual([4, 186, 50, 4])
  })

  it('breaks a long node label at the space nearest its middle', () => {
    expect(['Use', 'Auxiliary Recycled Feedstock Trade', 'Feedstock supply (fossil)', 'Polymerisationsanlagenausgang'].map(name => labelLines(name))).toEqual([
      ['Use'],
      ['Auxiliary Recycled', 'Feedstock Trade'],
      ['Feedstock', 'supply (fossil)'],
      ['Polymerisationsanlagenausgang'],
    ])
    // In three lines, at the spaces nearest a third and two thirds of it.
    expect(['High Value Chemical Production', 'Feedstock supply (fossil)', 'Use Phase'].map(name => labelLines(name, 3))).toEqual([
      ['High Value', 'Chemical', 'Production'],
      ['Feedstock', 'supply', '(fossil)'],
      ['Use Phase'],
    ])
  })

  it('fades the links the legend leaves out or a hovered node is not on, and those turned back', () => {
    const [placed] = layOut(sankeyGraphs(flows()).panels, EXTENT, true)
    const { panel, graph, flows: drawn } = placed!
    const none: Emphasis = { focus: null, link: null, node: null }
    const opacity = (link: (typeof graph.links)[number], emphasis: Emphasis) => linkOpacity(link, drawn.get(link)!, panel, emphasis, 'light')
    const back = graph.links.find(backward)!
    const forward = graph.links.find(link => !backward(link) && drawn.get(link)!.type === 'Use')!
    const other = graph.links.find(link => !backward(link) && drawn.get(link)!.type !== 'Use')!
    // Faded below a link turned back, which lies below the others, below a hovered one.
    const [faded, behind, plain, hovered] = [opacity(other, { ...none, focus: 'Use' }), opacity(back, none), opacity(forward, none), opacity(forward, { ...none, link: forward })]
    expect([faded < behind, behind < plain, plain < hovered]).toEqual([true, true, true])
    expect(opacity(forward, { ...none, focus: 'Use' })).toBe(plain)
    const use = graph.nodes.find(node => node.id === 'Use')!
    const onUse = graph.links.filter(link => opacity(link, { ...none, node: { node: use, panel } }) === hovered)
    expect(onUse).toHaveLength(use.incoming.length + use.outgoing.length)
  })

  it('fades for a hovered node the links of its panel alone, for the legend those of every panel', () => {
    const [first, second] = layOut(sankeyGraphs(flows({ splits: ['Time'] })).panels, EXTENT, true)
    const none: Emphasis = { focus: null, link: null, node: null }
    const use = { node: first!.graph.nodes.find(node => node.id === 'Use')!, panel: first!.panel }
    expect(opacities(second!, { ...none, node: use })).toEqual(opacities(second!, none))
    expect(opacities(first!, { ...none, node: use })).not.toEqual(opacities(first!, none))
    expect(opacities(second!, { ...none, focus: 'Use' })).not.toEqual(opacities(second!, none))
  })

  it('gives how far the loops turned back reach past the box, and keeps them within it', () => {
    // A turn from rightwards into leftwards reaches out right, and the other way round left.
    expect(overhang([turn('r', 'l')], [[0, 0], [120, 400]])).toEqual([0, 100 + 20 + 15 - 120])
    expect(overhang([turn('l', 'r')], [[90, 0], [400, 400]])).toEqual([90 - (100 - 20 - 15), 0])
    expect(overhang([turn('r', 'r')], [[90, 0], [99, 400]])).toEqual([0, 0])
    expect(overhang([], [[90, 0], [99, 400]])).toEqual([0, 0])
    // A recycling loop of three tenths, alone and in two panels.
    const loop = panelOf([['Production', 'Use', 10], ['Use', 'End of life', 10], ['End of life', 'Recycling', 3], ['End of life', 'Landfill', 7], ['Recycling', 'Production', 3]])
    const box: Extent = [[4, 12], [896, 468]]
    for (const shared of [false, true]) {
      for (const placed of layOut(shared ? [loop, { ...loop, label: 'again' }] : [loop], box, shared)) {
        expect(placed.graph.links.some(backward)).toBe(true)
        expect(overhang(placed.graph.links, box).map(reach => reach <= 0.5)).toEqual([true, true])
      }
    }
  })

  it('narrows a box for loops by at most half its width, and as often as they still reach past it', () => {
    const box: Extent = [[0, 0], [100, 100]]
    expect(narrowed(box, [10, 20])).toEqual([[10, 0], [80, 100]])
    expect(narrowed(box, [80, 40])).toEqual([[80 * 50 / 120, 0], [100 - 40 * 50 / 120, 100]])
    // A loop between two nodes in a 112 px box: its forward links stay forward, not mirrored.
    const [small] = layOut([panelOf([['N1', 'N4', 29], ['N4', 'N1', 43], ['N3', 'N2', 26]])], [[4, 12], [116, 316]], false)
    for (const forward of small!.graph.links.filter(link => !backward(link))) expect(forward.source.x1).toBeLessThanOrEqual(forward.target.x0)
    // Loops in a 352 px box, which one narrowing does not fit, fit after more.
    const repro: Extent = [[4, 12], [356, 316]]
    const [fitted] = layOut([panelOf([['N0', 'N3', 7], ['N3', 'N1', 3], ['N2', 'N4', 2], ['N4', 'N3', 49], ['N1', 'N2', 39]])], repro, false)
    expect(overhang(fitted!.graph.links, repro).map(reach => reach <= 0.5)).toEqual([true, true])
  })

  it('draws a link that runs rightwards as a band between level curves, at least 2 px wide', () => {
    expect(ribbonPath([{ x: 0, y: 10 }, { x: 100, y: 90 }], 20)).toBe('M0,0 C50,0 50,80 100,80 L100,100 C50,100 50,20 0,20 Z')
    // Through a point between its ends, both edges pass it level.
    expect(ribbonPath([{ x: 0, y: 10 }, { x: 50, y: 10 }, { x: 100, y: 30 }], 1)).toBe('M0,9 C25,9 25,9 50,9 C75,9 75,29 100,29 L100,31 C75,31 75,11 50,11 C25,11 25,11 0,11 Z')
    expect(ribbonPath([], 5)).toBe('')
  })

  it('counts the layers the layout puts the nodes in, which set the least width of a chart', () => {
    const fossil = panelOf([
      ['Imports', 'Market', 50], ['Fossil', 'Chemicals', 40], ['Chemicals', 'Polymers', 41], ['Polymers', 'Market', 41], ['Market', 'Use', 91],
      ['Use', 'Emissions', 60], ['Use', 'Exports', 31], ['Emissions', 'Atmosphere', 60], ['Atmosphere', 'Biomass', 1], ['Biomass', 'Chemicals', 1],
    ])
    const two = panelOf([['A', 'B', 1], ['A', 'C', 2]])
    for (const panel of [...sankeyGraphs(flows({ splits: ['Time'] })).panels, fossil, two]) {
      const [placed] = layOut([panel], EXTENT, false)
      expect(layers(panel)).toBe(Math.max(...placed!.graph.nodes.map(node => node.rank)) + 1)
    }
    expect([layers(two), layers(fossil)]).toEqual([2, 8])
    // In proportion to the layers of the widest graph of the chart.
    expect(leastWidth([two, fossil, { label: 'none', nodes: [], flows: [] }])).toBe(4 * leastWidth([two]))
    expect(leastWidth([])).toBe(0)
  })

  it('works out a label\'s box on each side of its bar from its lines\' length and the text\'s reach', () => {
    const node = { x0: 100, x1: 104, y0: 50, y1: 150 }
    const metrics = { size: 10, ascent: 8, descent: 2 }
    const box = (side: Parameters<typeof labelBox>[0], lines = 1, width = 500) => {
      const place = labelBox(side, node, lines, 40, 4, width, metrics)
      return place && [place.anchor, place.x, ...[place.box.x, place.box.y, place.box.width, place.box.height].map(n => Math.round(n * 100) / 100)]
    }
    expect(box('right')).toEqual(['start', 108, 108, 95.5, 40, 10])
    expect(box('left')).toEqual(['end', 96, 56, 95.5, 40, 10])
    // Two lines above, ending 4 px over the bar; one below, starting 4 px under it.
    expect(box('above', 2)).toEqual(['middle', 102, 82, 24.5, 40, 21])
    expect(box('below')).toEqual(['middle', 102, 82, 154, 40, 10])
    expect([box('below-right'), box('below-left')]).toEqual([['start', 100, 100, 154, 40, 10], ['end', 104, 64, 154, 40, 10]])
    // Out of a panel too narrow for it.
    expect([box('right', 1, 120), box('left', 1, 120), box('above', 1, 30)]).toEqual([null, ['end', 96, 56, 95.5, 40, 10], null])
  })

  it('sizes the header and the room it holds for the chart while it loads', () => {
    const labels = stage.values as string[]
    expect(headerHeight(labels, true, 800)).toBe(HEADER.legendTop + HEADER.legendBottom + HEADER.unitLine + HEADER.gap)
    expect(headerHeight(labels, false, 200)).toBe(HEADER.legendTop + 3 * HEADER.legendRow + HEADER.legendBottom + HEADER.gap)
    expect([headerHeight([], false, 800), headerHeight([], true, 800)]).toEqual([0, HEADER.unitLine + HEADER.gap])
    const plotArgs = flows()
    expect(reservedHeight({ ...plotArgs, compact: true }, 300)).toBe(diagramHeight({ ...plotArgs, compact: true }))
    const diagram = reservedHeight(plotArgs, 800) - MENU_ROOM - headerHeight(labels, true, 800)
    expect([diagram > diagramHeight(plotArgs) / 2, diagram < diagramHeight(plotArgs)]).toEqual([true, true])
    // Two panels side by side, or one under the other on a narrow page.
    const split = flows({ splits: ['Time'] })
    const header = (width: number) => MENU_ROOM + headerHeight(labels, true, width)
    const [wide, narrow] = [reservedHeight(split, 800) - header(800), reservedHeight(split, 380) - header(380)]
    expect([wide > PANEL_LABEL, narrow > 2 * wide]).toEqual([true, true])
  })

  it('measures the noise against the largest finite positive value, and counts infinite values', () => {
    const graphs = sankeyGraphs(flows({ extra: [['Recycling', 'Use', 'Recycling', -1e12], ['Use', 'Import', 'Use', Infinity]] }))
    expect([graphs.negative, graphs.infinite, graphs.panels[0]!.flows.length, caption(graphs)]).toEqual([2, 1, 6, 'Not drawn: 2 negative flows, 1 infinite flow.'])
  })

  it('names a link\'s ends, colour and value in its tooltip, and against a baseline its change', () => {
    const plotArgs = flows({ baseline: (value, row) => (row.From === 'Production' && row.Stage === 'Use' ? 7 : value) })
    const ch = sankeyChannels(plotArgs)
    const [production] = sankeyGraphs(plotArgs).panels[0]!.flows
    expect(linkTooltip(production!, ch, 't', null)).toEqual({ 'From → To': 'Production → Use', 'Stage': 'Use', 't': '10' })
    const compared = comparisons(plotArgs)!
    expect(linkTooltip(production!, ch, 't', compared.get(production!.row)!)).toEqual({ 'From → To': 'Production → Use', 'Stage': 'Use', 't': '10', 'baseline': '7', 'change': '+3 (+42.9%)' })
    // A flow the baseline lacks is compared with 0, without a relative change; the baseline's rows
    // may come in any order.
    const lacking = { ...plotArgs, baseline: plotArgs.baseline!.filter(row => row.From !== 'End of life' || row.To !== 'Landfill').toReversed() }
    const landfill = sankeyGraphs(lacking).panels[0]!.flows.find(flow => flow.target === 'Landfill')!
    expect(linkTooltip(landfill, ch, null, comparisons(lacking)!.get(landfill.row)!)).toMatchObject({ value: '5', baseline: '–', change: '+5' })
    expect(linkTooltip(production!, ch, 't', comparisons(lacking)!.get(production!.row)!)).toMatchObject({ baseline: '7', change: '+3 (+42.9%)' })
    expect([comparisons(flows()), comparisons({ ...plotArgs, baseline: [] })]).toEqual([null, null])
  })

  it('gives a node\'s totals in and out in its tooltip', () => {
    const drawn = sankeyGraphs(flows()).panels[0]!.flows
    expect(nodeTooltip('Production', drawn, 't')).toEqual({ title: 'Production', in: '3', out: '12', unit: 't' })
    expect(nodeTooltip('Landfill', drawn, null)).toEqual({ title: 'Landfill', in: '5', out: '–' })
  })

  it('does not draw the baseline behind, unlike the other built-ins', () => {
    expect(Object.keys(PLOT_TYPES).filter(drawsBaseline)).toEqual(['line', 'stacked_area', 'bar', 'stacked_bar'])
    expect(drawsBaseline('chord')).toBe(true)
  })

  it('knows whether a flow of the selection changed, from the measure on value', () => {
    // Rows to compare, but no change: the change bars would draw nothing.
    const plotArgs = flows({ baseline: value => value })
    expect([comparable(plotArgs), flowsChanged(plotArgs), nothingToCompare('sankey', plotArgs)]).toEqual([true, false, true])
    const changed = flows({ baseline: value => (value === null ? null : value + 1) })
    expect([flowsChanged(changed), nothingToCompare('sankey', changed), nothingToCompare('sankey', { ...changed, baseline: [] })]).toEqual([true, false, false])
  })
})
