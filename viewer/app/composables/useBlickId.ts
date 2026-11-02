/** The id of the Blick whose page the route shows, from its path; empty on any other page. */
export function useBlickId() {
  const route = useRoute()
  return computed(() => {
    const segments = route.params.id
    return Array.isArray(segments) ? segments.join('/') : String(segments ?? '')
  })
}
