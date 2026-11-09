import { describe, expect, it } from 'vitest'
import { readSpeechConfig } from './SpeechConfig'

describe('readSpeechConfig', () => {
  it('uses speech-2.8-hd and the local gateway by default', () => {
    expect(readSpeechConfig({})).toMatchObject({
      gatewayUrl: 'http://127.0.0.1:8000',
      model: 'speech-2.8-hd',
      enabled: false,
      configured: true,
    })
  })

  it('normalizes the gateway URL and reads the enable flag', () => {
    expect(readSpeechConfig({
      VITE_SPEECH_GATEWAY_URL: ' http://localhost:9000/// ',
      VITE_SPEECH_MODEL: 'speech-2.8-hd',
      VITE_SPEECH_ENABLED: 'true',
    })).toEqual({
      gatewayUrl: 'http://localhost:9000',
      model: 'speech-2.8-hd',
      enabled: true,
      configured: true,
    })
  })
})
