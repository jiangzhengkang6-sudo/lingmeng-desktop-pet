import { describe, expect, it, vi } from 'vitest'
import { SpeechPlaybackCoordinator } from './SpeechPlaybackCoordinator'

function createCoordinator() {
  const synthesize = vi.fn()
  const play = vi.fn()
  const events: string[] = []
  const mouths: string[] = []
  const coordinator = new SpeechPlaybackCoordinator(
    { synthesize },
    { play, stop: vi.fn() },
    {
      onState: (state) => events.push(`state:${state}`),
      onSpeaking: () => events.push('speaking'),
      onIdle: () => events.push('idle'),
      onMouthMode: (mode) => mouths.push(mode),
      onError: (error) => events.push(`error:${error.message}`),
    },
  )
  return { coordinator, synthesize, play, events, mouths }
}

describe('SpeechPlaybackCoordinator', () => {
  it('synthesizes Agent text with its response language and plays it', async () => {
    const { coordinator, synthesize, play, events, mouths } = createCoordinator()
    const response = { audioBase64: 'audio' }
    synthesize.mockResolvedValue(response)
    play.mockImplementation(async (_response, callbacks) => {
      callbacks.onStart?.()
      callbacks.onMouthMode?.('half-open', 0.1)
      callbacks.onEnd?.()
    })

    await expect(coordinator.playText('  你好  ', 'zh-CN')).resolves.toEqual({ status: 'completed' })
    expect(synthesize).toHaveBeenCalledWith({ text: '你好', language: 'zh-CN' })
    expect(play).toHaveBeenCalledWith(response, expect.any(Object))
    expect(events).toEqual(['state:synthesizing', 'speaking', 'state:playing', 'speaking', 'state:idle', 'idle'])
    expect(mouths).toEqual(['closed', 'closed', 'half-open', 'closed'])
  })

  it('does not let an older synthesis response start playback after a newer request', async () => {
    const { coordinator, synthesize, play } = createCoordinator()
    let resolveFirst!: (value: { audioBase64: string }) => void
    const first = new Promise<{ audioBase64: string }>((resolve) => { resolveFirst = resolve })
    synthesize.mockReturnValueOnce(first).mockResolvedValueOnce({ audioBase64: 'new' })
    play.mockResolvedValue(undefined)

    const firstRequest = coordinator.playText('旧回复', 'zh-CN')
    const secondRequest = coordinator.playText('新回复', 'en-US')
    resolveFirst({ audioBase64: 'old' })

    await expect(secondRequest).resolves.toEqual({ status: 'completed' })
    await expect(firstRequest).resolves.toEqual({ status: 'superseded' })
    expect(play).toHaveBeenCalledTimes(1)
    expect(synthesize).toHaveBeenNthCalledWith(2, { text: '新回复', language: 'en-US' })
  })

  it('reports playback failure without throwing it back to the caller', async () => {
    const { coordinator, synthesize, play, events, mouths } = createCoordinator()
    synthesize.mockResolvedValue({ audioBase64: 'audio' })
    play.mockRejectedValue(new Error('audio unavailable'))

    await expect(coordinator.playText('稍后再试', 'zh-CN')).resolves.toEqual({
      status: 'error',
      error: expect.any(Error),
    })
    expect(events).toContain('error:audio unavailable')
    expect(events.at(-1)).toBe('idle')
    expect(mouths.at(-1)).toBe('closed')
  })
})
