import { addons } from '@storybook/manager-api'
import { create } from '@storybook/theming'

/**
 * Storybook manager theme — sidebar / toolbar chrome only. Kept neutral
 * (Storybook's default light) so the canvas toggle drives the story
 * preview without flipping the surrounding app. Brand wordmark only.
 */
const mindtraceTheme = create({
  base: 'light',
  brandTitle: 'Mindtrace UI',
  brandUrl: 'https://github.com/Mindtrace',
  brandTarget: '_blank',
  colorPrimary: '#7C3AED',
  colorSecondary: '#7C3AED',
})

addons.setConfig({
  theme: mindtraceTheme,
  sidebar: { showRoots: true },
})
