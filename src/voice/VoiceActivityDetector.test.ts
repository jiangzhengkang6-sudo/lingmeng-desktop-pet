import { afterEach, describe, expect, it, vi } from 'vitest'
import { VoiceActivityDetector, calculateFrameRms } from './VoiceActivityDetector'

afterEach(() => vi.useRealTimers())

function silentFrame(length = 480) {
  return new Float32Array(length)
}

function voicedFrame(length = 480, amplitude = 0.1) {
  return Float32Array.from({ length }, (_, index) => (index % 2 === 0 ? amplitude : -amplitude))
}

describe('VoiceActivityDetector', () => {
  it('calculates mono RMS energy', () => {
    expect(calculateFrameRms(new Float32Array([0.1, -0.1]))).toBeCloseTo(0.1)
    expect(calculateFrameRms(new Float32Array(0))).toBe(0)
  })

  it('waits for sustained speech before entering speaking phase', () => {
    vi.useFakeTimers()
    let now = 0
    const detector = new VoiceActivityDetector({
      activationMs: 20,
      minimumSpeechMs: 20,
      silenceMs: 200,
      now: () => now,
    })

    const first = detector.process(voicedFrame(480, 0.1), 48_000)
    expect(first.phase).toBe('waiting')
    now += 10
    const second = detector.process(voicedFrame(480, 0.1), 48_000)
    expect(second.phase).toBe('speaking')
    expect(second.shouldStop).toBe(false)
  })

  it('does not submit a short noise burst after the following silence', () => {
    vi.useFakeTimers()
    let now = 0
    const detector = new VoiceActivityDetector({
      activationMs: 20,
      minimumSpeechMs: 300,
      silenceMs: 200,
      now: () => now,
    })

    detector.process(voicedFrame(), 48_000)
    now = 20
    detector.process(voicedFrame(), 48_000)
    expect(detector.process(silentFrame(), 48_000).phase).toBe('speaking')
    now = 120
    detector.process(silentFrame(), 48_000)
    now = 240
    const afterNoise = detector.process(silentFrame(), 48_000)

    expect(afterNoise.phase).toBe('waiting')
    expect(afterNoise.shouldStop).toBe(false)
  })

  it('stops after a real utterance followed by silence', () => {
    vi.useFakeTimers()
    let now = 0
    const detector = new VoiceActivityDetector({
      activationMs: 10,
      minimumSpeechMs: 300,
      silenceMs: 200,
      now: () => now,
    })

    for (let index = 0; index < 4; index += 1) {
      detector.process(voicedFrame(4_800), 48_000)
      now += 100
    }
    detector.process(silentFrame(4_800), 48_000)
    now += 100
    detector.process(silentFrame(4_800), 48_000)
    now += 100
    const decision = detector.process(silentFrame(4_800), 48_000)

    expect(decision.shouldStop).toBe(true)
    expect(decision.stopReason).toBe('silence')
    expect(decision.speechMs).toBeGreaterThanOrEqual(300)
  })

  it('ignores a single noise frame and caps real long utterances', () => {
    vi.useFakeTimers()
    let now = 0
    const detector = new VoiceActivityDetector({
      activationMs: 100,
      minimumSpeechMs: 300,
      maximumSpeechMs: 1000,
      now: () => now,
    })

    const noise = detector.process(voicedFrame(), 48_000)
    expect(noise.phase).toBe('waiting')
    now = 1000
    expect(detector.process(silentFrame(), 48_000).phase).toBe('waiting')

    for (let index = 0; index < 12; index += 1) {
      now += 100
      detector.process(voicedFrame(4_800), 48_000)
    }
    now += 100
    const capped = detector.process(voicedFrame(4_800), 48_000)
    expect(capped.phase).toBe('speaking')
    expect(capped.stopReason).toBe('maximum-duration')
  })
})
