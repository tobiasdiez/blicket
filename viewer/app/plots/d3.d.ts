// What the Sankey diagram uses of d3-sankey-diagram 0.9.4 and of d3-selection 1, which draws it;
// neither package ships declarations.

declare module 'd3-sankey-diagram' {
  /** A node as the layout reads it. */
  export interface NodeInput {
    id: string
  }

  /** A link as the layout reads it: its ends by node id, its type and its value. */
  export interface LinkInput {
    source: string
    target: string
    type?: string
    value: number
  }

  /** A node after the layout: its layer, its box, the larger of its totals in and out, and its links. */
  export interface LayoutNode extends NodeInput {
    rank: number
    x0: number
    x1: number
    y0: number
    y1: number
    value: number
    incoming: LayoutLink[]
    outgoing: LayoutLink[]
  }

  /**
   * A link after the layout: its ends, its width and the points its path runs through, each with
   * the direction the path takes there, `r` rightwards or `l` leftwards, and the radius of its
   * curve into the point and out of it.
   */
  export interface LayoutLink {
    source: LayoutNode
    target: LayoutNode
    type?: string
    value: number
    dy: number
    points: { x: number, y: number, d?: string, ri?: number, ro?: number }[]
  }

  /** The input graph, its objects completed in place. */
  export interface Graph {
    nodes: LayoutNode[]
    links: LayoutLink[]
  }

  export interface Layout {
    (graph: { nodes: NodeInput[], links: LinkInput[] }): Graph
    extent(extent: [[number, number], [number, number]]): Layout
    nodeWidth(width: number): Layout
    /** Pixels per unit of value; `null` fits the graph into the extent on the next call. */
    scale(): number | null
    scale(scale: number | null): Layout
  }

  export function sankey(): Layout

  /** Draws a laid-out graph, the datum of a selection, into its element. */
  export interface Diagram {
    (selection: unknown): void
    linkColor(color: (link: LayoutLink) => string | null): Diagram
    linkTitle(title: (link: LayoutLink) => string): Diagram
    /** The stacking order of links: those between two nodes go together, the least important first. */
    linkImportance(importance: (link: LayoutLink) => number): Diagram
    nodeTitle(title: (node: LayoutNode) => string): Diagram
  }

  export function sankeyDiagram(): Diagram
}

declare module 'd3-selection' {
  export interface Selection<Datum> {
    datum<T>(value: T): Selection<T>
    call(callback: (selection: Selection<Datum>) => void): Selection<Datum>
    selectAll<T>(selector: string): Selection<T>
    each(callback: (this: SVGElement, datum: Datum) => void): Selection<Datum>
  }

  export function select(node: Element): Selection<unknown>
}
