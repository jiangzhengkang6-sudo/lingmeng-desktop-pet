// 唤醒词门控：唤醒词来自角色知识库文档《米娅的基本信息.md》，
// 支持中/日/英三种语言的名字，并对 ASR 同音/近音误写做归一化匹配。

export type WakeWordDetection = {
  detected: boolean
  /** 实际识别文本中命中的名字片段，例如“米雅”“ミア” */
  wakeWord?: string
  /** 命中的规范名，例如“米娅”“ミーア”“Miya” */
  matchedName?: string
  command: string
}

type NameLanguage = 'zh' | 'ja' | 'en'

/** 桌宠三语规范名，来源：RAG 角色知识库《米娅的基本信息.md》 */
export const CHARACTER_NAMES: Record<NameLanguage, string> = {
  zh: '米娅',
  ja: 'ミーア',
  en: 'Miya',
}

/** 无法靠读音规则覆盖、需要显式登记的 ASR 常见误写 */
const EXTRA_ALIASES: Record<NameLanguage, string[]> = {
  zh: [],
  ja: ['美亜'],
  en: ['Mia', 'Meeya', 'Miyah', 'Meea'],
}

// ── 中文同音匹配（按音节枚举同音字）────────────────────────────
// “米娅”读 mǐ yā；任意“mi 音节字 + ya 音节字”相邻出现都视为唤醒，
// 例如：米雅、米亚、蜜娅、咪呀、米丫、蜜雅。
const ZH_MI_CHARS = [
  '米','蜜','密','觅','咪','迷','弥','秘','糜','眯','芈','冞','洣','猕',
]
const ZH_YA_CHARS = [
  '娅','雅','亚','呀','丫','鸦','桠','氩','玡','揠','猚',
]

/** 片假名归一目标：ミーア（mi-a）与 ミーヤ（mi-ya）读音一致，都算唤醒 */
const JA_TARGETS = ['ミア','ミヤ']
const EN_TARGETS = ['miya','mia','meeya','miyah','meea']

type NormalizedMatch = { start: number; end: number }

function codeOf(c: string): number {
  return c.codePointAt(0) ?? 0
}

function isCjkUnified(c: string): boolean {
  const code = codeOf(c)
  return code >= 0x4e00 && code <= 0x9fff
}

function isKana(c: string): boolean {
  const code = codeOf(c)
  return (code >= 0x3041 && code <= 0x3096) || (code >= 0x30a1 && code <= 0x30fc)
}

function isAsciiLetter(c: string): boolean {
  return /^[a-z]$/i.test(c)
}

/** 平假名 → 片假名（名字只涉及清音，清音范围即可） */
function hiraganaToKatakana(c: string): string {
  const code = codeOf(c)
  if (code >= 0x3041 && code <= 0x3096) {
    return String.fromCodePoint(code + 0x60)
  }
  return c
}

/**
 * 逐字符归一原文，再在归一结果中查找目标，返回命中段在原文中的索引范围。
 * 逐字符归一可容忍名字中间被 ASR 插入空白、标点或长音符。
 */
function matchNormalized(
  original: string,
  targets: string[],
  keep: (c: string) => string | null,
): NormalizedMatch | null {
  let normalized = ''
  const sourceIndex: number[] = []
  for (let i = 0; i < original.length; i += 1) {
    const converted = keep(original[i])
    if (converted === null) continue
    for (const c of converted) {
      normalized += c
      sourceIndex.push(i)
    }
  }

  let best: NormalizedMatch | null = null
  for (const target of targets) {
    const position = normalized.indexOf(target)
    if (position >= 0) {
      const candidate: NormalizedMatch = {
        start: sourceIndex[position],
        end: sourceIndex[position + target.length - 1],
      }
      // 位置最靠前优先；同一位置选择更长的目标，
      // 例如“Miyah”不应被短目标“Miya”截走尾部的“h”。
      if (
        !best
        || candidate.start < best.start
        || (candidate.start === best.start && candidate.end > best.end)
      ) {
        best = candidate
      }
    }
  }
  return best
}

/** 第一轮：汉字、假名原样保留，拉丁字母小写，用于命中规范名与显式别名 */
function keepLoose(c: string): string | null {
  if (isCjkUnified(c) || isKana(c)) return c
  if (isAsciiLetter(c)) return c.toLowerCase()
  return null
}

/** 第二轮：仅保留汉字，用于中文音节同音字匹配 */
function keepChinese(c: string): string | null {
  return isCjkUnified(c) ? c : null
}

/** 第三轮：假名归一（平转片、去长音符），其余字符丢弃 */
function keepJapanese(c: string): string | null {
  const code = codeOf(c)
  if (code === 0x30fc) return '' // 丢弃片假名长音符“ー”
  if (isKana(c)) return hiraganaToKatakana(c)
  return null
}

/** 第四轮：仅保留小写拉丁字母，用于英文名字匹配 */
function keepEnglish(c: string): string | null {
  return isAsciiLetter(c) ? c.toLowerCase() : null
}

function chineseSyllableTargets(): string[] {
  const targets: string[] = []
  for (const mi of ZH_MI_CHARS) {
    for (const ya of ZH_YA_CHARS) targets.push(mi + ya)
  }
  return targets
}

function buildCommand(original: string, match: NormalizedMatch): string {
  let command = (original.slice(0, match.start) + '，' + original.slice(match.end + 1))
    .replace(/[\s　]+/g, ' ')
    .trim()
  // “小 + 名字”叫法（如“小米娅”）剥离名字后会残留“小”，
  // 仅当“小”后紧跟分隔符时才删除，避免误伤“小心一点”这类指令。
  command = command.replace(/^小(?=[，。、,~～:：;；\s\-—])/, '')
  return command.replace(/^[，。、,~～:：;；\s\-—]+|[，。、,~～:：;；\s\-—]+$/g, '')
}

/** 判断命中片段对应哪一种语言的规范名 */
function identifyMatchedName(spoken: string): string {
  if (
    matchNormalized(spoken, JA_TARGETS, keepJapanese)
    || matchNormalized(spoken, EXTRA_ALIASES.ja, keepLoose)
  ) {
    return CHARACTER_NAMES.ja
  }
  if (matchNormalized(spoken, EN_TARGETS, keepEnglish)) return CHARACTER_NAMES.en
  return CHARACTER_NAMES.zh
}

export function normalizeWakeText(text: string): string {
  return text
    .toLowerCase()
    .replace(/[\s　]+/g, '')
    .replace(/[，。！？、,.!?！？~～\-—_:：;；"'“”‘’()（）【】\[\]{}]/g, '')
}

export function detectWakeWord(text: string): WakeWordDetection {
  const original = text.trim()
  if (!original) return { detected: false, command: original }

  // 1. 三语规范名 + 显式别名优先（精确、可解释）。
  const explicit = (Object.keys(CHARACTER_NAMES) as NameLanguage[]).flatMap((language) => [
    CHARACTER_NAMES[language],
    ...EXTRA_ALIASES[language],
  ])
  let match = matchNormalized(original, explicit, keepLoose)

  // 2. 中文同音字（米雅、米亚、蜜娅、咪呀……）
  if (!match) match = matchNormalized(original, chineseSyllableTargets(), keepChinese)

  // 3. 日文同音变体（ミア、みーあ、みあ、ミーヤ……）
  if (!match) match = matchNormalized(original, JA_TARGETS, keepJapanese)

  // 4. 英文变体（Mia、Meeya……）
  if (!match) match = matchNormalized(original, EN_TARGETS, keepEnglish)

  if (!match) return { detected: false, command: original }

  const spoken = original.slice(match.start, match.end + 1)
  return {
    detected: true,
    wakeWord: spoken,
    matchedName: identifyMatchedName(spoken),
    command: buildCommand(original, match),
  }
}
