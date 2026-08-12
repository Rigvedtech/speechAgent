/**
 * Pre-recorded proctor clips (no TTS API cost at runtime).
 * Files live in frontend/public/proctor/
 */

export type ProctorClip =
  | 'warning'
  | 'tab-switch'
  | 'multi-face'
  | 'face-missing'
  | 'locked'
  | 'auto-submit'
  | 'camera-lost'
  | 'continue'
  | 'fullscreen'
  | 'fullscreen-final'

const CLIP_SRC: Record<ProctorClip, string> = {
  warning: '/proctor/warning.mp3',
  'tab-switch': '/proctor/tab-switch.mp3',
  'multi-face': '/proctor/multi-face.mp3',
  'face-missing': '/proctor/face-missing.mp3',
  locked: '/proctor/locked.mp3',
  'auto-submit': '/proctor/auto-submit.mp3',
  'camera-lost': '/proctor/camera-lost.mp3',
  continue: '/proctor/continue.mp3',
  fullscreen: '/proctor/fullscreen.mp3',
  'fullscreen-final': '/proctor/fullscreen-final.mp3',
}

let current: HTMLAudioElement | null = null
let unlocked = false

/** Call once from a user gesture (Start coding round) so autoplay is allowed. */
export function unlockProctorAudio() {
  unlocked = true
  try {
    const a = new Audio(CLIP_SRC.warning)
    a.volume = 0.01
    void a
      .play()
      .then(() => {
        a.pause()
        a.currentTime = 0
      })
      .catch(() => undefined)
  } catch {
    // ignore
  }
}

export function stopProctorAudio() {
  if (current) {
    try {
      current.pause()
      current.currentTime = 0
    } catch {
      // ignore
    }
    current = null
  }
}

export function playProctorClip(clip: ProctorClip): void {
  if (typeof Audio === 'undefined') return
  stopProctorAudio()
  try {
    const audio = new Audio(CLIP_SRC[clip])
    audio.volume = 0.9
    current = audio
    const p = audio.play()
    if (p && typeof p.catch === 'function') {
      p.catch(() => {
        if (!unlocked) return
      })
    }
  } catch {
    // ignore
  }
}
