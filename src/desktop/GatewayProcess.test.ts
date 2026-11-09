import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  isTauri: vi.fn(),
  invoke: vi.fn(),
}))

vi.mock('@tauri-apps/api/core', () => ({
  invoke: mocks.invoke,
  isTauri: mocks.isTauri,
}))

import { getGatewayStatus, startGateway, stopGateway } from './GatewayProcess'

describe('GatewayProcess', () => {
  beforeEach(() => {
    mocks.isTauri.mockReset()
    mocks.invoke.mockReset()
    mocks.isTauri.mockReturnValue(true)
  })

  it('starts the managed local gateway through Tauri', async () => {
    mocks.invoke.mockResolvedValue({ running: true, pid: 8000, reusedExisting: false })

    await expect(startGateway()).resolves.toEqual({
      ok: true,
      status: { running: true, pid: 8000, reusedExisting: false },
    })
    expect(mocks.invoke).toHaveBeenCalledWith('start_gateway')
  })

  it('does not start processes from the browser preview', async () => {
    mocks.isTauri.mockReturnValue(false)

    await expect(startGateway()).resolves.toEqual({
      ok: false,
      message: '浏览器预览不能启动本地网关',
    })
    await expect(getGatewayStatus()).resolves.toEqual({ running: false, reusedExisting: false })
    expect(mocks.invoke).not.toHaveBeenCalled()
  })

  it('returns a controlled stop error', async () => {
    mocks.invoke.mockRejectedValue(new Error('not available'))

    await expect(stopGateway()).resolves.toEqual({
      ok: false,
      message: 'not available',
    })
  })
})
