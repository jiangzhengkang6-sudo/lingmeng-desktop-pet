export type DebugHistoryKind = 'asr' | 'agent' | 'tool' | 'tts' | 'audio' | 'system'
export type DebugHistoryStatus = 'info' | 'success' | 'warning' | 'error'

export type DebugHistoryEvent = {
  at: string
  kind: DebugHistoryKind
  status: DebugHistoryStatus
  message: string
  detail?: unknown
}

export type DebugHistoryRecord = {
  id: string
  startedAt: string
  endedAt?: string
  title: string
  kind: DebugHistoryKind
  status: DebugHistoryStatus
  source: 'manual-asr' | 'continuous-asr' | 'manual-tts' | 'system'
  language?: string
  transcript?: string
  reply?: string
  events: DebugHistoryEvent[]
}

const STORAGE_KEY = 'canvas-pet-debug-history-v1'
const MAX_RECORDS = 80
const MAX_EVENTS_PER_RECORD = 120

function safeParse(value: string | null): DebugHistoryRecord[] {
  if (!value) return []
  try {
    const parsed = JSON.parse(value) as DebugHistoryRecord[]
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function createId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `debug-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export class DebugHistoryStore {
  private records: DebugHistoryRecord[] = []
  private active?: DebugHistoryRecord

  constructor(private readonly storage: Storage = window.localStorage) {
    this.records = safeParse(this.storage.getItem(STORAGE_KEY))
  }

  list(): DebugHistoryRecord[] {
    return this.records
  }

  start(input: {
    title: string
    kind: DebugHistoryKind
    source: DebugHistoryRecord['source']
    language?: string
  }): DebugHistoryRecord {
    this.finishActive('warning', '会话被新的调试记录中断')
    const now = new Date().toISOString()
    this.active = {
      id: createId(),
      startedAt: now,
      title: input.title,
      kind: input.kind,
      status: 'info',
      source: input.source,
      language: input.language,
      events: [{
        at: now,
        kind: input.kind,
        status: 'info',
        message: input.title,
      }],
    }
    return this.active
  }

  event(input: {
    kind: DebugHistoryKind
    status: DebugHistoryStatus
    message: string
    detail?: unknown
  }): void {
    if (!this.active) return
    this.active.events.push({
      at: new Date().toISOString(),
      kind: input.kind,
      status: input.status,
      message: input.message,
      detail: input.detail,
    })
    if (this.active.events.length > MAX_EVENTS_PER_RECORD) {
      this.active.events = this.active.events.slice(-MAX_EVENTS_PER_RECORD)
    }
  }

  update(patch: Partial<Pick<DebugHistoryRecord, 'title' | 'transcript' | 'reply' | 'language' | 'status'>>): void {
    if (!this.active) return
    Object.assign(this.active, patch)
  }

  finish(status: DebugHistoryStatus, message: string, detail?: unknown): DebugHistoryRecord | undefined {
    if (!this.active) return undefined
    const record = this.active
    record.status = status
    record.endedAt = new Date().toISOString()
    record.events.push({
      at: record.endedAt,
      kind: status === 'error' ? 'system' : record.kind,
      status,
      message,
      detail,
    })
    this.records = [record, ...this.records.filter((item) => item.id !== record.id)].slice(0, MAX_RECORDS)
    this.persist()
    this.active = undefined
    return record
  }

  finishActive(status: DebugHistoryStatus, message: string): void {
    if (this.active) this.finish(status, message)
  }

  clear(): void {
    this.records = []
    this.active = undefined
    this.persist()
  }

  private persist(): void {
    try {
      this.storage.setItem(STORAGE_KEY, JSON.stringify(this.records))
    } catch (error) {
      // localStorage may be disabled or full; history is diagnostic-only.
      console.warn('Failed to persist debug history', error)
    }
  }
}
