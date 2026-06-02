import { defineConfig } from 'tsup'

/**
 * Build config — emits ESM + CJS + .d.ts for the package entrypoints.
 *
 * Externalized: all peer dependencies. The consumer brings React, MUI,
 * and emotion; we don't bundle them.
 */
export default defineConfig({
  entry: {
    index: 'src/index.ts',
    theme: 'src/theme/index.ts',
    tokens: 'src/theme/tokens.ts',
    provider: 'src/providers/MindtraceProvider.tsx',
  },
  format: ['esm', 'cjs'],
  dts: true,
  splitting: false,
  sourcemap: true,
  clean: true,
  treeshake: true,
  external: [
    'react',
    'react-dom',
    'react/jsx-runtime',
    '@mui/material',
    '@mui/material/styles',
    '@mui/icons-material',
    '@emotion/react',
    '@emotion/styled',
  ],
  esbuildOptions(opts) {
    opts.jsx = 'automatic'
  },
})
