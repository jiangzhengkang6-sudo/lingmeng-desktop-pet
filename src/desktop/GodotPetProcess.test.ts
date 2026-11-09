import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  isTauri: vi.fn(),
  invoke: vi.fn(),
}))

vi.mock('@tauri-apps/api/core', () => ({
  invoke: mocks.invoke,
  isTauri: mocks.isTauri,
}))

import { getGodotPetStatus, startGodotPet, stopGodotPet, syncGodotPreviewState } from './GodotPetProcess'

describe('GodotPetProcess', () => {
  beforeEach(() => {
    mocks.isTauri.mockReset()
    mocks.invoke.mockReset()
    mocks.isTauri.mockReturnValue(true)
  })

  it('starts the Godot process through the Tauri command', async () => {
    mocks.invoke.mockResolvedValue({ running: true, pid: 42, executablePath: 'Godot.exe' })

    await expect(startGodotPet()).resolves.toEqual({
      ok: true,
      status: { running: true, pid: 42, executablePath: 'Godot.exe' },
    })
    expect(mocks.invoke).toHaveBeenCalledWith('start_godot_pet')
  })

  it('returns a controlled error outside Tauri', async () => {
    mocks.isTauri.mockReturnValue(false)

    await expect(startGodotPet()).resolves.toEqual({
      ok: false,
      message: '浏览器预览不能启动 Godot 桌宠',
    })
    expect(mocks.invoke).not.toHaveBeenCalled()
  })

  it('syncs debug preview state to the Godot control file', async () => {
    mocks.invoke.mockResolvedValue(undefined)
    const state = { action: 'speaking', mouthMode: 'open' as const, paused: false, size: 320 }

    await expect(syncGodotPreviewState(state)).resolves.toBe(true)
    expect(mocks.invoke).toHaveBeenCalledWith('sync_godot_preview_state', { state })
  })

  it('reports stopped status when status lookup fails', async () => {
    mocks.invoke.mockRejectedValue(new Error('not available'))

    await expect(getGodotPetStatus()).resolves.toEqual({ running: false })
    await expect(stopGodotPet()).resolves.toEqual({
      ok: false,
      message: 'not available',
    })
  })
})
