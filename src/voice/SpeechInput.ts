import { normalizePetAction } from '../pet/petActions'
import type { PetAction } from '../types/pet'

export type VoiceInputLifecycle = 'recording' | 'recognizing' | 'success' | 'failure'

export type VoiceInputEvent = {
  type: 'voice-input'
  text: string
  language?: string
  traceId?: string
  receivedAt: string
}

export type VoiceInputEventInput = {
  text: string
  language?: string | null
  traceId?: string | null
}

const lifecycleActions: Record<VoiceInputLifecycle, PetAction> = {
  recording: 'listening',
  recognizing: 'thinking',
  success: 'idle',
  failure: 'displeased',
}

function optionalValue(value?: string | null) {
  const normalized = value?.trim()
  return normalized || undefined
}

export function voiceInputActionFor(lifecycle: VoiceInputLifecycle): PetAction {
  return normalizePetAction(lifecycleActions[lifecycle]) as PetAction
}

export function createVoiceInputEvent(
  input: VoiceInputEventInput,
  now: () => Date = () => new Date(),
): VoiceInputEvent | null {
  const text = input.text.trim()
  if (!text) return null

  return {
    type: 'voice-input',
    text,
    language: optionalValue(input.language),
    traceId: optionalValue(input.traceId),
    receivedAt: now().toISOString(),
  }
}
