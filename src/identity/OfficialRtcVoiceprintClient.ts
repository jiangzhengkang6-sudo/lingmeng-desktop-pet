import { loadOfficialRtcRuntime, type OfficialRtcEngineLike, type OfficialRtcRuntime } from './officialRtcRuntime'
import type { RtcClientJoinToken } from './IdentityClient'

export type OfficialRtcClientState = 'idle' | 'joining' | 'publishing' | 'active' | 'stopping' | 'error'
export type OfficialRtcClientPhase = 'idle' | 'joining' | 'capturing' | 'publishing' | 'active' | 'stopping'

export type OfficialRtcClientDiagnostic = {
  phase: OfficialRtcClientPhase
  connectionState: string
  connectionStateCode?: number
  transport: 'unknown' | 'udp' | 'tcp'
  lastEvent: string
  audioCapture: 'not_started' | 'started' | 'failed'
  publish: 'not_started' | 'started' | 'failed'
  tokenWillExpire: boolean
}

type RtcErrorLike = {
  code?: unknown
  errorCode?: unknown
}

const JOIN_TIMEOUT_MS = 20_000
const CONNECTION_STATE_LABELS: Record<number, string> = {
  0: '准备连接',
  1: '已断开',
  2: '连接中',
  3: '已连接',
  4: '重连中',
  5: '已重连',
  6: '连接丢失',
}

export function connectionStateLabel(state: number): string {
  return CONNECTION_STATE_LABELS[state] ?? '未知'
}

function errorCodeOf(error: unknown): string {
  if (!error || typeof error !== 'object') return 'UNKNOWN'
  const candidate = error as RtcErrorLike
  const code = typeof candidate.errorCode === 'string'
    ? candidate.errorCode
    : typeof candidate.code === 'string'
      ? candidate.code
      : ''
  return code || 'UNKNOWN'
}

export function classifyRtcError(
  phase: OfficialRtcClientPhase,
  error: unknown,
): { phase: OfficialRtcClientPhase; code: string; message: string } {
  const code = errorCodeOf(error)
  const messages: Record<string, string> = {
    INVALID_TOKEN: 'RTC Token 无效或已过期，请重新获取 Token',
    TOKEN_EXPIRED: 'RTC Token 已过期，请重新获取 Token',
    JOIN_ROOM_FAILED: 'RTC 入房失败，请检查 App ID、房间、Token 和网络',
    ICE_SERVER_WRONG: 'RTC 网络节点连接失败，请检查网络或防火墙设置',
    TIME_OUT: 'RTC 连接超时，请检查网络后重试',
    GET_AUDIO_TRACK_FAILED: '麦克风采集失败，请检查浏览器权限和设备占用情况',
    NO_PERMISSION: '麦克风权限被拒绝，请允许当前页面使用麦克风',
    NOT_SUPPORTED: '当前浏览器不支持 RTC 麦克风采集',
    PUBLISH_FAILED: 'RTC 发布麦克风失败，请查看网络和 SDK 诊断状态',
    TOKEN_NO_PUBLISH_PERMISSION: 'RTC Token 没有麦克风发布权限，请重新获取 Token',
    RECONNECT_FAILED: 'RTC 重连失败，请检查网络后重试',
  }
  const phaseMessages: Record<OfficialRtcClientPhase, string> = {
    idle: 'RTC 尚未连接',
    joining: 'RTC 入房失败，请检查 App ID、房间、Token 和网络',
    capturing: 'RTC 麦克风采集失败，请检查浏览器权限和设备占用情况',
    publishing: 'RTC 发布麦克风失败，请查看网络和 SDK 诊断状态',
    active: 'RTC 连接异常，请检查网络后重试',
    stopping: 'RTC 停止连接失败，请重试',
  }
  return { phase, code, message: messages[code] ?? phaseMessages[phase] }
}

export class OfficialRtcVoiceprintClient {
  private engine: OfficialRtcEngineLike | null = null
  private runtime: OfficialRtcRuntime | null = null
  private state: OfficialRtcClientState = 'idle'
  private phase: OfficialRtcClientPhase = 'idle'
  private joinTimeoutId: ReturnType<typeof globalThis.setTimeout> | undefined
  private diagnostic: OfficialRtcClientDiagnostic = {
    phase: 'idle',
    connectionState: '未连接',
    transport: 'unknown',
    lastEvent: '等待启动',
    audioCapture: 'not_started',
    publish: 'not_started',
    tokenWillExpire: false,
  }

  get currentState() {
    return this.state
  }

  get currentDiagnostic(): OfficialRtcClientDiagnostic {
    return { ...this.diagnostic }
  }

  async joinAndPublish(
    token: RtcClientJoinToken,
    onError?: (message: string) => void,
    onDiagnostic?: (diagnostic: OfficialRtcClientDiagnostic) => void,
  ): Promise<void> {
    if (this.state !== 'idle' && this.state !== 'error') return
    this.clearJoinTimeout()
    this.state = 'joining'
    this.setDiagnostic({
      phase: 'joining',
      connectionState: '准备连接',
      connectionStateCode: 1,
      transport: 'unknown',
      lastEvent: '正在加入 RTC 房间',
      audioCapture: 'not_started',
      publish: 'not_started',
      tokenWillExpire: false,
    }, onDiagnostic)
    const runtime = await loadOfficialRtcRuntime()
    this.runtime = runtime
    const engine = runtime.createEngine(token.appId)
    this.engine = engine
    const reportError = (phase: OfficialRtcClientPhase, error: unknown) => {
      const classified = classifyRtcError(phase, error)
      this.setDiagnostic({
        phase,
        lastEvent: classified.message,
        ...(phase === 'capturing' ? { audioCapture: 'failed' as const } : {}),
        ...(phase === 'publishing' ? { publish: 'failed' as const } : {}),
      }, onDiagnostic)
      onError?.(classified.message)
    }
    engine.on(runtime.events.onConnectionStateChanged, (event: unknown) => {
      const connectionEvent = event as { state: number }
      this.setDiagnostic({
        connectionState: connectionStateLabel(connectionEvent.state),
        connectionStateCode: connectionEvent.state,
        lastEvent: `连接状态：${connectionStateLabel(connectionEvent.state)}`,
      }, onDiagnostic)
    })
    engine.on(runtime.events.onVendorConnectionStateChanged, (event: unknown) => {
      const vendorEvent = event as { state: number }
      this.setDiagnostic({
        lastEvent: `Vendor ICE：${connectionStateLabel(vendorEvent.state)}`,
      }, onDiagnostic)
    })
    engine.on(runtime.events.onIceConnectWithTcp, () => {
      this.setDiagnostic({
        transport: 'tcp',
        lastEvent: 'RTC 正在使用 TCP 建立媒体连接',
      }, onDiagnostic)
    })
    engine.on(runtime.events.onRejoinWithTcp, () => {
      this.setDiagnostic({
        transport: 'tcp',
        lastEvent: 'RTC 正在通过 TCP 重新加入房间',
      }, onDiagnostic)
    })
    engine.on(runtime.events.onTokenWillExpire, () => {
      this.setDiagnostic({ tokenWillExpire: true, lastEvent: 'RTC Token 即将过期，请重新启动验证会话' }, onDiagnostic)
      onError?.('RTC Token 即将过期，请重新启动验证会话')
    })
    engine.on(runtime.events.onPublishResult, (event: unknown) => {
      const publishEvent = event as { errorCode?: unknown }
      if (publishEvent.errorCode) {
        reportError('publishing', { errorCode: publishEvent.errorCode })
        return
      }
      this.setDiagnostic({ publish: 'started', lastEvent: '麦克风发布成功' }, onDiagnostic)
    })
    engine.on(runtime.events.onError, (event: unknown) => {
      const errorEvent = event as { errorCode?: unknown }
      reportError(this.phase === 'active' ? 'active' : this.phase, { errorCode: errorEvent.errorCode })
    })
    try {
      const joinRoomPromise = engine.joinRoom(
        token.token,
        token.roomId,
        {
          userId: token.userId,
          extraInfo: JSON.stringify({ call_scene: 'desktop-pet-voiceprint' }),
        },
        {
          isAutoPublish: false,
          isAutoSubscribeAudio: true,
          roomProfileType: runtime.roomProfileType.chat,
        },
      )
      await new Promise<void>((resolve, reject) => {
        this.joinTimeoutId = globalThis.setTimeout(() => {
          reject({ errorCode: runtime.errorCode.TIME_OUT })
        }, JOIN_TIMEOUT_MS)
        void joinRoomPromise.then(() => resolve(), reject)
      })
      this.clearJoinTimeout()
      this.phase = 'capturing'
      this.state = 'publishing'
      this.setDiagnostic({ phase: 'capturing', lastEvent: '已入房，正在请求麦克风权限' }, onDiagnostic)
      await engine.startAudioCapture()
      this.phase = 'publishing'
      this.setDiagnostic({ phase: 'publishing', audioCapture: 'started', lastEvent: '麦克风采集已启动，正在发布音频' }, onDiagnostic)
      await engine.publishStream(runtime.mediaType.audio)
      this.clearJoinTimeout()
      this.phase = 'active'
      this.state = 'active'
      this.setDiagnostic({ phase: 'active', publish: 'started', lastEvent: '已入房并发布麦克风' }, onDiagnostic)
    } catch (error) {
      this.clearJoinTimeout()
      this.state = 'error'
      const classified = classifyRtcError(this.phase, error)
      reportError(this.phase, error)
      await this.dispose()
      throw new Error(classified.message)
    }
  }

  async leave(): Promise<void> {
    this.clearJoinTimeout()
    if (!this.engine) {
      this.state = 'idle'
      this.phase = 'idle'
      return
    }
    this.state = 'stopping'
    const engine = this.engine
    this.engine = null
    try {
      const runtime = this.runtime
      await engine.unpublishStream(runtime?.mediaType.audio ?? 0).catch(() => undefined)
      await engine.stopAudioCapture().catch(() => undefined)
      await engine.leaveRoom().catch(() => undefined)
    } finally {
      engine.destroy()
      this.runtime = null
      this.state = 'idle'
      this.phase = 'idle'
      this.diagnostic = {
        phase: 'idle',
        connectionState: '未连接',
        transport: 'unknown',
        lastEvent: '已停止 RTC 客户端',
        audioCapture: 'not_started',
        publish: 'not_started',
        tokenWillExpire: false,
      }
    }
  }

  private clearJoinTimeout() {
    if (this.joinTimeoutId === undefined) return
    globalThis.clearTimeout(this.joinTimeoutId)
    this.joinTimeoutId = undefined
  }

  private setDiagnostic(
    patch: Partial<OfficialRtcClientDiagnostic>,
    onDiagnostic?: (diagnostic: OfficialRtcClientDiagnostic) => void,
  ) {
    if (patch.phase) this.phase = patch.phase
    this.diagnostic = { ...this.diagnostic, ...patch }
    onDiagnostic?.({ ...this.diagnostic })
  }

  private async dispose(): Promise<void> {
    this.clearJoinTimeout()
    const engine = this.engine
    this.engine = null
    if (!engine) return
    await engine.stopAudioCapture().catch(() => undefined)
    await engine.leaveRoom().catch(() => undefined)
    engine.destroy()
  }
}

