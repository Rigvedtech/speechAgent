/**
 * Browser proctoring for public coding rounds.
 *
 * Rules:
 * - 3/3 pool: tab switch (return <10s) + multi-face → at 0: auto-submit
 * - Tab away ≥10s without return → auto-submit
 * - Face missing ≥10s continuous → auto-submit
 * - Fullscreen exits: SEPARATE track (blur + button). Exit1 soft, exit2 warn next,
 *   exit3 auto-submit. Does not use 3/3.
 */

import {
  postPublicProctorEvents,
  postPublicProctorFrame,
  startPublicCodingSession,
} from '@/lib/api'
import type {
  CodingProctorEventInput,
  CodingProctorSeverity,
  CodingProctorStartResult,
  CodingProctorSummary,
} from '@/types/api'
import { playProctorClip, stopProctorAudio, unlockProctorAudio } from './audio'
import type {
  ProctorChecklist,
  ProctorEngineOptions,
  ProctorLiveState,
  ProctorLockReason,
  ProctorPhase,
  ProctorViolationKind,
  ProctorWarningDialog,
} from './types'
import {
  FACE_MISSING_AUTO_SUBMIT_MS,
  FULLSCREEN_SUBMIT_AT_EXIT,
  FULLSCREEN_WARN_AT_EXIT,
  PROCTOR_MAX_WARNINGS,
  TAB_AWAY_AUTO_SUBMIT_MS,
} from './types'

const FRAME_INTERVAL_MS = 2800
const EVENT_FLUSH_MS = 4000
const FACE_GATE_STABLE_MS = 1500
const MULTI_FACE_CRITICAL_MS = 1800
const DEVTOOLS_CHECK_MS = 2500
const VIOLATION_COUNT_COOLDOWN_MS = 5000

function nowIso() {
  return new Date().toISOString()
}

function emptyChecklist(): ProctorChecklist {
  return { camera: false, face: false, fullscreen: false }
}

function initialState(
  attempts: number,
  fullscreenExitCount = 0,
): ProctorLiveState {
  return {
    phase: 'idle',
    checklist: emptyChecklist(),
    cameraError: null,
    faceCount: 0,
    multiFace: false,
    gaze: null,
    lastSignal: null,
    lastSeverity: null,
    tabHidden: false,
    fullscreen: false,
    secondDisplaySuspected: false,
    devtoolsSuspected: false,
    banner: null,
    summary: null,
    stream: null,
    warningAttemptsLeft: attempts,
    warningDialog: null,
    fullscreenExitCount,
    fullscreenGateOpen: false,
    fullscreenFinalWarn: fullscreenExitCount >= FULLSCREEN_WARN_AT_EXIT,
    screenLocked: false,
    lockReason: null,
    lockSecondsLeft: 0,
    finalSubmitPending: false,
    forceSubmitted: false,
    faceMissingSecondsLeft: null,
    tabAwaySecondsLeft: null,
  }
}

function dialogFor(
  kind: ProctorViolationKind,
  attemptsLeft: number,
  warningNumber: number,
): ProctorWarningDialog {
  if (kind === 'tab_switch') {
    return {
      kind,
      title: 'Tab switch detected',
      message:
        'Please stay on the coding tab. Leaving this page counts as a proctoring warning. If you stay away for 10 seconds, your code will be submitted automatically.',
      attemptsLeft,
      warningNumber,
    }
  }
  return {
    kind,
    title: 'Multiple faces detected',
    message: 'Only the candidate should be visible to the camera.',
    attemptsLeft,
    warningNumber,
  }
}

function clipFor(kind: ProctorViolationKind) {
  return kind === 'tab_switch' ? ('tab-switch' as const) : ('multi-face' as const)
}

export class CodingProctorEngine {
  private token: string
  private enabled: boolean
  private onSummary?: ProctorEngineOptions['onSummary']
  private onAlert?: ProctorEngineOptions['onAlert']
  private onAttemptsChange?: ProctorEngineOptions['onAttemptsChange']
  private onFullscreenExitCountChange?: ProctorEngineOptions['onFullscreenExitCountChange']
  private onForceSubmit?: ProctorEngineOptions['onForceSubmit']
  private state: ProctorLiveState
  private listeners = new Set<(s: ProctorLiveState) => void>()
  private videoEl: HTMLVideoElement | null = null
  private canvasEl: HTMLCanvasElement | null = null
  private queue: CodingProctorEventInput[] = []
  private flushTimer: number | null = null
  private frameTimer: number | null = null
  private devtoolsTimer: number | null = null
  private lockTimer: number | null = null
  private softDialogTimer: number | null = null
  private tabAwayTimer: number | null = null
  private tabAwayTickTimer: number | null = null
  private faceMissingTickTimer: number | null = null
  private faceOkSince: number | null = null
  private noFaceSince: number | null = null
  private multiFaceSince: number | null = null
  private tabHiddenAt: number | null = null
  private lastEmitted = new Map<string, number>()
  private lastViolationAt = new Map<string, number>()
  private lockUntilMs = 0
  private finalLockStarted = false
  private forceSubmitFired = false
  private destroyed = false
  private frameInFlight = false
  private frameFailStreak = 0
  private boundVisibility = () => this.onVisibility()
  private boundPageHide = () => this.onPageHide()
  private boundBlur = () => this.onBlur()
  private boundFocus = () => this.onFocus()
  private boundFullscreen = () => this.onFullscreen()
  private boundPaste = (e: ClipboardEvent) => this.onPaste(e)
  private boundCopy = (e: ClipboardEvent) => this.onCopy(e)
  private boundContext = (e: Event) => this.onContextMenu(e)

  constructor(opts: ProctorEngineOptions) {
    this.token = opts.token
    this.enabled = opts.enabled !== false
    this.onSummary = opts.onSummary
    this.onAlert = opts.onAlert
    this.onAttemptsChange = opts.onAttemptsChange
    this.onFullscreenExitCountChange = opts.onFullscreenExitCountChange
    this.onForceSubmit = opts.onForceSubmit
    const attempts =
      typeof opts.initialAttemptsLeft === 'number'
        ? Math.max(0, Math.min(PROCTOR_MAX_WARNINGS, opts.initialAttemptsLeft))
        : PROCTOR_MAX_WARNINGS
    const fsExits =
      typeof opts.initialFullscreenExitCount === 'number'
        ? Math.max(0, opts.initialFullscreenExitCount)
        : 0
    this.state = initialState(attempts, fsExits)
  }

  subscribe(fn: (s: ProctorLiveState) => void) {
    this.listeners.add(fn)
    fn(this.state)
    return () => this.listeners.delete(fn)
  }

  getState() {
    return this.state
  }

  dismissWarningDialog() {
    if (this.softDialogTimer != null) {
      window.clearTimeout(this.softDialogTimer)
      this.softDialogTimer = null
    }
    if (this.state.warningDialog) {
      this.setState({ warningDialog: null })
    }
  }

  private setState(patch: Partial<ProctorLiveState>) {
    this.state = { ...this.state, ...patch }
    for (const fn of this.listeners) fn(this.state)
  }

  private setChecklist(patch: Partial<ProctorChecklist>) {
    this.setState({ checklist: { ...this.state.checklist, ...patch } })
  }

  private setAttempts(left: number) {
    const next = Math.max(0, left)
    this.setState({ warningAttemptsLeft: next })
    this.onAttemptsChange?.(next)
  }

  private setFullscreenExits(count: number) {
    this.setState({
      fullscreenExitCount: count,
      fullscreenFinalWarn: count >= FULLSCREEN_WARN_AT_EXIT,
    })
    this.onFullscreenExitCountChange?.(count)
  }

  private isTerminal() {
    return (
      this.finalLockStarted ||
      this.forceSubmitFired ||
      this.state.forceSubmitted ||
      this.state.finalSubmitPending
    )
  }

  async beginGate(video: HTMLVideoElement, canvas: HTMLCanvasElement) {
    if (!this.enabled || this.destroyed) return
    this.videoEl = video
    this.canvasEl = canvas
    this.finalLockStarted = false
    this.forceSubmitFired = false
    this.clearTabAwayTimers()
    this.clearFaceMissingTimer()
    this.setState({
      phase: 'gating',
      banner: null,
      cameraError: null,
      warningDialog: null,
      screenLocked: false,
      lockReason: null,
      lockSecondsLeft: 0,
      finalSubmitPending: false,
      forceSubmitted: false,
      fullscreenGateOpen: false,
      fullscreenFinalWarn: false,
      faceMissingSecondsLeft: null,
      tabAwaySecondsLeft: null,
    })
    this.setFullscreenExits(0)
    this.attachDomListeners()
    await this.ensureCamera()
    await this.ensureFullscreen()
    this.startFrameLoop()
    this.startDevtoolsWatch()
    this.enqueue('proctor_resume', 'info', { phase: 'gating' })
  }

  async resumeActive(video: HTMLVideoElement, canvas: HTMLCanvasElement) {
    if (!this.enabled || this.destroyed) return
    this.videoEl = video
    this.canvasEl = canvas
    this.setState({ phase: 'active', banner: null })
    this.attachDomListeners()
    await this.ensureCamera()
    await this.ensureFullscreen()
    // If still not fullscreen after resume, open gate without counting another exit
    if (!document.fullscreenElement) {
      this.setState({
        fullscreen: false,
        fullscreenGateOpen: true,
        checklist: { ...this.state.checklist, fullscreen: false },
      })
    }
    this.startFrameLoop()
    this.startDevtoolsWatch()
    this.enqueue('proctor_resume', 'info', { phase: 'active' })
  }

  async completeGateAndStart(): Promise<CodingProctorStartResult> {
    const { checklist } = this.state
    if (!checklist.camera || !checklist.face || !checklist.fullscreen) {
      throw new Error('Complete camera, face, and fullscreen checks before starting')
    }
    unlockProctorAudio()
    this.enqueue('proctor_gate_passed', 'info', { ...checklist })
    await this.flushEvents(true)
    const result = await startPublicCodingSession(this.token)
    this.finalLockStarted = false
    this.forceSubmitFired = false
    this.setAttempts(PROCTOR_MAX_WARNINGS)
    this.setFullscreenExits(0)
    this.setState({
      phase: 'active',
      summary: result.summary,
      banner: null,
      warningDialog: null,
      screenLocked: false,
      finalSubmitPending: false,
      forceSubmitted: false,
      lockSecondsLeft: 0,
      lockReason: null,
      fullscreenGateOpen: false,
      fullscreenFinalWarn: false,
      faceMissingSecondsLeft: null,
      tabAwaySecondsLeft: null,
    })
    this.onSummary?.(result.summary)
    return result
  }

  async ensureFullscreen() {
    try {
      if (document.fullscreenElement) {
        this.setChecklist({ fullscreen: true })
        this.setState({
          fullscreen: true,
          fullscreenGateOpen: false,
        })
        return
      }
      const root = document.documentElement
      if (root.requestFullscreen) {
        await root.requestFullscreen()
      }
      const ok = Boolean(document.fullscreenElement)
      this.setChecklist({ fullscreen: ok })
      this.setState({
        fullscreen: ok,
        fullscreenGateOpen: this.state.phase === 'active' ? !ok : false,
      })
      if (ok) {
        this.enqueue('fullscreen_entered', 'info')
      }
    } catch {
      this.setChecklist({ fullscreen: false })
      this.setState({
        fullscreen: false,
        fullscreenGateOpen: this.state.phase === 'active',
      })
      this.alert('Enter fullscreen to continue', 'warn')
    }
  }

  async stop() {
    this.destroyed = true
    this.setState({
      phase: 'stopped',
      screenLocked: false,
      lockSecondsLeft: 0,
      warningDialog: null,
      fullscreenGateOpen: false,
      faceMissingSecondsLeft: null,
      tabAwaySecondsLeft: null,
    })
    this.detachDomListeners()
    this.clearTabAwayTimers()
    this.clearFaceMissingTimer()
    if (this.frameTimer != null) window.clearInterval(this.frameTimer)
    if (this.flushTimer != null) window.clearInterval(this.flushTimer)
    if (this.devtoolsTimer != null) window.clearInterval(this.devtoolsTimer)
    if (this.lockTimer != null) window.clearInterval(this.lockTimer)
    if (this.softDialogTimer != null) window.clearTimeout(this.softDialogTimer)
    this.frameTimer = null
    this.flushTimer = null
    this.devtoolsTimer = null
    this.lockTimer = null
    this.softDialogTimer = null
    stopProctorAudio()
    await this.flushEvents(true)
    const stream = this.state.stream
    if (stream) {
      for (const t of stream.getTracks()) t.stop()
    }
    this.setState({ stream: null })
  }

  notePasteBlocked(source = 'editor') {
    this.enqueue('paste_blocked', 'warn', { source })
    this.alert('Paste is disabled during the proctored coding round', 'warn')
  }

  // ── 3/3 attempt pool ───────────────────────────────────────────────────

  private registerViolation(
    kind: ProctorViolationKind,
    opts: {
      eventType: string
      severity: CodingProctorSeverity
      detail?: Record<string, unknown>
      warnMessage: string
    },
  ) {
    if (this.state.phase !== 'active') return
    if (this.isTerminal()) return

    const now = Date.now()
    const last = this.lastViolationAt.get(kind) ?? 0
    if (now - last < VIOLATION_COUNT_COOLDOWN_MS) return
    this.lastViolationAt.set(kind, now)

    this.enqueue(opts.eventType, opts.severity, opts.detail || {})

    const left = Math.max(0, this.state.warningAttemptsLeft - 1)
    this.setAttempts(left)
    const warningNumber = PROCTOR_MAX_WARNINGS - left

    if (left > 0) {
      playProctorClip(clipFor(kind))
      this.alert(
        `${opts.warnMessage} Warning ${warningNumber} of ${PROCTOR_MAX_WARNINGS}.`,
        opts.severity,
      )
      this.showSoftWarningDialog(kind, left, warningNumber)
      this.setState({
        banner: `${opts.warnMessage} Attempts left: ${left}`,
      })
      return
    }

    this.dismissWarningDialog()
    this.alert(
      `${opts.warnMessage} No attempts left. Screen locked — submission in 10 seconds.`,
      'critical',
    )
    this.startFinalLockAndSubmit(kind)
  }

  private showSoftWarningDialog(
    kind: ProctorViolationKind,
    attemptsLeft: number,
    warningNumber: number,
  ) {
    if (this.softDialogTimer != null) {
      window.clearTimeout(this.softDialogTimer)
      this.softDialogTimer = null
    }
    this.setState({
      warningDialog: dialogFor(kind, attemptsLeft, warningNumber),
    })
  }

  private startFinalLockAndSubmit(reason: Exclude<ProctorLockReason, null>) {
    if (this.finalLockStarted || this.forceSubmitFired) return
    this.finalLockStarted = true
    this.clearTabAwayTimers()
    this.clearFaceMissingTimer()
    this.lockUntilMs = 0

    playProctorClip('auto-submit')
    this.enqueue('session_submitted', 'critical', {
      source: 'proctor_force_submit',
      reason,
    })

    this.setState({
      screenLocked: true,
      warningDialog: null,
      fullscreenGateOpen: false,
      lockReason: reason,
      finalSubmitPending: true,
      forceSubmitted: false,
      lockSecondsLeft: 0,
      faceMissingSecondsLeft: null,
      tabAwaySecondsLeft: null,
      banner: 'Submitting your work…',
    })

    // Submit immediately — no 10s countdown.
    this.fireForceSubmit()
  }

  private fireForceSubmit() {
    if (this.forceSubmitFired) return
    this.forceSubmitFired = true
    if (this.lockTimer != null) {
      window.clearInterval(this.lockTimer)
      this.lockTimer = null
    }
    this.lockUntilMs = 0
    this.setState({
      screenLocked: true,
      finalSubmitPending: false,
      forceSubmitted: true,
      lockSecondsLeft: 0,
      warningDialog: null,
      fullscreenGateOpen: false,
      phase: 'stopped',
      banner: 'Submitting your coding round due to proctoring violations…',
    })
    const reason = this.state.lockReason
    try {
      this.onForceSubmit?.(reason)
    } catch {
      // page handler owns errors
    }
  }

  // ── Fullscreen (separate track) ────────────────────────────────────────

  private handleFullscreenExit() {
    if (this.state.phase !== 'active') {
      this.setChecklist({ fullscreen: false })
      this.setState({ fullscreen: false })
      return
    }
    if (this.isTerminal()) {
      this.setChecklist({ fullscreen: false })
      this.setState({ fullscreen: false, fullscreenGateOpen: true })
      return
    }

    const next = this.state.fullscreenExitCount + 1
    this.setFullscreenExits(next)
    this.enqueue('fullscreen_exited', 'warn', { exit_count: next })
    this.setChecklist({ fullscreen: false })
    this.setState({
      fullscreen: false,
      fullscreenGateOpen: true,
    })

    if (next >= FULLSCREEN_SUBMIT_AT_EXIT) {
      this.alert(
        'Fullscreen exited again. Screen locked — your code will be submitted.',
        'critical',
      )
      this.startFinalLockAndSubmit('fullscreen_exit')
      return
    }

    if (next === FULLSCREEN_WARN_AT_EXIT) {
      playProctorClip('fullscreen-final')
      this.alert(
        'You exited fullscreen twice. Next exit will auto-submit your code.',
        'warn',
      )
      this.setState({
        banner:
          'Fullscreen exit 2/2. Next exit will auto-submit your coding response.',
      })
      return
    }

    // First exit — soft blur + button only
    playProctorClip('fullscreen')
    this.setState({
      banner: null,
    })
  }

  private handleFullscreenEnter() {
    this.setChecklist({ fullscreen: true })
    this.setState({
      fullscreen: true,
      fullscreenGateOpen: false,
    })
    this.enqueue('fullscreen_entered', 'info')
    if (this.state.banner?.toLowerCase().includes('fullscreen')) {
      this.setState({ banner: null })
    }
  }

  // ── Tab away 10s ───────────────────────────────────────────────────────

  private clearTabAwayTimers() {
    if (this.tabAwayTimer != null) {
      window.clearTimeout(this.tabAwayTimer)
      this.tabAwayTimer = null
    }
    if (this.tabAwayTickTimer != null) {
      window.clearInterval(this.tabAwayTickTimer)
      this.tabAwayTickTimer = null
    }
    this.tabHiddenAt = null
  }

  private startTabAwayWatch() {
    this.clearTabAwayTimers()
    if (this.state.phase !== 'active' || this.isTerminal()) return
    this.tabHiddenAt = Date.now()
    this.setState({
      tabHidden: true,
      tabAwaySecondsLeft: Math.ceil(TAB_AWAY_AUTO_SUBMIT_MS / 1000),
    })

    this.tabAwayTickTimer = window.setInterval(() => {
      if (!this.tabHiddenAt) return
      const left = Math.max(
        0,
        Math.ceil((TAB_AWAY_AUTO_SUBMIT_MS - (Date.now() - this.tabHiddenAt)) / 1000),
      )
      this.setState({ tabAwaySecondsLeft: left })
    }, 250)

    this.tabAwayTimer = window.setTimeout(() => {
      if (document.hidden && this.state.phase === 'active' && !this.isTerminal()) {
        this.alert(
          'You left the coding tab for 10 seconds. Submitting automatically.',
          'critical',
        )
        this.startFinalLockAndSubmit('tab_away')
      }
    }, TAB_AWAY_AUTO_SUBMIT_MS)
  }

  private clearTabAwayOnReturn() {
    this.clearTabAwayTimers()
    this.setState({ tabHidden: false, tabAwaySecondsLeft: null })
  }

  // ── Face missing 10s ───────────────────────────────────────────────────

  private clearFaceMissingTimer() {
    if (this.faceMissingTickTimer != null) {
      window.clearInterval(this.faceMissingTickTimer)
      this.faceMissingTickTimer = null
    }
    this.noFaceSince = null
    if (this.state.faceMissingSecondsLeft != null) {
      this.setState({ faceMissingSecondsLeft: null })
    }
  }

  private ensureFaceMissingWatch() {
    if (this.state.phase !== 'active' || this.isTerminal()) return
    if (this.noFaceSince == null) {
      this.noFaceSince = Date.now()
      playProctorClip('face-missing')
      this.alert('Face not visible. Return to the camera within 10 seconds.', 'warn')
    }
    if (this.faceMissingTickTimer == null) {
      this.faceMissingTickTimer = window.setInterval(() => this.tickFaceMissing(), 250)
    }
    this.tickFaceMissing()
  }

  private tickFaceMissing() {
    if (this.noFaceSince == null || this.isTerminal()) return
    const elapsed = Date.now() - this.noFaceSince
    const left = Math.max(0, Math.ceil((FACE_MISSING_AUTO_SUBMIT_MS - elapsed) / 1000))
    this.setState({ faceMissingSecondsLeft: left })
    if (elapsed >= FACE_MISSING_AUTO_SUBMIT_MS) {
      this.alert(
        'Face not visible for 10 seconds. Submitting automatically.',
        'critical',
      )
      this.startFinalLockAndSubmit('no_face')
    }
  }

  // ── Camera ─────────────────────────────────────────────────────────────

  private async ensureCamera() {
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error('Camera API not available in this browser')
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: 'user',
          width: { ideal: 640 },
          height: { ideal: 480 },
        },
        audio: false,
      })
      if (this.videoEl) {
        this.videoEl.srcObject = stream
        await this.videoEl.play().catch(() => undefined)
      }
      for (const track of stream.getVideoTracks()) {
        track.addEventListener('ended', () => {
          this.setChecklist({ camera: false })
          this.enqueue('camera_lost', 'critical', { reason: 'track_ended' })
          playProctorClip('camera-lost')
          this.alert('Camera disconnected — please re-enable your webcam', 'critical')
          this.setState({
            banner: 'Camera lost. Reconnect your webcam to continue under proctoring.',
            cameraError: 'Camera track ended',
          })
        })
      }
      this.setState({ stream, cameraError: null })
      this.setChecklist({ camera: true })
      this.enqueue('camera_permission_granted', 'info')
      this.enqueue('camera_started', 'info')
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : 'Camera permission denied or unavailable'
      this.setState({ cameraError: msg, stream: null })
      this.setChecklist({ camera: false })
      this.enqueue('camera_permission_denied', 'critical', { message: msg })
      this.alert('Camera is required for this coding round', 'critical')
    }
  }

  // ── Frame loop ─────────────────────────────────────────────────────────

  private startFrameLoop() {
    if (this.frameTimer != null) return
    void this.captureAndAnalyze()
    this.frameTimer = window.setInterval(() => {
      void this.captureAndAnalyze()
    }, FRAME_INTERVAL_MS)
    if (this.flushTimer == null) {
      this.flushTimer = window.setInterval(() => {
        void this.flushEvents(false)
      }, EVENT_FLUSH_MS)
    }
  }

  private captureJpeg(): string | null {
    const video = this.videoEl
    const canvas = this.canvasEl
    if (!video || !canvas || video.readyState < 2) return null
    const w = video.videoWidth || 640
    const h = video.videoHeight || 480
    if (w < 8 || h < 8) return null
    canvas.width = Math.min(640, w)
    canvas.height = Math.round((canvas.width / w) * h)
    const ctx = canvas.getContext('2d')
    if (!ctx) return null
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
    return canvas.toDataURL('image/jpeg', 0.72)
  }

  private async captureAndAnalyze() {
    if (this.destroyed || this.frameInFlight) return
    if (!this.state.checklist.camera) return
    const image = this.captureJpeg()
    if (!image) return
    this.frameInFlight = true
    try {
      const result = await postPublicProctorFrame(this.token, image)
      this.onSummary?.(result.summary)
      this.setState({
        faceCount: result.face_count,
        multiFace: result.multi_face,
        gaze: result.gaze ?? null,
        lastSignal: result.signal,
        lastSeverity: (result.severity as CodingProctorSeverity) || 'info',
        summary: result.summary,
      })
      this.frameFailStreak = 0
      this.applyFaceGate(result.gate_ok, result.face_count, result.multi_face, result.signal)
    } catch {
      this.frameFailStreak += 1
      if (this.frameFailStreak >= 3 && this.state.phase === 'gating') {
        this.setState({
          banner:
            'Face check service unavailable. Retry in a moment, or contact the recruiter.',
        })
      }
    } finally {
      this.frameInFlight = false
    }
  }

  private applyFaceGate(
    gateOk: boolean,
    faceCount: number,
    multiFace: boolean,
    signal: string,
  ) {
    const now = Date.now()
    if (gateOk) {
      this.clearFaceMissingTimer()
      this.multiFaceSince = null
      if (this.faceOkSince == null) this.faceOkSince = now
      if (now - this.faceOkSince >= FACE_GATE_STABLE_MS) {
        this.setChecklist({ face: true })
      }
      return
    }

    this.faceOkSince = null
    this.setChecklist({ face: false })

    if (multiFace || faceCount >= 2) {
      this.clearFaceMissingTimer()
      if (this.multiFaceSince == null) this.multiFaceSince = now
      if (now - this.multiFaceSince >= MULTI_FACE_CRITICAL_MS) {
        if (this.state.phase === 'active') {
          this.registerViolation('multi_face', {
            eventType: 'multi_face',
            severity: 'critical',
            detail: { faceCount },
            warnMessage: 'Multiple faces detected.',
          })
        } else {
          this.setState({ banner: 'Multiple faces detected in camera view.' })
        }
      }
      return
    }

    if (faceCount <= 0 || signal === 'no_face') {
      this.multiFaceSince = null
      if (this.state.phase === 'active') {
        this.ensureFaceMissingWatch()
      } else {
        this.setState({ banner: 'Face not visible. Look at the camera.' })
      }
      return
    }

    if (signal === 'gaze_away' && this.state.phase === 'active') {
      this.emitThrottled('gaze_away', 'warn', 12000, { gaze: this.state.gaze })
    }
  }

  // ── DOM listeners ──────────────────────────────────────────────────────

  private attachDomListeners() {
    document.addEventListener('visibilitychange', this.boundVisibility)
    window.addEventListener('pagehide', this.boundPageHide)
    window.addEventListener('blur', this.boundBlur)
    window.addEventListener('focus', this.boundFocus)
    document.addEventListener('fullscreenchange', this.boundFullscreen)
    document.addEventListener('paste', this.boundPaste, true)
    document.addEventListener('copy', this.boundCopy, true)
    document.addEventListener('contextmenu', this.boundContext, true)
  }

  private detachDomListeners() {
    document.removeEventListener('visibilitychange', this.boundVisibility)
    window.removeEventListener('pagehide', this.boundPageHide)
    window.removeEventListener('blur', this.boundBlur)
    window.removeEventListener('focus', this.boundFocus)
    document.removeEventListener('fullscreenchange', this.boundFullscreen)
    document.removeEventListener('paste', this.boundPaste, true)
    document.removeEventListener('copy', this.boundCopy, true)
    document.removeEventListener('contextmenu', this.boundContext, true)
  }

  private onVisibility() {
    if (document.hidden) {
      this.registerViolation('tab_switch', {
        eventType: 'tab_hidden',
        severity: 'warn',
        detail: { source: 'visibilitychange' },
        warnMessage: 'Tab switch detected.',
      })
      this.startTabAwayWatch()
    } else {
      this.clearTabAwayOnReturn()
      this.enqueue('tab_visible', 'info')
      if (
        !this.state.screenLocked &&
        !this.state.warningDialog &&
        !this.state.fullscreenGateOpen
      ) {
        this.setState({ banner: null })
      }
    }
  }

  private onPageHide() {
    if (this.state.phase !== 'active') return
    this.registerViolation('tab_switch', {
      eventType: 'tab_hidden',
      severity: 'warn',
      detail: { source: 'pagehide' },
      warnMessage: 'Tab switch detected.',
    })
    this.startTabAwayWatch()
  }

  private onBlur() {
    if (this.state.phase === 'gating') return
    this.enqueue('window_blur', 'info')
  }

  private onFocus() {
    if (this.state.phase === 'gating') return
    this.enqueue('window_focus', 'info')
  }

  private onFullscreen() {
    if (document.fullscreenElement) {
      this.handleFullscreenEnter()
    } else {
      this.handleFullscreenExit()
    }
  }

  private onPaste(e: ClipboardEvent) {
    if (this.state.phase === 'idle' || this.state.phase === 'stopped') return
    e.preventDefault()
    this.notePasteBlocked('document')
  }

  private onCopy(e: ClipboardEvent) {
    if (this.state.phase !== 'active') return
    this.enqueue('copy_attempt', 'info', {
      target: (e.target as HTMLElement | null)?.tagName ?? null,
    })
  }

  private onContextMenu(e: Event) {
    if (this.state.phase === 'idle' || this.state.phase === 'stopped') return
    e.preventDefault()
    this.emitThrottled('context_menu_blocked', 'info', 10000)
  }

  private startDevtoolsWatch() {
    if (this.devtoolsTimer != null) return
    this.devtoolsTimer = window.setInterval(() => {
      this.checkDevtools()
      this.checkSecondDisplay()
    }, DEVTOOLS_CHECK_MS)
  }

  private checkDevtools() {
    if (this.state.phase !== 'active') return
    const widthGap = Math.abs(window.outerWidth - window.innerWidth)
    const heightGap = Math.abs(window.outerHeight - window.innerHeight)
    const suspected = widthGap > 160 || heightGap > 160
    if (suspected && !this.state.devtoolsSuspected) {
      this.setState({ devtoolsSuspected: true })
      this.emitThrottled('devtools_suspected', 'warn', 30000, {
        widthGap,
        heightGap,
        confidence: 'low',
      })
    } else if (!suspected && this.state.devtoolsSuspected) {
      this.setState({ devtoolsSuspected: false })
    }
  }

  private checkSecondDisplay() {
    if (this.state.phase !== 'active') return
    const screenAny = window.screen as Screen & { isExtended?: boolean }
    const suspected =
      Boolean(screenAny.isExtended) ||
      (typeof window.screenLeft === 'number' &&
        (window.screenLeft < -50 || window.screenLeft > window.screen.width + 50))
    if (suspected && !this.state.secondDisplaySuspected) {
      this.setState({ secondDisplaySuspected: true })
      this.emitThrottled('second_display_suspected', 'info', 60000, {
        isExtended: screenAny.isExtended ?? null,
        screenLeft: window.screenLeft,
        confidence: 'low',
      })
    } else if (!suspected && this.state.secondDisplaySuspected) {
      this.setState({ secondDisplaySuspected: false })
    }
  }

  private enqueue(
    event_type: string,
    severity: CodingProctorSeverity = 'info',
    detail: Record<string, unknown> = {},
  ) {
    this.queue.push({
      event_type,
      severity,
      detail,
      client_ts: nowIso(),
    })
    if (severity === 'warn' || severity === 'critical') {
      void this.flushEvents(true)
    }
  }

  private emitThrottled(
    event_type: string,
    severity: CodingProctorSeverity,
    minIntervalMs: number,
    detail: Record<string, unknown> = {},
  ) {
    const last = this.lastEmitted.get(event_type) ?? 0
    const t = Date.now()
    if (t - last < minIntervalMs) return
    this.lastEmitted.set(event_type, t)
    this.enqueue(event_type, severity, detail)
  }

  private async flushEvents(force: boolean) {
    if (!this.queue.length) return
    if (!force && this.queue.length < 2) return
    const batch = this.queue.splice(0, 50)
    try {
      const res = await postPublicProctorEvents(this.token, batch)
      this.setState({ summary: res.summary })
      this.onSummary?.(res.summary)
    } catch {
      this.queue.unshift(...batch)
    }
  }

  private alert(message: string, severity: CodingProctorSeverity) {
    this.onAlert?.(message, severity)
  }
}

export type { ProctorPhase }
