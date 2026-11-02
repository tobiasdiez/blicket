// SVG built by hand and its export, for a chart that vega-embed does not draw: the elements, a
// background in the surface colour, and an export menu in the look of vega-embed's that saves the
// chart's SVG parts, one under the other, as SVG or as PNG at twice the size.
import { FONT } from './theme'

const SVG = 'http://www.w3.org/2000/svg'
// The attribute that marks an SVG's background, which the image of several leaves out but one.
const BACKGROUND = 'data-background'

/** An SVG element with `attributes`. */
export function svgElement<K extends keyof SVGElementTagNameMap>(tag: K, attributes: Record<string, string | number> = {}): SVGElementTagNameMap[K] {
  const element = document.createElementNS(SVG, tag)
  for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, String(value))
  return element
}

/** An SVG text element holding `content`. */
export function svgText(content: string, attributes: Record<string, string | number>): SVGTextElement {
  const text = svgElement('text', attributes)
  text.textContent = content
  return text
}

/** The background of an SVG in the surface colour, which an exported image keeps. */
export function background(surface: string): SVGRectElement {
  return svgElement('rect', { 'width': '100%', 'height': '100%', 'fill': surface, [BACKGROUND]: '' })
}

/** The SVG parts, one under the other on one background in the surface colour, as one SVG file's text. */
function composed(parts: SVGSVGElement[], surface: string): { text: string, width: number, height: number } {
  const width = Math.max(...parts.map(part => part.width.baseVal.value))
  const svg = svgElement('svg', { 'xmlns': SVG, width, 'font-family': FONT })
  svg.append(background(surface))
  let height = 0
  for (const part of parts) {
    const group = svgElement('g', { transform: `translate(0,${height})` })
    for (const child of part.children) {
      if (!child.hasAttribute(BACKGROUND)) group.append(child.cloneNode(true))
    }
    svg.append(group)
    height += part.height.baseVal.value
  }
  svg.setAttribute('height', String(height))
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`)
  return { text: new XMLSerializer().serializeToString(svg), width, height }
}

/** An image of `text`, an SVG `width` by `height`, drawn on a canvas twice its size, as a PNG data URL. */
async function pngUrl({ text, width, height }: { text: string, width: number, height: number }): Promise<string> {
  const url = URL.createObjectURL(new Blob([text], { type: 'image/svg+xml' }))
  try {
    const image = new Image()
    image.src = url
    await image.decode()
    const canvas = document.createElement('canvas')
    canvas.width = width * 2
    canvas.height = height * 2
    const context = canvas.getContext('2d')!
    context.scale(2, 2)
    context.drawImage(image, 0, 0)
    return canvas.toDataURL('image/png')
  }
  finally {
    URL.revokeObjectURL(url)
  }
}

/** Save the data URL `url` as the file `name`. */
function save(url: string, name: string): void {
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = name
  anchor.click()
}

// The icon of vega-embed's export menu, which the other charts have.
const CIRCLES = '<svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor" aria-hidden="true"><circle r="2" cy="8" cx="2"></circle><circle r="2" cy="8" cx="8"></circle><circle r="2" cy="8" cx="14"></circle></svg>'

/**
 * The export menu at the top right of `box`, as vega-embed draws the other charts': the SVG of
 * `parts`, one under the other on the `surface` colour, and a PNG at twice the size, named `name`.
 * A click elsewhere and Escape close it; after a choice, the keyboard is back on its button. Its
 * listeners go with `signal`.
 */
export function exportMenu(box: HTMLElement, parts: SVGSVGElement[], surface: string, name: string, signal: AbortSignal): void {
  const details = document.createElement('details')
  details.title = 'Click to view actions'
  const summary = document.createElement('summary')
  summary.className = 'absolute top-0 right-0 z-10 cursor-pointer list-none rounded-full border border-accented bg-default p-1.5 leading-none text-muted [&::-webkit-details-marker]:hidden'
  summary.setAttribute('aria-label', `Export ${name}`)
  summary.innerHTML = CIRCLES
  const actions = document.createElement('div')
  actions.className = 'absolute top-[35px] -right-2 z-20 flex flex-col rounded border border-accented bg-default py-2 shadow-md'
  const close = () => {
    details.open = false
    summary.focus()
  }
  const formats = [
    ['SVG', async () => `data:image/svg+xml;charset=utf-8,${encodeURIComponent(composed(parts, surface).text)}`],
    ['PNG', () => pngUrl(composed(parts, surface))],
  ] as const
  for (const [format, url] of formats) {
    const link = document.createElement('a')
    link.href = '#'
    link.textContent = `Save as ${format}`
    link.className = 'px-4 py-2 text-sm font-semibold whitespace-nowrap text-default hover:bg-elevated focus:bg-elevated focus:outline-none'
    link.addEventListener('click', async (event) => {
      event.preventDefault()
      close()
      try {
        save(await url(), `${name}.${format.toLowerCase()}`)
      }
      catch (error) {
        console.error(`blicket: the ${format} of ${name} cannot be made`, error)
      }
    }, { signal })
    actions.append(link)
  }
  details.append(summary, actions)
  box.prepend(details)
  details.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && details.open) close()
  }, { signal })
  // In the capture phase: the chart's marks may stop the propagation of their clicks.
  document.addEventListener('click', (event) => {
    if (!details.contains(event.target as Node)) details.open = false
  }, { capture: true, signal })
}
