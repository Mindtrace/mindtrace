import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    css: false,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      exclude: [
        'node_modules/**',
        'dist/**',
        'storybook-static/**',
        '.storybook/**',
        '**/*.stories.tsx',
        '**/*.stories.ts',
        'vitest.*',
        'tsup.config.ts',
        'src/index.ts',
        'src/**/index.ts',
      ],
    },
  },
})
