import { detectWakeWord, type WakeWordDetection } from './WakeWordGate'

/** 唤醒后允许直接追问的时长；超时后需要再次叫桌宠名字。 */
export const WAKE_FOLLOW_UP_WINDOW_MS = 30_000

export type ContinuousWakeDecision = {
  /** 是否允许进入 Agent；未唤醒且超出追问窗口时为 false。 */
  accepted: boolean
  /** 本轮是否通过名字重新唤醒；用于识别“只叫名字”的场景。 */
  justWoken: boolean
  /** 去除唤醒词后，或追问窗口内保留的原始指令。 */
  command: string
  /** 本轮唤醒词检测详情，未命中时为空。 */
  wake?: WakeWordDetection
}

/**
 * 连续对话唤醒会话：一次唤醒后短时间内允许追问，避免每句话都重复叫名字。
 * 该类只维护时间窗口，不改变手动录音和关闭门控时的行为。
 */
export class ContinuousWakeSession {
  private unlockedUntil = 0

  reset(): void {
    this.unlockedUntil = 0
  }

  isUnlocked(now: number = Date.now()): boolean {
    return now < this.unlockedUntil
  }

  decide(text: string, now: number = Date.now()): ContinuousWakeDecision {
    const wake = detectWakeWord(text)
    if (wake.detected) {
      this.unlockedUntil = now + WAKE_FOLLOW_UP_WINDOW_MS
      return {
        accepted: true,
        justWoken: true,
        command: wake.command,
        wake,
      }
    }

    if (this.isUnlocked(now)) {
      return {
        accepted: true,
        justWoken: false,
        command: text.trim(),
      }
    }

    return {
      accepted: false,
      justWoken: false,
      command: text.trim(),
      wake,
    }
  }

  /** 一轮对话完成后续期，使连续追问期间保持窗口有效。 */
  keepAlive(now: number = Date.now()): void {
    this.unlockedUntil = now + WAKE_FOLLOW_UP_WINDOW_MS
  }
}
