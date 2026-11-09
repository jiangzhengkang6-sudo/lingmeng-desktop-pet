export type VoiceActivityPhase = 'waiting' | 'speaking'

export type VoiceActivityStopReason = 'silence' | 'maximum-duration'

export type VoiceActivityDecision = {
  phase: VoiceActivityPhase
  energy: number
  peak: number
  threshold: number
  noiseFloor: number
  voiced: boolean
  speechMs: number
  silenceMs: number
  shouldStop: boolean
  stopReason?: VoiceActivityStopReason
}

export type VoiceActivityDetectorOptions = {
  activationThreshold?: number
  activationMs?: number
  minimumSpeechMs?: number
  silenceMs?: number
  maximumSpeechMs?: number
  noiseCalibrationMs?: number
  noiseMarginMultiplier?: number
  maximumAdaptiveThreshold?: number
  now?: () => number
}

export function calculateFrameRms(samples: Float32Array): number {
  if (samples.length === 0) return 0
  let sum = 0
  for (let index = 0; index < samples.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, samples[index]))
    sum += sample * sample
  }
  return Math.sqrt(sum / samples.length)
}

export class VoiceActivityDetector {
  private readonly activationThreshold: number
  private readonly activationMs: number
  private readonly requiredSilenceMs: number
  private readonly minimumSpeechMs: number
  private readonly maximumSpeechMs: number
  private readonly initialNoiseCalibrationMs: number
  private readonly noiseMarginMultiplier: number
  private readonly maximumAdaptiveThreshold: number
  private readonly now: () => number

  private noiseCalibrationRemainingMs: number
  private noiseFloor: number | null = null
  private phase: VoiceActivityPhase = 'waiting'
  private firstVoicedAt: number | null = null
  private lastVoicedAt: number | null = null
  private voicedDurationMs = 0
  private silenceDurationMs = 0
  private peakEnergy = 0
  private stopped = false
  private stopReason: VoiceActivityStopReason | undefined

  constructor(options: VoiceActivityDetectorOptions = {}) {
    this.activationThreshold = options.activationThreshold ?? 0.018
    this.activationMs = options.activationMs ?? 180
    this.requiredSilenceMs = options.silenceMs ?? 900
    this.minimumSpeechMs = options.minimumSpeechMs ?? 320
    this.maximumSpeechMs = options.maximumSpeechMs ?? 15_000
    this.initialNoiseCalibrationMs = options.noiseCalibrationMs ?? 700
    this.noiseCalibrationRemainingMs = this.initialNoiseCalibrationMs
    this.noiseMarginMultiplier = options.noiseMarginMultiplier ?? 2.4
    this.maximumAdaptiveThreshold = options.maximumAdaptiveThreshold ?? 0.09
    this.now = options.now ?? (() => performance.now())
  }

  process(samples: Float32Array, sampleRate: number): VoiceActivityDecision {
    const energy = calculateFrameRms(samples)
    const frameMs = sampleRate > 0 ? samples.length * 1000 / sampleRate : 0
    const timestamp = this.now()
    const baseThreshold = this.currentThreshold(energy, frameMs, this.phase === 'waiting')
    const voiced = energy >= baseThreshold
    this.peakEnergy = Math.max(this.peakEnergy, energy)

    if (!this.stopped) {
      if (this.phase === 'waiting') {
        if (voiced) {
          if (this.firstVoicedAt === null) this.firstVoicedAt = timestamp
          this.voicedDurationMs += frameMs
          if (this.voicedDurationMs >= this.activationMs) {
            this.phase = 'speaking'
            this.firstVoicedAt = timestamp - this.voicedDurationMs
            this.lastVoicedAt = timestamp
            this.silenceDurationMs = 0
          }
        } else {
          this.voicedDurationMs = 0
          this.firstVoicedAt = null
        }
      } else {
        if (voiced) {
          this.voicedDurationMs += frameMs
          this.lastVoicedAt = timestamp
          this.silenceDurationMs = 0
        } else {
          const silenceStart = this.lastVoicedAt ?? timestamp
          this.silenceDurationMs += frameMs
          const silenceGap = this.silenceMsWithoutGaps(silenceStart, timestamp)
          if (this.voicedDurationMs < this.minimumSpeechMs && silenceGap >= this.requiredSilenceMs) {
            this.reset(Boolean(this.peakEnergy))
          } else if (
            this.voicedDurationMs >= this.minimumSpeechMs
            && silenceGap >= this.requiredSilenceMs
          ) {
            this.stopped = true
            this.stopReason = 'silence'
          }
        }

        const startedAt = this.firstVoicedAt ?? timestamp
        if (timestamp - startedAt >= this.maximumSpeechMs && this.voicedDurationMs >= this.minimumSpeechMs) {
          this.stopped = true
          this.stopReason = 'maximum-duration'
        }
      }
    }

    return {
      phase: this.phase,
      energy,
      peak: this.peakEnergy,
      threshold: baseThreshold,
      noiseFloor: this.noiseFloor ?? 0,
      voiced,
      speechMs: Math.max(0, Math.round(this.voicedDurationMs)),
      silenceMs: Math.max(0, Math.round(this.silenceDurationMs)),
      shouldStop: this.stopped,
      stopReason: this.stopReason,
    }
  }

  reset(keepPeak = false): void {
    this.phase = 'waiting'
    this.firstVoicedAt = null
    this.lastVoicedAt = null
    this.voicedDurationMs = 0
    this.silenceDurationMs = 0
    this.stopped = false
    this.stopReason = undefined
    this.noiseCalibrationRemainingMs = this.initialNoiseCalibrationMs
    this.noiseFloor = null
    if (!keepPeak) this.peakEnergy = 0
  }

  private currentThreshold(energy: number, frameMs: number, canCalibrate: boolean): number {
    if (canCalibrate && this.noiseCalibrationRemainingMs > 0) {
      const weight = Math.min(1, frameMs / Math.max(1, this.noiseCalibrationRemainingMs))
      this.noiseFloor = this.noiseFloor === null
        ? energy
        : this.noiseFloor * (1 - weight) + energy * weight
      this.noiseCalibrationRemainingMs = Math.max(0, this.noiseCalibrationRemainingMs - frameMs)
    }
    const adaptive = this.noiseFloor === null
      ? this.activationThreshold
      : Math.max(this.activationThreshold, this.noiseFloor * this.noiseMarginMultiplier + 0.004)
    return Math.min(adaptive, this.maximumAdaptiveThreshold)
  }

  private silenceMsWithoutGaps(silenceStart: number, timestamp: number) {
    return Math.max(0, timestamp - silenceStart)
  }
}
