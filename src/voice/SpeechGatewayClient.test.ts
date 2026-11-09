import { describe, expect, it, vi } from 'vitest'
import { SpeechGatewayClient } from './SpeechGatewayClient'

const enabledConfig = {
  gatewayUrl: 'http://127.0.0.1:8000',
  model: 'speech-2.8-hd',
  enabled: true,
  configured: true,
}

describe('SpeechGatewayClient', () => {
  it('sends model and synthesis parameters to the local gateway', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({
      audioHex: 'hex-audio',
      mimeType: 'audio/mpeg',
    }), { status: 200 }))
    const client = new SpeechGatewayClient(enabledConfig, fetchMock)

    await expect(client.synthesize({ text: '你好', language: 'zh-CN' })).resolves.toEqual({
      audioHex: 'hex-audio',
      mimeType: 'audio/mpeg',
    })
    expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8000/api/speech/tts', expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    }))
    expect(JSON.parse(fetchMock.mock.calls[0][1]?.body as string)).toMatchObject({
      model: 'speech-2.8-hd',
      text: '你好',
      language: 'zh-CN',
    })
    expect(fetchMock.mock.contexts[0]).toBe(globalThis)
  })

  it('uses multipart form data for recognition', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({
      text: 'hello',
      language: 'en',
    }), { status: 200 }))
    const client = new SpeechGatewayClient(enabledConfig, fetchMock)

    await expect(client.transcribe(new Blob(['audio']), 'en')).resolves.toMatchObject({ text: 'hello' })
    const body = fetchMock.mock.calls[0][1]?.body
    expect(body).toBeInstanceOf(FormData)
    expect((body as FormData).get('model')).toBe('speech-2.8-hd')
    expect((body as FormData).get('language')).toBe('en')
  })

  it('blocks requests while speech is disabled', async () => {
    const fetchMock = vi.fn<typeof fetch>()
    const client = new SpeechGatewayClient({ ...enabledConfig, enabled: false }, fetchMock)

    await expect(client.synthesize({ text: 'test' })).rejects.toMatchObject({
      code: 'DISABLED',
    })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('normalizes HTTP failures from the gateway', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({
      detail: 'provider unavailable',
    }), { status: 502 }))
    const client = new SpeechGatewayClient(enabledConfig, fetchMock)

    await expect(client.synthesize({ text: 'test' })).rejects.toMatchObject({
      code: 'HTTP',
      status: 502,
    })
  })

  it('creates a local-gateway WebSocket stream without provider credentials', () => {
    const client = new SpeechGatewayClient(enabledConfig)
    const stream = client.createAsrStream('zh-CN')

    expect(stream).toBeDefined()
  })


  it('uses the latest partial when ASR final confirmation times out', async () => {
    const events: string[] = []
    class PartialOnlySocket {
      static OPEN = 1
      readonly OPEN = 1
      readyState = 1
      binaryType = ''
      onopen: (() => void) | null = null
      onmessage: ((event: MessageEvent) => void) | null = null
      sent: Array<string | ArrayBuffer> = []

      constructor(public url: string) {
        setTimeout(() => this.onopen?.(), 0)
      }

      send(payload: string | ArrayBuffer) {
        this.sent.push(payload)
        if (payload === JSON.stringify({ type: 'start', language: 'zh-CN' })) {
          setTimeout(() => this.onmessage?.({ data: JSON.stringify({ type: 'ready' }) } as MessageEvent), 0)
        }
      }

      close() {
        this.readyState = 3
      }
    }

    const originalWebSocket = globalThis.WebSocket
    globalThis.WebSocket = PartialOnlySocket as unknown as typeof WebSocket
    try {
      const client = new SpeechGatewayClient(enabledConfig, fetch)
      const stream = client.createAsrStream('zh-CN', {
        onEvent: (event) => events.push(event.type),
      })
      await stream.start()
      const socket = (stream as unknown as { socket: PartialOnlySocket }).socket
      socket.onmessage?.({ data: JSON.stringify({ type: 'partial', text: '现在几点了？' }) } as MessageEvent)
      await stream.sendAudio(new ArrayBuffer(8))
      const result = await stream.stop(50)

      expect(result).toBe('partial-timeout')
      expect(stream.getLatestPartial().text).toBe('现在几点了？')
      expect(events).toContain('final-timeout')
    } finally {
      globalThis.WebSocket = originalWebSocket
    }
  })
})
