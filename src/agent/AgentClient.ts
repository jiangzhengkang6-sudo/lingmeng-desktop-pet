export type AgentRequest = {
  message: string
  language: string
  sessionId: string
  source?: 'text' | 'voice'
  ragCollection?: 'character_knowledge' | 'user_documents'
}

export type AgentSource = {
  document_id: string
  filename: string
  source_label: string
  chunk_index: number
  score: number
}

export type AgentMemoryCandidate = {
  id: string
  session_id: string
  content: string
  category: 'semantic' | 'preference' | 'routine'
  source: string
  created_at: string
  updated_at: string
}

export type AgentResponse = {
  session_id: string
  speaker_identity: 'unknown' | 'guest' | 'owner_verified'
  text: string
  language: string
  emotion: string
  action_id: string
  mouth_mode: 'closed' | 'half-open' | 'open'
  requires_confirmation: boolean
  tool_calls: Array<Record<string, unknown>>
  trace_id: string
  sources: AgentSource[]
  rag_status: 'disabled' | 'used' | 'empty' | 'unavailable'
  memory_candidates: AgentMemoryCandidate[]
}

export type AgentClientOptions = {
  baseUrl: string
  enabled?: boolean
  fetchImpl?: typeof fetch
  webSocketImpl?: typeof WebSocket
  webSocketEnabled?: boolean
  timeoutMs?: number
}

export type AgentClientEvent =
  | {
      type: 'agent.status'
      request_id: string
      session_id: string
      status: 'thinking' | 'completed'
    }
  | {
      type: 'agent.response'
      request_id: string
      session_id: string
      response: AgentResponse
    }
  | {
      type: 'pet.action'
      request_id: string
      session_id: string
      action: Record<string, unknown>
    }
  | {
      type: 'agent.error'
      request_id: string
      session_id: string
      code: string
      message: string
    }

export type AgentClientEventHandler = (event: AgentClientEvent) => void

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isAgentClientEvent(value: unknown): value is AgentClientEvent {
  if (!isRecord(value) || typeof value.type !== 'string') return false
  if (value.type === 'agent.error') {
    return typeof value.code === 'string' && typeof value.message === 'string'
  }
  if (
    typeof value.request_id !== 'string'
    || typeof value.session_id !== 'string'
  ) return false
  if (value.type === 'agent.status') {
    return value.status === 'thinking' || value.status === 'completed'
  }
  if (value.type === 'agent.response') {
    return isRecord(value.response)
      && typeof value.response.text === 'string'
      && typeof value.response.action_id === 'string'
      && typeof value.response.trace_id === 'string'
  }
  if (value.type === 'pet.action') return isRecord(value.action)
  return false
}

export class AgentClientError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'AgentClientError'
  }
}

export class AgentClient {
  private readonly baseUrl: string
  private readonly enabled: boolean
  private readonly fetchImpl: typeof fetch
  private readonly webSocketImpl?: typeof WebSocket
  private readonly webSocketEnabled: boolean
  private readonly timeoutMs: number

  constructor(options: AgentClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, '')
    this.enabled = options.enabled ?? true
    this.fetchImpl = options.fetchImpl ?? fetch
    this.webSocketImpl = options.webSocketImpl
      ?? (typeof window !== 'undefined' && typeof WebSocket !== 'undefined' ? WebSocket : undefined)
    this.webSocketEnabled = options.webSocketEnabled ?? true
    this.timeoutMs = options.timeoutMs ?? 35_000
  }

  async chat(input: AgentRequest, onEvent?: AgentClientEventHandler): Promise<AgentResponse> {
    if (!this.enabled) throw new AgentClientError('文本对话 Agent 尚未启用')
    if (!this.baseUrl) throw new AgentClientError('文本对话网关地址为空')
    if (!input.message.trim()) throw new AgentClientError('请输入对话内容')

    if (this.webSocketEnabled && this.webSocketImpl && input.source !== 'voice') {
      try {
        return await this.chatOverWebSocket(input, onEvent)
      } catch (error) {
        if (error instanceof AgentClientError && error.message !== '文本对话网关不可用') {
          throw error
        }
        // Voice turns use the direct HTTP path: remote chat replies can take
        // around 10s, and the one-shot HTTP response avoids waiting for a WS
        // timeout before using the compatibility path.
      }
    }
    return this.chatOverHttp(input)
  }

  private async chatOverHttp(input: AgentRequest): Promise<AgentResponse> {
    const controller = new AbortController()
    const timeoutId = globalThis.setTimeout(() => controller.abort(), this.timeoutMs)
    try {
      const response = await this.fetchImpl.call(globalThis, `${this.baseUrl}/api/agent/chat`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          message: input.message.trim(),
          language: input.language,
          session_id: input.sessionId,
          source: input.source ?? 'text',
          rag_collection: input.ragCollection,
        }),
        signal: controller.signal,
      })
      const payload = await response.json().catch(() => ({})) as {
        detail?: { message?: unknown } | unknown
      } & Partial<AgentResponse>
      if (!response.ok) {
        const detail = typeof payload.detail === 'object' && payload.detail !== null
          ? (payload.detail as { message?: unknown }).message
          : payload.detail
        throw new AgentClientError(typeof detail === 'string' ? detail : `文本对话失败（HTTP ${response.status}）`)
      }
      if (
        typeof payload.text !== 'string'
        || typeof payload.action_id !== 'string'
        || typeof payload.trace_id !== 'string'
      ) {
        throw new AgentClientError('Agent 返回格式无效')
      }
      return payload as AgentResponse
    } catch (error) {
      if (error instanceof AgentClientError) throw error
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new AgentClientError('文本对话请求超时')
      }
      throw new AgentClientError('文本对话网关不可用')
    } finally {
      globalThis.clearTimeout(timeoutId)
    }
  }

  private chatOverWebSocket(
    input: AgentRequest,
    onEvent?: AgentClientEventHandler,
  ): Promise<AgentResponse> {
    return new Promise((resolve, reject) => {
      if (!this.webSocketImpl) {
        reject(new AgentClientError('文本对话网关不可用'))
        return
      }

      const requestId = `agent-${Math.random().toString(36).slice(2, 10)}`
      const socket = new this.webSocketImpl(this.webSocketUrl())
      let settled = false
      let response: AgentResponse | null = null
      const timeoutId = globalThis.setTimeout(() => {
        finishReject(new AgentClientError('文本对话请求超时'))
      }, this.timeoutMs)

      const cleanup = () => {
        globalThis.clearTimeout(timeoutId)
        socket.onopen = null
        socket.onmessage = null
        socket.onerror = null
        socket.onclose = null
        if (socket.readyState === socket.OPEN || socket.readyState === socket.CONNECTING) {
          socket.close()
        }
      }
      const finishResolve = (response: AgentResponse) => {
        if (settled) return
        settled = true
        cleanup()
        resolve(response)
      }
      const finishReject = (error: AgentClientError) => {
        if (settled) return
        settled = true
        cleanup()
        reject(error)
      }

      socket.onopen = () => {
        socket.send(JSON.stringify({
          type: 'agent.message',
          request_id: requestId,
          session_id: input.sessionId,
          message: input.message.trim(),
          language: input.language,
          source: input.source ?? 'text',
          rag_collection: input.ragCollection,
        }))
      }
      socket.onmessage = (event) => {
        let payload: AgentClientEvent
        try {
          const parsed: unknown = JSON.parse(String(event.data))
          if (!isAgentClientEvent(parsed)) throw new Error('invalid event')
          payload = parsed
        } catch {
          finishReject(new AgentClientError('Agent 返回格式无效'))
          return
        }
        if (payload.type === 'agent.error' && !payload.request_id && !payload.session_id) {
          finishReject(new AgentClientError(payload.message))
          return
        }
        if (payload.request_id !== requestId || payload.session_id !== input.sessionId) return
        if (payload.type === 'agent.error') {
          finishReject(new AgentClientError(payload.message))
          return
        }
        if (payload.type === 'agent.response') {
          response = payload.response
        }
        onEvent?.(payload)
        if (payload.type === 'agent.status' && payload.status === 'completed') {
          if (!response) {
            finishReject(new AgentClientError('Agent 返回格式无效'))
            return
          }
          finishResolve(response)
        }
      }
      socket.onerror = () => finishReject(new AgentClientError('文本对话网关不可用'))
      socket.onclose = () => {
        if (!settled) finishReject(new AgentClientError('文本对话网关不可用'))
      }
    })
  }

  private webSocketUrl(): string {
    return this.baseUrl.replace(/^http:/i, 'ws:').replace(/^https:/i, 'wss:') + '/api/agent/events'
  }

  async clearSession(sessionId: string): Promise<void> {
    if (!this.enabled) throw new AgentClientError('文本对话 Agent 尚未启用')
    if (!this.baseUrl) throw new AgentClientError('文本对话网关地址为空')
    if (!sessionId.trim()) throw new AgentClientError('会话标识无效')

    const controller = new AbortController()
    const timeoutId = globalThis.setTimeout(() => controller.abort(), this.timeoutMs)
    try {
      const response = await this.fetchImpl.call(
        globalThis,
        `${this.baseUrl}/api/agent/sessions/${encodeURIComponent(sessionId.trim())}`,
        {
          method: 'DELETE',
          signal: controller.signal,
        },
      )
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as {
          detail?: { message?: unknown } | unknown
        }
        const detail = typeof payload.detail === 'object' && payload.detail !== null
          ? (payload.detail as { message?: unknown }).message
          : payload.detail
        throw new AgentClientError(typeof detail === 'string' ? detail : `清空对话失败（HTTP ${response.status}）`)
      }
    } catch (error) {
      if (error instanceof AgentClientError) throw error
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new AgentClientError('清空对话请求超时')
      }
      throw new AgentClientError('文本对话网关不可用')
    } finally {
      globalThis.clearTimeout(timeoutId)
    }
  }
}
