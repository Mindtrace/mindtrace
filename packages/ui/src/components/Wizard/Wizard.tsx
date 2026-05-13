/**
 * Wizard — multi-step flow orchestrator.
 *
 * The shell owns the active step index plus a per-step "valid" boolean
 * (the gate for the Next button). Step components render via the
 * `renderStep` prop and signal validity through the `helpers.setValid`
 * callback. Users can jump back to any reached step but cannot skip
 * forward past their high-water mark.
 *
 *   <Wizard
 *     steps={[
 *       { key: 'identity', title: 'Identity', description: 'Who is this?' },
 *       { key: 'access',   title: 'Access',   description: 'What can they do?' },
 *       { key: 'review',   title: 'Review',   description: 'Confirm and submit' },
 *     ]}
 *     persistKey="mt:setup"
 *     onCancel={cancel}
 *     onFinish={finish}
 *     renderStep={(key, h) => {
 *       if (key === 'identity') return <IdentityStep onValid={h.setValid} />
 *       ...
 *     }}
 *   />
 *
 * Layouts:
 *   - `layout="sidebar"` (default) — left rail with numbered steps + body
 *   - `layout="top"` — horizontal stepper above the body
 */

import CheckIcon from '@mui/icons-material/Check'
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft'
import ChevronRightIcon from '@mui/icons-material/ChevronRight'
import CloseIcon from '@mui/icons-material/Close'
import Box from '@mui/material/Box'
import Card from '@mui/material/Card'
import Divider from '@mui/material/Divider'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import { Button } from '../Button'

export type WizardStep = {
  /** Stable identifier passed to `renderStep` and used as React key. */
  key: string
  title: string
  /** Short subtitle/blurb shown under the title in the rail or header. */
  description?: string
}

export type WizardHelpers = {
  /** Mark the current step as valid/invalid (gates the Next button). */
  setValid: (valid: boolean) => void
  /** Advance to the next step if validity allows. */
  goNext: () => void
  /** Step backward. */
  goPrev: () => void
  /** Jump to a specific step (only if it's at or below the high-water mark). */
  goToStep: (idx: number) => void
}

export type WizardProps = {
  steps: WizardStep[]
  renderStep: (key: string, helpers: WizardHelpers) => ReactNode
  /** Layout variant. Default `'sidebar'`. */
  layout?: 'sidebar' | 'top'
  /** Persist step state in `localStorage` under this key. */
  persistKey?: string
  /** Controlled current step index. */
  currentStep?: number
  /** Uncontrolled starting index. */
  defaultStep?: number
  /** Notified whenever the current step changes. */
  onStepChange?: (idx: number) => void
  /** Cancel/exit handler. Adds a "Cancel" affordance when provided. */
  onCancel?: () => void
  /** Final-step submit handler. */
  onFinish?: () => void
  /** Label for the back button. Default `'Back'`. */
  backLabel?: string
  /** Label for the next button. Default `'Next'`. */
  nextLabel?: string
  /** Label for the finish button. Default `'Finish'`. */
  finishLabel?: string
  /** Label for the cancel button. Default `'Cancel'`. */
  cancelLabel?: string
  /** Title for the sidebar / step heading. Default none. */
  title?: ReactNode
}

type PersistedState = { step: number; max: number; valid: Record<string, boolean> }

function loadPersisted(key: string | undefined, stepCount: number): PersistedState | null {
  if (!key) return null
  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<PersistedState>
    const step =
      typeof parsed.step === 'number' && parsed.step >= 0 && parsed.step < stepCount ? parsed.step : 0
    const max =
      typeof parsed.max === 'number' && parsed.max >= 0 && parsed.max < stepCount ? parsed.max : step
    const valid = typeof parsed.valid === 'object' && parsed.valid ? parsed.valid : {}
    return { step, max, valid: valid as Record<string, boolean> }
  } catch {
    return null
  }
}

export function Wizard({
  steps,
  renderStep,
  layout = 'sidebar',
  persistKey,
  currentStep,
  defaultStep,
  onStepChange,
  onCancel,
  onFinish,
  backLabel = 'Back',
  nextLabel = 'Next',
  finishLabel = 'Finish',
  cancelLabel = 'Cancel',
  title,
}: WizardProps) {
  const lastIdx = steps.length - 1
  const persisted = useMemo(() => loadPersisted(persistKey, steps.length), [persistKey, steps.length])

  const isControlled = currentStep !== undefined
  const [uncontrolledStep, setUncontrolledStep] = useState<number>(
    persisted?.step ?? defaultStep ?? 0,
  )
  const stepIdx = isControlled ? currentStep! : uncontrolledStep

  const [valid, setValid] = useState<Record<string, boolean>>(persisted?.valid ?? {})
  const [maxReached, setMaxReached] = useState<number>(persisted?.max ?? stepIdx)

  useEffect(() => {
    if (!persistKey) return
    try {
      window.localStorage.setItem(persistKey, JSON.stringify({ step: stepIdx, max: maxReached, valid }))
    } catch {
      /* ignore quota errors */
    }
  }, [persistKey, stepIdx, maxReached, valid])

  function setStep(next: number) {
    if (next < 0 || next > lastIdx) return
    if (!isControlled) setUncontrolledStep(next)
    if (next > maxReached) setMaxReached(next)
    onStepChange?.(next)
  }

  const current = steps[stepIdx]
  const isFirst = stepIdx === 0
  const isLast = stepIdx === lastIdx
  const canAdvance = !!valid[current?.key ?? '']

  const goNext = useCallback(() => setStep(Math.min(lastIdx, stepIdx + 1)), [stepIdx, lastIdx])
  const goPrev = useCallback(() => setStep(Math.max(0, stepIdx - 1)), [stepIdx])
  const goToStep = useCallback(
    (idx: number) => {
      if (idx <= maxReached) setStep(idx)
    },
    [maxReached],
  )
  const setStepValid = useCallback(
    (next: boolean) => {
      const key = steps[stepIdx]?.key
      if (!key) return
      setValid((prev) => (prev[key] === next ? prev : { ...prev, [key]: next }))
    },
    [stepIdx, steps],
  )

  const helpers = useMemo<WizardHelpers>(
    () => ({ setValid: setStepValid, goNext, goPrev, goToStep }),
    [setStepValid, goNext, goPrev, goToStep],
  )

  const body = (
    <Card sx={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 480 }}>
      <Box sx={{ borderBottom: 1, borderColor: 'divider', px: 3, py: 2 }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'baseline' }}>
          <Typography variant="mono" color="text.secondary" sx={{ fontSize: '0.75rem' }}>
            Step {stepIdx + 1} / {steps.length}
          </Typography>
          <Typography variant="h6" component="h2">
            {current?.title}
          </Typography>
        </Stack>
        {current?.description && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
            {current.description}
          </Typography>
        )}
      </Box>
      <Box sx={{ flex: 1, overflowY: 'auto', p: 3 }}>{renderStep(current.key, helpers)}</Box>
      <Box
        sx={{
          borderTop: 1,
          borderColor: 'divider',
          px: 3,
          py: 2,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 2,
        }}
      >
        <Button variant="outlined" size="small" onClick={goPrev} disabled={isFirst} startIcon={<ChevronLeftIcon />}>
          {backLabel}
        </Button>
        {isLast ? (
          <Button
            variant="contained"
            size="small"
            onClick={() => onFinish?.()}
            disabled={!canAdvance}
            startIcon={<CheckIcon />}
          >
            {finishLabel}
          </Button>
        ) : (
          <Button
            variant="contained"
            size="small"
            onClick={goNext}
            disabled={!canAdvance}
            endIcon={<ChevronRightIcon />}
          >
            {nextLabel}
          </Button>
        )}
      </Box>
    </Card>
  )

  if (layout === 'top') {
    return (
      <Stack spacing={2}>
        <TopStepIndicator
          steps={steps}
          stepIdx={stepIdx}
          maxReached={maxReached}
          valid={valid}
          onStepClick={goToStep}
          title={title}
          onCancel={onCancel}
          cancelLabel={cancelLabel}
        />
        {body}
      </Stack>
    )
  }

  return (
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '240px 1fr' }, gap: 2 }}>
      <SidebarStepList
        steps={steps}
        stepIdx={stepIdx}
        maxReached={maxReached}
        valid={valid}
        onStepClick={goToStep}
        title={title}
        onCancel={onCancel}
        cancelLabel={cancelLabel}
      />
      {body}
    </Box>
  )
}

function SidebarStepList({
  steps,
  stepIdx,
  maxReached,
  valid,
  onStepClick,
  title,
  onCancel,
  cancelLabel,
}: {
  steps: WizardStep[]
  stepIdx: number
  maxReached: number
  valid: Record<string, boolean>
  onStepClick: (idx: number) => void
  title?: ReactNode
  onCancel?: () => void
  cancelLabel: string
}) {
  return (
    <Card sx={{ alignSelf: 'start', p: 1.5 }}>
      {title && (
        <Typography variant="tinyLabel" color="text.secondary" sx={{ display: 'block', mb: 1, px: 0.5 }}>
          {title}
        </Typography>
      )}
      <Stack component="ol" spacing={0.5} sx={{ m: 0, p: 0, listStyle: 'none' }}>
        {steps.map((s, i) => (
          <li key={s.key}>
            <StepRow
              idx={i}
              step={s}
              current={i === stepIdx}
              completed={!!valid[s.key] && i < stepIdx}
              locked={i > maxReached}
              onClick={() => onStepClick(i)}
            />
          </li>
        ))}
      </Stack>
      {onCancel && (
        <>
          <Divider sx={{ my: 1.5 }} />
          <Button variant="text" size="small" fullWidth onClick={onCancel} startIcon={<CloseIcon />}>
            {cancelLabel}
          </Button>
        </>
      )}
    </Card>
  )
}

function StepRow({
  idx,
  step,
  current,
  completed,
  locked,
  onClick,
}: {
  idx: number
  step: WizardStep
  current: boolean
  completed: boolean
  locked: boolean
  onClick: () => void
}) {
  return (
    <Box
      component="button"
      type="button"
      onClick={onClick}
      disabled={locked}
      sx={(theme) => ({
        width: '100%',
        display: 'flex',
        alignItems: 'center',
        gap: 1,
        py: 0.75,
        px: 1,
        borderRadius: 1,
        border: 0,
        textAlign: 'left',
        cursor: locked ? 'not-allowed' : 'pointer',
        bgcolor: current ? theme.palette.action.selected : 'transparent',
        color: current ? 'primary.main' : locked ? 'text.disabled' : 'text.primary',
        fontFamily: 'inherit',
        '&:hover': locked ? undefined : { bgcolor: current ? theme.palette.action.selected : theme.palette.action.hover },
      })}
    >
      <Box
        sx={(theme) => ({
          flexShrink: 0,
          width: 22,
          height: 22,
          borderRadius: '50%',
          border: 1,
          borderColor: completed
            ? theme.palette.success.main
            : current
              ? 'primary.main'
              : 'divider',
          bgcolor: completed
            ? theme.palette.success.main + '22'
            : 'transparent',
          color: completed ? 'success.main' : current ? 'primary.main' : 'text.secondary',
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '0.7rem',
          fontVariantNumeric: 'tabular-nums',
          fontWeight: 600,
        })}
      >
        {completed ? <CheckIcon sx={{ fontSize: 14 }} /> : <span>{idx + 1}</span>}
      </Box>
      <Box sx={{ minWidth: 0, flex: 1 }}>
        <Typography sx={{ fontSize: '0.825rem', fontWeight: current ? 600 : 500, lineHeight: 1.2 }} noWrap>
          {step.title}
        </Typography>
        {step.description && (
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1.2 }} noWrap>
            {step.description}
          </Typography>
        )}
      </Box>
    </Box>
  )
}

function TopStepIndicator({
  steps,
  stepIdx,
  maxReached,
  valid,
  onStepClick,
  title,
  onCancel,
  cancelLabel,
}: {
  steps: WizardStep[]
  stepIdx: number
  maxReached: number
  valid: Record<string, boolean>
  onStepClick: (idx: number) => void
  title?: ReactNode
  onCancel?: () => void
  cancelLabel: string
}) {
  return (
    <Card sx={{ p: 2 }}>
      <Stack direction="row" spacing={2} sx={{ alignItems: 'center', justifyContent: 'space-between' }}>
        {title && (
          <Typography variant="tinyLabel" color="text.secondary">
            {title}
          </Typography>
        )}
        <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', flex: 1, overflowX: 'auto' }}>
          {steps.map((s, i) => {
            const completed = !!valid[s.key] && i < stepIdx
            const current = i === stepIdx
            const locked = i > maxReached
            return (
              <Stack
                key={s.key}
                direction="row"
                spacing={1}
                sx={{ alignItems: 'center', flexShrink: 0 }}
                component="button"
                type="button"
                onClick={() => onStepClick(i)}
                disabled={locked}
                style={{
                  background: 'none',
                  border: 0,
                  padding: 0,
                  cursor: locked ? 'not-allowed' : 'pointer',
                }}
              >
                <Box
                  sx={(theme) => ({
                    width: 22,
                    height: 22,
                    borderRadius: '50%',
                    border: 1,
                    borderColor: completed
                      ? theme.palette.success.main
                      : current
                        ? 'primary.main'
                        : 'divider',
                    bgcolor: completed ? theme.palette.success.main + '22' : 'transparent',
                    color: completed ? 'success.main' : current ? 'primary.main' : 'text.secondary',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '0.7rem',
                    fontWeight: 600,
                  })}
                >
                  {completed ? <CheckIcon sx={{ fontSize: 14 }} /> : <span>{i + 1}</span>}
                </Box>
                <Typography
                  sx={{
                    fontSize: '0.825rem',
                    fontWeight: current ? 600 : 500,
                    color: locked ? 'text.disabled' : current ? 'primary.main' : 'text.primary',
                  }}
                >
                  {s.title}
                </Typography>
              </Stack>
            )
          })}
        </Stack>
        {onCancel && (
          <Button variant="text" size="small" onClick={onCancel} startIcon={<CloseIcon />}>
            {cancelLabel}
          </Button>
        )}
      </Stack>
    </Card>
  )
}
