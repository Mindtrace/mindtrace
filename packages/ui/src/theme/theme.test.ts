import { describe, expect, it } from 'vitest'

import { darkTheme, getTheme, lightTheme } from './index'

describe('theme', () => {
  it('exposes light + dark', () => {
    expect(lightTheme.palette.mode).toBe('light')
    expect(darkTheme.palette.mode).toBe('dark')
  })

  it('getTheme returns the right one', () => {
    expect(getTheme('light').palette.mode).toBe('light')
    expect(getTheme('dark').palette.mode).toBe('dark')
  })

  it('extends the palette with surface + border', () => {
    expect(lightTheme.palette.surface.subtle).toBeTruthy()
    expect(lightTheme.palette.border.subtle).toBeTruthy()
  })
})
