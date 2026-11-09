import { describe, expect, it, vi } from 'vitest'
import { ToolClient, ToolClientError } from './ToolClient'

describe('ToolClient', () => {
  it('lists tools and sends structured executions', async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify([{ name: 'get_time' }]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        call_id: 'tool-1',
        tool_name: 'get_time',
        risk_level: 'low',
        status: 'success',
        approval: 'auto_approved',
        requires_confirmation: false,
        audit_id: 'audit-1',
        created_at: '2026-09-09T00:00:00Z',
      }), { status: 200 }))
    const client = new ToolClient({ baseUrl: 'http://127.0.0.1:8000', fetchImpl })

    await expect(client.listTools()).resolves.toEqual([{ name: 'get_time' }])
    await expect(client.execute('get_time', {}, 'session-1')).resolves.toMatchObject({ status: 'success' })
    expect(fetchImpl).toHaveBeenLastCalledWith(
      'http://127.0.0.1:8000/api/tools/execute',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ tool_name: 'get_time', arguments: {}, session_id: 'session-1' }),
      }),
    )
  })

  it('surfaces gateway errors', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: { code: 'OWNER_VERIFICATION_REQUIRED', message: '请先完成主人身份验证' },
    }), { status: 403 }))
    const client = new ToolClient({ baseUrl: 'http://127.0.0.1:8000', fetchImpl })

    await expect(client.execute('search_files', {}, 'session-1'))
      .rejects.toEqual(new ToolClientError('请先完成主人身份验证'))
  })

  it('sends an optional idempotency key for tool execution', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      call_id: 'tool-1',
      tool_name: 'open_file',
      risk_level: 'medium',
      status: 'pending',
      approval: 'pending',
      requires_confirmation: true,
      audit_id: 'audit-1',
      created_at: '2026-09-09T00:00:00Z',
    }), { status: 200 }))
    const client = new ToolClient({ baseUrl: 'http://127.0.0.1:8000', fetchImpl })

    await client.execute('open_file', { path: 'C:/demo.txt' }, 'session-1', 'key-001')

    expect(fetchImpl).toHaveBeenLastCalledWith(
      'http://127.0.0.1:8000/api/tools/execute',
      expect.objectContaining({
        body: JSON.stringify({
          tool_name: 'open_file',
          arguments: { path: 'C:/demo.txt' },
          session_id: 'session-1',
          idempotency_key: 'key-001',
        }),
      }),
    )
  })
})
