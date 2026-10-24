import { defineConfig } from 'vitest/config'

// The tests cover app/lib and app/plots, which import no Nuxt auto-imports, so plain vitest runs
// them without Nuxt's test utilities.
export default defineConfig({
  test: {
    include: ['tests/**/*.test.ts'],
    environment: 'node',
  },
})
