import type { MouthMode } from '../types/pet'
import type { SpeechTtsResponse } from './SpeechGatewayClient'

export type AudioLipSyncCallbacks = {
  onStart?: () => void
  onMouthMode?: (mode: MouthMode, energy: number) => void
  onEnd?: () => void
}

export function hexToBytes(hex: string): Uint8Array {
  const normalized = hex.trim().replace(/^0x/i, '').replace(/\s+/g, '')
  if (!normalized || normalized.length % 2 !== 0 || !/^[0-9a-f]+$/i.test(normalized)) {
    throw new Error('音频 hex 数据无效')
  }

  const bytes = new Uint8Array(new ArrayBuffer(normalized.length / 2))
  for (let index = 0; index < bytes.length; index += 1) {
    bytes[index] = Number.parseInt(normalized.slice(index * 2, index * 2 + 2), 16)
  }
  return bytes
}

export function base64ToBytes(base64: string): Uint8Array {
  const normalized = base64.trim()
  if (!normalized) throw new Error('音频 base64 数据为空')

  try {
    const binary = atob(normalized)
    const bytes = new Uint8Array(new ArrayBuffer(binary.length))
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index)
    }
    return bytes
  } catch {
    throw new Error('音频 base64 数据无效')
  }
}

export function energyToMouthMode(energy: number): MouthMode {
  if (!Number.isFinite(energy) || energy < 0.045) return 'closed'
  if (energy < 0.14) return 'half-open'
  return 'open'
}

export function calculateRmsEnergy(samples: Uint8Array): number {
  if (samples.length === 0) return 0
  let sum = 0
  for (const sample of samples) {
    const normalized = (sample - 128) / 128
    sum += normalized * normalized
  }
  return Math.sqrt(sum / samples.length)
}

type AudioElementLike = Omit<Pick<HTMLAudioElement, 'src' | 'play' | 'pause' | 'load'>, 'onended' | 'onerror'> & {
  onended: ((event?: Event) => void) | null
  onerror: ((event?: Event) => void) | null
}

function createAudioElement(): AudioElementLike {
  const audio = new Audio()
  return audio as unknown as AudioElementLike
}

type PlaybackSession = {
  source: AudioBufferSourceNode
  analyser: AnalyserNode
  samples: Uint8Array<ArrayBuffer>
  callbacks: AudioLipSyncCallbacks
  frameId: number
  ended: boolean
  resolve: () => void
}

export class AudioLipSyncPlayer {
  private context: AudioContext | null = null
  private session: PlaybackSession | null = null
  private fallbackAudio: AudioElementLike | null = null
  private operationId = 0

  constructor(
    private readonly audioContextFactory: () => AudioContext = () => new AudioContext(),
    private readonly fetchImpl: typeof fetch = fetch,
    private readonly elementFactory: () => AudioElementLike = createAudioElement,
  ) {}

  async play(response: SpeechTtsResponse, callbacks: AudioLipSyncCallbacks = {}): Promise<void> {
    this.stop()
    const operationId = ++this.operationId

    try {
      const context = this.getContext()
      const audioData = await this.readAudioData(response)
      const buffer = await context.decodeAudioData(audioData)
      if (operationId !== this.operationId) return
      await context.resume()
      if (operationId !== this.operationId) return

      const source = context.createBufferSource()
      const analyser = context.createAnalyser()
      analyser.fftSize = 256
      source.buffer = buffer
      source.connect(analyser)
      analyser.connect(context.destination)

      return new Promise<void>((resolve) => {
        const session: PlaybackSession = {
          source,
          analyser,
          samples: new Uint8Array(new ArrayBuffer(analyser.fftSize)),
          callbacks,
          frameId: 0,
          ended: false,
          resolve,
        }
        this.session = session
        source.onended = () => this.finish(session)
        source.start()
        callbacks.onStart?.()
        this.sample(session)
      })
    } catch (webAudioError) {
      if (operationId !== this.operationId) return
      // Some WebView2 environments can return TTS successfully but fail
      // WebAudio decoding/autoplay. HTMLAudioElement is a simpler playback path
      // and keeps voice replies audible even if lip-sync analysis is unavailable.
      try {
        const audioData = await this.readAudioData(response)
        return await this.playWithAudioElement(audioData, response.mimeType, operationId, callbacks)
      } catch (fallbackError) {
        const error = new Error(`WebAudio 与兜底音频播放均失败：${webAudioError instanceof Error ? webAudioError.message : webAudioError}`)
        callbacks.onEnd?.()
        throw error
      }
    }
  }

  stop(): void {
    this.operationId += 1
    const fallback = this.fallbackAudio
    if (fallback) {
      fallback.onended = null
      fallback.onerror = null
      fallback.pause()
      this.fallbackAudio = null
    }
    const session = this.session
    if (!session) return
    this.finish(session)
    try {
      session.source.stop()
    } catch {
      // The source may already have ended naturally.
    }
  }

  private getContext(): AudioContext {
    if (!this.context) this.context = this.audioContextFactory()
    return this.context
  }

  private playWithAudioElement(
    audioData: ArrayBuffer,
    mimeType: string | undefined,
    operationId: number,
    callbacks: AudioLipSyncCallbacks,
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      const bytes = new Uint8Array(audioData)
      const blob = new Blob([bytes], { type: mimeType ?? 'audio/mpeg' })
      const url = URL.createObjectURL(blob)
      const audio = this.elementFactory()
      this.fallbackAudio = audio
      audio.onended = () => {
        URL.revokeObjectURL(url)
        if (this.fallbackAudio === audio) this.fallbackAudio = null
        callbacks.onMouthMode?.('closed', 0)
        callbacks.onEnd?.()
        resolve()
      }
      audio.onerror = () => {
        URL.revokeObjectURL(url)
        if (this.fallbackAudio === audio) this.fallbackAudio = null
        reject(new Error('浏览器音频兜底播放失败'))
      }
      audio.src = url
      callbacks.onStart?.()
      callbacks.onMouthMode?.('half-open', 0.08)
      void audio.play().catch((error) => {
        if (operationId === this.operationId) reject(error instanceof Error ? error : new Error('音频播放被阻止'))
      })
    })
  }

  private async readAudioData(response: SpeechTtsResponse): Promise<ArrayBuffer> {
    if (response.audioHex) return hexToBytes(response.audioHex).buffer as ArrayBuffer
    if (response.audioBase64) return base64ToBytes(response.audioBase64).buffer as ArrayBuffer
    if (response.audioUrl) {
      const audioResponse = await this.fetchImpl.call(globalThis, response.audioUrl)
      if (!audioResponse.ok) throw new Error(`音频下载失败（${audioResponse.status}）`)
      return audioResponse.arrayBuffer()
    }
    throw new Error('语音合成结果中没有音频数据')
  }

  private sample(session: PlaybackSession): void {
    if (this.session !== session || session.ended) return
    session.analyser.getByteTimeDomainData(session.samples)
    const energy = calculateRmsEnergy(session.samples)
    session.callbacks.onMouthMode?.(energyToMouthMode(energy), energy)
    session.frameId = requestAnimationFrame(() => this.sample(session))
  }

  private finish(session: PlaybackSession): void {
    if (session.ended) return
    session.ended = true
    cancelAnimationFrame(session.frameId)
    session.source.disconnect()
    session.analyser.disconnect()
    if (this.session === session) this.session = null
    session.callbacks.onMouthMode?.('closed', 0)
    session.callbacks.onEnd?.()
    session.resolve()
  }
}
