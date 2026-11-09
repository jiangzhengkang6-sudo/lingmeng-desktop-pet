export type ReminderStatus = 'pending' | 'fired' | 'cancelled'

export type ReminderRecord = {
  id: string
  session_id: string
  title: string
  remind_at: string
  status: ReminderStatus
  created_at: string
  updated_at: string
  fired_at?: string | null
}

export type DesktopSettings = {
  language: 'zh-CN' | 'ja-JP' | 'en-US'
  personality: 'warm' | 'balanced' | 'concise'
  voice_preference: 'default' | 'gentle' | 'lively'
  memory_policy: 'ask_before_save' | 'disabled'
  permission_mode: 'owner_confirmation'
  diagnostics_enabled: boolean
  updated_at: string
}

export type DesktopSettingsUpdate = Pick<
  DesktopSettings,
  'language' | 'personality' | 'voice_preference' | 'memory_policy' | 'diagnostics_enabled'
>

export type SystemLogRecord = {
  id: string
  category: 'reminder' | 'settings' | 'system'
  event_type: string
  status: 'success' | 'info' | 'warning' | 'failure'
  message: string
  created_at: string
}

export type LocalStateClientOptions = {
  baseUrl: string
  enabled?: boolean
  fetchImpl?: typeof fetch
  timeoutMs?: number
}

export class LocalStateClientError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'LocalStateClientError'
  }
}

export class LocalStateClient {
  private readonly baseUrl: string
  private readonly enabled: boolean
  private readonly fetchImpl: typeof fetch
  private readonly timeoutMs: number

  constructor(options: LocalStateClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, '')
    this.enabled = options.enabled ?? true
    this.fetchImpl = options.fetchImpl ?? fetch
    this.timeoutMs = options.timeoutMs ?? 10_000
  }

  listReminders(): Promise<ReminderRecord[]> {
    return this.request<ReminderRecord[]>('/api/reminders?status=pending')
  }

  createReminder(input: { title: string; remindAt: string; sessionId: string }): Promise<ReminderRecord> {
    const title = input.title.trim().replace(/\s+/g, ' ')
    if (!title) throw new LocalStateClientError('请输入提醒内容')
    if (!input.remindAt) throw new LocalStateClientError('请选择提醒时间')
    const timestamp = new Date(input.remindAt)
    if (Number.isNaN(timestamp.getTime()) || timestamp.getTime() <= Date.now()) {
      throw new LocalStateClientError('提醒时间必须晚于当前时间')
    }
    return this.request<ReminderRecord>('/api/reminders', {
      method: 'POST',
      body: JSON.stringify({
        title,
        remindAt: timestamp.toISOString(),
        sessionId: input.sessionId,
      }),
    })
  }

  cancelReminder(reminderId: string): Promise<void> {
    return this.request<{ deleted: boolean }>(`/api/reminders/${encodeURIComponent(reminderId)}`, {
      method: 'DELETE',
    }).then(() => undefined)
  }

  getSettings(): Promise<DesktopSettings> {
    return this.request<DesktopSettings>('/api/settings')
  }

  updateSettings(update: DesktopSettingsUpdate): Promise<DesktopSettings> {
    return this.request<DesktopSettings>('/api/settings', {
      method: 'PATCH',
      body: JSON.stringify(update),
    })
  }

  listLogs(): Promise<SystemLogRecord[]> {
    return this.request<SystemLogRecord[]>('/api/system/logs?limit=20')
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    if (!this.enabled) throw new LocalStateClientError('本地状态网关尚未启用')
    if (!this.baseUrl) throw new LocalStateClientError('本地网关地址为空')

    const controller = new AbortController()
    const timeoutId = globalThis.setTimeout(() => controller.abort(), this.timeoutMs)
    try {
      const response = await this.fetchImpl.call(globalThis, `${this.baseUrl}${path}`, {
        ...init,
        headers: {
          ...(init.body ? { 'content-type': 'application/json' } : {}),
          ...init.headers,
        },
        signal: controller.signal,
      })
      const payload = await response.json().catch(() => ({})) as {
        detail?: { message?: unknown } | unknown
      }
      if (!response.ok) {
        const detail = typeof payload.detail === 'object' && payload.detail !== null
          ? (payload.detail as { message?: unknown }).message
          : payload.detail
        throw new LocalStateClientError(typeof detail === 'string' ? detail : `本地状态请求失败（HTTP ${response.status}）`)
      }
      return payload as T
    } catch (error) {
      if (error instanceof LocalStateClientError) throw error
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new LocalStateClientError('本地状态请求超时')
      }
      throw new LocalStateClientError('本地状态网关不可用')
    } finally {
      globalThis.clearTimeout(timeoutId)
    }
  }
}
