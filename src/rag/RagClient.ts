export type RagCollection = 'character_knowledge' | 'user_documents'

export type RagHealthResponse = {
  ok: boolean
  store: string
  embedding_provider: string
  embedding_model: string
  embedding_configured: boolean
  collections: Record<RagCollection, boolean>
  error?: string | null
}

export type RagDocument = {
  collection: RagCollection
  document_id: string
  filename: string
  source_label: string
  chunk_count: number
  updated_at: number
  content_hash?: string
  deduplicated?: boolean
}

export type RagSearchHit = {
  document_id: string
  filename: string
  source_label: string
  chunk_index: number
  content: string
  updated_at: number
  score: number
}

export type RagSearchResponse = {
  collection: RagCollection
  results: RagSearchHit[]
}

export type RagClientOptions = {
  baseUrl: string
  enabled?: boolean
  fetchImpl?: typeof fetch
  timeoutMs?: number
}

export class RagClientError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'RagClientError'
  }
}

export class RagClient {
  private readonly baseUrl: string
  private readonly enabled: boolean
  private readonly fetchImpl: typeof fetch
  private readonly timeoutMs: number

  constructor(options: RagClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, '')
    this.enabled = options.enabled ?? true
    this.fetchImpl = options.fetchImpl ?? fetch
    this.timeoutMs = options.timeoutMs ?? 15_000
  }

  async health(): Promise<RagHealthResponse> {
    return this.request<RagHealthResponse>('/api/rag/health')
  }

  async listDocuments(collection: RagCollection): Promise<RagDocument[]> {
    return this.request<RagDocument[]>(
      `/api/rag/documents/${encodeURIComponent(collection)}`,
    )
  }

  async ingest(input: {
    collection: RagCollection
    document: File
    sourceLabel?: string
  }): Promise<RagDocument> {
    if (!input.document) throw new RagClientError('请选择 Markdown 或文本文件')

    const body = new FormData()
    body.append('collection', input.collection)
    body.append('document', input.document)
    if (input.sourceLabel?.trim()) body.append('source_label', input.sourceLabel.trim())

    return this.request<RagDocument>('/api/rag/documents', {
      method: 'POST',
      body,
    })
  }

  async search(input: {
    collection: RagCollection
    query: string
    limit?: number
  }): Promise<RagSearchResponse> {
    if (!input.query.trim()) throw new RagClientError('请输入检索内容')
    return this.request<RagSearchResponse>('/api/rag/search', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        collection: input.collection,
        query: input.query.trim(),
        limit: input.limit ?? 5,
      }),
    })
  }

  async deleteDocument(collection: RagCollection, documentId: string): Promise<void> {
    if (!documentId) throw new RagClientError('文档标识无效')
    await this.request(`/api/rag/documents/${collection}/${encodeURIComponent(documentId)}`, {
      method: 'DELETE',
    })
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    if (!this.enabled) throw new RagClientError('知识库网关尚未启用')
    if (!this.baseUrl) throw new RagClientError('知识库网关地址为空')

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
        throw new RagClientError(typeof detail === 'string' ? detail : `知识库请求失败（HTTP ${response.status}）`)
      }
      return payload as T
    } catch (error) {
      if (error instanceof RagClientError) throw error
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new RagClientError('知识库请求超时')
      }
      const detail = error instanceof Error && error.message ? `：${error.message}` : ''
      throw new RagClientError(`知识库网关不可用${detail}`)
    } finally {
      globalThis.clearTimeout(timeoutId)
    }
  }
}

