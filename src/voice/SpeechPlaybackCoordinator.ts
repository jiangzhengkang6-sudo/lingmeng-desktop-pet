import type { MouthMode } from '../types/pet'
import type { AudioLipSyncCallbacks, AudioLipSyncPlayer } from './AudioLipSyncPlayer'
import type { VoicePersona } from './personaVoices'
import type {
  SpeechGatewayClient,
  SpeechTtsRequest,
  SpeechTtsResponse,
} from './SpeechGatewayClient'

export type SpeechPlaybackState = 'idle' | 'synthesizing' | 'playing' | 'error'

export type SpeechPlaybackResult =
  | { status: 'skipped' }
  | { status: 'superseded' }
  | { status: 'completed' }
  | { status: 'error'; error: Error }

export type SpeechPlaybackCallbacks = {
  onState?: (state: SpeechPlaybackState) => void
  onSpeaking?: () => void
  onMouthMode?: (mode: MouthMode, energy: number) => void
  onIdle?: () => void
  onError?: (error: Error) => void
}

type SpeechSynthesizer = Pick<SpeechGatewayClient, 'synthesize'>
type SpeechPlayer = Pick<AudioLipSyncPlayer, 'play' | 'stop'>

function toError(error: unknown): Error {
  return error instanceof Error ? error : new Error('语音播放失败')
}

export class SpeechPlaybackCoordinator {
  private requestId = 0

  constructor(
    private readonly synthesizer: SpeechSynthesizer,
    private readonly player: SpeechPlayer,
    private readonly callbacks: SpeechPlaybackCallbacks = {},
  ) {}

  async playText(
    text: string,
    language: string,
    voice?: Pick<VoicePersona, 'voiceId' | 'emotion' | 'speed' | 'pitch' | 'vol'>,
  ): Promise<SpeechPlaybackResult> {
    const normalizedText = text.trim()
    if (!normalizedText) return { status: 'skipped' }

    const requestId = ++this.requestId
    this.player.stop()
    this.callbacks.onState?.('synthesizing')
    this.callbacks.onSpeaking?.()
    this.callbacks.onMouthMode?.('closed', 0)

    try {
      const response = await this.synthesizer.synthesize({
        text: normalizedText,
        language,
        voiceId: voice?.voiceId,
        emotion: voice?.emotion,
        speed: voice?.speed,
        pitch: voice?.pitch,
        vol: voice?.vol,
      })
      if (requestId !== this.requestId) return { status: 'superseded' }

      const playbackCallbacks: AudioLipSyncCallbacks = {
        onStart: () => {
          if (requestId !== this.requestId) return
          this.callbacks.onState?.('playing')
          this.callbacks.onSpeaking?.()
          this.callbacks.onMouthMode?.('closed', 0)
        },
        onMouthMode: (mode, energy) => {
          if (requestId === this.requestId) this.callbacks.onMouthMode?.(mode, energy)
        },
        onEnd: () => {
          if (requestId !== this.requestId) return
          this.callbacks.onState?.('idle')
          this.callbacks.onMouthMode?.('closed', 0)
          this.callbacks.onIdle?.()
        },
      }

      await this.player.play(response, playbackCallbacks)
      if (requestId !== this.requestId) return { status: 'superseded' }
      return { status: 'completed' }
    } catch (error) {
      if (requestId !== this.requestId) return { status: 'superseded' }
      const normalizedError = toError(error)
      this.callbacks.onState?.('error')
      this.callbacks.onError?.(normalizedError)
      this.callbacks.onMouthMode?.('closed', 0)
      this.callbacks.onIdle?.()
      return { status: 'error', error: normalizedError }
    }
  }

  stop(): void {
    this.requestId += 1
    this.player.stop()
    this.callbacks.onState?.('idle')
    this.callbacks.onMouthMode?.('closed', 0)
    this.callbacks.onIdle?.()
  }
}

export type { SpeechTtsRequest, SpeechTtsResponse }

