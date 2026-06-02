import CssBaseline from '@mui/material/CssBaseline'
import { ThemeProvider } from '@mui/material/styles'
import type { Preview } from '@storybook/react'
import { withThemeFromJSXProvider } from '@storybook/addon-themes'

import { defaultThemeKey, themes } from './themes'

const preview: Preview = {
  // Run the a11y (axe-core) addon on demand rather than automatically. By
  // default addon-a11y runs a full axe pass on *every* story render — which
  // means once per story, again per preview on a Docs/autodocs page (so the
  // composite "Patterns/PageLayout" docs page ran several heavy passes and
  // could lock the tab), and again on every navigation and every controls
  // change (the "navigation feels slow / delayed updates" symptom). With
  // `manual: true` the panel still works — reviewers click "Run test" — but
  // nothing runs axe unprompted. Flip back to `false` to restore auto-runs.
  initialGlobals: { a11y: { manual: true } },
  parameters: {
    layout: 'padded',
    controls: {
      matchers: { color: /(background|color)$/i, date: /Date$/i },
      expanded: true,
    },
    backgrounds: { disable: true },
    options: {
      storySort: {
        order: [
          'Introduction',
          'Foundations',
          ['Theme Builder', 'Palette', 'Typography', 'Shape', 'Shadows', 'Stack & Grid'],
          'Components',
          'Layout',
          'Patterns',
        ],
      },
    },
  },
  decorators: [
    withThemeFromJSXProvider({
      themes,
      defaultTheme: defaultThemeKey,
      Provider: ThemeProvider,
      GlobalStyles: CssBaseline,
    }),
  ],
}

export default preview
