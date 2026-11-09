import { describe, expect, it } from 'vitest'
import { ContinuousWakeSession, WAKE_FOLLOW_UP_WINDOW_MS } from './ContinuousWakeSession'

describe('ContinuousWakeSession 连续对话唤醒窗口', () => {
  it('首次未叫名字时拒绝进入 Agent', () => {
    const session = new ContinuousWakeSession()
    const decision = session.decide('现在几点了？', 1_000)

    expect(decision.accepted).toBe(false)
    expect(decision.justWoken).toBe(false)
    expect(decision.command).toBe('现在几点了？')
  })

  it('叫名字后剥离唤醒词并打开追问窗口', () => {
    const session = new ContinuousWakeSession()
    const decision = session.decide('米娅，现在几点了？', 1_000)

    expect(decision.accepted).toBe(true)
    expect(decision.justWoken).toBe(true)
    expect(decision.command).toBe('现在几点了？')
    expect(session.isUnlocked(1_000)).toBe(true)
  })

  it('只叫名字时接受但指令为空', () => {
    const session = new ContinuousWakeSession()
    const decision = session.decide('ミーア', 1_000)

    expect(decision.accepted).toBe(true)
    expect(decision.justWoken).toBe(true)
    expect(decision.command).toBe('')
  })

  it('追问窗口内不用再次叫名字', () => {
    const session = new ContinuousWakeSession()
    session.decide('Miya, what time is it?', 1_000)
    const followUp = session.decide('Help me open music.', 1_000 + WAKE_FOLLOW_UP_WINDOW_MS - 1)

    expect(followUp.accepted).toBe(true)
    expect(followUp.justWoken).toBe(false)
    expect(followUp.command).toBe('Help me open music.')
  })

  it('超出追问窗口后需要再次唤醒', () => {
    const session = new ContinuousWakeSession()
    session.decide('米娅，现在几点了？', 1_000)
    const expired = session.decide('帮我打开音乐', 1_000 + WAKE_FOLLOW_UP_WINDOW_MS)

    expect(expired.accepted).toBe(false)
    expect(expired.command).toBe('帮我打开音乐')
  })

  it('再次叫名字会重新打开窗口', () => {
    const session = new ContinuousWakeSession()
    session.decide('米娅，现在几点了？', 1_000)
    const rewoken = session.decide('米娅，帮我打开音乐', 1_000 + WAKE_FOLLOW_UP_WINDOW_MS + 1)

    expect(rewoken.accepted).toBe(true)
    expect(rewoken.justWoken).toBe(true)
    expect(rewoken.command).toBe('帮我打开音乐')
    expect(session.isUnlocked(1_000 + WAKE_FOLLOW_UP_WINDOW_MS + 1)).toBe(true)
  })

  it('reset 会清空已打开的追问窗口', () => {
    const session = new ContinuousWakeSession()
    session.decide('米娅，你好', 1_000)
    session.reset()

    expect(session.isUnlocked(1_000)).toBe(false)
  })

  it('keepAlive 会从当前时间续期', () => {
    const session = new ContinuousWakeSession()
    session.keepAlive(2_000)

    expect(session.isUnlocked(2_000)).toBe(true)
    expect(session.isUnlocked(2_000 + WAKE_FOLLOW_UP_WINDOW_MS)).toBe(false)
  })
})
