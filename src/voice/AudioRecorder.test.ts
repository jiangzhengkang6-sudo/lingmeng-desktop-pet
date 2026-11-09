import { describe, expect, it, vi } from 'vitest'
import { AudioRecorder, encodePcm16Wav, resampleMono } from './AudioRecorder'

describe('AudioRecorder helpers', () => {
  it('resamples mono audio to the target rate', () => {
    const output = resampleMono(new Float32Array([0, 1, 0, -1]), 4, 2)

    expect(output.length).toBe(2)
    expect(output[0]).toBe(0)
    expect(output[1]).toBe(0)
  })

  it('encodes mono PCM16 WAV data', async () => {
    const blob = encodePcm16Wav(new Float32Array([-1, 0, 1]))
    const bytes = new Uint8Array(await blob.arrayBuffer())

    expect(blob.type).toBe('audio/wav')
    expect(new TextDecoder().decode(bytes.slice(0, 4))).toBe('RIFF')
    expect(new TextDecoder().decode(bytes.slice(8, 12))).toBe('WAVE')
    expect(bytes.byteLength).toBe(50)
    expect(bytes[44]).toBe(0)
    expect(bytes[45]).toBe(128)
  })

  it('keeps the enrollment WAV format below its 30-second data limit', async () => {
    const samples = new Float32Array(16_000 * 30)
    const blob = encodePcm16Wav(samples)

    expect(blob.size).toBeLessThanOrEqual(1_500_000)
    expect(blob.size).toBe(960_044)
  })
})


describe('AudioRecorder realtime samples', () => {
  it('delivers mono frames while recording', async () => {
    const frame = new Float32Array([0, 0.2, 0, -0.2])
    const stopTrack = vi.fn()
    const handlerBox: { current: ((event: { inputBuffer: { getChannelData: () => Float32Array } }) => void) | null } = { current: null }
    const processor = {
      connect: vi.fn(),
      disconnect: vi.fn(),
      onaudioprocess: null as ((event: { inputBuffer: { getChannelData: () => Float32Array } }) => void) | null,
    }
    const source = { connect: vi.fn(), disconnect: vi.fn() }
    const gain = { connect: vi.fn(), disconnect: vi.fn(), gain: { value: 1 } }
    const context = {
      sampleRate: 100,
      resume: vi.fn(async () => undefined),
      createMediaStreamSource: vi.fn(() => source),
      createScriptProcessor: vi.fn(() => {
        handlerBox.current = (event) => processor.onaudioprocess?.(event)
        return processor
      }),
      createGain: vi.fn(() => gain),
      destination: {},
      close: vi.fn(async () => undefined),
      state: 'running',
    }
    const mediaDevices = {
      getUserMedia: vi.fn(async () => ({
        getTracks: () => [{ stop: stopTrack }],
      })),
    }
    const onSamples = vi.fn()
    const recorder = new AudioRecorder(
      mediaDevices as unknown as MediaDevices,
      (() => context) as unknown as () => AudioContext,
    )

    await recorder.start({ onSamples })
    handlerBox.current?.({ inputBuffer: { getChannelData: () => frame } })
    const audio = await recorder.stop()

    expect(onSamples).toHaveBeenCalledWith(frame, 100)
    expect(audio.type).toBe('audio/wav')
    expect(stopTrack).toHaveBeenCalledOnce()
    expect(processor.connect).toHaveBeenCalled()
  })
})
