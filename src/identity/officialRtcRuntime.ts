export type OfficialRtcConnectionEvent = {
  state: number
}

export type OfficialRtcVendorEvent = {
  state: number
}

export type OfficialRtcPublishEvent = {
  errorCode?: unknown
}

export type OfficialRtcErrorEvent = {
  errorCode?: unknown
}

export type OfficialRtcToken = {
  appId: string
  roomId: string
  userId: string
  token: string
}

export type OfficialRtcJoinOptions = {
  isAutoPublish: boolean
  isAutoSubscribeAudio: boolean
  roomProfileType: number
}

export type OfficialRtcEngineLike = {
  on(event: string, listener: (...args: unknown[]) => void): unknown
  joinRoom(
    token: string,
    roomId: string,
    userInfo: { userId: string; extraInfo: string },
    options: OfficialRtcJoinOptions,
  ): Promise<unknown>
  startAudioCapture(): Promise<unknown>
  publishStream(mediaType: number): Promise<unknown>
  unpublishStream(mediaType: number): Promise<unknown>
  stopAudioCapture(): Promise<unknown>
  leaveRoom(): Promise<unknown>
  destroy(): unknown
}

export type OfficialRtcRuntime = {
  createEngine(appId: string): OfficialRtcEngineLike
  events: {
    onConnectionStateChanged: string
    onVendorConnectionStateChanged: string
    onIceConnectWithTcp: string
    onRejoinWithTcp: string
    onTokenWillExpire: string
    onPublishResult: string
    onError: string
  }
  mediaType: {
    audio: number
  }
  roomProfileType: {
    chat: number
  }
  errorCode: {
    TIME_OUT: string
  }
  connectionState: {
    CONNECTION_START: number
    CONNECTION_STATE_DISCONNECTED: number
    CONNECTION_STATE_CONNECTING: number
    CONNECTION_STATE_CONNECTED: number
    CONNECTION_STATE_RECONNECTING: number
    CONNECTION_STATE_RECONNECTED: number
    CONNECTION_STATE_LOST: number
  }
}

export async function loadOfficialRtcRuntime(): Promise<OfficialRtcRuntime> {
  const VERTC = await import('@volcengine/rtc')
  return {
    createEngine: (appId) => VERTC.default.createEngine(appId) as unknown as OfficialRtcEngineLike,
    events: {
      onConnectionStateChanged: VERTC.default.events.onConnectionStateChanged,
      onVendorConnectionStateChanged: VERTC.default.events.onVendorConnectionStateChanged,
      onIceConnectWithTcp: VERTC.default.events.onIceConnectWithTcp,
      onRejoinWithTcp: VERTC.default.events.onRejoinWithTcp,
      onTokenWillExpire: VERTC.default.events.onTokenWillExpire,
      onPublishResult: VERTC.default.events.onPublishResult,
      onError: VERTC.default.events.onError,
    },
    mediaType: { audio: VERTC.MediaType.AUDIO },
    roomProfileType: { chat: VERTC.RoomProfileType.chat },
    errorCode: { TIME_OUT: VERTC.default.ErrorCode.TIME_OUT },
    connectionState: {
      CONNECTION_START: VERTC.ConnectionState.CONNECTION_START,
      CONNECTION_STATE_DISCONNECTED: VERTC.ConnectionState.CONNECTION_STATE_DISCONNECTED,
      CONNECTION_STATE_CONNECTING: VERTC.ConnectionState.CONNECTION_STATE_CONNECTING,
      CONNECTION_STATE_CONNECTED: VERTC.ConnectionState.CONNECTION_STATE_CONNECTED,
      CONNECTION_STATE_RECONNECTING: VERTC.ConnectionState.CONNECTION_STATE_RECONNECTING,
      CONNECTION_STATE_RECONNECTED: VERTC.ConnectionState.CONNECTION_STATE_RECONNECTED,
      CONNECTION_STATE_LOST: VERTC.ConnectionState.CONNECTION_STATE_LOST,
    },
  }
}
