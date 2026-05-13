import CssBaseline from '@mui/material/CssBaseline'
import { ThemeProvider } from '@mui/material/styles'
import type { Preview } from '@storybook/react'
import { withThemeFromJSXProvider } from '@storybook/addon-themes'

import { defaultThemeKey, themes } from './themes'

const preview: Preview = {
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
