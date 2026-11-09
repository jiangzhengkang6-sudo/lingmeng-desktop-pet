import { describe, expect, it, vi } from 'vitest'
import { DebugHistoryStore } from './DebugHistory'

function memoryStorage(): Storage {
  const map = new Map<string, string>()
  return {
    get length() { return map.size },
    clear: vi.fn(() => map.clear()),
    getItem: vi.fn((key: string) => map.get(key) ?? null),
    key: vi.fn((index: number) => Array.from(map.keys())[index] ?? null),
    removeItem: vi.fn((key: string) => { map.delete(key) }),
    setItem: vi.fn((key: string, value: string) => { map.set(key, value) }),
  }
}

describe('DebugHistoryStore', () => {
  it('persists completed debug sessions to storage', () => {
    const storage = memoryStorage()
    const store = new DebugHistoryStore(storage)
    store.start({ title: '手动语音调试', kind: 'asr', source: 'manual-asr', language: 'zh-CN' })
    store.event({ kind: 'asr', status: 'success', message: '收到 final' })
    store.update({ transcript: '现在几点了？' })
    store.finish('success', '完成')

    const next = new DebugHistoryStore(storage)
    const records = next.list()
    expect(records).toHaveLength(1)
    expect(records[0].title).toBe('手动语音调试')
    expect(records[0].transcript).toBe('现在几点了？')
    expect(records[0].events.some((event) => event.message === '收到 final')).toBe(true)
  })

  it('starts a new active session by closing the previous one', () => {
    const storage = memoryStorage()
    const store = new DebugHistoryStore(storage)
    store.start({ title: '第一次', kind: 'asr', source: 'manual-asr' })
    store.start({ title: '第二次', kind: 'tts', source: 'manual-tts' })
    store.finish('success', '第二次完成')

    const records = store.list()
    expect(records).toHaveLength(2)
    expect(records[0].title).toBe('第二次')
    expect(records[1].status).toBe('warning')
  })
})
