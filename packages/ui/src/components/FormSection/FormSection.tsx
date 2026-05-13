import Box from '@mui/material/Box'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import type { ReactNode } from 'react'

export type FormSectionProps = {
  /** Section heading. */
  title: ReactNode
  /** Optional supporting copy under the heading. */
  description?: ReactNode
  /** Form fields and other content. */
  children: ReactNode
  /** Right-aligned slot for section-level actions. */
  actions?: ReactNode
}

/**
 * Generic form grouping: a titled section with optional description and
 * action slot, sitting above a stack of form fields.
 *
 *   <FormSection title="Account" description="Where notifications get sent">
 *     <TextField label="Email" />
 *   </FormSection>
 */
export function FormSection({ title, description, children, actions }: FormSectionProps) {
  return (
    <Box component="section" sx={{ display: 'grid', gap: 2 }}>
      <Stack direction="row" spacing={2} sx={{ alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <Box>
          <Typography variant="h6" component="h3">
            {title}
          </Typography>
          {description ? (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              {description}
            </Typography>
          ) : null}
        </Box>
        {actions ? <Box sx={{ flexShrink: 0 }}>{actions}</Box> : null}
      </Stack>
      <Stack spacing={2}>{children}</Stack>
    </Box>
  )
}
