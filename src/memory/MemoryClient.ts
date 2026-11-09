export type MemoryCategory = 'semantic' | 'preference' | 'routine'

export type MemoryDraft = {
  content: string
  category: MemoryCategory
}

export type MemoryCandidate = MemoryDraft & {
  id: string
  session_id: string
  source: string
  created_at: string
  updated_at: string
}

export type MemoryRecord = MemoryDraft & {
  id: string
  source_session_id: string
  source: string
  confidence: number
  created_at: string
  updated_at: string
}

export type MemoryClientOptions = {
  baseUrl: string
  enabled?: boolean
  fetchImpl?: typeof fetch
  timeoutMs?: number
}

export class MemoryClientError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'MemoryClientError'
  }
}

export class MemoryClient {
  private readonly baseUrl: string
  private readonly enabled: boolean
  private readonly fetchImpl: typeof fetch
  private readonly timeoutMs: number

  constructor(options: MemoryClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, '')
    this.enabled = options.enabled ?? true
    this.fetchImpl = options.fetchImpl ?? fetch
    this.timeoutMs = options.timeoutMs ?? 10_000
  }

  listCandidates(): Promise<MemoryCandidate[]> {
    return this.request<MemoryCandidate[]>('/api/memories/candidates')
  }

  listMemories(): Promise<MemoryRecord[]> {
    return this.request<MemoryRecord[]>('/api/memories')
  }

  updateCandidate(candidateId: string, draft: MemoryDraft): Promise<MemoryCandidate> {
    return this.request<MemoryCandidate>(`/api/memories/candidates/${encodeURIComponent(candidateId)}`, {
      method: 'PATCH',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(this.normalizeDraft(draft)),
    })
  }

  confirmCandidate(candidateId: string, draft: MemoryDraft): Promise<MemoryRecord> {
    return this.request<MemoryRecord>(`/api/memories/candidates/${encodeURIComponent(candidateId)}/confirm`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(this.normalizeDraft(draft)),
    })
  }

  deleteCandidate(candidateId: string): Promise<void> {
    return this.delete(`/api/memories/candidates/${encodeURIComponent(candidateId)}`)
  }

  updateMemory(memoryId: string, draft: MemoryDraft): Promise<MemoryRecord> {
    return this.request<MemoryRecord>(`/api/memories/${encodeURIComponent(memoryId)}`, {
      method: 'PATCH',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(this.normalizeDraft(draft)),
    })
  }

  deleteMemory(memoryId: string): Promise<void> {
    return this.delete(`/api/memories/${encodeURIComponent(memoryId)}`)
  }

  private normalizeDraft(draft: MemoryDraft): MemoryDraft {
    const content = draft.content.trim().replace(/\s+/g, ' ')
    if (!content) throw new MemoryClientError('记忆内容不能为空')
    if (content.length > 300) throw new MemoryClientError('记忆内容不能超过 300 个字符')
    return { content, category: draft.category }
  }

  private async delete(path: string): Promise<void> {
    await this.request<{ deleted: boolean }>(path, { method: 'DELETE' })
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    if (!this.enabled) throw new MemoryClientError('记忆网关尚未启用')
    if (!this.baseUrl) throw new MemoryClientError('记忆网关地址为空')

    const controller = new AbortController()
    const timeoutId = globalThis.setTimeout(() => controller.abort(), this.timeoutMs)
    try {
      const response = await this.fetchImpl.call(globalThis, `${this.baseUrl}${path}`, {
        ...init,
        signal: controller.signal,
      })
      const payload = await response.json().catch(() => ({})) as {
        detail?: { message?: unknown } | unknown
      }
      if (!response.ok) {
        const detail = typeof payload.detail === 'object' && payload.detail !== null
          ? (payload.detail as { message?: unknown }).message
          : payload.detail
        throw new MemoryClientError(typeof detail === 'string' ? detail : `记忆请求失败（HTTP ${response.status}）`)
      }
      return payload as T
    } catch (error) {
      if (error instanceof MemoryClientError) throw error
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new MemoryClientError('记忆请求超时')
      }
      throw new MemoryClientError('记忆网关不可用')
    } finally {
      globalThis.clearTimeout(timeoutId)
    }
  }
}
