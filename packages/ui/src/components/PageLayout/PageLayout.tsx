/**
 * PageLayout — composite of PageHeader + PageContainer (+ optional tabs).
 *
 * The most common page shell: a heading block at the top, an optional
 * tab strip, and the page body in a scrollable container. Use this
 * instead of assembling PageHeader / PageContainer by hand on every
 * route.
 *
 *   <PageLayout
 *     title="Members"
 *     description="People with access to this workspace."
 *     breadcrumbs={[{ label: 'Settings' }, { label: 'Members' }]}
 *     actions={<Button variant="contained">Invite</Button>}
 *     tabs={{
 *       value: tab,
 *       onChange: setTab,
 *       tabs: [
 *         { value: 'active', label: 'Active', content: <Active/> },
 *         { value: 'invited', label: 'Invited', content: <Invited/> },
 *       ],
 *     }}
 *   />
 *
 * When `tabs` is provided, the active tab's `content` renders inside
 * the container; `children` is rendered above the tabs if present.
 */

import { type ReactNode } from 'react'

import { PageContainer } from '../PageContainer'
import { PageHeader, type Crumb } from '../PageHeader'
import { Tabs, type TabsItem, type TabsProps } from '../Tabs'

export type PageLayoutTabsConfig<T extends string = string> = Omit<
  TabsProps<T>,
  'tabs' | 'value' | 'onChange' | 'defaultValue'
> & {
  tabs: TabsItem<T>[]
  value?: T
  defaultValue?: T
  onChange?: (next: T) => void
}

export type PageLayoutProps<T extends string = string> = {
  /** Page heading. */
  title: ReactNode
  /** Supporting copy beneath the title. */
  description?: ReactNode
  /** Breadcrumbs displayed above the title. */
  breadcrumbs?: Crumb[]
  /** Right-aligned heading actions. */
  actions?: ReactNode
  /** Optional tab navigation just below the heading. */
  tabs?: PageLayoutTabsConfig<T>
  /** Page body. When `tabs` is set, this renders above the tabs. */
  children?: ReactNode
  /** Skip default padding/gap. */
  fullBleed?: boolean
  /** No padding when hosted inside an embedded shell. */
  embedded?: boolean
}

export function PageLayout<T extends string = string>({
  title,
  description,
  breadcrumbs,
  actions,
  tabs,
  children,
  fullBleed,
  embedded,
}: PageLayoutProps<T>) {
  return (
    <PageContainer fullBleed={fullBleed} embedded={embedded}>
      <PageHeader title={title} description={description} breadcrumbs={breadcrumbs} actions={actions} />
      {children}
      {tabs && <Tabs<T> {...tabs} />}
    </PageContainer>
  )
}
