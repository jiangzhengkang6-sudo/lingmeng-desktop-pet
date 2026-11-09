export type SpeechEnvironment = Record<string, unknown>

export type SpeechRuntimeConfig = {
  gatewayUrl: string
  model: string
  enabled: boolean
  configured: boolean
}

function readString(environment: SpeechEnvironment, key: string, fallback = '') {
  const value = environment[key]
  return typeof value === 'string' ? value.trim() : fallback
}

export function readSpeechConfig(environment: SpeechEnvironment = import.meta.env): SpeechRuntimeConfig {
  const gatewayUrl = readString(environment, 'VITE_SPEECH_GATEWAY_URL', 'http://127.0.0.1:8000')
  const model = readString(environment, 'VITE_SPEECH_MODEL', 'speech-2.8-hd')
  const enabled = readString(environment, 'VITE_SPEECH_ENABLED') === 'true'

  return {
    gatewayUrl: gatewayUrl.replace(/\/+$/, ''),
    model,
    enabled,
    configured: Boolean(gatewayUrl && model),
  }
}
