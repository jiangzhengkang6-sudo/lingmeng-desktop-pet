import { describe, expect, it, vi } from 'vitest'
import { IdentityClient, IdentityClientError } from './IdentityClient'

describe('IdentityClient', () => {
  it('reads identity status and sends mock verification commands', async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        status: 'unknown',
        adapter: 'mock',
        can_read_private_memory: false,
        can_use_tools: false,
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        status: 'owner_verified',
        adapter: 'mock',
        can_read_private_memory: true,
        can_use_tools: true,
      }), { status: 200 }))

    const client = new IdentityClient({ baseUrl: 'http://127.0.0.1:8000/', fetchImpl })
    expect((await client.getStatus()).status).toBe('unknown')
    expect((await client.mockVerify('owner')).status).toBe('owner_verified')
    expect(JSON.parse(fetchImpl.mock.calls[1][1].body as string)).toEqual({ sample: 'owner' })
  })

  it('surfaces gateway errors', async () => {
    const client = new IdentityClient({
      baseUrl: 'http://127.0.0.1:8000',
      fetchImpl: vi.fn().mockResolvedValue(new Response(JSON.stringify({
        detail: { message: '请先完成主人身份验证' },
      }), { status: 403 })),
    })

    await expect(client.getStatus()).rejects.toEqual(new IdentityClientError('请先完成主人身份验证'))
  })

  it('sends an explicitly confirmed WAV registration through the local gateway', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      voiceprintId: 'voiceprint-123',
      audioName: 'desktop-owner',
      algorithmVersion: 2,
      sceneUpdated: true,
    }), { status: 200 }))
    const client = new IdentityClient({ baseUrl: 'http://127.0.0.1:8000', fetchImpl })
    const audio = new File(['pcm-wav'], 'owner.wav', { type: 'audio/wav' })

    await expect(client.registerRtcVoiceprint(audio, true)).resolves.toMatchObject({
      voiceprintId: 'voiceprint-123',
      sceneUpdated: true,
    })
    expect(fetchImpl).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/identity/rtc/voiceprints/register',
      expect.objectContaining({ method: 'POST', body: expect.any(FormData) }),
    )
    const formData = fetchImpl.mock.calls[0][1].body as FormData
    expect(formData.get('audio')).toBe(audio)
    expect(formData.get('confirmed')).toBe('true')
  })

  it('starts and stops an explicitly confirmed RTC voiceprint session', async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        taskId: 'task-123',
        appId: 'rtc-app',
        roomId: 'room-1',
        requestId: 'request-start',
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        taskId: 'task-123',
        appId: 'rtc-app',
        roomId: 'room-1',
        requestId: 'request-stop',
      }), { status: 200 }))
    const client = new IdentityClient({ baseUrl: 'http://127.0.0.1:8000', fetchImpl })

    await expect(client.startRtcVoiceprintSession({
      roomId: 'room-1',
      agentUserId: 'pet-agent',
      targetUserIds: ['desktop-owner'],
      confirmed: true,
    })).resolves.toMatchObject({ taskId: 'task-123' })
    await expect(client.stopRtcVoiceprintSession('task-123')).resolves.toMatchObject({ taskId: 'task-123' })

    expect(fetchImpl.mock.calls[0][0]).toBe('http://127.0.0.1:8000/api/identity/rtc/sessions')
    expect(JSON.parse(fetchImpl.mock.calls[0][1].body as string)).toEqual({
      roomId: 'room-1',
      agentUserId: 'pet-agent',
      targetUserIds: ['desktop-owner'],
      confirmed: true,
    })
    expect(fetchImpl.mock.calls[1][0]).toBe('http://127.0.0.1:8000/api/identity/rtc/sessions/task-123')
    expect(fetchImpl.mock.calls[1][1]).toEqual(expect.objectContaining({ method: 'DELETE' }))
  })

  it('rejects an empty RTC task id before making a request', async () => {
    const fetchImpl = vi.fn()
    const client = new IdentityClient({ baseUrl: 'http://127.0.0.1:8000', fetchImpl })

    await expect(client.stopRtcVoiceprintSession('  ')).rejects.toEqual(
      new IdentityClientError('RTC 任务标识为空'),
    )
    expect(fetchImpl).not.toHaveBeenCalled()
  })
})
