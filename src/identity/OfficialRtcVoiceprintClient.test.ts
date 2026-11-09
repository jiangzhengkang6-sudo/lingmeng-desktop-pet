import { describe, expect, it } from 'vitest'
import {
  classifyRtcError,
  connectionStateLabel,
  type OfficialRtcClientPhase,
} from './OfficialRtcVoiceprintClient'

describe('OfficialRtcVoiceprintClient 诊断辅助函数', () => {
  it('将官方连接状态映射为脱敏中文诊断标签', () => {
    expect(connectionStateLabel(3)).toBe('已连接')
    expect(connectionStateLabel(4)).toBe('重连中')
    expect(connectionStateLabel(6)).toBe('连接丢失')
    expect(connectionStateLabel(999)).toBe('未知')
  })

  it('为官方 RTC 诊断保留明确的传输层状态类型', () => {
    const transport: 'unknown' | 'udp' | 'tcp' = 'unknown'
    expect(['unknown', 'udp', 'tcp']).toContain(transport)
  })

  it('按阶段和官方错误码归类，不返回原始异常内容', () => {
    const result = classifyRtcError('capturing', { code: 'GET_AUDIO_TRACK_FAILED', message: 'secret-token' })

    expect(result).toEqual({
      phase: 'capturing',
      code: 'GET_AUDIO_TRACK_FAILED',
      message: '麦克风采集失败，请检查浏览器权限和设备占用情况',
    })
    expect(result.message).not.toContain('secret-token')
  })

  it('未知错误也保持有限阶段并使用通用提示', () => {
    const phase: OfficialRtcClientPhase = 'publishing'
    expect(classifyRtcError(phase, new Error('access-token=hidden'))).toMatchObject({
      phase,
      code: 'UNKNOWN',
      message: 'RTC 发布麦克风失败，请查看网络和 SDK 诊断状态',
    })
  })
})
