import { describe, expect, it, vi } from 'vitest'
import { AudioLipSyncPlayer, calculateRmsEnergy, energyToMouthMode, hexToBytes } from './AudioLipSyncPlayer'

describe('AudioLipSyncPlayer helpers', () => {
  it('decodes hexadecimal audio bytes', () => {
    expect([...hexToBytes('0x00  ')]).toEqual([0])
    expect([...hexToBytes('00ff10')]).toEqual([0, 255, 16])
  })

  it('rejects malformed hexadecimal data', () => {
    expect(() => hexToBytes('abc')).toThrow()
    expect(() => hexToBytes('not-audio')).toThrow()
  })

  it('maps waveform energy to three mouth modes', () => {
    expect(energyToMouthMode(0)).toBe('closed')
    expect(energyToMouthMode(0.1)).toBe('half-open')
    expect(energyToMouthMode(0.3)).toBe('open')
  })

  it('calculates RMS energy around the audio midpoint', () => {
    expect(calculateRmsEnergy(new Uint8Array([128, 128, 128]))).toBe(0)
    expect(calculateRmsEnergy(new Uint8Array([0, 255]))).toBeGreaterThan(0.9)
  })
})


describe('AudioLipSyncPlayer fallback playback', () => {
  it('uses HTMLAudioElement when WebAudio decoding fails', async () => {
    class BrokenAudioContext {
      destination = {}
      resume = vi.fn(async () => undefined)
      decodeAudioData = vi.fn(async () => { throw new Error('decode failed') })
      createBufferSource = vi.fn()
      createAnalyser = vi.fn()
    }
    const element = {
      src: '',
      onended: null as null | (() => void),
      onerror: null as null | (() => void),
      play: vi.fn(async () => {
        setTimeout(() => element.onended?.(), 0)
      }),
      pause: vi.fn(),
      load: vi.fn(),
    }
    const response = { audioHex: Buffer ? '' : '', mimeType: 'audio/mpeg' }
    // Minimal ID3-like MP3 header represented as hex.
    response.audioHex = '4944330400'
    const player = new AudioLipSyncPlayer(
      (() => new BrokenAudioContext()) as unknown as () => AudioContext,
      fetch,
      (() => element) as unknown as () => never,
    )

    await player.play(response as never)

    expect(element.play).toHaveBeenCalledOnce()
    expect(element.src).toContain('blob:')
  })
})

