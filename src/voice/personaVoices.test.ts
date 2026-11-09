import { describe, expect, it } from 'vitest'
import { defaultVoicePersona, findVoicePersona, findVoicePersonaForLanguage, normalizeVoiceLanguageCode, voiceOptionsForAction, voicePersonas } from './personaVoices'

describe('voice personas', () => {
  it('provides selectable Chinese, Japanese, and English voices', () => {
    expect(voicePersonas.length).toBeGreaterThanOrEqual(6)
    expect(defaultVoicePersona.id).toBe('crimson-elf-tsundere')
    expect(findVoicePersona('unknown').id).toBe(defaultVoicePersona.id)

    const representativeVoices = [
      ['mature-woman-zh', 'Chinese (Mandarin)_Mature_Woman', 'zh-CN', '中文'],
      ['decisive-princess-ja', 'Japanese_DecisivePrincess', 'ja-JP', '日语'],
      ['compelling-lady-en', 'English_compelling_lady1', 'en-GB', '英语·英音'],
    ] as const

    for (const [id, voiceId, languageCode, languageLabel] of representativeVoices) {
      const persona = findVoicePersona(id)
      expect(persona.voiceId).toBe(voiceId)
      expect(persona.languageCode).toBe(languageCode)
      expect(persona.languageLabel).toBe(languageLabel)
    }
  })

  it('selects a language-matched persona for voice commands', () => {
    expect(normalizeVoiceLanguageCode('en-GB')).toBe('en-GB')
    expect(normalizeVoiceLanguageCode('en_US')).toBe('en-US')
    expect(findVoicePersonaForLanguage('ja-JP', 'crimson-elf-tsundere').id).toBe('decisive-princess-ja')
    expect(findVoicePersonaForLanguage('en-GB', 'crimson-elf-tsundere').id).toBe('compelling-lady-en')
    expect(findVoicePersonaForLanguage('zh-CN', 'crimson-elf-soft').id).toBe('crimson-elf-soft')
  })

  it('uses integer MiniMax voice parameters', () => {
    for (const persona of voicePersonas) {
      expect(Number.isInteger(persona.speed)).toBe(true)
      expect(Number.isInteger(persona.pitch)).toBe(true)
      expect(Number.isInteger(persona.vol)).toBe(true)
    }
  })

  it('maps current pet actions to voice emotion', () => {
    expect(voiceOptionsForAction(defaultVoicePersona, 'displeased').emotion).toBe('angry')
    expect(voiceOptionsForAction(defaultVoicePersona, 'shy').emotion).toBe('embarrassed')
    expect(voiceOptionsForAction(defaultVoicePersona, 'listening').emotion).toBe('neutral')
    expect(voiceOptionsForAction(defaultVoicePersona, 'speaking').voiceId).toBe(defaultVoicePersona.voiceId)
  })
})
