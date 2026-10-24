import embed from 'vega-embed'
import * as vega from 'vega'
import type { TopLevelSpec } from 'vega-lite'
import type { PlotArgs, PlotType } from './types'

/**
 * A plot type whose browser half is the Vega-Lite specification `build` makes for a chart of a
 * given width: drawn as SVG, with Vega-Lite's tooltips and PNG and SVG export at twice the size.
 */
export function definePlot(build: (args: PlotArgs, width: number) => TopLevelSpec): PlotType {
  return {
    async render({ el, ...args }) {
      const result = await embed(el, build(args, el.clientWidth), {
        renderer: 'svg',
        actions: { export: { png: true, svg: true }, source: false, compiled: false, editor: false },
        scaleFactor: 2,
        downloadFileName: args.name,
        tooltip: { theme: args.theme },
        // Errors only: the hover layers of line charts start without data, which Vega warns about.
        logLevel: vega.Error,
      })
      el.querySelector('.vega-embed summary')?.setAttribute('aria-label', 'Export')
      return () => result.finalize()
    },
  }
}
