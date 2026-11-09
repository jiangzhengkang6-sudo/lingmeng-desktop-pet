import { beforeEach, describe, expect, it, vi } from 'vitest'

const { dynamicImport } = vi.hoisted(() => ({ dynamicImport: vi.fn() }))

vi.mock('@volcengine/rtc', () => ({
  default: {
    createEngine: vi.fn(() => ({ engine: true })),
    events: {
      onConnectionStateChanged: 'onConnectionStateChanged',
      onVendorConnectionStateChanged: 'onVendorConnectionStateChanged',
      onIceConnectWithTcp: 'onIceConnectWithTcp',
      onRejoinWithTcp: 'onRejoinWithTcp',
      onTokenWillExpire: 'onTokenWillExpire',
      onPublishResult: 'onPublishResult',
      onError: 'onError',
    },
    ErrorCode: { TIME_OUT: 'TIME_OUT' },
  },
  ConnectionState: {
    CONNECTION_START: 0,
    CONNECTION_STATE_DISCONNECTED: 1,
    CONNECTION_STATE_CONNECTING: 2,
    CONNECTION_STATE_CONNECTED: 3,
    CONNECTION_STATE_RECONNECTING: 4,
    CONNECTION_STATE_RECONNECTED: 5,
    CONNECTION_STATE_LOST: 6,
  },
  MediaType: { AUDIO: 1 },
  RoomProfileType: { chat: 1 },
}))

describe('official RTC runtime', () => {
  beforeEach(() => {
    vi.resetModules()
    dynamicImport.mockReset()
  })

  it('loads the RTC SDK dynamically and maps its constants', async () => {
    const { loadOfficialRtcRuntime } = await import('./officialRtcRuntime')
    const runtime = await loadOfficialRtcRuntime()

    expect(runtime.createEngine('app-id')).toEqual({ engine: true })
    expect(runtime.events.onConnectionStateChanged).toBe('onConnectionStateChanged')
    expect(runtime.mediaType.audio).toBe(1)
    expect(runtime.roomProfileType.chat).toBe(1)
    expect(runtime.errorCode.TIME_OUT).toBe('TIME_OUT')
    expect(runtime.connectionState.CONNECTION_STATE_CONNECTED).toBe(3)
  })
})
