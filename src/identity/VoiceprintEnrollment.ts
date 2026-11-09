export const RTC_VOICEPRINT_ENROLLMENT_MAX_BYTES = 1_500_000
export const RTC_VOICEPRINT_ENROLLMENT_MIN_SECONDS = 15
export const RTC_VOICEPRINT_ENROLLMENT_MAX_SECONDS = 30

export type VoiceprintWavValidation = {
  valid: boolean
  durationSeconds?: number
  message: string
}

function invalid(message: string): VoiceprintWavValidation {
  return { valid: false, message }
}

function fourCc(view: DataView, offset: number) {
  return String.fromCharCode(
    view.getUint8(offset),
    view.getUint8(offset + 1),
    view.getUint8(offset + 2),
    view.getUint8(offset + 3),
  )
}

export async function validateVoiceprintWav(file: File): Promise<VoiceprintWavValidation> {
  if (!file.size) return invalid('请选择有效的 WAV 文件')
  if (file.size > RTC_VOICEPRINT_ENROLLMENT_MAX_BYTES) {
    return invalid('文件超过 1.5 MB 限制')
  }

  const bytes = await file.arrayBuffer()
  const view = new DataView(bytes)
  if (view.byteLength < 12 || fourCc(view, 0) !== 'RIFF' || fourCc(view, 8) !== 'WAVE') {
    return invalid('文件不是有效的 WAV 格式')
  }

  let offset = 12
  let format: { audioFormat: number; channels: number; sampleRate: number; bitsPerSample: number } | undefined
  let dataLength: number | undefined

  while (offset + 8 <= view.byteLength) {
    const chunkName = fourCc(view, offset)
    const chunkLength = view.getUint32(offset + 4, true)
    const chunkStart = offset + 8
    const chunkEnd = chunkStart + chunkLength
    if (chunkEnd > view.byteLength) return invalid('WAV 文件数据不完整')

    if (chunkName === 'fmt ') {
      if (chunkLength < 16) return invalid('WAV 格式信息不完整')
      format = {
        audioFormat: view.getUint16(chunkStart, true),
        channels: view.getUint16(chunkStart + 2, true),
        sampleRate: view.getUint32(chunkStart + 4, true),
        bitsPerSample: view.getUint16(chunkStart + 14, true),
      }
    } else if (chunkName === 'data') {
      dataLength = chunkLength
    }

    offset = chunkEnd + (chunkLength % 2)
  }

  if (!format || dataLength === undefined) return invalid('WAV 文件缺少音频数据')
  if (
    format.audioFormat !== 1
    || format.channels !== 1
    || format.sampleRate !== 16_000
    || format.bitsPerSample !== 16
  ) {
    return invalid('仅支持 16 kHz、16-bit、单声道 PCM WAV')
  }

  const bytesPerSecond = format.sampleRate * format.channels * (format.bitsPerSample / 8)
  const durationSeconds = dataLength / bytesPerSecond
  if (
    durationSeconds < RTC_VOICEPRINT_ENROLLMENT_MIN_SECONDS
    || durationSeconds > RTC_VOICEPRINT_ENROLLMENT_MAX_SECONDS
  ) {
    return invalid('录音时长必须在 15 到 30 秒之间')
  }
  return {
    valid: true,
    durationSeconds,
    message: `WAV 已通过本地校验，时长 ${durationSeconds.toFixed(1)} 秒`,
  }
}
