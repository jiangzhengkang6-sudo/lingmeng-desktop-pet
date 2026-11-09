import type { PetAction } from '../types/pet'

export type VoiceLanguageCode = 'zh-CN' | 'ja-JP' | 'en-US' | 'en-GB'

export type VoicePersona = {
  id: string
  label: string
  description: string
  voiceId: string
  languageCode: VoiceLanguageCode
  languageLabel: string
  emotion: string
  speed: number
  pitch: number
  vol: number
}

export const voicePersonas: VoicePersona[] = [
  {
    id: 'crimson-elf-tsundere',
    label: '赤红精灵·傲娇',
    description: '甜美活泼、娇俏，带一点撒娇感，适配赤红精灵',
    voiceId: 'Chinese_huolishaonv',
    languageCode: 'zh-CN',
    languageLabel: '中文',
    emotion: 'happy',
    speed: 1,
    pitch: 0,
    vol: 1,
  },
  {
    id: 'crimson-elf-soft',
    label: '赤红精灵·温柔',
    description: '柔和舒缓、治愈陪伴，适合安静对话',
    voiceId: 'Chinese_wenrounvxing',
    languageCode: 'zh-CN',
    languageLabel: '中文',
    emotion: 'neutral',
    speed: 1,
    pitch: 0,
    vol: 1,
  },
  {
    id: 'reliable-executive',
    label: '沉稳执行官',
    description: '低沉可靠、清晰专业，当前男声风格',
    voiceId: 'Chinese (Mandarin)_Reliable_Executive',
    languageCode: 'zh-CN',
    languageLabel: '中文',
    emotion: 'neutral',
    speed: 1,
    pitch: 0,
    vol: 1,
  },
  {
    id: 'mature-woman-zh',
    label: '傲娇御姐',
    description: '低沉沙哑、慵懒舒缓、性感撩人，适合成熟御姐或美艳角色',
    voiceId: 'Chinese (Mandarin)_Mature_Woman',
    languageCode: 'zh-CN',
    languageLabel: '中文',
    emotion: 'neutral',
    speed: 1,
    pitch: 0,
    vol: 1,
  },
  {
    id: 'decisive-princess-ja',
    label: '雷厉千金',
    description: '清脆透亮、节奏紧凑、傲娇严厉，适合强势少女或动漫角色',
    voiceId: 'Japanese_DecisivePrincess',
    languageCode: 'ja-JP',
    languageLabel: '日语',
    emotion: 'neutral',
    speed: 1,
    pitch: 0,
    vol: 1,
  },
  {
    id: 'compelling-lady-en',
    label: '灵动女声',
    description: '清脆明亮、抑扬顿挫、富有故事感，适合英音旁白和角色配音',
    voiceId: 'English_compelling_lady1',
    languageCode: 'en-GB',
    languageLabel: '英语·英音',
    emotion: 'neutral',
    speed: 1,
    pitch: 0,
    vol: 1,
  },
]

export const defaultVoicePersona = voicePersonas[0]

const actionPersonaOverrides: Partial<Record<PetAction, Pick<VoicePersona, 'emotion'>>> = {
  listening: { emotion: 'neutral' },
  thinking: { emotion: 'neutral' },
  speaking: { emotion: 'happy' },
  displeased: { emotion: 'angry' },
  shy: { emotion: 'embarrassed' },
  'open-app': { emotion: 'happy' },
}

export function normalizeVoiceLanguageCode(language: string | null | undefined): VoiceLanguageCode {
  const normalized = language?.trim().toLowerCase().replace('_', '-')
  if (normalized === 'ja' || normalized === 'ja-jp') return 'ja-JP'
  if (normalized === 'en' || normalized === 'en-us' || normalized === 'en-gb') {
    return normalized === 'en-gb' ? 'en-GB' : 'en-US'
  }
  return 'zh-CN'
}

function personaSupportsLanguage(persona: VoicePersona, languageCode: VoiceLanguageCode) {
  if (persona.languageCode.startsWith('en') && languageCode.startsWith('en')) return true
  return persona.languageCode === languageCode
}

export function findVoicePersonaForLanguage(
  language: string | null | undefined,
  preferredId: string | null | undefined,
): VoicePersona {
  const languageCode = normalizeVoiceLanguageCode(language)
  const preferred = findVoicePersona(preferredId)
  if (personaSupportsLanguage(preferred, languageCode)) return preferred
  return voicePersonas.find((persona) => personaSupportsLanguage(persona, languageCode)) ?? defaultVoicePersona
}

export function findVoicePersona(id: string | null | undefined): VoicePersona {
  return voicePersonas.find((persona) => persona.id === id) ?? defaultVoicePersona
}

export function voiceOptionsForAction(persona: VoicePersona, action?: PetAction) {
  const override = action ? actionPersonaOverrides[action] : undefined
  return {
    voiceId: persona.voiceId,
    emotion: override?.emotion ?? persona.emotion,
    speed: persona.speed,
    pitch: persona.pitch,
    vol: persona.vol,
  }
}
