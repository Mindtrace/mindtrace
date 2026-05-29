/**
 * HeroBackground — full-bleed decorative section for landing / login screens.
 *
 * Renders a tinted gradient surface with a subtle noise overlay. The
 * `professional` variant tones the gradient down for marketing-vs-tool
 * contexts. Stateless and brand-agnostic — drop any content inside it.
 *
 *   <HeroBackground>
 *     <LoginForm />
 *   </HeroBackground>
 */

import Box, { type BoxProps } from '@mui/material/Box'
import type { ReactNode } from 'react'

const NOISE_DATA_URI =
  "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.4 0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>\")"

export type HeroBackgroundProps = {
  children: ReactNode
  /** Use the tamer, content-forward palette. Default `false`. */
  professional?: boolean
  /** Extra sx forwarded to the section. */
  sx?: BoxProps['sx']
}

export function HeroBackground({ children, professional = false, sx }: HeroBackgroundProps) {
  return (
    <Box
      component="section"
      sx={[
        (theme) => {
          const isDark = theme.palette.mode === 'dark'
          const gradient = professional
            ? isDark
              ? 'radial-gradient(120% 80% at 50% -10%, rgba(124,58,237,0.18), transparent 60%), linear-gradient(180deg, #0B0B0F 0%, #111118 100%)'
              : 'radial-gradient(120% 80% at 50% -10%, rgba(124,58,237,0.10), transparent 60%), linear-gradient(180deg, #FAFAFC 0%, #FFFFFF 100%)'
            : isDark
              ? 'radial-gradient(140% 90% at 50% -10%, rgba(124,58,237,0.35), transparent 60%), linear-gradient(180deg, #0B0B0F 0%, #15101F 100%)'
              : 'radial-gradient(140% 90% at 50% -10%, rgba(124,58,237,0.18), transparent 60%), linear-gradient(180deg, #FFFFFF 0%, #F6F2FF 100%)'
          return {
            position: 'relative',
            minHeight: '100vh',
            width: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            overflow: 'hidden',
            color: theme.palette.text.primary,
            backgroundImage: gradient,
          }
        },
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    >
      <Box
        aria-hidden
        sx={{
          position: 'absolute',
          inset: 0,
          pointerEvents: 'none',
          opacity: 0.18,
          mixBlendMode: 'overlay',
          backgroundImage: NOISE_DATA_URI,
          backgroundSize: '200px 200px',
        }}
      />
      <Box sx={{ position: 'relative', zIndex: 1, width: '100%' }}>{children}</Box>
    </Box>
  )
}
