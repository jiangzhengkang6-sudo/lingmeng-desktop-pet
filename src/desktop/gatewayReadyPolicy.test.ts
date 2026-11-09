import { describe, expect, it } from 'vitest'
import { shouldRefreshGatewayDataOnReady } from './gatewayReadyPolicy'

describe('shouldRefreshGatewayDataOnReady', () => {
  it('首次冷启动就绪时补刷数据', () => {
    expect(shouldRefreshGatewayDataOnReady('ready', 'checking', false)).toBe(true)
    expect(shouldRefreshGatewayDataOnReady('ready', 'idle', false)).toBe(true)
  })

  it('已经就绪后，普通健康检查造成的 checking 到 ready 不重复补刷', () => {
    expect(shouldRefreshGatewayDataOnReady('ready', 'checking', true)).toBe(false)
  })

  it('网关从异常恢复时重新补刷数据', () => {
    expect(shouldRefreshGatewayDataOnReady('ready', 'error', true)).toBe(true)
  })

  it('非就绪状态不补刷', () => {
    expect(shouldRefreshGatewayDataOnReady('checking', 'ready', true)).toBe(false)
    expect(shouldRefreshGatewayDataOnReady('error', 'checking', false)).toBe(false)
  })
})
