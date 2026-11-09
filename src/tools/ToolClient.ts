export type ToolRiskLevel = 'low' | 'medium' | 'high'
export type ToolApprovalState = 'auto_approved' | 'pending' | 'approved' | 'rejected'
export type ToolExecutionState = 'pending' | 'success' | 'failure' | 'rejected'

export type ToolDefinition = {
  name: string
  label: string
  description: string
  risk_level: ToolRiskLevel
  requires_owner: boolean
  requires_confirmation: boolean
  enabled: boolean
  unavailable_reason?: string | null
}

export type ToolCallResult = {
  call_id: string
  tool_name: string
  risk_level: ToolRiskLevel
  status: ToolExecutionState
  approval: ToolApprovalState
  requires_confirmation: boolean
  result?: Record<string, unknown> | null
  error_code?: string | null
  error_message?: string | null
  audit_id: string
  created_at: string
}

export type ToolApproval = {
  approval_id: string
  call_id: string
  session_id: string
  tool_name: string
  risk_level: ToolRiskLevel
  arguments: Record<string, unknown>
  status: 'pending' | 'approved' | 'rejected' | 'expired'
  created_at: string
  updated_at: string
  expires_at: string
}

export type ToolAuditRecord = {
  audit_id: string
  call_id: string
  session_id: string
  speaker_identity: string
  tool_name: string
  risk_level: ToolRiskLevel
  approval: ToolApprovalState
  status: ToolExecutionState
  arguments_summary: string
  result_summary?: string | null
  error_code?: string | null
  created_at: string
}

export type ToolClientOptions = {
  baseUrl: string
  enabled?: boolean
  fetchImpl?: typeof fetch
  timeoutMs?: number
}

export class ToolClientError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ToolClientError'
  }
}

export class ToolClient {
  private readonly baseUrl: string
  private readonly enabled: boolean
  private readonly fetchImpl: typeof fetch
  private readonly timeoutMs: number

  constructor(options: ToolClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, '')
    this.enabled = options.enabled ?? true
    this.fetchImpl = options.fetchImpl ?? fetch
    this.timeoutMs = options.timeoutMs ?? 10_000
  }

  listTools(): Promise<ToolDefinition[]> {
    return this.request<ToolDefinition[]>('/api/tools')
  }

  listApprovals(): Promise<ToolApproval[]> {
    return this.request<ToolApproval[]>('/api/tools/approvals?status=pending')
  }

  listAudit(): Promise<ToolAuditRecord[]> {
    return this.request<ToolAuditRecord[]>('/api/tools/audit')
  }

  execute(
    toolName: string,
    arguments_: Record<string, unknown>,
    sessionId: string,
    idempotencyKey?: string,
  ): Promise<ToolCallResult> {
    const payload: Record<string, unknown> = {
      tool_name: toolName,
      arguments: arguments_,
      session_id: sessionId,
    }
    if (idempotencyKey) {
      payload.idempotency_key = idempotencyKey
    }
    return this.request<ToolCallResult>('/api/tools/execute', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  }

  approve(approvalId: string): Promise<ToolCallResult> {
    return this.request<ToolCallResult>(`/api/tools/approvals/${encodeURIComponent(approvalId)}/approve`, {
      method: 'POST',
    })
  }

  reject(approvalId: string): Promise<ToolCallResult> {
    return this.request<ToolCallResult>(`/api/tools/approvals/${encodeURIComponent(approvalId)}/reject`, {
      method: 'POST',
    })
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    if (!this.enabled) throw new ToolClientError('受控桌面工具尚未启用')
    if (!this.baseUrl) throw new ToolClientError('本地网关地址为空')
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
      } & T
      if (!response.ok) {
        const detail = typeof payload.detail === 'object' && payload.detail !== null
          ? (payload.detail as { message?: unknown }).message
          : payload.detail
        throw new ToolClientError(typeof detail === 'string' ? detail : `工具请求失败（HTTP ${response.status}）`)
      }
      return payload as T
    } catch (error) {
      if (error instanceof ToolClientError) throw error
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new ToolClientError('工具请求超时')
      }
      throw new ToolClientError('受控桌面工具网关不可用')
    } finally {
      globalThis.clearTimeout(timeoutId)
    }
  }
}
