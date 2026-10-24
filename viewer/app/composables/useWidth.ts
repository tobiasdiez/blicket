/**
 * The width of the element `el` holds, kept up to date while it changes size; `null` without an
 * element.
 */
export function useWidth(el: Readonly<Ref<HTMLElement | null>>) {
  const width = ref<number | null>(null)
  const observer = new ResizeObserver(() => {
    width.value = el.value?.clientWidth ?? null
  })
  watch(el, (current, old) => {
    if (old) observer.unobserve(old)
    if (current) observer.observe(current)
    width.value = current?.clientWidth ?? null
  }, { immediate: true })
  onBeforeUnmount(() => observer.disconnect())
  return width
}
