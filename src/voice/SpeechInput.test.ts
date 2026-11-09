import { describe, expect, it } from 'vitest'
import { createVoiceInputEvent, voiceInputActionFor } from './SpeechInput'

describe('voice input results', () => {
  it('creates a normalized Agent-independent result event from final speech text', () => {
    const event = createVoiceInputEvent(
      {
        text: '  你吃饭了吗？  ',
        language: ' zh-CN ',
        traceId: ' trace-123 ',
      },
      () => new Date('2026-09-03T08:00:00.000Z'),
    )

    expect(event).toEqual({
      type: 'voice-input',
      text: '你吃饭了吗？',
      language: 'zh-CN',
      traceId: 'trace-123',
      receivedAt: '2026-09-03T08:00:00.000Z',
    })
  })

  it('does not create an event for an empty final result', () => {
    expect(createVoiceInputEvent({ text: '   ', language: 'zh-CN' })).toBeNull()
  })

  it('maps the full voice lifecycle to pet actions', () => {
    expect(voiceInputActionFor('recording')).toBe('listening')
    expect(voiceInputActionFor('recognizing')).toBe('thinking')
    expect(voiceInputActionFor('success')).toBe('idle')
    expect(voiceInputActionFor('failure')).toBe('displeased')
  })
})
