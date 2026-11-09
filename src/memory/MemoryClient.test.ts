import { describe, expect, it, vi } from 'vitest'
import { MemoryClient, MemoryClientError } from './MemoryClient'

describe('MemoryClient', () => {
  it('confirms an edited candidate through the local gateway', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(
      JSON.stringify({
        id: 'mem-1',
        source_session_id: 'session-1',
        content: '称呼我为小明',
        category: 'preference',
        source: 'user_confirmed_conversation',
        confidence: 1,
        created_at: '2026-09-09T00:00:00+00:00',
        updated_at: '2026-09-09T00:00:00+00:00',
      }),
      { status: 200, headers: { 'content-type': 'application/json' } },
    ))
    const client = new MemoryClient({ baseUrl: 'http://127.0.0.1:8000/', fetchImpl })

    await expect(client.confirmCandidate('candidate 1', {
      content: '  称呼我为小明  ',
      category: 'preference',
    })).resolves.toMatchObject({ id: 'mem-1', content: '称呼我为小明' })
    expect(fetchImpl).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/memories/candidates/candidate%201/confirm',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ content: '称呼我为小明', category: 'preference' }),
      }),
    )
  })

  it('does not send blank memory edits to the gateway', async () => {
    const fetchImpl = vi.fn<typeof fetch>()
    const client = new MemoryClient({ baseUrl: 'http://127.0.0.1:8000', fetchImpl })

    expect(() => client.updateMemory('mem-1', {
      content: '   ',
      category: 'semantic',
    })).toThrow(new MemoryClientError('记忆内容不能为空'))
    expect(fetchImpl).not.toHaveBeenCalled()
  })
})
