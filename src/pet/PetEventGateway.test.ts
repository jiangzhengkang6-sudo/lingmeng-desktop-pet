import { describe, expect, it, vi } from 'vitest'
import { PetEventGateway } from './PetEventGateway'

describe('PetEventGateway', () => {
  it('publishes a normalized pet.action event to the local gateway', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(
      JSON.stringify({ ok: true, delivered: 1 }),
      { status: 200, headers: { 'content-type': 'application/json' } },
    ))
    const gateway = new PetEventGateway({
      baseUrl: 'http://127.0.0.1:8000/',
      fetchImpl,
    })

    const result = await gateway.publish({
      actionId: 'speaking',
      emotion: 'happy',
      mouthMode: 'open',
      durationMs: 1000,
      interruptible: true,
    })

    expect(result).toEqual({ ok: true, delivered: 1 })
    expect(fetchImpl).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/pet/events',
      expect.objectContaining({
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          type: 'pet.action',
          actionId: 'speaking',
          emotion: 'happy',
          mouthMode: 'open',
          durationMs: 1000,
          interruptible: true,
        }),
      }),
    )
    expect(fetchImpl.mock.contexts[0]).toBe(globalThis)
  })

  it('does not call fetch when disabled', async () => {
    const fetchImpl = vi.fn<typeof fetch>()
    const gateway = new PetEventGateway({
      baseUrl: 'http://127.0.0.1:8000',
      enabled: false,
      fetchImpl,
    })

    await expect(gateway.publish({ actionId: 'idle' })).resolves.toEqual({ ok: true, delivered: 0 })
    expect(fetchImpl).not.toHaveBeenCalled()
  })

  it('contains gateway failures instead of throwing into the UI', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockRejectedValue(new Error('offline'))
    const gateway = new PetEventGateway({
      baseUrl: 'http://127.0.0.1:8000',
      fetchImpl,
    })

    await expect(gateway.publish({ actionId: 'idle' })).resolves.toEqual({
      ok: false,
      message: '桌宠事件网关不可用',
    })
  })
})
