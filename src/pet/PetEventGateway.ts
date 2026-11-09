import type { MouthMode, PetAction } from '../types/pet'

export type PetActionEventInput = {
  actionId: PetAction
  emotion?: string
  mouthMode?: MouthMode
  durationMs?: number
  interruptible?: boolean
}

export type PetEventGatewayOptions = {
  baseUrl: string
  enabled?: boolean
  fetchImpl?: typeof fetch
  timeoutMs?: number
}

export type PetEventPublishResult =
  | { ok: true; delivered: number }
  | { ok: false; message: string }

export class PetEventGateway {
  private readonly baseUrl: string
  private readonly enabled: boolean
  private readonly fetchImpl: typeof fetch
  private readonly timeoutMs: number

  constructor(options: PetEventGatewayOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, '')
    this.enabled = options.enabled ?? true
    this.fetchImpl = options.fetchImpl ?? fetch
    this.timeoutMs = options.timeoutMs ?? 1500
  }

  async publish(input: PetActionEventInput): Promise<PetEventPublishResult> {
    if (!this.enabled) return { ok: true, delivered: 0 }
    if (!this.baseUrl) return { ok: false, message: '桌宠事件网关地址为空' }

    const controller = new AbortController()
    const timeoutId = globalThis.setTimeout(() => controller.abort(), this.timeoutMs)
    try {
      const response = await this.fetchImpl.call(globalThis, `${this.baseUrl}/api/pet/events`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          type: 'pet.action',
          actionId: input.actionId,
          emotion: input.emotion,
          mouthMode: input.mouthMode,
          durationMs: input.durationMs,
          interruptible: input.interruptible ?? true,
        }),
        signal: controller.signal,
      })
      if (!response.ok) {
        return { ok: false, message: `桌宠事件发布失败（HTTP ${response.status}）` }
      }
      const payload = await response.json() as { delivered?: unknown }
      return {
        ok: true,
        delivered: typeof payload.delivered === 'number' ? payload.delivered : 0,
      }
    } catch (error) {
      return {
        ok: false,
        message: error instanceof DOMException && error.name === 'AbortError'
          ? '桌宠事件发布超时'
          : '桌宠事件网关不可用',
      }
    } finally {
      globalThis.clearTimeout(timeoutId)
    }
  }
}
