import type { CodingProctorSeverity, CodingProctorSummary } from '@/types/api'

export type ProctorPhase = 'idle' | 'gating' | 'active' | 'stopped'

/** Violations that consume the shared 3/3 attempt pool. */
export type ProctorViolationKind = 'tab_switch' | 'multi_face'

export type ProctorLockReason =
  | ProctorViolationKind
  | 'no_face'
  | 'tab_away'
  | 'fullscreen_exit'
  | 'second_display'
  | 'camera_lost'
  | null

export interface ProctorChecklist {
  camera: boolean
  face: boolean
  fullscreen: boolean
  /** False when an extended / second display is detected. */
  singleDisplay: boolean
}

/** Soft warning dialog (blur) — 3/3 pool or second-display track. */
export interface ProctorWarningDialog {
  kind: ProctorViolationKind | 'second_display'
  title: string
  message: string
  attemptsLeft: number
  warningNumber: number
}

export interface ProctorLiveState {
  phase: ProctorPhase
  checklist: ProctorChecklist
  cameraError: string | null
  faceCount: number
  multiFace: boolean
  gaze: string | null
  lastSignal: string | null
  lastSeverity: CodingProctorSeverity | 'info' | null
  tabHidden: boolean
  fullscreen: boolean
  secondDisplaySuspected: boolean
  /**
   * Second-display track (separate from 3/3).
   * 0 = clean, 1 = soft warned, 2 = auto-submit triggered.
   */
  secondDisplayWarnCount: number
  devtoolsSuspected: boolean
  banner: string | null
  summary: CodingProctorSummary | null
  stream: MediaStream | null
  /** Remaining soft warnings in the 3/3 pool (tab return / multi-face). */
  warningAttemptsLeft: number
  /** Soft blur dialog after a counted 3/3 warning. */
  warningDialog: ProctorWarningDialog | null
  /**
   * Fullscreen exit track (separate from 3/3).
   * 1 = soft blur, 2 = warn next exit submits, 3 = auto-submit.
   */
  fullscreenExitCount: number
  /** Coding UI blurred until candidate re-enters fullscreen. */
  fullscreenGateOpen: boolean
  /** On 2nd fullscreen exit: show “next exit auto-submits” message. */
  fullscreenFinalWarn: boolean
  /** True while editor is hard-locked before auto-submit. */
  screenLocked: boolean
  lockReason: ProctorLockReason
  lockSecondsLeft: number
  finalSubmitPending: boolean
  forceSubmitted: boolean
  /** Seconds left before face-missing auto-submit (null if face OK). */
  faceMissingSecondsLeft: number | null
  /** Seconds left before tab-away auto-submit (null if tab visible). */
  tabAwaySecondsLeft: number | null
}

export interface ProctorEngineOptions {
  token: string
  enabled?: boolean
  initialAttemptsLeft?: number
  initialFullscreenExitCount?: number
  onSummary?: (summary: CodingProctorSummary) => void
  onAlert?: (message: string, severity: CodingProctorSeverity) => void
  onAttemptsChange?: (left: number) => void
  onFullscreenExitCountChange?: (count: number) => void
  onForceSubmit?: (reason: ProctorLockReason) => void
}

export const PROCTOR_MAX_WARNINGS = 3
/** Soft fullscreen exits allowed before the “next = submit” warning (exit #2). */
export const FULLSCREEN_WARN_AT_EXIT = 2
/** Exit number that triggers auto-submit. */
export const FULLSCREEN_SUBMIT_AT_EXIT = 3
/** Continuous face missing → auto-submit. */
export const FACE_MISSING_AUTO_SUBMIT_MS = 10_000
/** Tab away without return → auto-submit. */
export const TAB_AWAY_AUTO_SUBMIT_MS = 10_000
/** Soft warn once for second display; next detection auto-submits. */
export const SECOND_DISPLAY_SUBMIT_AT_WARN = 2
/** Cooldown between second-display soft-warn and escalate. */
export const SECOND_DISPLAY_COOLDOWN_MS = 8_000
