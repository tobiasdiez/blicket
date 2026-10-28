import { TAB } from '~/lib/controls'

/** The tab shown, chart or data (`ChartTabs`), kept in the URL so a link can open the data. */
export function useTab() {
  const route = useRoute()
  const router = useRouter()
  return computed({
    get: () => (route.query[TAB] === 'data' ? 'data' : 'chart'),
    set: (value: string | number) => void router.replace({ query: { ...route.query, [TAB]: value === 'data' ? 'data' : undefined } }),
  })
}
