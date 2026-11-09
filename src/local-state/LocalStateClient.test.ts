import { describe, expect, it, vi } from 'vitest'
import { LocalStateClient, LocalStateClientError } from './LocalStateClient'

function futureLocalDateTime(minutes: number): string {
  const date = new Date(Date.now() + minutes * 60_000)
  const pad = (value: number) => String(value).padStart(2, '0')
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
  ].join('-') + `T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

describe('LocalStateClient', () => {
  it('creates a future reminder with an ISO timestamp', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(
      JSON.stringify({ id: 'rem-1', status: 'pending' }),
      { status: 200, headers: { 'content-type': 'application/json' } },
    ))
    const client = new LocalStateClient({ baseUrl: 'http://127.0.0.1:8000/', fetchImpl })
    const future = futureLocalDateTime(5)

    await expect(client.createReminder({
      title: '  喝水  ',
      remindAt: future,
      sessionId: 'session-1',
    })).resolves.toMatchObject({ id: 'rem-1' })
    expect(fetchImpl).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/reminders',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"title":"喝水"'),
      }),
    )
  })

  it('does not send reminders scheduled in the past', () => {
    const fetchImpl = vi.fn<typeof fetch>()
    const client = new LocalStateClient({ baseUrl: 'http://127.0.0.1:8000', fetchImpl })

    expect(() => client.createReminder({
      title: '测试',
      remindAt: '2020-01-01T00:00',
      sessionId: 'session-1',
    })).toThrow(new LocalStateClientError('提醒时间必须晚于当前时间'))
    expect(fetchImpl).not.toHaveBeenCalled()
  })

  it('updates persisted display preferences through the owner-only route', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(
      JSON.stringify({ language: 'ja-JP', diagnostics_enabled: false }),
      { status: 200, headers: { 'content-type': 'application/json' } },
    ))
    const client = new LocalStateClient({ baseUrl: 'http://127.0.0.1:8000', fetchImpl })

    await client.updateSettings({
      language: 'ja-JP',
      personality: 'warm',
      voice_preference: 'default',
      memory_policy: 'ask_before_save',
      diagnostics_enabled: false,
    })
    expect(fetchImpl).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/settings',
      expect.objectContaining({ method: 'PATCH' }),
    )
  })
})
