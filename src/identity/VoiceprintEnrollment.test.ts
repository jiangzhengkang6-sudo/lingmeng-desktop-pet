import { describe, expect, it } from 'vitest'
import {
  RTC_VOICEPRINT_ENROLLMENT_MAX_BYTES,
  validateVoiceprintWav,
} from './VoiceprintEnrollment'

function createPcmWav(seconds = 15): File {
  const sampleRate = 16_000
  const channels = 1
  const bitsPerSample = 16
  const dataLength = sampleRate * channels * (bitsPerSample / 8) * seconds
  const bytes = new ArrayBuffer(44 + dataLength)
  const view = new DataView(bytes)
  const writeFourCc = (offset: number, value: string) => {
    for (let index = 0; index < value.length; index += 1) view.setUint8(offset + index, value.charCodeAt(index))
  }
  writeFourCc(0, 'RIFF')
  view.setUint32(4, 36 + dataLength, true)
  writeFourCc(8, 'WAVE')
  writeFourCc(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, channels, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * channels * (bitsPerSample / 8), true)
  view.setUint16(32, channels * (bitsPerSample / 8), true)
  view.setUint16(34, bitsPerSample, true)
  writeFourCc(36, 'data')
  view.setUint32(40, dataLength, true)
  return new File([bytes], 'owner.wav', { type: 'audio/wav' })
}

describe('validateVoiceprintWav', () => {
  it('accepts a 15-second PCM WAV enrollment sample', async () => {
    await expect(validateVoiceprintWav(createPcmWav())).resolves.toEqual({
      valid: true,
      durationSeconds: 15,
      message: 'WAV 已通过本地校验，时长 15.0 秒',
    })
  })

  it('rejects a non-WAV file and an oversized sample before upload', async () => {
    await expect(validateVoiceprintWav(new File(['not-a-wav'], 'owner.wav', {
      type: 'audio/wav',
    }))).resolves.toMatchObject({ valid: false, message: '文件不是有效的 WAV 格式' })

    const oversized = new File([new Uint8Array(RTC_VOICEPRINT_ENROLLMENT_MAX_BYTES + 1)], 'owner.wav', {
      type: 'audio/wav',
    })
    await expect(validateVoiceprintWav(oversized)).resolves.toMatchObject({
      valid: false,
      message: '文件超过 1.5 MB 限制',
    })
  })
})
