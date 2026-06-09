/**
 * Design tokens — the source of truth for color, spacing, radius, type.
 *
 * Three-layer color system:
 *   Layer 1: Accent ramps (purple, teal, blue) — the *default* palette
 *   Layer 2: Product foundation (neutrals, surfaces) — 90% of daily UI
 *   Layer 3: Semantic — success/warning/error/info
 *
 * These are defaults, not a fixed identity. The purple accent is wired in
 * as `palette.primary` only so the library has a sensible out-of-the-box
 * look; consumers re-theme by passing their own `primary` (and friends) to
 * `createTheme` / `MindtraceProvider`. Everything that signals "active /
 * selected / focused" derives from `palette.primary` at render time, so
 * turning the primary knob recolors the whole UI — see `theme/components.ts`
 * and `theme/palette.ts`.
 *
 * Usage rules (for the defaults):
 *   Accent (primary) → primary action, active selection, focus
 *   Teal   → data signals, analysis accents
 *   Blue   → secondary emphasis, links, informational
 *   Neutrals → surfaces, text, borders, panels, dense operational areas
 */

// ─── Layer 1: Accent ramps (default palette) ─────────────────────────────

export const brand = {
  purple: {
    50: '#F5F3FF',
    100: '#EDE9FE',
    200: '#DDD6FE',
    300: '#C4B5FD',
    400: '#A78BFA',
    500: '#8B5CF6',
    600: '#7C3AED',
    700: '#6D28D9',
    800: '#5B21B6',
    900: '#4C1D95',
  },
  teal: {
    50: '#F0FDFA',
    100: '#CCFBF1',
    200: '#99F6E4',
    300: '#5EEAD4',
    400: '#2DD4BF',
    500: '#14B8A6',
    600: '#0D9488',
    700: '#0F766E',
  },
  blue: {
    50: '#EFF6FF',
    100: '#DBEAFE',
    200: '#BFDBFE',
    300: '#93C5FD',
    400: '#60A5FA',
    500: '#3B82F6',
    600: '#2563EB',
    700: '#1D4ED8',
  },
} as const

// ─── Layer 2: Product Foundation ─────────────────────────────────────────

export const neutral = {
  50: '#FAFAFA',
  100: '#F4F4F5',
  200: '#E4E4E7',
  300: '#D4D4D8',
  400: '#A1A1AA',
  500: '#71717A',
  600: '#52525B',
  700: '#3F3F46',
  800: '#27272A',
  900: '#18181B',
  950: '#09090B',
} as const

// ─── Layer 3: Semantic ───────────────────────────────────────────────────

export const semantic = {
  success: { main: '#16A34A', light: '#22C55E', dark: '#15803D', muted: '#166534' },
  warning: { main: '#D97706', light: '#F59E0B', dark: '#B45309', muted: '#92400E' },
  error: { main: '#DC2626', light: '#EF4444', dark: '#B91C1C', muted: '#991B1B' },
  info: { main: '#0891B2', light: '#06B6D4', dark: '#0E7490', muted: '#155E75' },
} as const

// ─── Data Visualization ──────────────────────────────────────────────────

export const dataViz = {
  series: ['#7C3AED', '#14B8A6', '#3B82F6', '#F59E0B', '#EC4899', '#8B5CF6', '#06B6D4', '#F97316'],
  ranking: { first: '#F59E0B', second: '#A1A1AA', third: '#CD7F32', rest: '#52525B' },
} as const

// ─── Primitives ──────────────────────────────────────────────────────────

export const radii = { xs: 4, sm: 6, md: 10, lg: 14, xl: 20, pill: 999 } as const
export const spacingUnit = 8

export const zIndex = {
  contentBelow: 0,
  content: 1,
  rail: 1000,
  topBar: 1200,
  drawer: 1300,
  modal: 1400,
  snackbar: 1500,
  tooltip: 1600,
} as const

export const layout = {
  topBarHeight: 60,
  topBarHeightWithBorder: 61,
  railWidth: 64,
  railWidthExpanded: 180,
  contentPadding: 28,
} as const

// `Inter` / `JetBrains Mono` lead the stacks as a *progressive enhancement*:
// the package does not ship or load them, so a consumer only gets that face if
// they install + load it themselves (the design reference uses Inter — see the
// README "Fonts" note). Without it the stack falls back to Roboto / system-ui,
// which is the guaranteed-available look. No font-specific OpenType features
// are forced in CssBaseline, so the fallback renders cleanly.
export const fontFamily = {
  sans: "'Inter', 'Roboto', 'Helvetica Neue', system-ui, -apple-system, sans-serif",
  mono: "'JetBrains Mono', 'Fira Code', 'SF Mono', Menlo, monospace",
} as const

export const fontWeight = {
  regular: 400,
  medium: 500,
  semibold: 600,
  bold: 700,
} as const

export const duration = { fast: 120, standard: 200, slow: 320 } as const
