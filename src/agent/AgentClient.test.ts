import { describe, expect, it, vi } from 'vitest'
import { AgentClient, AgentClientError } from './AgentClient'

class MockWebSocket {
  static readonly OPEN = 1
  static readonly CONNECTING = 0
  static instances: MockWebSocket[] = []
  readonly OPEN = MockWebSocket.OPEN
  readonly CONNECTING = MockWebSocket.CONNECTING
  readonly url: string
  readyState = MockWebSocket.CONNECTING
  onopen: (() => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null
  sent: string[] = []

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  send(payload: string) {
    this.sent.push(payload)
  }

  close() {
    this.readyState = 3
  }

  open() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.()
  }

  message(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent)
  }
}

describe('AgentClient', () => {
  it('uses the Agent WebSocket protocol and correlates the structured response', async () => {
    MockWebSocket.instances = []
    const client = new AgentClient({
      baseUrl: 'http://127.0.0.1:8000/',
      fetchImpl: vi.fn<typeof fetch>(),
      webSocketImpl: MockWebSocket as unknown as typeof WebSocket,
    })
    const request = client.chat({
      message: '  你好 ',
      language: 'zh-CN',
      sessionId: 'demo',
      ragCollection: 'character_knowledge',
    })
    const socket = MockWebSocket.instances[0]
    socket.open()
    expect(socket.url).toBe('ws://127.0.0.1:8000/api/agent/events')
    expect(JSON.parse(socket.sent[0])).toMatchObject({
      type: 'agent.message',
      session_id: 'demo',
      message: '你好',
      language: 'zh-CN',
      rag_collection: 'character_knowledge',
    })
    socket.message({
      type: 'agent.status',
      request_id: 'wrong-request',
      session_id: 'demo',
      status: 'thinking',
    })
    socket.message({
      type: 'agent.response',
      request_id: JSON.parse(socket.sent[0]).request_id,
      session_id: 'demo',
      response: {
        session_id: 'demo',
        text: '你好',
        language: 'zh-CN',
        emotion: 'calm',
        action_id: 'speaking',
        mouth_mode: 'half-open',
        requires_confirmation: false,
        tool_calls: [],
        trace_id: 'ws-1',
        sources: [],
        rag_status: 'disabled',
        memory_candidates: [],
      },
    })
    socket.message({
      type: 'pet.action',
      request_id: JSON.parse(socket.sent[0]).request_id,
      session_id: 'demo',
      action: { action_id: 'speaking', mouth_mode: 'half-open' },
    })
    socket.message({
      type: 'agent.status',
      request_id: JSON.parse(socket.sent[0]).request_id,
      session_id: 'demo',
      status: 'completed',
    })

    await expect(request).resolves.toMatchObject({ trace_id: 'ws-1' })
  })

  it('falls back to HTTP when the Agent WebSocket is unavailable', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(
      JSON.stringify({
        session_id: 'demo',
        text: '你好',
        language: 'zh-CN',
        emotion: 'calm',
        action_id: 'speaking',
        mouth_mode: 'half-open',
        requires_confirmation: false,
        tool_calls: [],
        trace_id: 'http-fallback',
        sources: [],
        rag_status: 'disabled',
        memory_candidates: [],
      }),
      { status: 200, headers: { 'content-type': 'application/json' } },
    ))
    class UnavailableWebSocket extends MockWebSocket {
      open() {
        this.onerror?.()
      }
    }
    MockWebSocket.instances = []
    const client = new AgentClient({
      baseUrl: 'http://127.0.0.1:8000',
      fetchImpl,
      webSocketImpl: UnavailableWebSocket as unknown as typeof WebSocket,
    })

    const request = client.chat({
      message: 'hello',
      language: 'en-US',
      sessionId: 'demo',
    })
    const socket = MockWebSocket.instances[0] as UnavailableWebSocket | undefined
    if (!socket) throw new Error('WebSocket mock was not created')
    socket.open()

    await expect(request).resolves.toMatchObject({ trace_id: 'http-fallback' })
    expect(fetchImpl).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/agent/chat',
      expect.objectContaining({ method: 'POST' }),
    )
  })


  it('uses direct HTTP for voice turns instead of waiting on Agent WebSocket', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(
      JSON.stringify({
        session_id: 'voice-demo',
        text: '我在。',
        language: 'zh-CN',
        emotion: 'calm',
        action_id: 'speaking',
        mouth_mode: 'half-open',
        requires_confirmation: false,
        tool_calls: [],
        trace_id: 'voice-http-1',
        sources: [],
        rag_status: 'disabled',
        memory_candidates: [],
      }),
      { status: 200, headers: { 'content-type': 'application/json' } },
    ))
    MockWebSocket.instances = []
    const client = new AgentClient({
      baseUrl: 'http://127.0.0.1:8000',
      fetchImpl,
      webSocketImpl: MockWebSocket as unknown as typeof WebSocket,
    })

    await client.chat({
      message: '下午好',
      language: 'zh-CN',
      sessionId: 'voice-demo',
      source: 'voice',
    })

    expect(MockWebSocket.instances).toHaveLength(0)
    expect(fetchImpl).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/agent/chat',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"source":"voice"'),
      }),
    )
  })

  it('delivers pet action events before resolving the completed response', async () => {
    MockWebSocket.instances = []
    const events: string[] = []
    const client = new AgentClient({
      baseUrl: 'http://127.0.0.1:8000',
      fetchImpl: vi.fn<typeof fetch>(),
      webSocketImpl: MockWebSocket as unknown as typeof WebSocket,
    })
    const request = client.chat({
      message: '说话',
      language: 'zh-CN',
      sessionId: 'demo',
    }, (event) => events.push(event.type))
    const socket = MockWebSocket.instances[0]
    socket.open()
    const requestId = JSON.parse(socket.sent[0]).request_id
    socket.message({
      type: 'agent.response',
      request_id: requestId,
      session_id: 'demo',
      response: {
        session_id: 'demo',
        text: '好的',
        language: 'zh-CN',
        emotion: 'calm',
        action_id: 'speaking',
        mouth_mode: 'half-open',
        requires_confirmation: false,
        tool_calls: [],
        trace_id: 'ws-action',
        sources: [],
        rag_status: 'disabled',
        memory_candidates: [],
      },
    })
    socket.message({
      type: 'pet.action',
      request_id: requestId,
      session_id: 'demo',
      action: { action_id: 'speaking', mouth_mode: 'half-open' },
    })
    expect(events).toEqual(['agent.response', 'pet.action'])
    let settled = false
    void request.then(() => { settled = true })
    await Promise.resolve()
    expect(settled).toBe(false)
    socket.message({
      type: 'agent.status',
      request_id: requestId,
      session_id: 'demo',
      status: 'completed',
    })
    await expect(request).resolves.toMatchObject({ trace_id: 'ws-action' })
  })

  it('rejects unknown WebSocket events instead of passing them to the UI', async () => {
    MockWebSocket.instances = []
    const client = new AgentClient({
      baseUrl: 'http://127.0.0.1:8000',
      fetchImpl: vi.fn<typeof fetch>(),
      webSocketImpl: MockWebSocket as unknown as typeof WebSocket,
    })
    const request = client.chat({
      message: 'invalid event',
      language: 'en-US',
      sessionId: 'demo',
    })
    const socket = MockWebSocket.instances[0]
    if (!socket) throw new Error('WebSocket mock was not created')
    socket.open()
    socket.message({
      type: 'agent.unknown',
      request_id: JSON.parse(socket.sent[0]).request_id,
      session_id: 'demo',
    })

    await expect(request).rejects.toEqual(new AgentClientError('Agent 返回格式无效'))
  })

  it('posts a text message and returns the structured agent response', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(
      JSON.stringify({
        session_id: 'demo',
        text: '你好',
        language: 'zh-CN',
        emotion: 'calm',
        action_id: 'speaking',
        mouth_mode: 'half-open',
        requires_confirmation: false,
        tool_calls: [],
        trace_id: 'mock-1',
        sources: [{
          document_id: 'source-1',
          filename: 'character.md',
          source_label: 'character guide',
          chunk_index: 0,
          score: 0.9,
        }],
        rag_status: 'used',
        memory_candidates: [],
      }),
      { status: 200, headers: { 'content-type': 'application/json' } },
    ))
    const client = new AgentClient({ baseUrl: 'http://127.0.0.1:8000/', fetchImpl })

    await expect(client.chat({
      message: '  你好 ',
      language: 'zh-CN',
      sessionId: 'demo',
      ragCollection: 'character_knowledge',
    })).resolves.toMatchObject({ action_id: 'speaking', trace_id: 'mock-1' })
    expect(fetchImpl).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/agent/chat',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          message: '你好',
          language: 'zh-CN',
          session_id: 'demo',
          source: 'text',
          rag_collection: 'character_knowledge',
        }),
      }),
    )
    expect(fetchImpl.mock.contexts[0]).toBe(globalThis)
  })

  it('surfaces gateway errors without leaking raw fetch failures', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockRejectedValue(new Error('offline'))
    const client = new AgentClient({ baseUrl: 'http://127.0.0.1:8000', fetchImpl })

    await expect(client.chat({
      message: 'hello',
      language: 'en-US',
      sessionId: 'demo',
    })).rejects.toEqual(new AgentClientError('文本对话网关不可用'))
  })

  it('uses the configured timeout for slow gateway responses', async () => {
    vi.useFakeTimers()
    try {
      const fetchImpl = vi.fn<typeof fetch>().mockImplementation((_input, init) => (
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => {
            reject(new DOMException('Aborted', 'AbortError'))
          })
        })
      ))
      const client = new AgentClient({
        baseUrl: 'http://127.0.0.1:8000',
        fetchImpl,
        timeoutMs: 25,
      })

      const request = client.chat({
        message: 'slow',
        language: 'en-US',
        sessionId: 'demo',
      })
      const assertion = expect(request).rejects.toEqual(new AgentClientError('文本对话请求超时'))
      await vi.advanceTimersByTimeAsync(25)

      await assertion
    } finally {
      vi.useRealTimers()
    }
  })

  it('rejects disabled clients before making a request', async () => {
    const fetchImpl = vi.fn<typeof fetch>()
    const client = new AgentClient({ baseUrl: 'http://127.0.0.1:8000', enabled: false, fetchImpl })

    await expect(client.chat({
      message: 'hello',
      language: 'en-US',
      sessionId: 'demo',
    })).rejects.toEqual(new AgentClientError('文本对话 Agent 尚未启用'))
    expect(fetchImpl).not.toHaveBeenCalled()
  })

  it('clears a server-side conversation by session id', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(
      JSON.stringify({ session_id: 'demo session', cleared: true }),
      { status: 200, headers: { 'content-type': 'application/json' } },
    ))
    const client = new AgentClient({ baseUrl: 'http://127.0.0.1:8000/', fetchImpl })

    await expect(client.clearSession(' demo session ')).resolves.toBeUndefined()
    expect(fetchImpl).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/agent/sessions/demo%20session',
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(fetchImpl.mock.contexts[0]).toBe(globalThis)
  })
})
