import { describe, expect, it } from 'vitest'
import { CHARACTER_NAMES, detectWakeWord, normalizeWakeText } from './WakeWordGate'

describe('WakeWordGate 三语名字门控', () => {
  it('中文规范名命中并剥离为指令', () => {
    expect(normalizeWakeText(' 米 娅，现在 几点？ ')).toBe('米娅现在几点')
    const result = detectWakeWord('米娅，现在几点了？')
    expect(result.detected).toBe(true)
    expect(result.wakeWord).toBe('米娅')
    expect(result.matchedName).toBe(CHARACTER_NAMES.zh)
    expect(result.command).toBe('现在几点了？')
  })

  it.each([
    '米雅',
    '米亚',
    '蜜娅',
    '咪呀',
    '米丫',
    '蜜雅',
  ])('中文 ASR 同音误写“%s”也命中', (alias) => {
    const result = detectWakeWord(`${alias}，下午好`)
    expect(result.detected).toBe(true)
    expect(result.matchedName).toBe(CHARACTER_NAMES.zh)
    expect(result.command).toBe('下午好')
  })

  it('支持“小米娅”这类带前缀的叫法', () => {
    const result = detectWakeWord('小米娅，帮我打开音乐')
    expect(result.detected).toBe(true)
    expect(result.command).toBe('帮我打开音乐')
  })

  it.each([
    'ミーア',
    'ミア',
    'みーあ',
    'みあ',
    'ミーヤ',
    'みーや',
  ])('日文同音变体“%s”命中', (alias) => {
    const result = detectWakeWord(alias)
    expect(result.detected).toBe(true)
    expect(result.matchedName).toBe(CHARACTER_NAMES.ja)
  })

  it('日文汉字写法“美亜”命中并归到日文规范名', () => {
    const result = detectWakeWord('美亜、こんにちは')
    expect(result.detected).toBe(true)
    expect(result.matchedName).toBe(CHARACTER_NAMES.ja)
    expect(result.command).toBe('こんにちは')
  })

  it.each([
    'Miya',
    'miya',
    'Mia',
    'Meeya',
    'Miyah',
  ])('英文变体“%s”命中', (alias) => {
    const result = detectWakeWord(`${alias}, what time is it?`)
    expect(result.detected).toBe(true)
    expect(result.matchedName).toBe(CHARACTER_NAMES.en)
    expect(result.command).toBe('what time is it?')
  })

  it('容忍名字中间的空白与标点', () => {
    expect(detectWakeWord('米 娅，你好').detected).toBe(true)
    expect(detectWakeWord('Hey Miya, hello').detected).toBe(true)
  })

  it.each([
    '下午好。',
    '米饭好吃',
    '东南亚',
    '今天天气不错',
  ])('普通语句“%s”不被误触发', (text: string) => {
    const result = detectWakeWord(text)
    expect(result.detected).toBe(false)
    expect(result.command).toBe(text)
  })

  it('只叫名字不带指令时命令为空', () => {
    expect(detectWakeWord('米娅').command).toBe('')
  })
})
