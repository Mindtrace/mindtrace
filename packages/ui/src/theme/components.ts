/**
 * Component-level overrides — tighter, denser defaults than MUI's base.
 */

import type { Components, Theme } from '@mui/material/styles'
import { fontWeight, radii } from './tokens'

export function buildComponents(mode: 'light' | 'dark'): Components<Theme> {
  const isDark = mode === 'dark'
  const surfaceElevated = isDark ? '#111116' : '#FFFFFF'
  const surfaceBorder = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.08)'

  return {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          scrollbarWidth: 'thin',
          scrollbarColor: isDark ? 'rgba(255,255,255,0.10) transparent' : 'rgba(0,0,0,0.10) transparent',
          fontFeatureSettings: "'cv11', 'ss01'",
        },
        '*::-webkit-scrollbar': { width: 8, height: 8 },
        '*::-webkit-scrollbar-thumb': {
          backgroundColor: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)',
          borderRadius: radii.pill,
          border: '2px solid transparent',
          backgroundClip: 'content-box',
        },
        '*::-webkit-scrollbar-thumb:hover': {
          backgroundColor: isDark ? 'rgba(255,255,255,0.18)' : 'rgba(0,0,0,0.18)',
        },
      },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: {
          borderRadius: radii.sm,
          paddingLeft: 14,
          paddingRight: 14,
          fontWeight: fontWeight.semibold,
        },
        sizeSmall: { paddingLeft: 10, paddingRight: 10 },
        contained: ({ ownerState }) => {
          if (!isDark || ownerState.color !== 'primary') return {}
          return {
            backgroundColor: '#7F23CF',
            color: '#FFFFFF',
            '&:hover': { backgroundColor: '#6D1DB5' },
          }
        },
      },
    },
    MuiIconButton: { styleOverrides: { root: { borderRadius: radii.sm } } },
    MuiChip: {
      styleOverrides: {
        root: {
          borderRadius: radii.sm,
          fontWeight: fontWeight.medium,
          minHeight: 20,
          fontSize: '0.72rem',
        },
        sizeSmall: { height: 22, minHeight: 20, fontSize: '0.72rem' },
        outlined: isDark ? { borderColor: 'rgba(255,255,255,0.12)', color: 'rgba(255,255,255,0.7)' } : {},
        filled: isDark ? { backgroundColor: 'rgba(255,255,255,0.08)', color: 'rgba(255,255,255,0.8)' } : {},
      },
    },
    MuiCard: {
      defaultProps: { elevation: 0 },
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          borderRadius: radii.md,
          border: `1px solid ${surfaceBorder}`,
          backgroundColor: surfaceElevated,
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: { backgroundImage: 'none' },
        outlined: { borderColor: surfaceBorder, backgroundColor: surfaceElevated },
      },
    },
    MuiTextField: { defaultProps: { size: 'small', variant: 'outlined' } },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: radii.sm,
          ...(isDark
            ? {
                color: '#FAFAFA',
                '& .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.10)' },
                '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.20)' },
                '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: '#7F23CF' },
              }
            : {}),
        },
        input: isDark
          ? {
              '&::placeholder': { color: 'rgba(255,255,255,0.3)' },
              '&::-webkit-calendar-picker-indicator': { filter: 'invert(1)' },
            }
          : {},
      },
    },
    MuiInputLabel: {
      styleOverrides: {
        root: isDark ? { color: 'rgba(255,255,255,0.5)', '&.Mui-focused': { color: '#A78BFA' } } : {},
      },
    },
    MuiSelect: {
      styleOverrides: {
        select: { cursor: 'pointer' },
        icon: isDark ? { color: 'rgba(255,255,255,0.4)' } : {},
      },
    },
    MuiMenuItem: {
      styleOverrides: {
        root: isDark
          ? {
              '&.Mui-selected': {
                backgroundColor: 'rgba(167,139,250,0.12)',
                '&:hover': { backgroundColor: 'rgba(167,139,250,0.18)' },
              },
            }
          : {},
      },
    },
    MuiSwitch: {
      styleOverrides: { root: isDark ? { '& .MuiSwitch-track': { backgroundColor: 'rgba(255,255,255,0.15)' } } : {} },
    },
    MuiCheckbox: {
      styleOverrides: {
        root: isDark ? { color: 'rgba(255,255,255,0.3)', '&.Mui-checked': { color: '#A78BFA' } } : {},
      },
    },
    MuiToggleButton: {
      styleOverrides: {
        root: {
          borderColor: surfaceBorder,
          ...(isDark
            ? {
                color: 'rgba(255,255,255,0.5)',
                '&.Mui-selected': {
                  backgroundColor: 'rgba(167,139,250,0.12)',
                  color: '#A78BFA',
                  borderColor: 'rgba(167,139,250,0.30)',
                  '&:hover': { backgroundColor: 'rgba(167,139,250,0.18)' },
                },
              }
            : {}),
        },
      },
    },
    MuiAlert: {
      styleOverrides: {
        root: isDark ? { backgroundColor: 'rgba(255,255,255,0.04)', border: `1px solid ${surfaceBorder}` } : {},
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: {
          borderRadius: radii.sm,
          '&.Mui-selected': {
            backgroundColor: isDark ? 'rgba(167, 139, 250, 0.12)' : 'rgba(124, 58, 237, 0.08)',
            '&:hover': {
              backgroundColor: isDark ? 'rgba(167, 139, 250, 0.18)' : 'rgba(124, 58, 237, 0.14)',
            },
          },
        },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          borderRadius: radii.sm,
          fontSize: '0.75rem',
          fontWeight: fontWeight.medium,
          padding: '6px 10px',
          ...(isDark ? { backgroundColor: '#1A1A20', border: `1px solid ${surfaceBorder}` } : {}),
        },
      },
    },
    MuiAppBar: {
      defaultProps: { elevation: 0 },
      styleOverrides: { root: { backgroundImage: 'none' } },
    },
    MuiDialog: {
      styleOverrides: {
        paper: {
          borderRadius: radii.lg,
          ...(isDark ? { backgroundColor: '#141418', border: `1px solid ${surfaceBorder}` } : {}),
        },
      },
    },
    MuiMenu: {
      styleOverrides: {
        paper: {
          borderRadius: radii.md,
          ...(isDark ? { backgroundColor: '#141418', border: `1px solid ${surfaceBorder}` } : {}),
        },
      },
    },
    MuiDivider: { styleOverrides: { root: { borderColor: surfaceBorder } } },
    MuiTypography: {
      defaultProps: {
        variantMapping: {
          subheading: 'h3',
          sectionLabel: 'div',
          metricLabel: 'div',
          tinyLabel: 'div',
          microCaption: 'span',
          mono: 'span',
          label: 'div',
        },
      },
    },
  }
}
