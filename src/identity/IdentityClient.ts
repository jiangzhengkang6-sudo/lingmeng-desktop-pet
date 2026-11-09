export type IdentityStatus = 'unknown' | 'guest' | 'owner_verified'

export type IdentitySnapshot = {
  status: IdentityStatus
  adapter: string
  can_read_private_memory: boolean
  can_use_tools: boolean
  temporary_open_access: boolean
  persistent?: boolean
}

export type RtcVoiceprintBridgeStatus = {
  provider: string
  identityBridgeConfigured: boolean
  openapiConfigured: boolean
  sceneConfigured: boolean
  sessionControlAvailable: boolean
  apiVersion: string
  usesCurrentApiVersion: boolean
  clientTokenConfigured: boolean
  message: string
}

export type RtcClientJoinToken = {
  appId: string
  roomId: string
  userId: string
  token: string
  expiresAtMs: number
}

export type RtcVoiceprintEnrollment = {
  voiceprintId: string
  audioName: string
  algorithmVersion: number
  sceneUpdated: boolean
  requestId?: string
}

export type RtcVoiceChatStartRequest = {
  roomId: string
  agentUserId: string
  targetUserIds: string[]
  confirmed: true
  taskId?: string
}

export type RtcVoiceChatSession = {
  taskId: string
  appId?: string
  roomId?: string
  requestId?: string
}

export type IdentityClientOptions = {
  baseUrl: string
  enabled?: boolean
  fetchImpl?: typeof fetch
  timeoutMs?: number
}

export class IdentityClientError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'IdentityClientError'
  }
}

export class IdentityClient {
  private readonly baseUrl: string
  private readonly enabled: boolean
  private readonly fetchImpl: typeof fetch
  private readonly timeoutMs: number

  constructor(options: IdentityClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, '')
    this.enabled = options.enabled ?? true
    this.fetchImpl = options.fetchImpl ?? fetch
    this.timeoutMs = options.timeoutMs ?? 35_000
  }

  getStatus(): Promise<IdentitySnapshot> {
    return this.request<IdentitySnapshot>('/api/identity')
  }

  mockVerify(sample: 'owner' | 'guest'): Promise<IdentitySnapshot> {
    return this.request<IdentitySnapshot>('/api/identity/mock/verify', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ sample }),
    })
  }

  reset(): Promise<IdentitySnapshot> {
    return this.request<IdentitySnapshot>('/api/identity/reset', { method: 'POST' })
  }

  getRtcVoiceprintBridge(): Promise<RtcVoiceprintBridgeStatus> {
    return this.request<RtcVoiceprintBridgeStatus>('/api/identity/rtc/bridge')
  }

  registerRtcVoiceprint(audio: File, confirmed: true): Promise<RtcVoiceprintEnrollment> {
    if (!audio.size) return Promise.reject(new IdentityClientError('请选择声纹注册 WAV 文件'))
    const formData = new FormData()
    formData.set('audio', audio)
    formData.set('confirmed', String(confirmed))
    return this.request<RtcVoiceprintEnrollment>('/api/identity/rtc/voiceprints/register', {
      method: 'POST',
      body: formData,
    })
  }

  startRtcVoiceprintSession(request: RtcVoiceChatStartRequest): Promise<RtcVoiceChatSession> {
    return this.request<RtcVoiceChatSession>('/api/identity/rtc/sessions', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(request),
    })
  }

  stopRtcVoiceprintSession(taskId: string): Promise<RtcVoiceChatSession> {
    const normalizedTaskId = taskId.trim()
    if (!normalizedTaskId) return Promise.reject(new IdentityClientError('RTC 任务标识为空'))
    return this.request<RtcVoiceChatSession>(
      `/api/identity/rtc/sessions/${encodeURIComponent(normalizedTaskId)}`,
      { method: 'DELETE' },
    )
  }

  getRtcClientToken(taskId: string, userId: string, ttlSeconds = 900): Promise<RtcClientJoinToken> {
    const normalizedTaskId = taskId.trim()
    const normalizedUserId = userId.trim()
    if (!normalizedTaskId) return Promise.reject(new IdentityClientError('RTC 任务标识为空'))
    if (!normalizedUserId) return Promise.reject(new IdentityClientError('RTC 客户端用户 ID 为空'))
    return this.request<RtcClientJoinToken>('/api/identity/rtc/client-token', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        taskId: normalizedTaskId,
        userId: normalizedUserId,
        ttlSeconds,
      }),
    })
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    if (!this.enabled) throw new IdentityClientError('身份网关尚未启用')
    if (!this.baseUrl) throw new IdentityClientError('身份网关地址为空')

    const controller = new AbortController()
    const timeoutId = globalThis.setTimeout(() => controller.abort(), this.timeoutMs)
    try {
      const response = await this.fetchImpl.call(globalThis, `${this.baseUrl}${path}`, {
        ...init,
        signal: controller.signal,
      })
      const payload = await response.json().catch(() => ({})) as {
        detail?: { message?: unknown } | unknown
      } & Partial<T>
      if (!response.ok) {
        const detail = typeof payload.detail === 'object' && payload.detail !== null
          ? (payload.detail as { message?: unknown }).message
          : payload.detail
        throw new IdentityClientError(typeof detail === 'string' ? detail : `身份请求失败（HTTP ${response.status}）`)
      }
      return payload as T
    } catch (error) {
      if (error instanceof IdentityClientError) throw error
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new IdentityClientError('身份请求超时')
      }
      throw new IdentityClientError('身份网关不可用')
    } finally {
      globalThis.clearTimeout(timeoutId)
    }
  }
}
