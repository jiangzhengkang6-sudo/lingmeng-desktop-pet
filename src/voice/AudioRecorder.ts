export type AudioRecorderState = 'idle' | 'recording'

export type AudioRecorderStartOptions = {
  onSamples?: (samples: Float32Array, sampleRate: number) => void
}

type AudioContextLike = AudioContext

export function resampleMono(
  samples: Float32Array,
  sourceRate: number,
  targetRate: number,
): Float32Array {
  if (sourceRate <= 0 || targetRate <= 0) throw new Error('音频采样率无效')
  if (samples.length === 0 || sourceRate === targetRate) return new Float32Array(samples)

  const outputLength = Math.max(1, Math.round(samples.length * targetRate / sourceRate))
  const output = new Float32Array(outputLength)
  const ratio = sourceRate / targetRate
  for (let index = 0; index < output.length; index += 1) {
    const sourceIndex = index * ratio
    const left = Math.floor(sourceIndex)
    const right = Math.min(left + 1, samples.length - 1)
    const weight = sourceIndex - left
    output[index] = samples[left] * (1 - weight) + samples[right] * weight
  }
  return output
}

export function encodePcm16Wav(samples: Float32Array, sampleRate = 16_000): Blob {
  if (sampleRate <= 0) throw new Error('WAV 采样率无效')

  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(buffer)
  const writeAscii = (offset: number, value: string) => {
    for (let index = 0; index < value.length; index += 1) {
      view.setUint8(offset + index, value.charCodeAt(index))
    }
  }
  const clamp = (value: number) => Math.max(-1, Math.min(1, value))

  writeAscii(0, 'RIFF')
  view.setUint32(4, 36 + samples.length * 2, true)
  writeAscii(8, 'WAVE')
  writeAscii(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeAscii(36, 'data')
  view.setUint32(40, samples.length * 2, true)

  for (let index = 0; index < samples.length; index += 1) {
    const sample = clamp(samples[index])
    const value = sample < 0 ? sample * 0x8000 : sample * 0x7fff
    view.setInt16(44 + index * 2, Math.round(value), true)
  }
  return new Blob([buffer], { type: 'audio/wav' })
}

export class AudioRecorder {
  private context: AudioContextLike | null = null
  private stream: MediaStream | null = null
  private source: MediaStreamAudioSourceNode | null = null
  private processor: ScriptProcessorNode | null = null
  private silentGain: GainNode | null = null
  private chunks: Float32Array[] = []
  private state: AudioRecorderState = 'idle'

  constructor(
    private readonly mediaDevices: Pick<MediaDevices, 'getUserMedia'> = navigator.mediaDevices,
    private readonly audioContextFactory: () => AudioContextLike = () => new AudioContext(),
  ) {}

  get currentState(): AudioRecorderState {
    return this.state
  }

  async start(options: AudioRecorderStartOptions = {}): Promise<void> {
    if (this.state === 'recording') return
    if (!this.mediaDevices?.getUserMedia) throw new Error('当前环境不支持麦克风')

    this.stream = await this.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      },
    })
    this.context = this.audioContextFactory()
    await this.context.resume()
    this.source = this.context.createMediaStreamSource(this.stream)
    this.processor = this.context.createScriptProcessor(4096, 1, 1)
    this.silentGain = this.context.createGain()
    this.silentGain.gain.value = 0
    this.chunks = []
    this.processor.onaudioprocess = (event) => {
      if (this.state !== 'recording') return
      const channel = event.inputBuffer.getChannelData(0)
      const frame = new Float32Array(channel)
      this.chunks.push(frame)
      options.onSamples?.(frame, this.context?.sampleRate ?? 16_000)
    }
    this.source.connect(this.processor)
    this.processor.connect(this.silentGain)
    this.silentGain.connect(this.context.destination)
    this.state = 'recording'
  }

  async stop(maximumDurationSeconds?: number): Promise<Blob> {
    if (this.state !== 'recording') return encodePcm16Wav(new Float32Array())
    const samples = this.chunks.length === 1
      ? this.chunks[0]
      : this.mergeChunks()
    const sampleRate = this.context?.sampleRate ?? 16_000
    this.cleanup()
    const resampled = resampleMono(samples, sampleRate, 16_000)
    const maximumSamples = maximumDurationSeconds === undefined
      ? resampled.length
      : Math.max(0, Math.floor(maximumDurationSeconds * 16_000))
    return encodePcm16Wav(resampled.slice(0, maximumSamples))
  }

  cancel(): void {
    this.chunks = []
    this.cleanup()
  }

  private mergeChunks(): Float32Array {
    const length = this.chunks.reduce((total, chunk) => total + chunk.length, 0)
    const merged = new Float32Array(length)
    let offset = 0
    for (const chunk of this.chunks) {
      merged.set(chunk, offset)
      offset += chunk.length
    }
    return merged
  }

  private cleanup(): void {
    this.processor?.disconnect()
    this.source?.disconnect()
    this.silentGain?.disconnect()
    this.processor = null
    this.source = null
    this.silentGain = null
    for (const track of this.stream?.getTracks() ?? []) track.stop()
    this.stream = null
    this.state = 'idle'
    const context = this.context
    this.context = null
    if (context && context.state !== 'closed') void context.close()
  }
}
