/** The id the route's path names on the page of a unit of `kind`, `blick` or `check`; empty on any other page. */
function unitId(kind: 'blick' | 'check') {
  const route = useRoute()
  return computed(() => {
    if (!route.path.startsWith(`/${kind}/`)) return ''
    const segments = route.params.id
    return Array.isArray(segments) ? segments.join('/') : String(segments ?? '')
  })
}

/** The id of the Blick whose page the route shows, from its path; empty on any other page. */
export function useBlickId() {
  return unitId('blick')
}

/** The id of the check whose page the route shows, from its path; empty on any other page. */
export function useCheckId() {
  return unitId('check')
}
