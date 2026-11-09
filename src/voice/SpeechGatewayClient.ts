import { readSpeechConfig, type SpeechRuntimeConfig } from './SpeechConfig'

export type SpeechTtsRequest = {
  text: string
  language?: string
  voiceId?: string
  emotion?: string
  speed?: number
  pitch?: number
  vol?: number
}

export type SpeechTtsResponse = {
  audioUrl?: string
  audioHex?: string
  audioBase64?: string
  mimeType?: string
  durationMs?: number
}

export type SpeechAsrResponse = {
  text: string
  language?: string
  confidence?: number
}

export type SpeechAsrStreamEvent =
  | { type: 'ready' }
  | { type: 'partial' | 'final'; text: string; language?: string | null; traceId?: string | null }
  | { type: 'final-timeout'; text: string; language?: string | null; traceId?: string | null }
  | { type: 'error'; code: string; message: string }
  | { type: 'closed' }

export type SpeechAsrStreamHandlers = {
  onEvent?: (event: SpeechAsrStreamEvent) => void
}

export class SpeechGatewayError extends Error {
  constructor(
    message: string,
    public readonly code: 'DISABLED' | 'NETWORK' | 'HTTP' | 'INVALID_RESPONSE',
    public readonly status?: number,
  ) {
    super(message)
    this.name = 'SpeechGatewayError'
  }
}

type FetchLike = typeof fetch

export class SpeechGatewayClient {
  constructor(
    private readonly config: SpeechRuntimeConfig = readSpeechConfig(),
    private readonly fetchImpl: FetchLike = fetch,
  ) {}

  async synthesize(request: SpeechTtsRequest): Promise<SpeechTtsResponse> {
    this.ensureEnabled()
    const response = await this.postJson('/api/speech/tts', {
      model: this.config.model,
      ...request,
    })
    if (!response || typeof response !== 'object') {
      throw new SpeechGatewayError('语音合成返回格式无效', 'INVALID_RESPONSE')
    }
    return response as SpeechTtsResponse
  }

  async transcribe(audio: Blob, language?: string): Promise<SpeechAsrResponse> {
    this.ensureEnabled()
    const form = new FormData()
    form.append('audio', audio, 'speech.webm')
    form.append('model', this.config.model)
    if (language) form.append('language', language)

    let response: Response
    try {
      response = await this.fetchImpl.call(globalThis, `${this.config.gatewayUrl}/api/speech/asr`, {
        method: 'POST',
        body: form,
      })
    } catch {
      throw new SpeechGatewayError('语音识别网关不可用', 'NETWORK')
    }
    return this.readJsonResponse<SpeechAsrResponse>(response)
  }

  createAsrStream(language?: string, handlers: SpeechAsrStreamHandlers = {}): SpeechAsrStream {
    this.ensureEnabled()
    const gatewayUrl = this.config.gatewayUrl.replace(/^http/, 'ws')
    return new SpeechAsrStream(`${gatewayUrl}/api/speech/asr/stream`, language, handlers)
  }

  private async postJson(path: string, body: unknown) {
    let response: Response
    try {
      response = await this.fetchImpl.call(globalThis, `${this.config.gatewayUrl}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
    } catch {
      throw new SpeechGatewayError('语音网关不可用', 'NETWORK')
    }
    return this.readJsonResponse<SpeechTtsResponse>(response)
  }

  private async readJsonResponse<T>(response: Response): Promise<T> {
    let data: unknown
    try {
      data = await response.json()
    } catch {
      throw new SpeechGatewayError('语音网关返回了无法解析的数据', 'INVALID_RESPONSE', response.status)
    }
    if (!response.ok) {
      const detail = (data as { detail?: { message?: unknown } | unknown }).detail
      const serverMessage = typeof detail === 'object' && detail !== null
        ? (detail as { message?: unknown }).message
        : detail
      const message = typeof serverMessage === 'string' && serverMessage
        ? serverMessage
        : `语音网关请求失败（${response.status}）`
      throw new SpeechGatewayError(message, 'HTTP', response.status)
    }
    return data as T
  }

  private ensureEnabled() {
    if (!this.config.enabled) {
      throw new SpeechGatewayError('语音功能尚未启用', 'DISABLED')
    }
  }
}

export class SpeechAsrStream {
  private socket: WebSocket | null = null
  private readyPromise: Promise<void> | null = null
  private closedPromise: Promise<void> | null = null
  private resolveClosed: (() => void) | null = null
  private started = false
  private latestText = ''
  private latestLanguage: string | null | undefined
  private latestTraceId: string | null | undefined
  private stopTimeout: ReturnType<typeof setTimeout> | null = null

  constructor(
    private readonly url: string,
    private readonly language: string | undefined,
    private readonly handlers: SpeechAsrStreamHandlers = {},
    private readonly webSocketFactory: (url: string) => WebSocket = (socketUrl) => new WebSocket(socketUrl),
  ) {}

  start(): Promise<void> {
    if (this.readyPromise) return this.readyPromise
    this.readyPromise = new Promise<void>((resolve, reject) => {
      const socket = this.webSocketFactory(this.url)
      this.socket = socket
      this.closedPromise = new Promise<void>((closedResolve) => {
        this.resolveClosed = closedResolve
      })
      socket.binaryType = 'arraybuffer'
      socket.onopen = () => {
        socket.send(JSON.stringify({ type: 'start', language: this.language }))
      }
      socket.onmessage = (message) => {
        let event: SpeechAsrStreamEvent
        try {
          event = JSON.parse(String(message.data)) as SpeechAsrStreamEvent
        } catch {
          reject(new SpeechGatewayError('流式语音识别返回格式无效', 'INVALID_RESPONSE'))
          return
        }
        if (event.type === 'partial' || event.type === 'final') {
          if (event.text.trim()) {
            this.latestText = event.text
            this.latestLanguage = event.language
            this.latestTraceId = event.traceId
          }
        }
        this.handlers.onEvent?.(event)
        if (event.type === 'ready') {
          this.started = true
          resolve()
        } else if (event.type === 'error' && !this.started) {
          reject(new SpeechGatewayError(event.message, 'HTTP'))
        } else if (event.type === 'final' || event.type === 'closed') {
          if (this.stopTimeout) {
            clearTimeout(this.stopTimeout)
            this.stopTimeout = null
          }
          this.resolveClosed?.()
        }
      }
      socket.onerror = () => {
        const error = new SpeechGatewayError('流式语音识别网关不可用', 'NETWORK')
        if (!this.started) reject(error)
        this.handlers.onEvent?.({ type: 'error', code: error.code, message: error.message })
      }
      socket.onclose = () => {
        this.resolveClosed?.()
        this.started = false
      }
    })
    return this.readyPromise
  }

  async sendAudio(audio: Blob | ArrayBuffer | Uint8Array): Promise<void> {
    await this.start()
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new SpeechGatewayError('流式语音识别连接未打开', 'NETWORK')
    }
    const data = audio instanceof Blob ? await audio.arrayBuffer() : audio
    this.socket.send(data)
  }

  async stop(timeoutMs = 5_000): Promise<'final' | 'partial-timeout'> {
    await this.start()
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type: 'stop' }))
    }
    const closed = this.closedPromise ?? Promise.resolve()
    let timeoutHandle: ReturnType<typeof setTimeout> | undefined
    const timeout = new Promise<'partial-timeout'>((resolve) => {
      timeoutHandle = setTimeout(() => {
        this.handlers.onEvent?.({
          type: 'final-timeout',
          text: this.latestText,
          language: this.latestLanguage,
          traceId: this.latestTraceId,
        })
        resolve('partial-timeout')
      }, timeoutMs)
    })
    try {
      const result = await Promise.race([closed.then(() => 'final' as const), timeout])
      return result
    } finally {
      if (timeoutHandle) clearTimeout(timeoutHandle)
      if (this.stopTimeout) {
        clearTimeout(this.stopTimeout)
        this.stopTimeout = null
      }
    }
  }

  getLatestPartial(): { text: string; language?: string | null; traceId?: string | null } {
    return {
      text: this.latestText,
      language: this.latestLanguage,
      traceId: this.latestTraceId,
    }
  }

  close(): void {
    if (this.stopTimeout) {
      clearTimeout(this.stopTimeout)
      this.stopTimeout = null
    }
    this.socket?.close()
    this.started = false
  }
}
