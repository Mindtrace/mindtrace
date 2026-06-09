import type { StorybookConfig } from '@storybook/react-vite'

/**
 * Storybook config — picks up stories co-located in
 * `src/components/<Name>/<Name>.stories.tsx` and foundation stories in
 * `src/stories/*.stories.@(ts|tsx)`.
 */
const config: StorybookConfig = {
  stories: ['../src/**/*.mdx', '../src/**/*.stories.@(ts|tsx)'],
  addons: [
    '@storybook/addon-essentials',
    '@storybook/addon-a11y',
    '@storybook/addon-themes',
    '@storybook/addon-interactions',
  ],
  framework: { name: '@storybook/react-vite', options: {} },
  docs: { autodocs: 'tag' },
  typescript: {
    reactDocgen: 'react-docgen-typescript',
    reactDocgenTypescriptOptions: {
      shouldExtractLiteralValuesFromEnum: true,
      shouldRemoveUndefinedFromOptional: true,
      // Skip props inherited from node_modules (MUI, React) so the controls
      // panel shows only props this component actually defines + whatever
      // the story author has explicitly added via `argTypes`. Without this
      // filter MUI wrappers like Button or TextField produce hundreds of
      // inherited controls and drown out the relevant ones.
      propFilter: (prop) => {
        if (prop.parent) {
          return !/node_modules/.test(prop.parent.fileName)
        }
        return true
      },
    },
  },
}

export default config
