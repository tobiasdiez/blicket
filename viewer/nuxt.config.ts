// The viewer is a static site that reads one build directory through relative paths: no server
// rendering, hash routing, and a relative base URL, so that it works from any sub-path. The dev
// server forwards the build's files to `blicket serve`.
const serve = process.env.BLICKET_SERVE ?? 'http://127.0.0.1:8765'

// Relative asset paths in a generated site; the dev server serves from the root. Setting
// app.baseURL to './' instead still generates '/_nuxt/' paths and baseURL "/" in index.html (Nuxt
// 4.6): the prerendered page takes the base URL from this variable.
if (process.env.NODE_ENV !== 'development') process.env.NUXT_APP_BASE_URL ??= './'

// Browsers run no module scripts in a page opened from a file, so this classic script says what
// to do instead of leaving the page blank.
const fromFile = `if (location.protocol === 'file:') addEventListener('DOMContentLoaded', function () {
  var text = document.createElement('p');
  text.textContent = 'Browsers do not let a page opened from a file read the files next to it. '
    + 'Serve this folder instead: blicket serve <this folder>, or python -m http.server inside it, '
    + 'and open the address it prints.';
  text.style.cssText = 'font: 16px/1.5 system-ui, sans-serif; margin: 2rem; max-width: 40rem';
  document.body.replaceChildren(text);
});`

export default defineNuxtConfig({
  modules: ['@nuxt/ui'],
  css: ['~/assets/css/main.css'],
  ssr: false,
  router: { options: { hashMode: true } },
  app: {
    head: {
      title: 'blicket',
      htmlAttrs: { lang: 'en' },
      link: [{ rel: 'icon', type: 'image/svg+xml', href: './favicon.svg' }],
      script: [{ innerHTML: fromFile }],
    },
  },
  // Offline: icons bundled from @iconify-json/lucide, never fetched; system fonts only.
  icon: {
    provider: 'none',
    fallbackToApi: false,
    clientBundle: { scan: true },
  },
  ui: { fonts: false },
  // No app manifest: a static site has no route rules to fetch from _nuxt/builds.
  experimental: { appManifest: false },
  nitro: {
    devProxy: {
      '/manifest.json': { target: `${serve}/manifest.json` },
      '/blicks': { target: `${serve}/blicks` },
      '/compare': { target: `${serve}/compare` },
    },
    hooks: {
      // Copies of index.html for servers that route every path to a page; hash routing needs
      // neither.
      'prerender:generate'(route) {
        if (route.route === '/200.html' || route.route === '/404.html') route.skip = true
      },
    },
  },
  // oxlint does not report unused variables in .vue files; nuxt typecheck does with this.
  typescript: { tsConfig: { compilerOptions: { noUnusedLocals: true } } },
  devtools: { enabled: false },
  telemetry: false,
  compatibilityDate: '2026-10-01',
})
