export type PersonaProfileDraft = {
  profile_name: string
  character_name: string
  personality: string
  speaking_style: string
  default_action: string
  voice_id: string
  system_prompt: string
}

export type PersonaProfile = PersonaProfileDraft & {
  id: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export type PersonaProfileVersion = {
  version_id: string
  profile_id: string
  snapshot: PersonaProfileDraft
  note: string
  created_at: string
}

export type PersonaClientOptions = {
  baseUrl: string
  enabled?: boolean
  fetchImpl?: typeof fetch
  timeoutMs?: number
}

export class PersonaClientError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'PersonaClientError'
  }
}

export class PersonaClient {
  private readonly baseUrl: string
  private readonly enabled: boolean
  private readonly fetchImpl: typeof fetch
  private readonly timeoutMs: number

  constructor(options: PersonaClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, '')
    this.enabled = options.enabled ?? true
    this.fetchImpl = options.fetchImpl ?? fetch
    this.timeoutMs = options.timeoutMs ?? 15_000
  }

  list(): Promise<PersonaProfile[]> {
    return this.request<PersonaProfile[]>('/api/personas')
  }

  active(): Promise<PersonaProfile | null> {
    return this.request<PersonaProfile | null>('/api/personas/active')
  }

  create(draft: PersonaProfileDraft): Promise<PersonaProfile> {
    return this.request<PersonaProfile>('/api/personas', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(draft),
    })
  }

  update(profileId: string, draft: PersonaProfileDraft): Promise<PersonaProfile> {
    return this.request<PersonaProfile>(
      `/api/personas/${encodeURIComponent(profileId)}`,
      {
        method: 'PATCH',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(draft),
      },
    )
  }

  remove(profileId: string): Promise<void> {
    return this.request<void>(`/api/personas/${encodeURIComponent(profileId)}`, {
      method: 'DELETE',
    })
  }

  activate(profileId: string): Promise<PersonaProfile> {
    return this.request<PersonaProfile>(
      `/api/personas/${encodeURIComponent(profileId)}/activate`,
      { method: 'POST' },
    )
  }

  deactivate(): Promise<void> {
    return this.request<void>('/api/personas/deactivate', { method: 'POST' })
  }

  versions(profileId: string): Promise<PersonaProfileVersion[]> {
    return this.request<PersonaProfileVersion[]>(
      `/api/personas/${encodeURIComponent(profileId)}/versions`,
    )
  }

  rollback(profileId: string, versionId: string): Promise<PersonaProfile> {
    return this.request<PersonaProfile>(
      `/api/personas/${encodeURIComponent(profileId)}/rollback`,
      {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ version_id: versionId }),
      },
    )
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    if (!this.enabled) throw new PersonaClientError('人格网关尚未启用')
    if (!this.baseUrl) throw new PersonaClientError('人格网关地址为空')

    const controller = new AbortController()
    const timeoutId = globalThis.setTimeout(() => controller.abort(), this.timeoutMs)
    try {
      const response = await this.fetchImpl.call(globalThis, `${this.baseUrl}${path}`, {
        ...init,
        signal: controller.signal,
      })
      const payload = await response.json().catch(() => null) as {
        detail?: { message?: unknown } | null
      } | null
      if (!response.ok) {
        const detail = payload && typeof payload.detail === 'object'
          ? payload.detail?.message
          : payload?.detail
        throw new PersonaClientError(
          typeof detail === 'string' ? detail : `人格请求失败（HTTP ${response.status}）`,
        )
      }
      return payload as T
    } catch (error) {
      if (error instanceof PersonaClientError) throw error
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new PersonaClientError('人格请求超时')
      }
      const detail = error instanceof Error && error.message ? `：${error.message}` : ''
      throw new PersonaClientError(`人格网关不可用${detail}`)
    } finally {
      globalThis.clearTimeout(timeoutId)
    }
  }
}
