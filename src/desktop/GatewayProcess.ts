import { invoke, isTauri } from '@tauri-apps/api/core'

export type GatewayStatus = {
  running: boolean
  pid?: number
  executablePath?: string
  reusedExisting: boolean
  lastError?: string
}

export type GatewayProcessResult =
  | { ok: true; status: GatewayStatus }
  | { ok: false; message: string }

function errorResult(message: string): GatewayProcessResult {
  return { ok: false, message }
}

function errorMessage(error: unknown, fallback: string) {
  if (typeof error === 'string' && error) return error
  return error instanceof Error && error.message ? error.message : fallback
}

export async function getGatewayStatus(): Promise<GatewayStatus> {
  if (!isTauri()) return { running: false, reusedExisting: false }
  try {
    return await invoke<GatewayStatus>('get_gateway_status')
  } catch {
    return { running: false, reusedExisting: false }
  }
}

export async function startGateway(): Promise<GatewayProcessResult> {
  if (!isTauri()) return errorResult('浏览器预览不能启动本地网关')
  try {
    return {
      ok: true,
      status: await invoke<GatewayStatus>('start_gateway'),
    }
  } catch (error) {
    return errorResult(errorMessage(error, '无法启动本地网关'))
  }
}

export async function stopGateway(): Promise<GatewayProcessResult> {
  if (!isTauri()) return errorResult('浏览器预览不能关闭本地网关')
  try {
    return {
      ok: true,
      status: await invoke<GatewayStatus>('stop_gateway'),
    }
  } catch (error) {
    return errorResult(errorMessage(error, '无法关闭本地网关'))
  }
}
