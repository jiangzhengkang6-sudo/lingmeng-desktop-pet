import { invoke, isTauri } from '@tauri-apps/api/core'

export type GodotPetStatus = {
  running: boolean
  pid?: number
  executablePath?: string
  lastError?: string
}

export type GodotPreviewState = {
  action: string
  mouthMode: 'closed' | 'half-open' | 'open'
  paused: boolean
  size: number
}

export type GodotProcessResult =
  | { ok: true; status: GodotPetStatus }
  | { ok: false; message: string }

function errorResult(message: string): GodotProcessResult {
  return { ok: false, message }
}

function errorMessage(error: unknown, fallback: string) {
  if (typeof error === 'string' && error) return error
  return error instanceof Error && error.message ? error.message : fallback
}

export async function getGodotPetStatus(): Promise<GodotPetStatus> {
  if (!isTauri()) return { running: false }
  try {
    return await invoke<GodotPetStatus>('get_godot_pet_status')
  } catch {
    return { running: false }
  }
}

export async function startGodotPet(): Promise<GodotProcessResult> {
  if (!isTauri()) return errorResult('浏览器预览不能启动 Godot 桌宠')
  try {
    return {
      ok: true,
      status: await invoke<GodotPetStatus>('start_godot_pet'),
    }
  } catch (error) {
    return errorResult(errorMessage(error, '无法启动 Godot 桌宠'))
  }
}

export async function stopGodotPet(): Promise<GodotProcessResult> {
  if (!isTauri()) return errorResult('浏览器预览不能关闭 Godot 桌宠')
  try {
    return {
      ok: true,
      status: await invoke<GodotPetStatus>('stop_godot_pet'),
    }
  } catch (error) {
    return errorResult(errorMessage(error, '无法关闭 Godot 桌宠'))
  }
}

export async function syncGodotPreviewState(state: GodotPreviewState): Promise<boolean> {
  if (!isTauri()) return false
  try {
    await invoke('sync_godot_preview_state', { state })
    return true
  } catch {
    return false
  }
}
