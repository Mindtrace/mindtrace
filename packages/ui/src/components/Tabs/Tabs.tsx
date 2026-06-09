/**
 * Tabs — tabbed view with a flat `tabs` array and built-in panel rendering.
 *
 *   <Tabs
 *     value={tab}
 *     onChange={setTab}
 *     tabs={[
 *       { value: 'overview', label: 'Overview', content: <Overview/> },
 *       { value: 'members', label: 'Members', content: <Members/>, badge: <NumberBadge>3</NumberBadge> },
 *     ]}
 *   />
 *
 * Pass `value` + `onChange` to control externally, or omit them for
 * uncontrolled (use `defaultValue`). Each tab's `content` is rendered
 * inside an accessible `role="tabpanel"` region.
 */

import Box from '@mui/material/Box'
import Stack from '@mui/material/Stack'
import MuiTab, { type TabProps as MuiTabProps } from '@mui/material/Tab'
import MuiTabs, { type TabsProps as MuiTabsProps } from '@mui/material/Tabs'
import { useState, type ReactNode, type SyntheticEvent } from 'react'

export type TabsItem<T extends string = string> = {
  value: T
  label: ReactNode
  /** Body rendered when this tab is active. */
  content?: ReactNode
  /** Right-side adornment (e.g. a NumberBadge). */
  badge?: ReactNode
  /** Optional leading icon. */
  icon?: ReactNode
  disabled?: boolean
}

export type TabsProps<T extends string = string> = Omit<MuiTabsProps, 'onChange' | 'value' | 'children'> & {
  tabs: TabsItem<T>[]
  /** Controlled active tab value. */
  value?: T
  /** Uncontrolled starting value. */
  defaultValue?: T
  /** Notified when the active tab changes. */
  onChange?: (next: T) => void
  /** Render `content` for the active tab. Default `true`. */
  renderContent?: boolean
  /** Extra props for each individual MUI Tab. */
  tabProps?: Partial<MuiTabProps>
}

export function Tabs<T extends string = string>({
  tabs,
  value,
  defaultValue,
  onChange,
  renderContent = true,
  tabProps,
  ...muiProps
}: TabsProps<T>) {
  const isControlled = value !== undefined
  const [internal, setInternal] = useState<T>((defaultValue ?? tabs[0]?.value) as T)
  const active = isControlled ? value : internal

  function handle(_: SyntheticEvent, next: T) {
    if (!isControlled) setInternal(next)
    onChange?.(next)
  }

  return (
    <Box>
      <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
        <MuiTabs {...muiProps} value={active} onChange={handle}>
          {tabs.map((t) => (
            <MuiTab
              key={t.value}
              value={t.value}
              disabled={t.disabled}
              icon={t.icon as MuiTabProps['icon']}
              iconPosition={t.icon ? 'start' : undefined}
              label={
                t.badge ? (
                  <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                    <span>{t.label}</span>
                    {t.badge}
                  </Stack>
                ) : (
                  t.label
                )
              }
              {...tabProps}
            />
          ))}
        </MuiTabs>
      </Box>
      {renderContent &&
        tabs.map((t) => (
          <Box
            key={t.value}
            role="tabpanel"
            id={`tabpanel-${t.value}`}
            aria-labelledby={`tab-${t.value}`}
            hidden={t.value !== active}
            sx={{ pt: 2 }}
          >
            {t.value === active ? t.content : null}
          </Box>
        ))}
    </Box>
  )
}
