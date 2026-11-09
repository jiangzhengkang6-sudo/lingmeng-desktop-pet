<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import PetCanvas from './components/PetCanvas.vue'
import GlideSelect from './components/GlideSelect.vue'
import GlowCursor from './components/GlowCursor.vue'
import { isTauri } from '@tauri-apps/api/core'
import { captureFrame, deleteFaceProfile, fileToBlob, getFaceStatus, probeCamera, registerFace, startCamera, verifyFace, type FaceStatus } from './face/FaceAuthClient'
import { syncResourcePackageToGodot } from './desktop/GodotResourceSync'
import { getGodotPetStatus, startGodotPet, stopGodotPet, syncGodotPreviewState } from './desktop/GodotPetProcess'
import { getGatewayStatus, startGateway, type GatewayStatus } from './desktop/GatewayProcess'
import { shouldRefreshGatewayDataOnReady } from './desktop/gatewayReadyPolicy'
import { clampPetWindowSize } from './desktop/PetWindowLayout'
import { downloadJson, parseActionJson, parseManifestJson, resolveSpriteSheet, toActionJson, toManifestJson } from './engine/ResourcePackage'
import { clearResourcePackage, loadResourcePackage, saveResourcePackage } from './engine/ResourcePackageStorage'
import { validateSpriteManifest } from './engine/ManifestValidator'
import { parseFrameList } from './engine/FrameList'
import { isPngFile } from './engine/ImageFile'
import { calculateSpriteSheetGeometry } from './engine/SpriteSheetGeometry'
import {
  createCrimsonElfCoreActions,
  createCrimsonElfCoreSpriteSheets,
  createCrimsonElfTransitionActions,
  createCrimsonElfTransitionSpriteSheets,
  createCrimsonElfWalkActions,
  createCrimsonElfWalkSpriteSheets,
  crimsonElfIdleSpriteSheetKey,
} from './characters/CrimsonElfIdleSpriteSheet'
import { PetEventGateway } from './pet/PetEventGateway'
import { normalizePetAction } from './pet/petActions'
import { readSpeechConfig } from './voice/SpeechConfig'
import { AudioLipSyncPlayer } from './voice/AudioLipSyncPlayer'
import { AudioRecorder } from './voice/AudioRecorder'
import { SpeechAsrStream, SpeechGatewayClient } from './voice/SpeechGatewayClient'
import { SpeechPlaybackCoordinator } from './voice/SpeechPlaybackCoordinator'
import { createVoiceInputEvent, voiceInputActionFor, type VoiceInputEvent } from './voice/SpeechInput'
import { VoiceActivityDetector } from './voice/VoiceActivityDetector'
import { ContinuousWakeSession } from './voice/ContinuousWakeSession'
import { DebugHistoryStore, type DebugHistoryRecord } from './debug/DebugHistory'
import { defaultVoicePersona, findVoicePersona, findVoicePersonaForLanguage, normalizeVoiceLanguageCode, voiceOptionsForAction, voicePersonas, type VoicePersona } from './voice/personaVoices'
import { AgentClient, AgentClientError, type AgentClientEvent, type AgentResponse, type AgentSource } from './agent/AgentClient'
import {
  MemoryClient,
  MemoryClientError,
  type MemoryCandidate,
  type MemoryDraft,
  type MemoryRecord,
} from './memory/MemoryClient'
import {
  IdentityClient,
  IdentityClientError,
  type IdentitySnapshot,
  type IdentityStatus,
  type RtcVoiceChatSession,
  type RtcVoiceprintBridgeStatus,
  type RtcVoiceprintEnrollment,
} from './identity/IdentityClient'
import { OfficialRtcVoiceprintClient, type OfficialRtcClientDiagnostic } from './identity/OfficialRtcVoiceprintClient'
import {
  validateVoiceprintWav,
  type VoiceprintWavValidation,
} from './identity/VoiceprintEnrollment'
import {
  RagClient,
  RagClientError,
  type RagCollection,
  type RagDocument,
  type RagHealthResponse,
  type RagSearchHit,
} from './rag/RagClient'
import {
  PersonaClient,
  PersonaClientError,
  type PersonaProfile,
  type PersonaProfileDraft,
  type PersonaProfileVersion,
} from './persona/PersonaClient'
import {
  ToolClient,
  ToolClientError,
  type ToolApproval,
  type ToolAuditRecord,
  type ToolCallResult,
  type ToolDefinition,
} from './tools/ToolClient'
import {
  LocalStateClient,
  LocalStateClientError,
  type DesktopSettings,
  type ReminderRecord,
  type SystemLogRecord,
} from './local-state/LocalStateClient'

import uiBackground from './assets/ui/background-neon-sakura.png'
import bannerCityBlue from './assets/ui/banner-city-blue.png'
import bannerCityPink from './assets/ui/banner-city-pink.png'
import bannerForest from './assets/ui/banner-forest.png'
import characterBlueDress from './assets/ui/character-blue-dress.png'
import characterBlueWhite from './assets/ui/character-blue-white.png'
import characterPinkClassic from './assets/ui/character-pink-classic.png'
import characterPurpleGothic from './assets/ui/character-purple-gothic.png'
import characterWhiteBlue from './assets/ui/character-white-blue.png'
import decoGalaxyMoon from './assets/ui/deco-galaxy-moon.png'
import decoGoldSwirl from './assets/ui/deco-gold-swirl.png'
import decoLotus from './assets/ui/deco-lotus.png'
import decoMoonTrail from './assets/ui/deco-moon-trail.png'
import decoSakura from './assets/ui/deco-sakura.png'
import decoStarS from './assets/ui/deco-star-s.png'
import { isPetAction, type ActionDefinition, type PetAction, type SpriteManifest, type SpriteSheetSource, type TransitionAction, type WalkAction } from './types/pet'

type ActionConfig = {
  start: number
  end: number
  fps: number
  loop: boolean
  sheet: string
  frameIndices?: number[]
}

type FrameEditMode = 'action' | 'valid' | 'blank'

type GatewayHealth = {
  ok: boolean
  provider: string
  model: string
  ttsConfigured: boolean
  asrConfigured: boolean
  doubaoAsrConfigured: boolean
  agentProvider: string
  agentModel: string
  agentConfigured: boolean
  agentFallbackToMock: boolean
  ragEmbeddingProvider: string
  ragEmbeddingConfigured: boolean
}

const actions: Array<{ id: PetAction; label: string; tone: string }> = [
  { id: 'idle', label: '待机', tone: 'calm' },
  { id: 'listening', label: '聆听', tone: 'blue' },
  { id: 'thinking', label: '思考', tone: 'violet' },
  { id: 'speaking', label: '说话', tone: 'rose' },
  { id: 'displeased', label: '不悦', tone: 'rose' },
  { id: 'shy', label: '害羞', tone: 'pink' },
  { id: 'open-app', label: '打开应用', tone: 'amber' },
]

type UiTabId = 'pet' | 'chat' | 'voice' | 'resource' | 'knowledge' | 'system'

const uiTabs: Array<{ id: UiTabId; label: string; hint: string }> = [
  { id: 'pet', label: '主控', hint: '桌宠舞台' },
  { id: 'chat', label: '对话', hint: '文本与记忆' },
  { id: 'voice', label: '语音', hint: 'TTS / ASR' },
  { id: 'resource', label: '资源', hint: 'SpriteSheet' },
  { id: 'knowledge', label: '知识', hint: 'RAG 检索' },
  { id: 'system', label: '系统', hint: '身份与工具' },
]
const uiTabStorageKey = 'anime-agent-ui-tab'
const savedUiTab = window.localStorage.getItem(uiTabStorageKey) as UiTabId | null
const activeUiTab = ref<UiTabId>(
  savedUiTab && uiTabs.some((item) => item.id === savedUiTab) ? savedUiTab : 'pet',
)
function selectUiTab(tab: UiTabId) {
  activeUiTab.value = tab
  window.localStorage.setItem(uiTabStorageKey, tab)
}

const uiVisualsByTab: Record<UiTabId, { banner: string; character: string; deco: string }> = {
  pet: { banner: bannerCityBlue, character: characterPinkClassic, deco: decoGalaxyMoon },
  chat: { banner: bannerCityPink, character: characterPurpleGothic, deco: decoStarS },
  voice: { banner: bannerCityBlue, character: characterPinkClassic, deco: decoMoonTrail },
  resource: { banner: bannerForest, character: characterBlueDress, deco: decoGoldSwirl },
  knowledge: { banner: bannerForest, character: characterWhiteBlue, deco: decoLotus },
  system: { banner: bannerCityBlue, character: characterBlueWhite, deco: decoSakura },
}
const uiVisuals = computed(() => uiVisualsByTab[activeUiTab.value])
const uiShellStyle = computed<Record<string, string>>(() => ({
  '--ui-tab-banner': `url("${uiVisuals.value.banner}")`,
  '--ui-tab-character': `url("${uiVisuals.value.character}")`,
  '--ui-tab-deco': `url("${uiVisuals.value.deco}")`,
}))

const languageGlideOptions = [
  { value: 'zh-CN', label: '中文', tag: 'ZH' },
  { value: 'ja-JP', label: '日本語', tag: 'JA' },
  { value: 'en-US', label: 'English', tag: 'EN' },
  { value: 'en-GB', label: 'English UK', tag: 'GB' },
]

const currentAction = ref<PetAction>('idle')
const isDesktopMode = isTauri()
const petSize = ref(260)
const mouthMode = ref<'closed' | 'half-open' | 'open'>('closed')
const paused = ref(false)
const currentFrame = ref(0)
const fallback = ref(false)
const currentSourceKey = ref('')
const sourceImages = reactive<Record<string, SpriteSheetSource>>({})
const supplementalActions = reactive<Partial<Record<WalkAction | TransitionAction, ActionDefinition>>>({})
const frameEditMode = ref<FrameEditMode>('action')
const importError = ref('')
const importNotice = ref('')
const resourceStorageState = ref<'idle' | 'saving' | 'saved' | 'restored' | 'error'>('idle')
const resourceStorageError = ref('')
const resourcePersistenceEnabled = ref(false)
const godotSyncState = ref<'idle' | 'syncing' | 'synced' | 'error'>('idle')
const godotSyncError = ref('')
const godotPetRunning = ref(false)
const godotPetPid = ref<number | undefined>()
const godotPetError = ref('')
const gatewayStatus = ref<GatewayStatus>({ running: false, reusedExisting: false })
const gatewayHealth = ref<GatewayHealth | null>(null)
const gatewayHealthState = ref<'idle' | 'checking' | 'ready' | 'error'>('idle')
const gatewayError = ref('')
const speechConfig = readSpeechConfig()

function readFrontendTimeout(value: string | undefined, fallback: number) {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}

const petEventGateway = new PetEventGateway({
  baseUrl: import.meta.env.VITE_PET_EVENT_GATEWAY_URL || speechConfig.gatewayUrl,
  enabled: import.meta.env.VITE_PET_EVENT_ENABLED !== 'false',
})
const speechClient = new SpeechGatewayClient(speechConfig)
const speechPlayer = new AudioLipSyncPlayer()
const audioRecorder = new AudioRecorder()
const voiceprintRecorder = new AudioRecorder()
const agentClient = new AgentClient({
  baseUrl: import.meta.env.VITE_AGENT_GATEWAY_URL || speechConfig.gatewayUrl,
  enabled: import.meta.env.VITE_AGENT_ENABLED !== 'false',
  timeoutMs: readFrontendTimeout(import.meta.env.VITE_AGENT_TIMEOUT_MS, 35_000),
})
const memoryClient = new MemoryClient({
  baseUrl: import.meta.env.VITE_AGENT_GATEWAY_URL || speechConfig.gatewayUrl,
  enabled: import.meta.env.VITE_AGENT_ENABLED !== 'false',
})
const identityClient = new IdentityClient({
  baseUrl: import.meta.env.VITE_AGENT_GATEWAY_URL || speechConfig.gatewayUrl,
  enabled: import.meta.env.VITE_AGENT_ENABLED !== 'false',
  timeoutMs: readFrontendTimeout(import.meta.env.VITE_IDENTITY_TIMEOUT_MS, 35_000),
})
const ragClient = new RagClient({
  baseUrl: import.meta.env.VITE_RAG_GATEWAY_URL || speechConfig.gatewayUrl,
  enabled: import.meta.env.VITE_RAG_ENABLED !== 'false',
})

// 对话/语音页面的语言与声线偏好：持久化到本机，应用重启后恢复
const agentLanguageStorageKey = 'anime-agent-agent-language'
const ttsLanguageStorageKey = 'anime-agent-tts-language'
const asrLanguageStorageKey = 'anime-agent-asr-language'
const voicePersonaStorageKey = 'anime-agent-voice-persona'
const persistedLanguageCodes = ['zh-CN', 'ja-JP', 'en-US', 'en-GB']

function readStoredLanguage(storageKey: string): string | null {
  const value = window.localStorage.getItem(storageKey)
  return value && persistedLanguageCodes.includes(value) ? value : null
}

function readStoredVoicePersonaId(): string {
  const value = window.localStorage.getItem(voicePersonaStorageKey)
  return value && voicePersonas.some((persona) => persona.id === value)
    ? value
    : defaultVoicePersona.id
}

const ttsText = ref('')
const ttsLanguage = ref(readStoredLanguage(ttsLanguageStorageKey) ?? 'zh-CN')
const selectedVoicePersonaId = ref(readStoredVoicePersonaId())
const ttsDebugSpeed = ref(defaultVoicePersona.speed)
const ttsDebugPitch = ref(defaultVoicePersona.pitch)
const ttsDebugVolume = ref(defaultVoicePersona.vol)
const ttsDebugEmotion = ref(defaultVoicePersona.emotion)
const ttsState = ref<'idle' | 'synthesizing' | 'playing' | 'error'>('idle')
const ttsError = ref('')
const asrLanguage = ref(readStoredLanguage(asrLanguageStorageKey) ?? 'zh-CN')
const asrText = ref('')
const asrState = ref<'idle' | 'recording' | 'recognizing' | 'success' | 'error'>('idle')
const asrError = ref('')
const voiceInputEvent = ref<VoiceInputEvent | null>(null)
const continuousConversationEnabled = ref(false)
const wakeWordGateEnabled = ref(true)
const continuousWakeSession = new ContinuousWakeSession()
const continuousConversationStatus = ref('开启后先说“米娅”（支持中/日/英三种名字），唤醒后30秒内追问无需重复叫名字；回复时会自动暂停麦克风')
const voiceInputLevel = ref(0)
const voiceNoiseFloor = ref(0)
const voiceActivationThreshold = ref(0.018)
const voiceInputSpeechMs = ref(0)
const voicePipelineTrace = ref<string[]>([])
const debugHistoryStore = new DebugHistoryStore()
const debugHistoryRecords = ref<DebugHistoryRecord[]>(debugHistoryStore.list())
const showDebugHistory = ref(false)
type AgentChatMessage = {
  role: 'user' | 'assistant'
  text: string
  traceId?: string
  sources?: AgentSource[]
  ragStatus?: AgentResponse['rag_status']
  ragCollection?: RagCollection
}
const agentText = ref('')
const agentLanguage = ref(readStoredLanguage(agentLanguageStorageKey) ?? 'zh-CN')
const agentState = ref<'idle' | 'thinking' | 'success' | 'error'>('idle')
const agentError = ref('')
const agentMessages = ref<AgentChatMessage[]>([])

watch(agentLanguage, (value) => window.localStorage.setItem(agentLanguageStorageKey, value))
watch(ttsLanguage, (value) => window.localStorage.setItem(ttsLanguageStorageKey, value))
watch(asrLanguage, (value) => window.localStorage.setItem(asrLanguageStorageKey, value))
watch(selectedVoicePersonaId, (value) => window.localStorage.setItem(voicePersonaStorageKey, value))

function createAgentSessionId() {
  return `desktop-pet-${Math.random().toString(36).slice(2, 10)}`
}
const agentSessionId = ref(createAgentSessionId())
const speechPlayback = new SpeechPlaybackCoordinator(speechClient, speechPlayer, {
  onState: (state) => { ttsState.value = state },
  onSpeaking: () => { currentAction.value = 'speaking' },
  onMouthMode: (mode) => { mouthMode.value = mode },
  onIdle: () => {
    if (currentAction.value === 'speaking') currentAction.value = 'idle'
  },
  onError: (error) => { ttsError.value = error.message },
})
const memoryCandidates = ref<MemoryCandidate[]>([])
const confirmedMemories = ref<MemoryRecord[]>([])
const memoryState = ref<'idle' | 'loading' | 'saving' | 'error'>('idle')
const memoryError = ref('')
const activeMemoryId = ref('')
const identitySnapshot = ref<IdentitySnapshot | null>(null)
const identityState = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
const identityError = ref('')
// ── 人脸识别 ──────────────────────────────────────
const faceStatus = ref<FaceStatus | null>(null)
const faceStatusState = ref<'idle' | 'loading' | 'error'>('idle')
const faceMode = ref<'idle' | 'register' | 'verify'>('idle')
const faceError = ref('')
const faceCapturedSamples = ref<Blob[]>([])
const faceRegisterName = ref('owner')
let faceCameraStop: (() => void) | null = null
const faceVideoRef = ref<HTMLVideoElement | null>(null)
const faceCameraActive = ref(false)

// 录入方式：camera 摄像头抓拍 / upload 上传图片
const faceInputMode = ref<'camera' | 'upload'>('camera')
const faceUploadFiles = ref<File[]>([])

let faceUploadInput: HTMLInputElement | null = null

async function loadFaceStatus() {
  faceStatusState.value = 'loading'
  faceError.value = ''
  try {
    faceStatus.value = await getFaceStatus()
    faceStatusState.value = 'idle'
  } catch (err) {
    const msg = err instanceof Error ? err.message : '获取人脸状态失败'
    faceError.value = msg + '（请确认本地网关已启动，或点击上方"重试网关"后再试）'
    faceStatusState.value = 'error'
  }
}

async function faceStartCamera(mode: 'register' | 'verify') {
  if (faceStatusState.value === 'error' || !faceStatus.value) {
    faceError.value = '人脸服务暂不可用：' + (faceError.value || '无法连接本地网关，请点击上方"重试网关"启动本地服务后再试')
    return
  }
  if (!faceStatus.value.configured) {
    faceError.value = '人脸模型未就绪，请检查模型文件是否完整（查看 diagnostics.models 中的候选路径）'
    return
  }
  if (mode === 'verify' && !faceStatus.value.has_profile) {
    faceError.value = '请先录入主人人脸，再进行验证'
    return
  }
  // 先切到摄像头模式，等 DOM 更新后再获取 video 元素
  faceMode.value = mode
  faceInputMode.value = 'camera'
  faceError.value = ''
  faceCapturedSamples.value = []
  await nextTick()
  if (!faceVideoRef.value) {
    faceError.value = '视频元素未就绪，请刷新页面后重试'
    return
  }
  try {
    faceCameraStop = await startCamera(faceVideoRef.value)
    faceCameraActive.value = true
  } catch (err) {
    faceError.value = (err instanceof Error ? err.message : '无法打开摄像头') + '（请确保已允许应用使用摄像头，或检查设备是否被占用）'
    faceCameraActive.value = false
  }
}

function faceStopCamera() {
  if (faceCameraStop) {
    faceCameraStop()
    faceCameraStop = null
  }
  faceCameraActive.value = false
}

function faceCaptureSample() {
  if (!faceVideoRef.value || !faceCameraActive.value) return
  try {
    const blob = captureFrame(faceVideoRef.value)
    faceCapturedSamples.value = [...faceCapturedSamples.value, blob]
    faceError.value = ''
  } catch (err) {
    faceError.value = err instanceof Error ? err.message : '抓拍失败'
  }
}

function faceRemoveSample(index: number) {
  faceCapturedSamples.value = faceCapturedSamples.value.filter((_, i) => i !== index)
}

async function faceRegisterSubmit() {
  const samples = faceInputMode.value === 'upload'
    ? faceUploadFiles.value
    : faceCapturedSamples.value
  if (samples.length < (faceStatus.value?.min_samples ?? 3)) {
    faceError.value = `至少需要 ${faceStatus.value?.min_samples ?? 3} 张参考照片`
    return
  }
  faceError.value = ''
  try {
    const blobs = faceInputMode.value === 'upload'
      ? await Promise.all(faceUploadFiles.value.map((f) => fileToBlob(f)))
      : faceCapturedSamples.value
    await registerFace(faceRegisterName.value, blobs)
    faceStopCamera()
    faceMode.value = 'idle'
    faceCapturedSamples.value = []
    faceUploadFiles.value = []
    await loadFaceStatus()
    // 注册成功后，用第一张样本自动做一次验证，
    // 避免用户录完人脸还处于"未验证"状态。
    try {
      const result = await verifyFace(blobs[0])
      identitySnapshot.value = result as IdentitySnapshot
      identityState.value = result.status === 'owner_verified' ? 'ready' : 'error'
    } catch {
      await refreshIdentity()
    }
    await refreshLocalState()
  } catch (err) {
    faceError.value = err instanceof Error ? err.message : '注册失败'
  }
}

async function faceVerifySubmit() {
  if (faceInputMode.value === 'camera' && (!faceVideoRef.value || !faceCameraActive.value)) {
    faceError.value = '摄像头未就绪'
    return
  }
  faceError.value = ''
  identityState.value = 'loading'
  try {
    const blob = faceInputMode.value === 'upload' && faceUploadFiles.value[0]
      ? await fileToBlob(faceUploadFiles.value[0])
      : captureFrame(faceVideoRef.value!)
    const result = await verifyFace(blob)
    faceStopCamera()
    faceMode.value = 'idle'
    faceUploadFiles.value = []
    identitySnapshot.value = result as IdentitySnapshot
    identityState.value = result.status === 'owner_verified' ? 'ready' : 'error'
  } catch (err) {
    faceError.value = err instanceof Error ? err.message : '验证失败'
    identityState.value = 'error'
  }
}

async function faceDeleteProfile() {
  if (!confirm('确定要删除已注册的人脸档案吗？删除后需重新录入。')) return
  try {
    await deleteFaceProfile()
    await loadFaceStatus()
    await refreshIdentity()
  } catch (err) {
    faceError.value = err instanceof Error ? err.message : '删除失败'
  }
}

function faceSampleUrl(sample: Blob) {
  return URL.createObjectURL(sample)
}

function faceCancel() {
  faceStopCamera()
  faceMode.value = 'idle'
  faceCapturedSamples.value = []
  faceError.value = ''
  faceUploadFiles.value = []
}

function handleFaceFileSelect(event: Event) {
  const input = event.target as HTMLInputElement
  if (!input.files) return
  const files = Array.from(input.files)
  faceError.value = ''
  // 校验：必须是图片
  for (const f of files) {
    if (!f.type.startsWith('image/')) {
      faceError.value = `文件 ${f.name} 不是图片格式`
      return
    }
  }
  faceUploadFiles.value = files
}

function triggerFaceFileSelect() {
  if (!faceUploadInput) {
    faceUploadInput = document.createElement('input')
    faceUploadInput.type = 'file'
    faceUploadInput.accept = 'image/*'
    faceUploadInput.multiple = true
    faceUploadInput.addEventListener('change', handleFaceFileSelect)
  }
  faceUploadInput.click()
}
// ── 人脸识别 end ──────────────────────────────────

const rtcVoiceprintBridge = ref<RtcVoiceprintBridgeStatus | null>(null)
const rtcVoiceprintBridgeState = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
const rtcVoiceprintFile = ref<File | null>(null)
const rtcVoiceprintValidation = ref<VoiceprintWavValidation | null>(null)
const rtcVoiceprintConfirmed = ref(false)
const rtcVoiceprintEnrollment = ref<RtcVoiceprintEnrollment | null>(null)
const rtcVoiceprintEnrollmentState = ref<'idle' | 'uploading' | 'success' | 'error'>('idle')
const rtcVoiceprintEnrollmentError = ref('')
const rtcVoiceprintSession = ref<RtcVoiceChatSession | null>(null)
const rtcVoiceprintSessionState = ref<'idle' | 'starting' | 'active' | 'stopping' | 'error'>('idle')
const rtcVoiceprintSessionError = ref('')
const rtcVoiceprintRoomId = ref(import.meta.env.VITE_RTC_ROOM_ID?.trim() || 'desktop-pet-identity')
const rtcVoiceprintAgentUserId = ref(import.meta.env.VITE_RTC_AGENT_USER_ID?.trim() || 'desktop-pet-agent')
const rtcVoiceprintTargetUserIds = ref(import.meta.env.VITE_RTC_TARGET_USER_IDS?.trim() || 'desktop-owner')
const rtcVoiceprintRecordingState = ref<'idle' | 'recording' | 'processing' | 'error'>('idle')
const rtcVoiceprintRecordingError = ref('')
const rtcVoiceprintRecordingSeconds = ref(0)
const rtcVoiceprintRecordingStartedAt = ref<number | null>(null)
const rtcOfficialClient = new OfficialRtcVoiceprintClient()
const rtcOfficialClientState = ref<'idle' | 'joining' | 'publishing' | 'active' | 'stopping' | 'error'>('idle')
const rtcOfficialClientError = ref('')
const rtcOfficialClientDiagnostic = ref<OfficialRtcClientDiagnostic>(rtcOfficialClient.currentDiagnostic)
const rtcManualJoinToken = ref('')
let rtcVoiceprintRecordingTimer: number | undefined
let identityStatusTimer: number | undefined
const toolClient = new ToolClient({
  baseUrl: import.meta.env.VITE_AGENT_GATEWAY_URL || speechConfig.gatewayUrl,
  enabled: import.meta.env.VITE_AGENT_ENABLED !== 'false',
})
const localStateClient = new LocalStateClient({
  baseUrl: import.meta.env.VITE_AGENT_GATEWAY_URL || speechConfig.gatewayUrl,
  enabled: import.meta.env.VITE_AGENT_ENABLED !== 'false',
})
const toolDefinitions = ref<ToolDefinition[]>([])
const toolApprovals = ref<ToolApproval[]>([])
const toolAudit = ref<ToolAuditRecord[]>([])
const toolState = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
const toolError = ref('')
const toolNotice = ref('')
const toolLastResult = ref<ToolCallResult | null>(null)
const toolSearchRoot = ref('backend')
const toolSearchPattern = ref('*.md')
const toolAppName = ref('')
const toolFilePath = ref('')
const reminders = ref<ReminderRecord[]>([])
const desktopSettings = ref<DesktopSettings | null>(null)
const systemLogs = ref<SystemLogRecord[]>([])
const localStateStatus = ref<'idle' | 'loading' | 'saving' | 'ready' | 'error'>('idle')
const localStateError = ref('')
const localStateNotice = ref('')
const reminderTitle = ref('')
const reminderAt = ref('')
const activeReminderId = ref('')
const ragCollection = ref<RagCollection>('character_knowledge')
const ragFile = ref<File | null>(null)
const rtcVoiceprintCanStopRecording = computed(() => rtcVoiceprintRecordingSeconds.value >= 15)
const rtcVoiceprintAudioBusy = computed(() => (
  rtcVoiceprintRecordingState.value === 'recording'
  || rtcVoiceprintRecordingState.value === 'processing'
))
const ragSourceLabel = ref('')
const ragQuery = ref('')
const ragHealth = ref<RagHealthResponse | null>(null)
const ragHealthState = ref<'idle' | 'checking' | 'ready' | 'error'>('idle')
const ragHealthError = ref('')
const ragUploadState = ref<'idle' | 'uploading' | 'success' | 'error'>('idle')
const ragSearchState = ref<'idle' | 'searching' | 'success' | 'error'>('idle')
const ragError = ref('')
const ragNotice = ref('')
const ragResults = ref<RagSearchHit[]>([])
const ragRecentDocuments = ref<RagDocument[]>([])
const ragDeletingDocumentId = ref('')

// 人格 Profile：与 RAG 资料分离，可启用/停用/版本回滚
const personaProfiles = ref<PersonaProfile[]>([])
const activePersona = ref<PersonaProfile | null>(null)
const personaState = ref<'idle' | 'loading' | 'saving' | 'ready' | 'error'>('idle')
const personaError = ref('')
const personaNotice = ref('')
const personaBusyId = ref('')
const editingPersonaId = ref<string | null>(null)
const versioningPersonaId = ref<string | null>(null)
const personaVersions = ref<PersonaProfileVersion[]>([])
const personaClient = new PersonaClient({
  baseUrl: import.meta.env.VITE_PERSONA_GATEWAY_URL || speechConfig.gatewayUrl,
  enabled: import.meta.env.VITE_PERSONA_ENABLED !== 'false',
})
const personaDraft = reactive<PersonaProfileDraft>(emptyPersonaDraft())
let asrStream: SpeechAsrStream | null = null
let activeVoiceTurnId = 0
let activeCaptureMode: 'manual' | 'continuous' | null = null
let activeCaptureFinalizer: ((reason?: 'silence' | 'maximum-duration' | 'manual') => Promise<void>) | null = null
let activeCaptureCancel: (() => void) | null = null
let continuousConversationToken = 0
let continuousConversationFailures = 0
let voiceCaptureStartedAt = 0
// 最近一次 Agent 回复的 TTS 播放过程，供连续对话等待播放结束后再重新开麦。
let activeReplyPlayback: Promise<void> | null = null
const continuousVoiceStorageKey = 'canvas-pet-continuous-voice-enabled'
const wakeWordGateStorageKey = 'canvas-pet-wake-word-gate-enabled'
let resourceSaveTimer: number | undefined
let godotStatusTimer: number | undefined
let transientActionTimer: number | undefined
let gatewayStatusTimer: number | undefined
let gatewayHealthCheckInFlight = false
let gatewayReadyRefreshInFlight = false
let hasObservedGatewayReady = false
let ragHealthCheckInFlight = false
let personaRefreshInFlight = false
let suppressNextPetActionPublish = false
let suppressNextPetPreviewSync = false
let previewSyncInFlight: Promise<void> | null = null
let previewSyncDirty = false

const petSizeStorageKey = 'canvas-pet-window-size'
type PetPreviewState = {
  action: PetAction
  mouthMode: typeof mouthMode.value
  paused: boolean
  size: number
}
const actionConfigs = reactive<Record<PetAction, ActionConfig>>(
  Object.fromEntries(actions.map(({ id }) => [
    id,
    {
      start: 0,
      end: 3,
      fps: 8,
      loop: !['success', 'failure', 'refuse'].includes(id),
      sheet: '',
    },
  ])) as Record<PetAction, ActionConfig>,
)

function registerDefaultCharacterSpriteSheet() {
  Object.assign(sourceImages, createCrimsonElfCoreSpriteSheets())
  Object.assign(sourceImages, createCrimsonElfWalkSpriteSheets())
  Object.assign(sourceImages, createCrimsonElfTransitionSpriteSheets())
  Object.assign(supplementalActions, createCrimsonElfWalkActions())
  Object.assign(supplementalActions, createCrimsonElfTransitionActions())
  currentSourceKey.value = crimsonElfIdleSpriteSheetKey
  for (const action of Object.values(createCrimsonElfCoreActions())) {
    actionConfigs[action.id as PetAction] = {
      start: 0,
      end: 31,
      fps: 8,
      loop: true,
      sheet: action.sheet ?? '',
    }
  }
}

function clearSupplementalActions() {
  for (const key of Object.keys(supplementalActions) as Array<WalkAction | TransitionAction>) delete supplementalActions[key]
}

if (isDesktopMode || import.meta.env.DEV) registerDefaultCharacterSpriteSheet()

const sourceEntries = computed(() => Object.entries(sourceImages))
const sourceImage = computed(() => currentSourceKey.value ? sourceImages[currentSourceKey.value] : undefined)
const spriteSheet = computed(() => sourceImage.value)
const frameWidth = computed({
  get: () => sourceImage.value?.frameWidth ?? 0,
  set: (value: number) => {
    if (sourceImage.value) updateSourceFrameSize(sourceImage.value, Number(value) || 0, sourceImage.value.frameHeight)
  },
})
const frameHeight = computed({
  get: () => sourceImage.value?.frameHeight ?? 0,
  set: (value: number) => {
    if (sourceImage.value) updateSourceFrameSize(sourceImage.value, sourceImage.value.frameWidth, Number(value) || 0)
  },
})
const validFramesText = computed({
  get: () => sourceImage.value?.validFrameIndices.join(', ') ?? '',
  set: (value: string) => { if (sourceImage.value) sourceImage.value.validFrameIndices = parseFrameList(value) },
})
const blankFramesText = computed({
  get: () => sourceImage.value?.blankFrameIndices.join(', ') ?? '',
  set: (value: string) => { if (sourceImage.value) sourceImage.value.blankFrameIndices = parseFrameList(value) },
})
const anchorMode = computed<SpriteSheetSource['anchor'], SpriteSheetSource['anchor']>({
  get: () => sourceImage.value?.anchor ?? 'bottom-center',
  set: (value) => { if (sourceImage.value) sourceImage.value.anchor = value },
})

const manifest = computed<SpriteManifest>(() => ({
  schemaVersion: '1.0',
  name: sourceImage.value?.fileName ?? 'canvas-pet-placeholder',
  version: '0.1.0',
  canvas: { width: 520, height: 520, background: 'transparent' },
  spriteSheets: sourceEntries.value.length > 0 ? sourceImages : undefined,
  actions: {
    ...Object.fromEntries(actions.map(({ id, label }) => {
      const config = actionConfigs[id]
      return [id, {
        id,
        label,
        sheet: config.sheet || undefined,
        frameIndices: buildFrameIndices(config),
        fps: config.fps,
        loop: config.loop,
        interruptible: id !== 'working',
        anchor: sourceImages[config.sheet]?.anchor ?? anchorMode.value,
      }]
    })),
    ...supplementalActions,
  },
}))

const validation = computed(() => validateSpriteManifest(manifest.value))
const activeManifest = computed(() => manifest.value)
const currentLabel = computed(() => actions.find((item) => item.id === currentAction.value)?.label ?? '待机')

const currentVoicePersona = computed<VoicePersona>(() => findVoicePersona(selectedVoicePersonaId.value))

const selectedConfig = computed(() => actionConfigs[currentAction.value])
const frameTotal = computed(() => buildFrameIndices(selectedConfig.value).length)
const frameGridIndices = computed(() => Array.from({ length: spriteSheet.value?.frameCount ?? 0 }, (_, index) => index))
const currentActionFrames = computed(() => buildFrameIndices(selectedConfig.value))
const resourceMode = computed(() => sourceEntries.value.length === 0 ? '占位角色' : sourceImage.value?.src ? 'SpriteSheet 已导入' : '资源清单已载入')
const resourceState = computed(() => sourceEntries.value.length === 0 ? 'PENDING' : validation.value.valid && sourceEntries.value.every(([, source]) => Boolean(source.src)) ? 'READY' : validation.value.valid ? 'CONFIG' : 'CHECK')
const statusCopy = computed(() => {
  if (!validation.value.valid) return '动作清单需要修正'
  if (fallback.value) return '资源缺失，已回退到待机'
  if (paused.value) return '播放已暂停'
  return sourceImage.value?.src ? `${sourceImage.value.fileName} 帧预览中` : sourceImage.value ? '资源清单已载入，等待图片' : '占位角色预览中'
})

function resetActionConfigs() {
  for (const { id } of actions) {
    Object.assign(actionConfigs[id], {
      start: 0,
      end: 3,
      fps: 8,
      loop: !['success', 'failure', 'refuse'].includes(id),
      sheet: '',
      frameIndices: undefined,
    })
  }
}

function cancelScheduledResourcePersistence() {
  if (resourceSaveTimer === undefined) return
  window.clearTimeout(resourceSaveTimer)
  resourceSaveTimer = undefined
}

function scheduleResourcePersistence() {
  if (!resourcePersistenceEnabled.value) return
  cancelScheduledResourcePersistence()
  resourceStorageState.value = 'saving'
  resourceStorageError.value = ''
  resourceSaveTimer = window.setTimeout(async () => {
    resourceSaveTimer = undefined
    try {
      await saveResourcePackage(manifest.value)
      resourceStorageState.value = 'saved'
    } catch (error) {
      resourceStorageState.value = 'error'
      resourceStorageError.value = error instanceof Error ? error.message : '本地资源保存失败'
    }
  }, 350)
}

async function restoreSavedResourcePackage() {
  try {
    const saved = await loadResourcePackage()
    if (!saved) return
    if (isLegacyDefaultIdlePackage(saved.manifest)) {
      importNotice.value = '已检测到旧版默认待机资源，已切换到透明待机资源'
      return
    }

    resetActionConfigs()
    clearSupplementalActions()
    replaceSources(saved.manifest.spriteSheets ?? (saved.manifest.spriteSheet ? { default: saved.manifest.spriteSheet } : {}))
    for (const action of Object.values(saved.manifest.actions)) {
      if (action) applyActionDefinition(action)
    }
    resourcePersistenceEnabled.value = true
    currentSourceKey.value = ''
    syncCurrentSource(currentAction.value)
    resourceStorageState.value = 'restored'
    importNotice.value = `已恢复本地资源包（${new Date(saved.savedAt).toLocaleString()}）`
  } catch (error) {
    resourceStorageState.value = 'error'
    resourceStorageError.value = error instanceof Error ? error.message : '本地资源恢复失败'
  }
}

function isLegacyDefaultIdlePackage(savedManifest: SpriteManifest) {
  const sources = Object.values(savedManifest.spriteSheets ?? {})
  const legacyIdle = sources.find((source) => source.fileName === 'idle-front.png')
  const idle = savedManifest.actions.idle
  return Boolean(
    legacyIdle
    && legacyIdle.width === 1024
    && legacyIdle.height === 1024
    && idle
    && idle.frameIndices.length === 1
    && idle.frameIndices[0] === 0
    && idle.sheet === 'idle-front',
  )
}

async function saveCurrentResourcePackage() {
  cancelScheduledResourcePersistence()
  resourcePersistenceEnabled.value = true
  resourceStorageState.value = 'saving'
  resourceStorageError.value = ''
  try {
    await saveResourcePackage(manifest.value)
    resourceStorageState.value = 'saved'
    importNotice.value = '当前资源包已保存到本机'
  } catch (error) {
    resourceStorageState.value = 'error'
    resourceStorageError.value = error instanceof Error ? error.message : '本地资源保存失败'
  }
}

async function clearSavedResourcePackage() {
  cancelScheduledResourcePersistence()
  try {
    await clearResourcePackage()
    resourcePersistenceEnabled.value = false
    resourceStorageState.value = 'idle'
    resourceStorageError.value = ''
    importNotice.value = '已清除本机保存的资源包；当前预览仍保持不变'
  } catch (error) {
    resourceStorageState.value = 'error'
    resourceStorageError.value = error instanceof Error ? error.message : '本地资源清除失败'
  }
}

async function syncCurrentResourcePackageToGodot() {
  if (!validation.value.valid) {
    godotSyncState.value = 'error'
    godotSyncError.value = '清单存在错误，修正后才能同步到 Godot'
    return
  }

  godotSyncState.value = 'syncing'
  godotSyncError.value = ''
  try {
    const result = await syncResourcePackageToGodot(manifest.value)
    godotSyncState.value = 'synced'
    importNotice.value = `已同步 ${result.imageCount} 张 SpriteSheet；Godot 将自动重载资源`
  } catch (error) {
    godotSyncState.value = 'error'
    godotSyncError.value = error instanceof Error ? error.message : '同步到 Godot 失败'
  }
}

function restoreDefaultCharacterResource() {
  cancelScheduledResourcePersistence()
  resetActionConfigs()
  clearSupplementalActions()
  for (const key of Object.keys(sourceImages)) delete sourceImages[key]
  registerDefaultCharacterSpriteSheet()
  currentSourceKey.value = crimsonElfIdleSpriteSheetKey
  currentAction.value = 'idle'
  resourcePersistenceEnabled.value = false
  resourceStorageState.value = 'idle'
  resourceStorageError.value = ''
  importNotice.value = '已恢复默认角色资源'
}

function buildFrameIndices(config: ActionConfig) {
  if (config.frameIndices) return config.frameIndices
  if (!Number.isInteger(config.start) || !Number.isInteger(config.end) || config.start < 0 || config.end < config.start) return []
  return Array.from({ length: config.end - config.start + 1 }, (_, offset) => config.start + offset)
}

function sourceKeyForFile(fileName: string) {
  const exact = sourceEntries.value.find(([, source]) => source.fileName === fileName)
  return exact?.[0] ?? fileName
}

function syncCurrentSource(action: PetAction) {
  const configured = actionConfigs[action].sheet
  if (configured && sourceImages[configured]) {
    currentSourceKey.value = configured
    return
  }
  const byFileName = sourceEntries.value.find(([, source]) => source.fileName === configured)
  if (byFileName) {
    actionConfigs[action].sheet = byFileName[0]
    currentSourceKey.value = byFileName[0]
    return
  }
  if (sourceImages[action]) {
    actionConfigs[action].sheet = action
    currentSourceKey.value = action
    return
  }
  if (!currentSourceKey.value || !sourceImages[currentSourceKey.value]) currentSourceKey.value = sourceEntries.value[0]?.[0] ?? ''
}


function selectAction(action: PetAction) {
  const availableAction = normalizePetAction(action)
  currentAction.value = availableAction
  syncCurrentSource(availableAction)
  paused.value = false
}

function publishPetAction() {
  if (isDesktopMode) return
  void petEventGateway.publish({
    actionId: currentAction.value,
    mouthMode: mouthMode.value,
  })
}

async function broadcastPetPreview() {
  if (!isDesktopMode || !godotPetRunning.value) return
  previewSyncDirty = true
  if (previewSyncInFlight) return previewSyncInFlight

  previewSyncInFlight = (async () => {
    while (previewSyncDirty && godotPetRunning.value) {
      previewSyncDirty = false
      const state = {
        action: currentAction.value,
        mouthMode: mouthMode.value,
        paused: paused.value,
        size: petSize.value,
      } satisfies PetPreviewState
      await syncGodotPreviewState(state)
    }
  })().finally(() => {
    previewSyncInFlight = null
    if (previewSyncDirty && godotPetRunning.value) void broadcastPetPreview()
  })

  await previewSyncInFlight
}

async function showPetWindow() {
  const result = await startGodotPet()
  if (!result.ok) {
    godotPetError.value = result.message
    return
  }
  godotPetError.value = ''
  godotPetRunning.value = result.status.running
  godotPetPid.value = result.status.pid
  await broadcastPetPreview()
}

async function requestPetWindowToggle() {
  if (godotPetRunning.value) {
    const result = await stopGodotPet()
    if (!result.ok) {
      godotPetError.value = result.message
      return
    }
    godotPetError.value = ''
    godotPetRunning.value = false
    godotPetPid.value = undefined
    return
  }
  await showPetWindow()
}

async function refreshGodotPetStatus() {
  if (!isDesktopMode) return
  const status = await getGodotPetStatus()
  godotPetRunning.value = status.running
  godotPetPid.value = status.pid
  godotPetError.value = status.lastError ?? ''
}

async function refreshGatewayStatus() {
  if (!isDesktopMode) return
  gatewayStatus.value = await getGatewayStatus()
}

type BackgroundRefreshOptions = {
  silent?: boolean
  background?: boolean
}

async function refreshGatewayHealth(options: BackgroundRefreshOptions = {}) {
  if (gatewayHealthCheckInFlight) return
  gatewayHealthCheckInFlight = true
  if (!options.background) gatewayHealthState.value = 'checking'
  if (!options.silent) gatewayError.value = ''
  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), 5_000)
  try {
    const response = await fetch(`${speechConfig.gatewayUrl}/api/health`, { signal: controller.signal })
    const payload = await response.json().catch(() => ({})) as Partial<GatewayHealth>
    if (!response.ok || payload.ok !== true) {
      throw new Error(`本地网关请求失败（HTTP ${response.status}）`)
    }
    gatewayHealth.value = payload as GatewayHealth
    gatewayHealthState.value = 'ready'
  } catch (error) {
    gatewayHealth.value = null
    gatewayHealthState.value = 'error'
    if (options.silent && !options.background) return
    gatewayError.value = error instanceof DOMException && error.name === 'AbortError'
      ? '本地网关响应超时'
      : error instanceof Error && error.message
        ? `本地网关不可用：${error.message}`
        : '本地网关不可用'
  } finally {
    window.clearTimeout(timeoutId)
    gatewayHealthCheckInFlight = false
  }
}

async function refreshRuntimeDiagnostics(options: BackgroundRefreshOptions = {}) {
  await Promise.all([
    refreshGatewayHealth(options),
    refreshRagHealth(options),
    ...(isDesktopMode ? [refreshGatewayStatus(), refreshGodotPetStatus()] : []),
  ])
}

async function retryGateway() {
  await prepareDesktopGateway()
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

async function waitForGatewayReady(timeoutMs = 30_000) {
  const startedAt = Date.now()
  while (Date.now() - startedAt < timeoutMs) {
    await refreshGatewayHealth({ silent: true })
    if (gatewayHealthState.value === 'ready') return true
    await wait(300)
  }
  gatewayError.value = '本地网关进程已启动，但健康检查在限定时间内未就绪。请稍后点击“重试网关”。'
  return false
}

async function prepareDesktopGateway() {
  gatewayHealthState.value = 'checking'
  gatewayError.value = ''
  const result = await startGateway()
  if (!result.ok) {
    gatewayError.value = result.message
    return
  }
  gatewayStatus.value = result.status
  await waitForGatewayReady()
}

async function handleGatewayReady() {
  if (gatewayReadyRefreshInFlight) return
  gatewayReadyRefreshInFlight = true
  hasObservedGatewayReady = true
  try {
    await Promise.all([
      refreshRuntimeDiagnostics({ background: true }),
      refreshIdentity().then(() => Promise.all([
        refreshMemories(),
        refreshToolData(),
        refreshLocalState(),
      ])),
      loadRagDocuments(),
      refreshPersonas({ background: true }),
      refreshRtcVoiceprintBridge(),
      loadFaceStatus(),
    ])
  } finally {
    gatewayReadyRefreshInFlight = false
  }
}

function readSavedPetSize() {
  const saved = Number(window.localStorage.getItem(petSizeStorageKey))
  return Number.isFinite(saved) && saved > 0 ? clampPetWindowSize(saved) : undefined
}

function savePetSize(size: number) {
  window.localStorage.setItem(petSizeStorageKey, String(size))
}

async function initializePetSize() {
  petSize.value = readSavedPetSize() ?? 260
  savePetSize(petSize.value)
}

async function updatePetSize(event: Event) {
  const input = event.target as HTMLInputElement
  const size = clampPetWindowSize(Number(input.value))
  petSize.value = size
  savePetSize(size)
  if (isDesktopMode) {
    if (godotPetRunning.value) await broadcastPetPreview()
    return
  }
}

watch([currentAction, mouthMode], () => {
  if (suppressNextPetActionPublish) {
    suppressNextPetActionPublish = false
    return
  }
  publishPetAction()
})

watch([currentAction, mouthMode, paused], () => {
  if (suppressNextPetPreviewSync) {
    suppressNextPetPreviewSync = false
    return
  }
  if (godotPetRunning.value) void broadcastPetPreview()
})

watch(manifest, () => {
  if (godotSyncState.value === 'synced') godotSyncState.value = 'idle'
  scheduleResourcePersistence()
}, { deep: true })


function setTransientPetAction(action: PetAction, durationMs: number) {
  if (transientActionTimer !== undefined) window.clearTimeout(transientActionTimer)
  currentAction.value = action
  mouthMode.value = 'closed'
  transientActionTimer = window.setTimeout(() => {
    currentAction.value = 'idle'
    transientActionTimer = undefined
  }, durationMs)
}

function reset() {
  stopSpeech()
  cancelRecording()
  if (transientActionTimer !== undefined) window.clearTimeout(transientActionTimer)
  transientActionTimer = undefined
  currentAction.value = 'idle'
  syncCurrentSource('idle')
  paused.value = false
  mouthMode.value = 'closed'
}

function stopSpeech() {
  speechPlayback.stop()
  ttsError.value = ''
}

function closeAsrStream() {
  asrStream?.close()
  asrStream = null
}

function cancelRecording() {
  activeVoiceTurnId += 1
  activeCaptureCancel?.()
  activeCaptureCancel = null
  activeCaptureFinalizer = null
  activeCaptureMode = null
  audioRecorder.cancel()
  closeAsrStream()
  asrState.value = 'idle'
  asrError.value = ''
  if (currentAction.value === 'listening' || currentAction.value === 'thinking') currentAction.value = 'idle'
}

function setAsrFailure(message: string) {
  asrState.value = 'error'
  asrError.value = message
  currentAction.value = voiceInputActionFor('failure')
}

type VoiceCaptureOutcome = {
  cancelled: boolean
  text?: string
  language?: string | null
  traceId?: string | null
  error?: string
}

function waitForVoiceTurn(durationMs: number) {
  return new Promise<void>((resolve) => { window.setTimeout(resolve, durationMs) })
}

function traceVoicePipeline(stage: string, kind: Parameters<DebugHistoryStore['event']>[0]['kind'] = 'asr', status: Parameters<DebugHistoryStore['event']>[0]['status'] = 'info', detail?: unknown) {
  const stamp = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  voicePipelineTrace.value = [...voicePipelineTrace.value.slice(-8), `${stamp} ${stage}`]
  debugHistoryStore.event({ kind, status, message: stage, detail })
  if (typeof window !== 'undefined') {
    window.console.info('[voice-pipeline]', stage)
  }
}

function refreshDebugHistory() {
  debugHistoryRecords.value = debugHistoryStore.list()
}

function clearDebugHistory() {
  debugHistoryStore.clear()
  refreshDebugHistory()
}

function formatDebugTime(value?: string): string {
  if (!value) return '-'
  try {
    return new Date(value).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return value
  }
}

function beginVoiceCapture(mode: 'manual' | 'continuous'): Promise<VoiceCaptureOutcome> {
  if (
    asrState.value === 'recording'
    || asrState.value === 'recognizing'
    || ttsState.value !== 'idle'
    || agentState.value === 'thinking'
    || rtcVoiceprintAudioBusy.value
  ) {
    return Promise.resolve({ cancelled: false, error: '语音通道正忙' })
  }

  if (asrState.value === 'error') {
    asrState.value = 'idle'
    asrError.value = ''
  }

  asrError.value = ''
  asrText.value = ''
  voiceInputEvent.value = null
  voiceInputLevel.value = 0
  voicePipelineTrace.value = []
  traceVoicePipeline(`${mode === 'manual' ? '手动' : '连续'}语音捕获开始`)
  debugHistoryStore.start({
    title: `${mode === 'manual' ? '手动' : '连续'}语音调试`,
    kind: 'asr',
    source: mode === 'manual' ? 'manual-asr' : 'continuous-asr',
    language: asrLanguage.value,
  })
  refreshDebugHistory()
  voiceInputSpeechMs.value = 0
  const voiceTurnId = ++activeVoiceTurnId
  let finished = false
  // settled 只表示本次捕获的 Promise 是否已结算；finished 表示录音/收尾流程是否已结束。
  // 二者必须分开：finalizeCapture 一开始就会把 finished 置为 true，
  // 若复用同一个标志，收尾期间到达的 ASR final 将永远无法结算 Promise。
  let settled = false
  let recognizedText = ''
  let recognizedLanguage: string | null | undefined
  let recognizedTraceId: string | null | undefined
  let finalEventReceived = false
  let stream: SpeechAsrStream | null = null
  const detector = new VoiceActivityDetector({
    activationMs: 180,
    silenceMs: mode === 'manual' ? 1_200 : 900,
    maximumSpeechMs: 15_000,
  })

  const promise = new Promise<VoiceCaptureOutcome>((resolve) => {
    const resolveOnce = (outcome: VoiceCaptureOutcome) => {
      if (settled) return
      settled = true
      finished = true
      resolve(outcome)
    }
    const clearActiveCapture = () => {
      if (asrStream === stream) asrStream = null
      if (activeCaptureFinalizer === finalizeCapture) activeCaptureFinalizer = null
      if (activeCaptureCancel === cancelCapture) activeCaptureCancel = null
      if (activeCaptureMode === mode) activeCaptureMode = null
    }
    const cancelCapture = () => {
      debugHistoryStore.finish('warning', '语音捕获已取消')
      refreshDebugHistory()
      resolveOnce({ cancelled: true })
    }
    activeCaptureCancel = cancelCapture

    const finalizeCapture = async (reason?: 'silence' | 'maximum-duration' | 'manual' | 'provider-final') => {
      if (finished || asrState.value !== 'recording' || !stream) return
      finished = true
      traceVoicePipeline(`结束录音流程开始：${reason ?? 'unknown'}`, 'asr', 'info')
      asrState.value = 'recognizing'
      currentAction.value = voiceInputActionFor('recognizing')
      continuousConversationStatus.value = reason === 'maximum-duration'
        ? '已达到单句最长时长，正在识别…'
        : '检测到停顿，正在识别…'
      try {
        traceVoicePipeline('停止本地麦克风', 'asr')
        const audio = await audioRecorder.stop()
        traceVoicePipeline(`上传音频：${audio.size} bytes`)
        await stream.sendAudio(audio)
        // VAD has already detected an utterance boundary. Do not let the UI
        // wait indefinitely on provider final/closed events: use any visible
        // non-empty ASR text after a short grace period and continue to Agent.
        const hadTextBeforeStop = recognizedText.trim().length > 0
        if (finalEventReceived && hadTextBeforeStop) {
          recognizedText = recognizedText.trim()
        } else {
          const stopGraceMs = hadTextBeforeStop ? (reason === 'manual' ? 800 : 1_200) : 3_000
          const stopResult = await stream.stop(stopGraceMs)
          if (stopResult === 'partial-timeout') {
            const latest = stream.getLatestPartial()
            recognizedText = latest.text || recognizedText
            recognizedLanguage = latest.language ?? recognizedLanguage
            recognizedTraceId = latest.traceId ?? recognizedTraceId
            continuousConversationStatus.value = recognizedText.trim()
              ? 'ASR 已出文本，正在跳过 final 等待并提交 Agent…'
              : 'ASR final 超时，且没有可用文本…'
          }
        }
        traceVoicePipeline('ASR 捕获结束，准备进入后续链路', 'asr', 'success')
        const event = createVoiceInputEvent({
          text: recognizedText,
          language: recognizedLanguage ?? asrLanguage.value,
          traceId: recognizedTraceId,
        })
        if (!event) {
          const diagnostic = `豆包 ASR 未返回文本（本地人声 ${voiceInputSpeechMs.value}ms，峰值音量 ${voiceInputLevel.value}%）。请靠近麦克风、检查 Windows 输入设备，或改用手动录音测试。`
          setAsrFailure(diagnostic)
          traceVoicePipeline(`ASR 无有效文本：${diagnostic}`, 'asr', 'warning', diagnostic)
          debugHistoryStore.finish('warning', diagnostic)
          refreshDebugHistory()
          resolveOnce({ cancelled: false, error: diagnostic })
        } else {
          asrText.value = event.text
          voiceInputEvent.value = event
          asrState.value = 'success'
          asrError.value = ''
          debugHistoryStore.update({ transcript: event.text, language: event.language ?? asrLanguage.value, status: 'success' })
          resolveOnce({ cancelled: false, text: event.text, language: event.language, traceId: event.traceId })
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : '语音识别失败'
        setAsrFailure(message)
        traceVoicePipeline(`语音识别异常：${message}`, 'asr', 'error', message)
        debugHistoryStore.finish('error', message)
        refreshDebugHistory()
        resolveOnce({ cancelled: false, error: message })
      } finally {
        stream?.close()
        clearActiveCapture()
      }
    }
    activeCaptureFinalizer = finalizeCapture

    currentAction.value = voiceInputActionFor('recording')
    voiceCaptureStartedAt = Date.now()
    try {
      stream = speechClient.createAsrStream(asrLanguage.value, {
        onEvent: (event) => {
          if (voiceTurnId !== activeVoiceTurnId) return
          if (event.type === 'partial') {
            asrText.value = event.text
            recognizedText = event.text
            recognizedLanguage = event.language
            recognizedTraceId = event.traceId
            if (event.text.trim()) {
              continuousConversationStatus.value = `ASR 已识别：${event.text}，等待句尾确认…`
            }
          }
          if (event.type === 'final' || event.type === 'final-timeout') {
            recognizedText = event.text
            recognizedLanguage = event.language
            recognizedTraceId = event.traceId
            finalEventReceived = true
            if (event.text.trim()) {
              traceVoicePipeline('收到非空 ASR final', 'asr', 'success')
              continuousConversationStatus.value = 'ASR final 已确认，正在结束录音…'
              if (!finished) {
                void finalizeCapture('provider-final')
              } else {
                // System/WebView watchdog: a previous finalize can be waiting
                // on recorder/WebSocket teardown. A non-empty provider final is
                // sufficient to continue; do not let OS audio cleanup block the
                // local tool / Agent / TTS chain.
                traceVoicePipeline('final 看门狗强制放行后续链路', 'asr', 'warning')
                const forcedText = recognizedText.trim()
                const forcedLanguage = recognizedLanguage ?? asrLanguage.value
                const forcedTraceId = recognizedTraceId
                try { audioRecorder.cancel() } catch { /* recorder may already be stopped */ }
                try { stream?.close() } catch { /* stream may already be closed */ }
                clearActiveCapture()
                resolveOnce({
                  cancelled: false,
                  text: forcedText,
                  language: forcedLanguage,
                  traceId: forcedTraceId,
                })
              }
            }
          }
          if (event.type === 'error') {
            traceVoicePipeline(`ASR 错误：${event.message}`, 'asr', 'error', event.message)
            activeVoiceTurnId += 1
            finished = true
            audioRecorder.cancel()
            stream?.close()
            clearActiveCapture()
            setAsrFailure(event.message)
            debugHistoryStore.finish('error', event.message)
            refreshDebugHistory()
            resolveOnce({ cancelled: false, error: event.message })
          }
        },
      })
      void stream.start().then(async () => {
        if (voiceTurnId !== activeVoiceTurnId || finished) {
          stream?.close()
          resolveOnce({ cancelled: true })
          return
        }
        await audioRecorder.start({
          onSamples: (samples, sampleRate) => {
            if (voiceTurnId !== activeVoiceTurnId || finished || !detector) return
            const decision = detector.process(samples, sampleRate)
            voiceInputLevel.value = Math.round(Math.min(1, decision.energy / 0.15) * 100)
            voiceInputSpeechMs.value = decision.speechMs
            voiceNoiseFloor.value = decision.noiseFloor
            voiceActivationThreshold.value = decision.threshold
            if (mode === 'continuous') {
              const modeText = !wakeWordGateEnabled.value
                ? '等待人声'
                : continuousWakeSession.isUnlocked()
                  ? '30秒追问窗口内，可直接说话'
                  : '等待“米娅”'
              if (decision.phase === 'waiting') {
                continuousConversationStatus.value = `连续对话监听中：${modeText}，音量 ${voiceInputLevel.value}%`
              } else {
                continuousConversationStatus.value = `听到人声 ${(decision.speechMs / 1000).toFixed(1)} 秒，音量 ${voiceInputLevel.value}%，停顿后识别`
              }
            } else if (decision.phase === 'speaking') {
              continuousConversationStatus.value = `手动录音：听到人声 ${(decision.speechMs / 1000).toFixed(1)} 秒，停顿或点按钮后识别`
            } else {
              continuousConversationStatus.value = '手动录音监听中：正在校准环境噪声…'
            }
            if (decision.shouldStop) void finalizeCapture(decision.stopReason)
          },
        })
        if (voiceTurnId !== activeVoiceTurnId || finished) {
          audioRecorder.cancel()
          stream?.close()
          resolveOnce({ cancelled: true })
          return
        }
        asrStream = stream
        activeCaptureMode = mode
        asrState.value = 'recording'
        continuousConversationStatus.value = mode === 'continuous'
          ? (!wakeWordGateEnabled.value
            ? '连续对话监听中：请直接对桌宠说话'
            : continuousWakeSession.isUnlocked()
              ? '连续对话监听中：30秒内可直接追问'
              : '连续对话监听中：请先说“米娅”')
          : '手动录音监听中：停顿后会自动识别，也可点按钮停止'
      }).catch((error) => {
        if (finished) return
        const message = error instanceof Error ? error.message : '麦克风或语音识别启动失败'
        audioRecorder.cancel()
        stream?.close()
        clearActiveCapture()
        setAsrFailure(message)
        traceVoicePipeline(`麦克风/ASR 启动异常：${message}`, 'asr', 'error', message)
        debugHistoryStore.finish('error', message)
        refreshDebugHistory()
        resolveOnce({ cancelled: false, error: message })
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : '麦克风或语音识别启动失败'
      audioRecorder.cancel()
      stream?.close()
      clearActiveCapture()
      setAsrFailure(message)
      resolveOnce({ cancelled: false, error: message })
    }
  })

  return promise
}

async function toggleRecording() {
  if (continuousConversationEnabled.value) return
  if (asrState.value === 'recording' && activeCaptureMode === 'manual') {
    await activeCaptureFinalizer?.()
    return
  }
  if (
    ttsState.value !== 'idle'
    || asrState.value === 'recognizing'
    || agentState.value === 'thinking'
    || rtcVoiceprintAudioBusy.value
  ) return

  asrError.value = ''
  asrText.value = ''
  voiceInputEvent.value = null
  const outcomePromise = beginVoiceCapture('manual')
  void outcomePromise.then(async (outcome) => {
    if (!outcome.cancelled && outcome.text) {
      traceVoicePipeline(`手动链路拿到文本：${outcome.text}`, 'asr', 'success')
      debugHistoryStore.update({ transcript: outcome.text })
      continuousConversationStatus.value = '手动录音已识别，准备提交 Agent…'
      const handled = await submitRecognizedVoiceCommand(outcome.text, outcome.language ?? undefined)
      traceVoicePipeline(handled ? '手动语音后续链路完成' : '手动语音后续链路返回失败', handled ? 'system' : 'system', handled ? 'success' : 'error')
      debugHistoryStore.finish(handled ? 'success' : 'error', handled ? '语音链路完成' : '语音链路失败')
      refreshDebugHistory()
      if (!handled) continuousConversationStatus.value = '语音文本已识别，但 Agent 提交失败或被跳过'
      return
    }
    if (!outcome.cancelled && outcome.error) {
      continuousConversationStatus.value = outcome.error
      asrError.value = outcome.error
      debugHistoryStore.finish('error', outcome.error)
      refreshDebugHistory()
    }
  }).catch((error) => {
    const message = error instanceof Error ? error.message : '手动语音链路失败'
    continuousConversationStatus.value = message
    asrError.value = message
    setAsrFailure(message)
  })
}

function stopContinuousConversation() {
  continuousConversationEnabled.value = false
  continuousConversationToken += 1
  continuousWakeSession.reset()
  window.localStorage.setItem(continuousVoiceStorageKey, 'false')
  if (asrState.value === 'recording' && activeCaptureMode === 'continuous') {
    cancelRecording()
  } else if (currentAction.value === 'listening' || currentAction.value === 'thinking') {
    currentAction.value = 'idle'
  }
  continuousConversationStatus.value = '连续对话已关闭'
}


function persistWakeWordGate() {
  window.localStorage.setItem(wakeWordGateStorageKey, wakeWordGateEnabled.value ? 'true' : 'false')
  continuousWakeSession.reset()
  continuousConversationStatus.value = wakeWordGateEnabled.value
    ? '已开启唤醒词门控：请先说“米娅”（ミーア / Miya），唤醒后30秒内可直接追问'
    : '已关闭唤醒词门控：连续对话会接受所有人声'
}

async function toggleContinuousConversation(event: Event) {
  const enabled = (event.target as HTMLInputElement).checked
  if (!enabled) {
    stopContinuousConversation()
    return
  }
  if (
    !speechConfig.enabled
    || !gatewayHealth.value?.doubaoAsrConfigured
    || ttsState.value !== 'idle'
    || asrState.value === 'recognizing'
    || agentState.value === 'thinking'
    || rtcVoiceprintAudioBusy.value
  ) {
    continuousConversationEnabled.value = false
    continuousConversationStatus.value = '豆包 ASR 未就绪或语音通道正忙，暂时不能开启'
    return
  }

  continuousConversationEnabled.value = true
  window.localStorage.setItem(continuousVoiceStorageKey, 'true')
  const token = ++continuousConversationToken
  continuousConversationFailures = 0
  continuousWakeSession.reset()
  try {
    while (token === continuousConversationToken && continuousConversationEnabled.value) {
      asrText.value = ''
      const outcome = await beginVoiceCapture('continuous')
      if (token !== continuousConversationToken || outcome.cancelled) break
      if (outcome.error || !outcome.text) {
        continuousConversationFailures += 1
        if (continuousConversationFailures >= 3) {
          continuousConversationStatus.value = '连续多次没有听清，已自动关闭连续对话'
          break
        }
        continuousConversationStatus.value = `没有听清（本地人声 ${voiceInputSpeechMs.value}ms，音量 ${voiceInputLevel.value}%），稍后继续监听…`
        await waitForVoiceTurn(450)
        continue
      }

      if (wakeWordGateEnabled.value) {
        const wakeDecision = continuousWakeSession.decide(outcome.text)
        if (!wakeDecision.accepted) {
          continuousConversationStatus.value = `已忽略环境语音：${outcome.text}。请先说“米娅”`
          await waitForVoiceTurn(450)
          continue
        }
        outcome.text = wakeDecision.command
        if (wakeDecision.justWoken && !outcome.text) {
          continuousConversationStatus.value = '我在，请说指令。'
          await speechPlayback.playText('我在，请说指令。', asrLanguage.value, voiceOptionsForAction(findVoicePersonaForLanguage(asrLanguage.value, selectedVoicePersonaId.value), 'speaking'))
          await waitForVoiceTurn(220)
          continue
        }
      }

      continuousConversationFailures = 0
      continuousConversationStatus.value = '桌宠回复中，麦克风已自动避让…'
      const handled = await submitRecognizedVoiceCommand(outcome.text, outcome.language ?? undefined)
      debugHistoryStore.finish(
        handled ? 'success' : 'error',
        handled ? '语音链路完成' : '语音链路失败',
      )
      refreshDebugHistory()
      // 等回复 TTS 播放结束再重新开麦，避免桌宠听到自己的声音（带超时兜底，防止卡死监听循环）。
      if (handled) await waitForReplyPlayback(15_000)
      if (handled && wakeWordGateEnabled.value) continuousWakeSession.keepAlive()
      if (!handled) {
        continuousConversationFailures += 1
        if (continuousConversationFailures >= 3) {
          continuousConversationStatus.value = '连续处理失败，已自动关闭连续对话'
          break
        }
      }
      if (token !== continuousConversationToken) break
      await waitForVoiceTurn(220)
      continuousConversationStatus.value = wakeWordGateEnabled.value
        ? '连续对话监听中：30秒内可直接追问，超时请再次叫“米娅”'
        : '连续对话监听中：请直接对桌宠说话'
    }
  } finally {
    if (token === continuousConversationToken) {
      continuousConversationEnabled.value = false
      window.localStorage.setItem(continuousVoiceStorageKey, 'false')
      continuousWakeSession.reset()
      if (asrState.value === 'recording' && activeCaptureMode === 'continuous') cancelRecording()
    }
  }
}

function resetVoiceDebugOptions() {
  const persona = findVoicePersona(selectedVoicePersonaId.value)
  ttsDebugSpeed.value = persona.speed
  ttsDebugPitch.value = persona.pitch
  ttsDebugVolume.value = persona.vol
  ttsDebugEmotion.value = persona.emotion
}

async function speakText() {
  const text = ttsText.value.trim()
  if (!text || ttsState.value === 'synthesizing' || rtcVoiceprintAudioBusy.value) return
  debugHistoryStore.start({ title: '手动 TTS 调试', kind: 'tts', source: 'manual-tts', language: ttsLanguage.value })
  debugHistoryStore.update({ transcript: text })
  refreshDebugHistory()
  ttsError.value = ''
  const persona = findVoicePersona(selectedVoicePersonaId.value)
  debugHistoryStore.event({ kind: 'tts', status: 'info', message: '调用 MiniMax TTS 合成并播放' })
  try {
    traceVoicePipeline('调用 MiniMax TTS 合成并播放', 'tts')
    await speechPlayback.playText(text, ttsLanguage.value, {
      ...voiceOptionsForAction(persona, 'speaking'),
      emotion: ttsDebugEmotion.value,
      speed: Number(ttsDebugSpeed.value),
      pitch: Number(ttsDebugPitch.value),
      vol: Number(ttsDebugVolume.value),
    })
    debugHistoryStore.update({ reply: text, status: 'success' })
    debugHistoryStore.finish('success', '手动 TTS 播放完成')
  } catch (error) {
    const message = error instanceof Error ? error.message : '手动 TTS 播放失败'
    ttsError.value = message
    debugHistoryStore.finish('error', message)
  } finally {
    refreshDebugHistory()
  }
}

function waitForReplyPlayback(timeoutMs: number): Promise<void> {
  const playback = activeReplyPlayback ?? Promise.resolve()
  let timeoutId = 0
  const timeout = new Promise<void>((resolve) => {
    timeoutId = window.setTimeout(resolve, timeoutMs)
  })
  return Promise.race([playback, timeout]).finally(() => window.clearTimeout(timeoutId))
}

function playAgentSpeech(text: string, language: string) {
  if (
    !speechConfig.enabled
    || rtcVoiceprintAudioBusy.value
    || asrState.value === 'recording'
    || asrState.value === 'recognizing'
  ) return
  const persona = findVoicePersona(selectedVoicePersonaId.value)
  // 记录播报前的动作：播放期间 coordinator 会切到 speaking，
  // 播报结束后需要恢复 Agent 指定的非说话动作（如 displeased / open-app）。
  const actionBeforeSpeech = currentAction.value
  const playback = speechPlayback
    .playText(text, language, voiceOptionsForAction(persona, currentAction.value))
    .then(() => undefined, () => undefined)
  const tracked = playback.then(() => {
    if (activeReplyPlayback === tracked) activeReplyPlayback = null
    if (
      actionBeforeSpeech !== 'speaking'
      && actionBeforeSpeech !== currentAction.value
    ) {
      currentAction.value = actionBeforeSpeech
    }
  })
  activeReplyPlayback = tracked
}

type AgentMessageSource = 'text' | 'voice'

async function submitRecognizedVoiceCommand(message: string, language?: string): Promise<boolean> {
  const voiceLanguage = normalizeVoiceLanguageCode(language ?? asrLanguage.value)
  // Agent 当前统一接受 en-US；MiniMax 仍可使用英音音色朗读返回内容。
  const agentLanguageCode = voiceLanguage.startsWith('en') ? 'en-US' : voiceLanguage
  // ASR 识别出的内容仍标记为 voice，由后端统一执行语音工具规划；
  // 普通聊天再进入 Agent，避免前端和后端长期保留两套工具路由。
  return submitAgentMessage(message, { source: 'voice', language: agentLanguageCode })
}

async function submitAgentMessage(message: string, options: { source?: AgentMessageSource; language?: string } = {}): Promise<boolean> {
  const source = options.source ?? 'text'
  const language = options.language ?? agentLanguage.value
  if (!message) return false
  if (source === 'text' && agentState.value === 'thinking') return false

  agentError.value = ''
  agentState.value = 'thinking'
  if (source === 'voice') {
    continuousConversationStatus.value = 'Agent 已收到请求，正在思考…'
  }
  agentMessages.value.push({ role: 'user', text: message })
  currentAction.value = 'thinking'
  try {
    const response: AgentResponse = await agentClient.chat({
      message,
      language,
      sessionId: agentSessionId.value,
      source,
      ragCollection: ragCollection.value,
    }, applyAgentEvent)
    agentMessages.value.push({
      role: 'assistant',
      text: response.text,
      traceId: response.trace_id,
      sources: response.sources,
      ragStatus: response.rag_status,
      ragCollection: ragCollection.value,
    })
    const finalAction = normalizePetAction(response.action_id)
    const voiceAction: PetAction = source === 'voice' && finalAction === 'idle' ? 'speaking' : finalAction
    const voiceResponse: AgentResponse = voiceAction !== finalAction
      ? { ...response, action_id: voiceAction, mouth_mode: response.mouth_mode === 'closed' ? 'half-open' : response.mouth_mode }
      : response
    applyAgentResponseAction(voiceResponse)
    if (source === 'voice') {
      if (isDesktopMode && godotPetRunning.value) await broadcastPetPreview()
      const persona = findVoicePersonaForLanguage(response.language, selectedVoicePersonaId.value)
      const voiceOptions = voiceOptionsForAction(persona, voiceAction)
      if (activePersona.value?.voice_id) {
        voiceOptions.voiceId = activePersona.value.voice_id
      }
      continuousConversationStatus.value = 'MiniMax TTS 正在合成并播放回复…'
      await speechPlayback.playText(response.text, response.language, voiceOptions)
      // 工具/情绪类动作在 TTS 口型结束后恢复为 Agent 指定动作（例如 open-app / displeased）。
      if (voiceAction !== 'speaking') {
        applyAgentResponseAction(response)
        if (isDesktopMode && godotPetRunning.value) await broadcastPetPreview()
        else if (!isDesktopMode) publishPetAction()
      }
    } else {
      playAgentSpeech(response.text, response.language)
    }
    window.setTimeout(() => {
      // If the returned state did not change a watched value, do not let the
      // suppression marker affect the next user-initiated action.
      suppressNextPetActionPublish = false
      suppressNextPetPreviewSync = false
    }, 0)
    agentState.value = 'success'
    if (response.memory_candidates.length) void refreshMemories()
    if (source === 'voice') {
      traceVoicePipeline('Agent 回复与 TTS 播放完成', 'audio', 'success')
      debugHistoryStore.update({ reply: response.text, status: 'success' })
      debugHistoryStore.finish('success', 'Agent 回复与 TTS 播放完成')
      refreshDebugHistory()
    }
    return true
  } catch (error) {
    const messageText = error instanceof AgentClientError || error instanceof Error
      ? error.message
      : '文本对话失败'
    agentState.value = 'error'
    agentError.value = messageText
    currentAction.value = 'displeased'
    if (source === 'voice') {
      traceVoicePipeline(`Agent/TTS 链路失败：${messageText}`, 'agent', 'error', messageText)
      debugHistoryStore.finish('error', messageText)
      refreshDebugHistory()
    }
    return false
  }
}

async function sendAgentMessage() {
  const message = agentText.value.trim()
  if (!message || agentState.value === 'thinking') return
  agentText.value = ''
  await submitAgentMessage(message)
}

function applyAgentResponseAction(response: AgentResponse) {
  if (!isPetAction(response.action_id)) return
  suppressNextPetActionPublish = true
  suppressNextPetPreviewSync = true
  currentAction.value = normalizePetAction(response.action_id)
  mouthMode.value = response.mouth_mode
}

function applyAgentEvent(event: AgentClientEvent) {
  if (event.type !== 'pet.action') return
  const rawActionId = typeof event.action.action_id === 'string'
    ? event.action.action_id
    : typeof event.action.actionId === 'string'
      ? event.action.actionId
      : undefined
  const actionId = rawActionId ? normalizePetAction(rawActionId) : undefined
  if (!actionId || !isPetAction(actionId)) return

  const mouth = event.action.mouth_mode ?? event.action.mouthMode
  suppressNextPetActionPublish = true
  suppressNextPetPreviewSync = true
  currentAction.value = actionId
  if (mouth === 'closed' || mouth === 'half-open' || mouth === 'open') {
    mouthMode.value = mouth
  }
}

function memoryDraft(item: Pick<MemoryCandidate | MemoryRecord, 'content' | 'category'>): MemoryDraft {
  return { content: item.content, category: item.category }
}

function replaceMemoryCandidate(candidate: MemoryCandidate) {
  memoryCandidates.value = memoryCandidates.value.map((item) => item.id === candidate.id ? candidate : item)
}

function replaceConfirmedMemory(memory: MemoryRecord) {
  confirmedMemories.value = confirmedMemories.value.map((item) => item.id === memory.id ? memory : item)
}

async function refreshMemories() {
  if (identitySnapshot.value && !identitySnapshot.value.can_read_private_memory) {
    memoryCandidates.value = []
    confirmedMemories.value = []
    memoryState.value = 'idle'
    memoryError.value = ''
    return
  }
  memoryState.value = 'loading'
  memoryError.value = ''
  try {
    const [candidates, memories] = await Promise.all([
      memoryClient.listCandidates(),
      memoryClient.listMemories(),
    ])
    memoryCandidates.value = candidates
    confirmedMemories.value = memories
    memoryState.value = 'idle'
  } catch (error) {
    memoryState.value = 'error'
    memoryError.value = error instanceof MemoryClientError || error instanceof Error
      ? error.message
      : '记忆列表加载失败'
  }
}

function identityStatusLabel(status: IdentityStatus | undefined) {
  if (status === 'owner_verified') return '主人已验证'
  if (status === 'guest') return '访客模式'
  return '未验证'
}

const identityTemporaryOpen = computed(() => Boolean(identitySnapshot.value?.temporary_open_access))

async function refreshIdentity(quiet = false) {
  if (!quiet) identityState.value = 'loading'
  identityError.value = ''
  try {
    const previousSnapshot = identitySnapshot.value
    const nextSnapshot = await identityClient.getStatus()
    identitySnapshot.value = nextSnapshot
    identityState.value = 'ready'
    if (
      previousSnapshot
      && (
        previousSnapshot.status !== nextSnapshot.status
        || previousSnapshot.can_read_private_memory !== nextSnapshot.can_read_private_memory
        || previousSnapshot.can_use_tools !== nextSnapshot.can_use_tools
        || previousSnapshot.temporary_open_access !== nextSnapshot.temporary_open_access
      )
    ) {
      await Promise.all([refreshMemories(), refreshToolData(), refreshLocalState()])
    }
  } catch (error) {
    identityState.value = 'error'
    identityError.value = error instanceof IdentityClientError || error instanceof Error
      ? error.message
      : '身份状态加载失败'
  }
}

async function mockVerifyIdentity(sample: 'owner' | 'guest') {
  identityState.value = 'loading'
  identityError.value = ''
  try {
    identitySnapshot.value = await identityClient.mockVerify(sample)
    identityState.value = 'ready'
    await Promise.all([refreshMemories(), refreshToolData(), refreshLocalState()])
  } catch (error) {
    identityState.value = 'error'
    identityError.value = error instanceof IdentityClientError || error instanceof Error
      ? error.message
      : '身份验证失败'
  }
}

async function resetIdentity() {
  identityState.value = 'loading'
  identityError.value = ''
  try {
    identitySnapshot.value = await identityClient.reset()
    identityState.value = 'ready'
    await Promise.all([refreshMemories(), refreshToolData(), refreshLocalState()])
  } catch (error) {
    identityState.value = 'error'
    identityError.value = error instanceof IdentityClientError || error instanceof Error
      ? error.message
      : '身份重置失败'
  }
}

async function refreshRtcVoiceprintBridge() {
  rtcVoiceprintBridgeState.value = 'loading'
  try {
    rtcVoiceprintBridge.value = await identityClient.getRtcVoiceprintBridge()
    rtcVoiceprintBridgeState.value = 'ready'
  } catch {
    rtcVoiceprintBridge.value = null
    rtcVoiceprintBridgeState.value = 'error'
  }
}

function rtcVoiceprintSessionStatusLabel() {
  if (rtcVoiceprintSessionState.value === 'starting') return '启动中'
  if (rtcVoiceprintSessionState.value === 'active') return '运行中'
  if (rtcVoiceprintSessionState.value === 'stopping') return '停止中'
  if (rtcVoiceprintSessionState.value === 'error') return '异常'
  return rtcVoiceprintSession.value ? '已停止' : '未启动'
}

function parsedRtcVoiceprintTargetUserIds(): string[] {
  return [...new Set<string>(
    rtcVoiceprintTargetUserIds.value
      .split(/[\n,，]/)
      .map((value: string) => value.trim())
      .filter(Boolean),
  )]
}

async function startRtcVoiceprintSession() {
  if (rtcVoiceprintSessionState.value === 'starting' || rtcVoiceprintSessionState.value === 'active' || rtcVoiceprintSessionState.value === 'stopping') return
  const roomId = rtcVoiceprintRoomId.value.trim()
  const agentUserId = rtcVoiceprintAgentUserId.value.trim()
  const targetUserIds = parsedRtcVoiceprintTargetUserIds()
  if (!roomId || !agentUserId || targetUserIds.length === 0) {
    rtcVoiceprintSessionState.value = 'error'
    rtcVoiceprintSessionError.value = '请填写房间 ID、Agent 用户 ID 和至少一个目标用户 ID'
    return
  }
  if (!rtcVoiceprintBridge.value?.sessionControlAvailable) {
    rtcVoiceprintSessionState.value = 'error'
    rtcVoiceprintSessionError.value = rtcVoiceprintBridge.value?.message ?? 'RTC 会话控制尚未就绪'
    return
  }

  rtcVoiceprintSessionState.value = 'starting'
  rtcVoiceprintSessionError.value = ''
  try {
    rtcVoiceprintSession.value = await identityClient.startRtcVoiceprintSession({
      roomId,
      agentUserId,
      targetUserIds,
      confirmed: true,
    })
    rtcVoiceprintSessionState.value = 'active'
  } catch (error) {
    rtcVoiceprintSessionState.value = 'error'
    rtcVoiceprintSessionError.value = error instanceof IdentityClientError || error instanceof Error
      ? error.message
      : 'RTC 声纹验证会话启动失败'
  }
}

async function startOfficialRtcClient() {
  const session = rtcVoiceprintSession.value
  if (!session?.taskId || !session.roomId) {
    rtcOfficialClientState.value = 'error'
    rtcOfficialClientError.value = '请先启动 RTC 验证会话'
    return
  }
  const userId = parsedRtcVoiceprintTargetUserIds()[0]
  if (!userId) {
    rtcOfficialClientState.value = 'error'
    rtcOfficialClientError.value = '没有可用的目标用户 ID'
    return
  }
  if (rtcOfficialClientState.value !== 'idle' && rtcOfficialClientState.value !== 'error') return

  rtcOfficialClientState.value = 'joining'
  rtcOfficialClientError.value = ''
  try {
    const token = await identityClient.getRtcClientToken(session.taskId, userId)
    await rtcOfficialClient.joinAndPublish(
      token,
      (message) => { rtcOfficialClientError.value = message },
      (diagnostic) => { rtcOfficialClientDiagnostic.value = diagnostic },
    )
    rtcOfficialClientState.value = 'active'
  } catch (error) {
    rtcOfficialClientState.value = 'error'
    rtcOfficialClientError.value = error instanceof IdentityClientError || error instanceof Error
      ? error.message
      : '官方 RTC SDK 入房失败'
  }
}

async function stopOfficialRtcClient() {
  if (rtcOfficialClientState.value === 'idle' || rtcOfficialClientState.value === 'stopping') return
  rtcOfficialClientState.value = 'stopping'
  try {
    await rtcOfficialClient.leave()
    rtcOfficialClientState.value = 'idle'
    rtcOfficialClientDiagnostic.value = rtcOfficialClient.currentDiagnostic
  } catch (error) {
    rtcOfficialClientState.value = 'error'
    rtcOfficialClientError.value = error instanceof Error ? error.message : '官方 RTC SDK 退房失败'
  }
}

async function stopRtcVoiceprintSession() {
  const taskId = rtcVoiceprintSession.value?.taskId
  if (!taskId || rtcVoiceprintSessionState.value === 'stopping') return

  rtcVoiceprintSessionState.value = 'stopping'
  rtcVoiceprintSessionError.value = ''
  try {
    await stopOfficialRtcClient()
    rtcVoiceprintSession.value = await identityClient.stopRtcVoiceprintSession(taskId)
    rtcVoiceprintSessionState.value = 'idle'
    await refreshIdentity()
    await Promise.all([refreshMemories(), refreshToolData(), refreshLocalState()])
  } catch (error) {
    rtcVoiceprintSessionState.value = 'error'
    rtcVoiceprintSessionError.value = error instanceof IdentityClientError || error instanceof Error
      ? error.message
      : 'RTC 声纹验证会话停止失败'
  }
}

async function selectRtcVoiceprintFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  input.value = ''
  await setRtcVoiceprintFile(file)
}

async function setRtcVoiceprintFile(file: File | null) {
  rtcVoiceprintFile.value = file
  rtcVoiceprintValidation.value = null
  rtcVoiceprintEnrollment.value = null
  rtcVoiceprintEnrollmentError.value = ''
  rtcVoiceprintRecordingError.value = ''
  rtcVoiceprintEnrollmentState.value = 'idle'
  rtcVoiceprintConfirmed.value = false
  if (!file) return

  try {
    rtcVoiceprintValidation.value = await validateVoiceprintWav(file)
  } catch {
    rtcVoiceprintValidation.value = { valid: false, message: '无法读取 WAV 文件' }
  }
}

function clearRtcVoiceprintRecordingTimer() {
  if (rtcVoiceprintRecordingTimer !== undefined) {
    window.clearInterval(rtcVoiceprintRecordingTimer)
    rtcVoiceprintRecordingTimer = undefined
  }
}

function updateRtcVoiceprintRecordingSeconds() {
  if (rtcVoiceprintRecordingStartedAt.value === null) return
  rtcVoiceprintRecordingSeconds.value = Math.min(
    30,
    Math.floor((Date.now() - rtcVoiceprintRecordingStartedAt.value) / 1_000),
  )
}

async function startRtcVoiceprintRecording() {
  if (rtcVoiceprintAudioBusy.value) return
  if (asrState.value === 'recording' || asrState.value === 'recognizing') {
    rtcVoiceprintRecordingState.value = 'error'
    rtcVoiceprintRecordingError.value = '请先完成当前语音识别，再录制声纹样本'
    return
  }
  if (ttsState.value !== 'idle') {
    rtcVoiceprintRecordingState.value = 'error'
    rtcVoiceprintRecordingError.value = '请等待语音播放结束，再录制声纹样本'
    return
  }

  rtcVoiceprintRecordingError.value = ''
  rtcVoiceprintRecordingState.value = 'idle'
  await setRtcVoiceprintFile(null)
  try {
    await voiceprintRecorder.start()
    rtcVoiceprintRecordingStartedAt.value = Date.now()
    rtcVoiceprintRecordingSeconds.value = 0
    rtcVoiceprintRecordingState.value = 'recording'
    currentAction.value = 'listening'
    rtcVoiceprintRecordingTimer = window.setInterval(() => {
      updateRtcVoiceprintRecordingSeconds()
      if (rtcVoiceprintRecordingSeconds.value >= 30) void stopRtcVoiceprintRecording()
    }, 250)
  } catch (error) {
    voiceprintRecorder.cancel()
    rtcVoiceprintRecordingState.value = 'error'
    rtcVoiceprintRecordingError.value = error instanceof Error ? error.message : '无法启动麦克风录音'
  }
}

async function stopRtcVoiceprintRecording() {
  if (rtcVoiceprintRecordingState.value !== 'recording') return
  updateRtcVoiceprintRecordingSeconds()
  if (rtcVoiceprintRecordingSeconds.value < 15) return

  clearRtcVoiceprintRecordingTimer()
  rtcVoiceprintRecordingState.value = 'processing'
  try {
    const audio = await voiceprintRecorder.stop(30)
    const file = new File(
      [audio],
      `voiceprint-${new Date().toISOString().replace(/[:.]/g, '-')}.wav`,
      { type: 'audio/wav' },
    )
    await setRtcVoiceprintFile(file)
    rtcVoiceprintRecordingState.value = rtcVoiceprintValidation.value?.valid ? 'idle' : 'error'
    if (!rtcVoiceprintValidation.value?.valid) {
      rtcVoiceprintRecordingError.value = rtcVoiceprintValidation.value?.message ?? '录音样本未通过本地校验'
    }
  } catch (error) {
    voiceprintRecorder.cancel()
    rtcVoiceprintRecordingState.value = 'error'
    rtcVoiceprintRecordingError.value = error instanceof Error ? error.message : '声纹样本录制失败'
  } finally {
    rtcVoiceprintRecordingStartedAt.value = null
    if (currentAction.value === 'listening') currentAction.value = 'idle'
  }
}

function cancelRtcVoiceprintRecording() {
  voiceprintRecorder.cancel()
  clearRtcVoiceprintRecordingTimer()
  rtcVoiceprintRecordingState.value = 'idle'
  rtcVoiceprintRecordingError.value = ''
  rtcVoiceprintRecordingStartedAt.value = null
  rtcVoiceprintRecordingSeconds.value = 0
  if (currentAction.value === 'listening') currentAction.value = 'idle'
}

function clearRtcVoiceprintSample() {
  if (rtcVoiceprintAudioBusy.value) return
  void setRtcVoiceprintFile(null)
}

async function registerRtcVoiceprint() {
  const file = rtcVoiceprintFile.value
  const validation = rtcVoiceprintValidation.value
  if (!file || !validation?.valid || !rtcVoiceprintConfirmed.value) return

  rtcVoiceprintEnrollmentState.value = 'uploading'
  rtcVoiceprintEnrollmentError.value = ''
  rtcVoiceprintEnrollment.value = null
  try {
    rtcVoiceprintEnrollment.value = await identityClient.registerRtcVoiceprint(file, true)
    rtcVoiceprintEnrollmentState.value = 'success'
    await Promise.all([refreshRtcVoiceprintBridge(), refreshRuntimeDiagnostics()])
  } catch (error) {
    rtcVoiceprintEnrollmentState.value = 'error'
    rtcVoiceprintEnrollmentError.value = error instanceof IdentityClientError || error instanceof Error
      ? error.message
      : '声纹注册失败'
  }
}

function toolDefinition(name: string) {
  return toolDefinitions.value.find((item) => item.name === name)
}

function toolNameLabel(name: string) {
  return toolDefinition(name)?.label ?? name
}

function toolJson(value: unknown) {
  return JSON.stringify(value, null, 2)
}

async function refreshToolData() {
  toolState.value = 'loading'
  toolError.value = ''
  try {
    const definitions = await toolClient.listTools()
    toolDefinitions.value = definitions
    if (identitySnapshot.value?.can_use_tools) {
      const [approvals, audit] = await Promise.all([
        toolClient.listApprovals(),
        toolClient.listAudit(),
      ])
      toolApprovals.value = approvals
      toolAudit.value = audit
    } else {
      toolApprovals.value = []
      toolAudit.value = []
    }
    toolState.value = 'ready'
  } catch (error) {
    toolState.value = 'error'
    toolError.value = error instanceof ToolClientError || error instanceof Error
      ? error.message
      : '受控工具状态加载失败'
  }
}

function applyDesktopSettings(settings: DesktopSettings) {
  desktopSettings.value = settings
  // 仅在用户从未显式切换过对应语言时，才使用设置中的“默认语言”作为初值；
  // 用户显式选择的语言已持久化，刷新本地状态或重启应用都不会被覆盖。
  if (!readStoredLanguage(ttsLanguageStorageKey)) ttsLanguage.value = settings.language
  if (!readStoredLanguage(asrLanguageStorageKey)) asrLanguage.value = settings.language
  if (!readStoredLanguage(agentLanguageStorageKey)) agentLanguage.value = settings.language
}

async function refreshLocalState() {
  if (identitySnapshot.value && !identitySnapshot.value.can_read_private_memory) {
    reminders.value = []
    desktopSettings.value = null
    systemLogs.value = []
    localStateStatus.value = 'idle'
    localStateError.value = ''
    return
  }

  localStateStatus.value = 'loading'
  localStateError.value = ''
  try {
    const [settings, pendingReminders, logs] = await Promise.all([
      localStateClient.getSettings(),
      localStateClient.listReminders(),
      localStateClient.listLogs(),
    ])
    applyDesktopSettings(settings)
    reminders.value = pendingReminders
    systemLogs.value = logs
    localStateStatus.value = 'ready'
  } catch (error) {
    localStateStatus.value = 'error'
    localStateError.value = error instanceof LocalStateClientError || error instanceof Error
      ? error.message
      : '本地状态加载失败'
  }
}

async function createReminder() {
  localStateStatus.value = 'saving'
  localStateError.value = ''
  localStateNotice.value = ''
  try {
    const reminder = await localStateClient.createReminder({
      title: reminderTitle.value,
      remindAt: reminderAt.value,
      sessionId: agentSessionId.value,
    })
    reminders.value = [...reminders.value, reminder].sort((left, right) => left.remind_at.localeCompare(right.remind_at))
    reminderTitle.value = ''
    reminderAt.value = ''
    systemLogs.value = await localStateClient.listLogs()
    localStateNotice.value = '提醒已保存到本机'
    localStateStatus.value = 'ready'
  } catch (error) {
    localStateStatus.value = 'error'
    localStateError.value = error instanceof LocalStateClientError || error instanceof Error
      ? error.message
      : '提醒创建失败'
  }
}

async function cancelReminder(reminderId: string) {
  activeReminderId.value = reminderId
  localStateStatus.value = 'saving'
  localStateError.value = ''
  localStateNotice.value = ''
  try {
    await localStateClient.cancelReminder(reminderId)
    reminders.value = reminders.value.filter((item) => item.id !== reminderId)
    systemLogs.value = await localStateClient.listLogs()
    localStateNotice.value = '提醒已取消'
    localStateStatus.value = 'ready'
  } catch (error) {
    localStateStatus.value = 'error'
    localStateError.value = error instanceof LocalStateClientError || error instanceof Error
      ? error.message
      : '提醒取消失败'
  } finally {
    activeReminderId.value = ''
  }
}

async function saveDesktopSettings() {
  if (!desktopSettings.value) return
  localStateStatus.value = 'saving'
  localStateError.value = ''
  localStateNotice.value = ''
  try {
    const settings = await localStateClient.updateSettings({
      language: desktopSettings.value.language,
      personality: desktopSettings.value.personality,
      voice_preference: desktopSettings.value.voice_preference,
      memory_policy: desktopSettings.value.memory_policy,
      diagnostics_enabled: desktopSettings.value.diagnostics_enabled,
    })
    applyDesktopSettings(settings)
    systemLogs.value = await localStateClient.listLogs()
    localStateNotice.value = '偏好已保存到本机'
    localStateStatus.value = 'ready'
  } catch (error) {
    localStateStatus.value = 'error'
    localStateError.value = error instanceof LocalStateClientError || error instanceof Error
      ? error.message
      : '设置保存失败'
  }
}

function formatLocalStateTime(value: string) {
  return new Date(value).toLocaleString()
}

async function executeControlledTool(toolName: string, arguments_: Record<string, unknown>) {
  toolState.value = 'loading'
  toolError.value = ''
  toolNotice.value = ''
  setTransientPetAction('open-app', 4_000)
  try {
    const result = await toolClient.execute(toolName, arguments_, agentSessionId.value)
    toolLastResult.value = result
    toolNotice.value = result.status === 'pending' ? '操作已进入审批队列' : '工具执行完成'
    setTransientPetAction('open-app', result.status === 'pending' ? 2_000 : 4_000)
    await refreshToolData()
  } catch (error) {
    toolState.value = 'error'
    toolError.value = error instanceof ToolClientError || error instanceof Error
      ? error.message
      : '工具执行失败'
    setTransientPetAction('displeased', 2_500)
  }
}

async function resolveToolApproval(approvalId: string, decision: 'approve' | 'reject') {
  toolState.value = 'loading'
  toolError.value = ''
  toolNotice.value = ''
  setTransientPetAction(decision === 'approve' ? 'open-app' : 'displeased', 4_000)
  try {
    toolLastResult.value = decision === 'approve'
      ? await toolClient.approve(approvalId)
      : await toolClient.reject(approvalId)
    toolNotice.value = decision === 'approve' ? '审批已通过并执行' : '审批已拒绝'
    setTransientPetAction(decision === 'approve' ? 'open-app' : 'displeased', decision === 'approve' ? 4_000 : 2_500)
    await refreshToolData()
  } catch (error) {
    toolState.value = 'error'
    toolError.value = error instanceof ToolClientError || error instanceof Error
      ? error.message
      : '审批处理失败'
    setTransientPetAction('displeased', 2_500)
  }
}

async function updateMemoryCandidate(candidate: MemoryCandidate) {
  activeMemoryId.value = candidate.id
  memoryState.value = 'saving'
  memoryError.value = ''
  try {
    replaceMemoryCandidate(await memoryClient.updateCandidate(candidate.id, memoryDraft(candidate)))
    memoryState.value = 'idle'
  } catch (error) {
    memoryState.value = 'error'
    memoryError.value = error instanceof MemoryClientError || error instanceof Error
      ? error.message
      : '候选记忆更新失败'
  } finally {
    activeMemoryId.value = ''
  }
}

async function confirmMemoryCandidate(candidate: MemoryCandidate) {
  activeMemoryId.value = candidate.id
  memoryState.value = 'saving'
  memoryError.value = ''
  try {
    const memory = await memoryClient.confirmCandidate(candidate.id, memoryDraft(candidate))
    memoryCandidates.value = memoryCandidates.value.filter((item) => item.id !== candidate.id)
    confirmedMemories.value = [
      memory,
      ...confirmedMemories.value.filter((item) => item.id !== memory.id),
    ]
    memoryState.value = 'idle'
  } catch (error) {
    memoryState.value = 'error'
    memoryError.value = error instanceof MemoryClientError || error instanceof Error
      ? error.message
      : '候选记忆确认失败'
  } finally {
    activeMemoryId.value = ''
  }
}

async function rejectMemoryCandidate(candidateId: string) {
  activeMemoryId.value = candidateId
  memoryState.value = 'saving'
  memoryError.value = ''
  try {
    await memoryClient.deleteCandidate(candidateId)
    memoryCandidates.value = memoryCandidates.value.filter((item) => item.id !== candidateId)
    memoryState.value = 'idle'
  } catch (error) {
    memoryState.value = 'error'
    memoryError.value = error instanceof MemoryClientError || error instanceof Error
      ? error.message
      : '候选记忆拒绝失败'
  } finally {
    activeMemoryId.value = ''
  }
}

async function updateConfirmedMemory(memory: MemoryRecord) {
  activeMemoryId.value = memory.id
  memoryState.value = 'saving'
  memoryError.value = ''
  try {
    replaceConfirmedMemory(await memoryClient.updateMemory(memory.id, memoryDraft(memory)))
    memoryState.value = 'idle'
  } catch (error) {
    memoryState.value = 'error'
    memoryError.value = error instanceof MemoryClientError || error instanceof Error
      ? error.message
      : '已确认记忆更新失败'
  } finally {
    activeMemoryId.value = ''
  }
}

async function deleteConfirmedMemory(memoryId: string) {
  activeMemoryId.value = memoryId
  memoryState.value = 'saving'
  memoryError.value = ''
  try {
    await memoryClient.deleteMemory(memoryId)
    confirmedMemories.value = confirmedMemories.value.filter((item) => item.id !== memoryId)
    memoryState.value = 'idle'
  } catch (error) {
    memoryState.value = 'error'
    memoryError.value = error instanceof MemoryClientError || error instanceof Error
      ? error.message
      : '已确认记忆删除失败'
  } finally {
    activeMemoryId.value = ''
  }
}

async function clearAgentConversation() {
  const previousSessionId = agentSessionId.value
  agentSessionId.value = createAgentSessionId()
  agentMessages.value = []
  agentText.value = ''
  agentError.value = ''
  agentState.value = 'idle'
  if (currentAction.value === 'thinking') currentAction.value = 'idle'
  try {
    await agentClient.clearSession(previousSessionId)
  } catch (error) {
    agentError.value = error instanceof AgentClientError || error instanceof Error
      ? `本地对话已清空；服务端上下文清理失败：${error.message}`
      : '本地对话已清空；服务端上下文清理失败'
  }
}

function ragCollectionLabel(collection: RagCollection) {
  return collection === 'character_knowledge' ? '角色知识' : '用户文档'
}

function agentRagStatusLabel(status: AgentResponse['rag_status'] | undefined, collection: RagCollection | undefined) {
  const label = collection ? ragCollectionLabel(collection) : '知识库'
  if (status === 'used') return `已参考${label}`
  if (status === 'empty') return `${label}未命中，已按常规对话回答`
  if (status === 'unavailable') return '知识库暂不可用，已降级为常规对话'
  return '未使用知识库'
}

function selectRagDocument(event: Event) {
  const input = event.target as HTMLInputElement
  ragFile.value = input.files?.[0] ?? null
  ragError.value = ''
  ragNotice.value = ''
}

async function refreshRagHealth(options: { background?: boolean } = {}) {
  if (ragHealthCheckInFlight) return
  ragHealthCheckInFlight = true
  if (!options.background) ragHealthState.value = 'checking'
  ragHealthError.value = ''
  try {
    ragHealth.value = await ragClient.health()
    ragHealthState.value = ragHealth.value.ok ? 'ready' : 'error'
    if (!ragHealth.value.ok) {
      ragHealthError.value = ragHealth.value.error || '知识库服务不可用'
    }
  } catch (error) {
    ragHealthState.value = 'error'
    ragHealthError.value = error instanceof RagClientError || error instanceof Error
      ? error.message
      : '知识库状态检查失败'
  } finally {
    ragHealthCheckInFlight = false
  }
}

async function uploadRagDocument(event: Event) {
  const form = event.currentTarget as HTMLFormElement
  const document = ragFile.value
  if (!document || ragUploadState.value === 'uploading') return

  ragUploadState.value = 'uploading'
  ragError.value = ''
  ragNotice.value = ''
  try {
    const uploaded = await ragClient.ingest({
      collection: ragCollection.value,
      document,
      sourceLabel: ragSourceLabel.value,
    })
    ragFile.value = null
    ragSourceLabel.value = ''
    form.reset()
    ragUploadState.value = 'success'
    await refreshRagHealth()
    await loadRagDocuments()
    ragNotice.value = uploaded.deduplicated
      ? '文档已存在，未重复写入'
      : `已写入${ragCollectionLabel(uploaded.collection)}`
  } catch (error) {
    ragUploadState.value = 'error'
    ragError.value = error instanceof RagClientError || error instanceof Error
      ? error.message
      : '文档上传失败'
  }
}

async function searchRagDocuments() {
  if (!ragQuery.value.trim() || ragSearchState.value === 'searching') return

  ragSearchState.value = 'searching'
  ragError.value = ''
  ragNotice.value = ''
  try {
    const response = await ragClient.search({
      collection: ragCollection.value,
      query: ragQuery.value,
    })
    ragResults.value = response.results
    ragSearchState.value = 'success'
    ragNotice.value = response.results.length
      ? `找到 ${response.results.length} 条相关片段`
      : '没有找到相关片段'
  } catch (error) {
    ragSearchState.value = 'error'
    ragError.value = error instanceof RagClientError || error instanceof Error
      ? error.message
      : '文档检索失败'
  }
}

async function deleteRagDocument(documentId: string) {
  if (!documentId || ragDeletingDocumentId.value) return
  const targetDocument = ragRecentDocuments.value.find(
    (item) => item.document_id === documentId,
  )
  if (!window.confirm(
    `确定删除文档《${targetDocument?.filename ?? documentId}》吗？它的所有片段都会被移除。`,
  )) return

  ragDeletingDocumentId.value = documentId
  ragError.value = ''
  ragNotice.value = ''
  try {
    await ragClient.deleteDocument(ragCollection.value, documentId)
    ragResults.value = ragResults.value.filter(
      (item) => item.document_id !== documentId,
    )
    await loadRagDocuments()
    ragNotice.value = '文档已删除'
  } catch (error) {
    ragError.value = error instanceof RagClientError || error instanceof Error
      ? error.message
      : '文档删除失败'
  } finally {
    ragDeletingDocumentId.value = ''
  }
}

async function loadRagDocuments() {
  try {
    ragRecentDocuments.value = await ragClient.listDocuments(ragCollection.value)
  } catch {
    ragRecentDocuments.value = []
  }
}

async function clearRagCollection() {
  const documents = [...ragRecentDocuments.value]
  if (!documents.length) return
  if (!window.confirm(
    `确定清空“${ragCollectionLabel(ragCollection.value)}”集合吗？将永久删除全部 ${documents.length} 个文档。`,
  )) return
  ragError.value = ''
  try {
    for (const document of documents) {
      await ragClient.deleteDocument(ragCollection.value, document.document_id)
    }
    ragResults.value = []
    await loadRagDocuments()
    ragNotice.value = '集合已清空'
  } catch (error) {
    ragError.value = error instanceof RagClientError || error instanceof Error
      ? error.message
      : '清空集合失败'
  }
}

function emptyPersonaDraft(): PersonaProfileDraft {
  return {
    profile_name: '',
    character_name: '',
    personality: '',
    speaking_style: '',
    default_action: 'idle',
    voice_id: '',
    system_prompt: '',
  }
}

function resetPersonaDraft() {
  Object.assign(personaDraft, emptyPersonaDraft())
}

function draftFromProfile(profile: PersonaProfile) {
  Object.assign(personaDraft, {
    profile_name: profile.profile_name,
    character_name: profile.character_name,
    personality: profile.personality,
    speaking_style: profile.speaking_style,
    default_action: profile.default_action,
    voice_id: profile.voice_id,
    system_prompt: profile.system_prompt,
  })
}

function personaDraftIsValid() {
  return Boolean(
    personaDraft.profile_name.trim()
    && personaDraft.character_name.trim()
    && personaDraft.personality.trim()
    && personaDraft.speaking_style.trim()
    && personaDraft.default_action,
  )
}

function collectPersonaDraft(): PersonaProfileDraft {
  return {
    profile_name: personaDraft.profile_name.trim(),
    character_name: personaDraft.character_name.trim(),
    personality: personaDraft.personality.trim(),
    speaking_style: personaDraft.speaking_style.trim(),
    default_action: personaDraft.default_action,
    voice_id: personaDraft.voice_id.trim(),
    system_prompt: personaDraft.system_prompt.trim(),
  }
}

async function refreshPersonas(options: { background?: boolean } = {}) {
  if (personaRefreshInFlight) return
  personaRefreshInFlight = true
  if (!options.background) personaState.value = 'loading'
  personaError.value = ''
  try {
    const [profiles, active] = await Promise.all([
      personaClient.list(),
      personaClient.active(),
    ])
    personaProfiles.value = profiles
    activePersona.value = active
    personaState.value = 'ready'
  } catch (error) {
    personaState.value = 'error'
    personaError.value = error instanceof PersonaClientError || error instanceof Error
      ? error.message
      : '人格列表加载失败'
  } finally {
    personaRefreshInFlight = false
  }
}

function startNewPersona() {
  resetPersonaDraft()
  editingPersonaId.value = 'new'
  versioningPersonaId.value = null
  personaVersions.value = []
  personaError.value = ''
  personaNotice.value = ''
}

function editPersona(profile: PersonaProfile) {
  draftFromProfile(profile)
  editingPersonaId.value = profile.id
  versioningPersonaId.value = null
  personaVersions.value = []
  personaError.value = ''
  personaNotice.value = ''
}

function cancelPersonaEdit() {
  editingPersonaId.value = null
  resetPersonaDraft()
}

async function savePersona() {
  if (!personaDraftIsValid() || personaState.value === 'saving') return
  personaState.value = 'saving'
  personaError.value = ''
  try {
    if (editingPersonaId.value === 'new') {
      await personaClient.create(collectPersonaDraft())
      personaNotice.value = '人格配置已创建（尚未启用）'
    } else if (editingPersonaId.value) {
      await personaClient.update(editingPersonaId.value, collectPersonaDraft())
      personaNotice.value = '人格配置已更新，旧版本已自动留存'
    }
    editingPersonaId.value = null
    resetPersonaDraft()
    await refreshPersonas()
  } catch (error) {
    personaError.value = error instanceof PersonaClientError || error instanceof Error
      ? error.message
      : '人格配置保存失败'
  } finally {
    personaState.value = 'ready'
  }
}

function applyPersonaDefaultAction(profile: PersonaProfile) {
  currentAction.value = normalizePetAction(profile.default_action)
}

async function activatePersona(profile: PersonaProfile) {
  if (personaBusyId.value) return
  personaBusyId.value = profile.id
  personaError.value = ''
  try {
    const activated = await personaClient.activate(profile.id)
    activePersona.value = activated
    personaProfiles.value = personaProfiles.value.map((item) => ({
      ...item,
      is_active: item.id === activated.id,
    }))
    applyPersonaDefaultAction(activated)
    personaNotice.value = `已启用人格《${activated.profile_name}》`
  } catch (error) {
    personaError.value = error instanceof PersonaClientError || error instanceof Error
      ? error.message
      : '人格启用失败'
  } finally {
    personaBusyId.value = ''
  }
}

async function deactivatePersona() {
  if (personaBusyId.value) return
  personaBusyId.value = '__deactivate'
  personaError.value = ''
  try {
    await personaClient.deactivate()
    activePersona.value = null
    personaProfiles.value = personaProfiles.value.map((item) => ({
      ...item,
      is_active: false,
    }))
    personaNotice.value = '已停用人格，回到内置默认设定'
  } catch (error) {
    personaError.value = error instanceof PersonaClientError || error instanceof Error
      ? error.message
      : '人格停用失败'
  } finally {
    personaBusyId.value = ''
  }
}

async function removePersona(profile: PersonaProfile) {
  if (!window.confirm(
    `确定删除人格配置《${profile.profile_name}》吗？它的历史版本也会一起删除。`,
  )) return
  if (personaBusyId.value) return
  personaBusyId.value = profile.id
  personaError.value = ''
  try {
    await personaClient.remove(profile.id)
    if (activePersona.value?.id === profile.id) activePersona.value = null
    if (editingPersonaId.value === profile.id) cancelPersonaEdit()
    await refreshPersonas()
    personaNotice.value = '人格配置已删除'
  } catch (error) {
    personaError.value = error instanceof PersonaClientError || error instanceof Error
      ? error.message
      : '人格删除失败'
  } finally {
    personaBusyId.value = ''
  }
}

async function togglePersonaVersions(profile: PersonaProfile) {
  personaError.value = ''
  if (versioningPersonaId.value === profile.id) {
    versioningPersonaId.value = null
    personaVersions.value = []
    return
  }
  try {
    personaVersions.value = await personaClient.versions(profile.id)
    versioningPersonaId.value = profile.id
  } catch (error) {
    personaError.value = error instanceof PersonaClientError || error instanceof Error
      ? error.message
      : '历史版本加载失败'
  }
}

async function rollbackPersona(
  profile: PersonaProfile,
  version: PersonaProfileVersion,
) {
  if (!window.confirm('确定把该人格回滚到所选历史版本吗？')) return
  if (personaBusyId.value) return
  personaBusyId.value = profile.id
  personaError.value = ''
  try {
    const rolledBack = await personaClient.rollback(profile.id, version.version_id)
    await refreshPersonas()
    if (rolledBack.is_active) {
      activePersona.value = rolledBack
      applyPersonaDefaultAction(rolledBack)
    }
    personaVersions.value = await personaClient.versions(profile.id)
    versioningPersonaId.value = profile.id
    personaNotice.value = '已回滚到所选历史版本'
  } catch (error) {
    personaError.value = error instanceof PersonaClientError || error instanceof Error
      ? error.message
      : '人格回滚失败'
  } finally {
    personaBusyId.value = ''
  }
}

function formatRagTime(timestamp: number) {
  return new Date(timestamp * 1_000).toLocaleString()
}

function clearExactFrames(config: ActionConfig) {
  config.frameIndices = undefined
}

function setAnchor(anchor: SpriteSheetSource['anchor']) {
  anchorMode.value = anchor
}

function isActionFrame(frameIndex: number) {
  return currentActionFrames.value.includes(frameIndex)
}

function isBlankFrame(frameIndex: number) {
  return spriteSheet.value?.blankFrameIndices.includes(frameIndex) ?? false
}

function isValidFrame(frameIndex: number) {
  const source = spriteSheet.value
  if (!source) return false
  return source.validFrameIndices.length === 0 ? !isBlankFrame(frameIndex) : source.validFrameIndices.includes(frameIndex)
}

function toggleFrame(frames: number[], frameIndex: number) {
  return frames.includes(frameIndex)
    ? frames.filter((frame) => frame !== frameIndex)
    : [...frames, frameIndex].sort((left, right) => left - right)
}

function setActionFrames(frameIndices: number[]) {
  const config = selectedConfig.value
  config.frameIndices = frameIndices
  config.start = frameIndices[0] ?? 0
  config.end = frameIndices[frameIndices.length - 1] ?? config.start
}

function toggleFrameSelection(frameIndex: number) {
  const source = spriteSheet.value
  if (!source) return
  if (frameEditMode.value === 'action') {
    setActionFrames(toggleFrame(currentActionFrames.value, frameIndex))
    return
  }
  if (frameEditMode.value === 'valid') {
    const validFrames = source.validFrameIndices.length > 0
      ? source.validFrameIndices
      : Array.from({ length: source.frameCount }, (_, index) => index).filter((index) => !isBlankFrame(index))
    source.validFrameIndices = toggleFrame(validFrames, frameIndex)
    if (isBlankFrame(frameIndex)) source.blankFrameIndices = toggleFrame(source.blankFrameIndices, frameIndex)
    return
  }
  source.blankFrameIndices = toggleFrame(source.blankFrameIndices, frameIndex)
  if (source.validFrameIndices.length > 0 && isValidFrame(frameIndex)) {
    source.validFrameIndices = toggleFrame(source.validFrameIndices, frameIndex)
  }
}

function frameStatus(frameIndex: number) {
  if (isBlankFrame(frameIndex)) return '空白帧'
  if (isActionFrame(frameIndex)) return '当前动作帧'
  return isValidFrame(frameIndex) ? '有效帧' : '未使用帧'
}

function frameThumbnailStyle(frameIndex: number) {
  const source = spriteSheet.value
  if (!source?.src || source.columns <= 0 || source.rows <= 0) return {}
  const column = frameIndex % source.columns
  const row = Math.floor(frameIndex / source.columns)
  const x = source.columns === 1 ? 0 : (column / (source.columns - 1)) * 100
  const y = source.rows === 1 ? 0 : (row / (source.rows - 1)) * 100
  return {
    backgroundImage: `url("${source.src}")`,
    backgroundSize: `${source.columns * 100}% ${source.rows * 100}%`,
    backgroundPosition: `${x}% ${y}%`,
  }
}

function applyActionDefinition(action: ActionDefinition) {
  if (!isPetAction(action.id)) {
    supplementalActions[action.id] = {
      ...action,
      frameIndices: [...action.frameIndices],
    }
    return
  }
  const config = actionConfigs[action.id]
  config.frameIndices = [...action.frameIndices]
  config.start = action.frameIndices[0] ?? 0
  config.end = action.frameIndices[action.frameIndices.length - 1] ?? config.start
  config.fps = action.fps
  config.loop = action.loop
  config.sheet = action.sheet ?? ''
}

function createSource(key: string, fileName: string, width: number, height: number, metadata?: Partial<SpriteSheetSource>, src = ''): SpriteSheetSource {
  const frameWidth = metadata?.frameWidth ?? width
  const frameHeight = metadata?.frameHeight ?? height
  const geometry = calculateSpriteSheetGeometry(width, height, frameWidth, frameHeight)
  return {
    src,
    fileName: metadata?.fileName || fileName,
    width,
    height,
    frameWidth,
    frameHeight,
    columns: metadata?.columns ?? geometry.columns,
    rows: metadata?.rows ?? geometry.rows,
    frameCount: metadata?.frameCount ?? geometry.frameCount,
    validFrameIndices: metadata?.validFrameIndices ? [...metadata.validFrameIndices] : [],
    blankFrameIndices: metadata?.blankFrameIndices ? [...metadata.blankFrameIndices] : [],
    anchor: metadata?.anchor ?? 'bottom-center',
  }
}

function updateSourceFrameSize(source: SpriteSheetSource, frameWidth: number, frameHeight: number) {
  const geometry = calculateSpriteSheetGeometry(source.width, source.height, frameWidth, frameHeight)
  source.frameWidth = frameWidth
  source.frameHeight = frameHeight
  source.columns = geometry.columns
  source.rows = geometry.rows
  source.frameCount = geometry.frameCount
}

function replaceSources(nextSources: Record<string, Partial<SpriteSheetSource>>) {
  const previousSources = Object.values(sourceImages)
  for (const key of Object.keys(sourceImages)) delete sourceImages[key]
  for (const [key, source] of Object.entries(nextSources)) {
    const existing = previousSources.find((candidate) => candidate.fileName === source.fileName)
    sourceImages[key] = createSource(
      key,
      source.fileName ?? key,
      source.width ?? 0,
      source.height ?? 0,
      source,
      source.src ?? existing?.src ?? '',
    )
  }
}

function applySourceMetadata(key: string, metadata?: Partial<SpriteSheetSource>) {
  const source = sourceImages[key]
  if (!source || !metadata) return
  Object.assign(source, {
    ...metadata,
    validFrameIndices: metadata.validFrameIndices ? [...metadata.validFrameIndices] : source.validFrameIndices,
    blankFrameIndices: metadata.blankFrameIndices ? [...metadata.blankFrameIndices] : source.blankFrameIndices,
  })
}

function readJson(file: File) {
  return file.text().then((text) => JSON.parse(text) as unknown)
}

async function importManifest(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  importError.value = ''
  importNotice.value = ''
  try {
    const parsed = parseManifestJson(await readJson(file))
    const imported = parsed.manifest
    if (!imported) throw new Error('manifest.json 内容为空')
    clearSupplementalActions()
    replaceSources(parsed.spriteSheets ?? (parsed.spriteSheet ? { default: parsed.spriteSheet } : {}))
    for (const action of Object.values(imported.actions)) if (action) applyActionDefinition(action)
    currentSourceKey.value = ''
    syncCurrentSource(currentAction.value)
    resourcePersistenceEnabled.value = true
    scheduleResourcePersistence()
    importNotice.value = `已载入 ${file.name}，共 ${sourceEntries.value.length} 张 SpriteSheet；请确认 PNG 文件是否已单独导入`
  } catch (error) {
    importError.value = error instanceof Error ? error.message : 'manifest.json 读取失败'
  } finally {
    input.value = ''
  }
}

async function importAction(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  importError.value = ''
  importNotice.value = ''
  try {
    const parsed = parseActionJson(await readJson(file))
    if (!parsed.action) throw new Error('action.json 内容为空')
    const key = parsed.action.sheet || parsed.spriteSheet?.fileName || parsed.action.id
    if (parsed.spriteSheet && !sourceImages[key]) {
      sourceImages[key] = createSource(key, parsed.spriteSheet.fileName ?? key, parsed.spriteSheet.width ?? 0, parsed.spriteSheet.height ?? 0, parsed.spriteSheet)
    }
    applyActionDefinition(parsed.action)
    if (isPetAction(parsed.action.id)) {
      actionConfigs[parsed.action.id].sheet = key
      currentAction.value = parsed.action.id
    }
    currentSourceKey.value = key
    resourcePersistenceEnabled.value = true
    scheduleResourcePersistence()
    importNotice.value = `已载入动作 ${parsed.action.id}，绑定资源 ${key}`
  } catch (error) {
    importError.value = error instanceof Error ? error.message : 'action.json 读取失败'
  } finally {
    input.value = ''
  }
}

function exportManifest() {
  if (!validation.value.valid) {
    importError.value = '清单存在错误，修正后才能导出'
    return
  }
  downloadJson('manifest.json', toManifestJson(manifest.value))
  importNotice.value = '已导出 manifest.json'
}

function exportAction() {
  const action = manifest.value.actions[currentAction.value]
  if (!action || !validation.value.valid) {
    importError.value = '当前动作清单存在错误，修正后才能导出'
    return
  }
  downloadJson('action.json', toActionJson(action, resolveSpriteSheet(manifest.value, action)))
  importNotice.value = `已导出 ${currentAction.value}/action.json`
}

function readFileAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      if (typeof reader.result === 'string') resolve(reader.result)
      else reject(new Error(`${file.name} 无法读取为可传输图片`))
    }
    reader.onerror = () => reject(new Error(`${file.name} 无法读取为可传输图片`))
    reader.readAsDataURL(file)
  })
}

async function loadImage(file: File) {
  const dataUrl = await readFileAsDataUrl(file)
  return new Promise<{ width: number; height: number; src: string }>((resolve, reject) => {
    const image = new Image()
    image.onload = () => {
      resolve({ width: image.naturalWidth, height: image.naturalHeight, src: dataUrl })
    }
    image.onerror = () => reject(new Error(`${file.name} 无法作为 PNG 图片读取`))
    image.src = dataUrl
  })
}

async function importSpriteSheet(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  if (files.length === 0) return
  importError.value = ''
  importNotice.value = ''
  const invalidFile = files.find((file) => !isPngFile(file))
  if (invalidFile) {
    importError.value = `${invalidFile.name} 不是 PNG 文件`
    input.value = ''
    return
  }

  try {
    for (const file of files) {
      const dimensions = await loadImage(file)
      const key = sourceKeyForFile(file.name)
      const previous = sourceImages[key]
      const source = createSource(key, file.name, dimensions.width, dimensions.height, previous, dimensions.src)
      sourceImages[key] = source
      if (!actionConfigs[currentAction.value].sheet || actionConfigs[currentAction.value].sheet === crimsonElfIdleSpriteSheetKey) {
        actionConfigs[currentAction.value].sheet = key
      }
    }
    if (!currentSourceKey.value || currentSourceKey.value === crimsonElfIdleSpriteSheetKey || !sourceImages[currentSourceKey.value]) {
      currentSourceKey.value = sourceKeyForFile(files[0].name)
    }
    const fileNames = files.map((file) => file.name).join('、')
    resourcePersistenceEnabled.value = true
    scheduleResourcePersistence()
    importNotice.value = `已导入 ${fileNames}；请设置单帧尺寸与动作帧范围`
  } catch (error) {
    importError.value = error instanceof Error ? error.message : '图片读取失败，请换一个 PNG 文件'
  } finally {
    input.value = ''
  }
}

onBeforeUnmount(() => {
  stopContinuousConversation()
  cancelScheduledResourcePersistence()
  speechPlayback.stop()
  audioRecorder.cancel()
  voiceprintRecorder.cancel()
  void rtcOfficialClient.leave()
  clearRtcVoiceprintRecordingTimer()
  closeAsrStream()
  if (godotStatusTimer !== undefined) window.clearInterval(godotStatusTimer)
  if (gatewayStatusTimer !== undefined) window.clearInterval(gatewayStatusTimer)
  if (identityStatusTimer !== undefined) window.clearInterval(identityStatusTimer)
})

onMounted(() => {
  wakeWordGateEnabled.value = window.localStorage.getItem(wakeWordGateStorageKey) !== 'false'
  if (window.localStorage.getItem(continuousVoiceStorageKey) === 'true') {
    continuousConversationStatus.value = '上次开启了连续对话；请再次点击开关并先说“米娅”，唤醒后30秒内可直接追问'
  }
  void restoreSavedResourcePackage()
  if (isDesktopMode) {
    void prepareDesktopGateway()
  } else {
    void handleGatewayReady()
  }
  identityStatusTimer = window.setInterval(() => {
    if (rtcVoiceprintSessionState.value === 'active' || identitySnapshot.value?.status === 'owner_verified') {
      void refreshIdentity(true)
    }
  }, 2_500)
  if (isDesktopMode) {
    void initializePetSize()
    void refreshGodotPetStatus()
    godotStatusTimer = window.setInterval(() => { void refreshGodotPetStatus() }, 1_000)
    gatewayStatusTimer = window.setInterval(() => {
      void refreshGatewayStatus()
      void refreshGatewayHealth({ silent: true, background: true })
    }, 2_500)
  }
})

watch(ragCollection, () => {
  ragResults.value = []
  ragError.value = ''
  ragNotice.value = ''
  ragSearchState.value = 'idle'
  void loadRagDocuments()
})

// 网关从冷启动/异常中恢复后，自动补刷此前可能失败的身份、RAG、本地状态和人脸数据。
watch(gatewayHealthState, (newState, oldState) => {
  // 自动刷新本身会短暂进入 checking；首次 ready 和 error -> ready 才补刷，
  // 避免 ready -> checking -> ready 反复触发整套请求。
  if (shouldRefreshGatewayDataOnReady(newState, oldState, hasObservedGatewayReady)) {
    void handleGatewayReady()
  }
})
</script>

<template>
  <main class="workspace" :data-ui-tab="activeUiTab" :style="uiShellStyle">
    <div class="ui-background" aria-hidden="true">
      <img class="ui-background__image" :src="uiBackground" alt="">
      <span class="ui-background__veil" />
      <span class="ui-background__grid" />
      <span class="ui-background__sparkles" />
      <span
        v-for="petal in 12"
        :key="petal"
        class="ui-background__petal"
        :style="{
          '--petal-left': `${(petal * 8.33 - 6).toFixed(2)}%`,
          '--petal-delay': `${(petal * 0.72).toFixed(2)}s`,
          '--petal-duration': `${(11 + (petal % 5) * 1.35).toFixed(2)}s`,
          '--petal-size': `${(10 + (petal % 4) * 2)}px`,
        }"
      />
      <img class="ui-background__deco" :src="uiVisuals.deco" alt="">
    </div>
    <GlowCursor
      :color="activeUiTab === 'chat' ? '#f472b6' : '#22d3ee'"
      :secondary-color="activeUiTab === 'resource' ? '#fbbf24' : '#a78bfa'"
    />
    <header class="topbar">
      <div class="brand">
        <span class="brand-mark">LM</span>
        <div>
          <p class="eyebrow">LINGMENG DESKTOP PET</p>
          <h1>灵梦桌宠</h1>
        </div>
      </div>
      <div class="topbar-meta">
        <button
          v-if="isDesktopMode"
          class="pet-visibility-toggle"
          :class="{ active: godotPetRunning }"
          type="button"
          :aria-pressed="godotPetRunning"
          @click="requestPetWindowToggle"
        >
          <span class="toggle-indicator" aria-hidden="true" />
          {{ godotPetRunning ? '关闭桌宠' : '打开桌宠' }}
        </button>
        <span v-if="godotPetError" class="pet-visibility-error" role="status">{{ godotPetError }}</span>
        <span class="status-dot" />
        <span>{{ isDesktopMode ? (godotPetRunning ? 'Godot 桌宠运行中' : 'Godot 桌宠已关闭') : '本地预览' }}</span>
        <span v-if="godotPetRunning && godotPetPid" class="version">PID {{ godotPetPid }}</span>
        <span class="version">v0.4</span>
      </div>
    </header>

    <nav class="ui-tabs" aria-label="界面分区导航">
      <button
        v-for="tab in uiTabs"
        :key="tab.id"
        class="ui-tabs__item"
        :class="{ active: activeUiTab === tab.id }"
        type="button"
        @click="selectUiTab(tab.id)"
      >
        <strong>{{ tab.label }}</strong>
        <span>{{ tab.hint }}</span>
      </button>
    </nav>

    <div class="ui-context-strip" aria-hidden="true">
      <span class="ui-context-strip__badge">{{ uiTabs.find((item) => item.id === activeUiTab)?.hint }}</span>
      <span class="ui-context-strip__line" />
    </div>
    <div class="ui-character" aria-hidden="true" />

    <section class="content-grid">
      <aside class="panel action-panel">
        <div class="panel-heading">
          <div>
            <p class="eyebrow">ACTION MAP</p>
            <h2>动作状态</h2>
          </div>
          <span class="count">{{ actions.length }}</span>
        </div>
        <div class="action-list">
          <button
            v-for="item in actions"
            :key="item.id"
            class="action-button"
            :class="[{ active: currentAction === item.id }, `tone-${item.tone}`]"
            type="button"
            @click="selectAction(item.id)"
          >
            <span class="action-swatch" />
            <span>{{ item.label }}</span>
            <span class="action-key">{{ item.id }}</span>
          </button>
        </div>
        <button class="reset-button" type="button" @click="reset">
          <span>↺</span>
          重置预览
        </button>
      </aside>

      <section class="stage-section">
        <div class="stage-toolbar">
          <div>
            <p class="eyebrow">LIVE PREVIEW</p>
            <h2>角色渲染画布</h2>
          </div>
          <div class="stage-actions">
            <button class="icon-button" type="button" :aria-label="paused ? '继续播放' : '暂停播放'" @click="paused = !paused">
              {{ paused ? '▶' : 'Ⅱ' }}
            </button>
            <span class="frame-readout">FRAME {{ String(currentFrame + 1).padStart(2, '0') }} / {{ String(frameTotal).padStart(2, '0') }}</span>
          </div>
        </div>
        <div class="stage">
          <div class="stage-grid" />
          <div class="stage-label">CANVAS / 2D CONTEXT</div>
          <PetCanvas
            :action="currentAction"
            :mouth-mode="mouthMode"
            :manifest="activeManifest"
            :paused="paused"
            @snapshot="(snapshot) => { currentFrame = snapshot.framePosition; fallback = snapshot.usingFallback }"
          />
          <div class="stage-floor" />
        </div>
        <div class="stage-caption">
          <span class="live-line" />
          <span>{{ statusCopy }}</span>
          <span class="caption-spacer" />
          <span class="mono">{{ currentAction }}</span>
        </div>

        <section class="resource-editor" aria-labelledby="resource-editor-title">
          <div class="resource-editor-heading">
            <div>
              <p class="eyebrow">SPRITE PACKAGE</p>
              <h2 id="resource-editor-title">角色资源与动作清单</h2>
            </div>
            <div class="package-actions">
              <label class="upload-control">
                <input type="file" accept="application/json,.json" @change="importManifest">
                导入 manifest
              </label>
              <label class="upload-control">
                <input type="file" accept="application/json,.json" @change="importAction">
                导入 action
              </label>
              <button class="text-button" type="button" @click="exportManifest">导出 manifest</button>
              <button class="text-button" type="button" @click="exportAction">导出 action</button>
              <label class="upload-control">
                <input type="file" accept="image/png" multiple @change="importSpriteSheet">
                导入 PNG
              </label>
              <button class="text-button storage-button" type="button" @click="saveCurrentResourcePackage">保存到本机</button>
              <button class="text-button storage-button" type="button" @click="restoreSavedResourcePackage">恢复本地资源</button>
              <button class="text-button storage-button" type="button" @click="clearSavedResourcePackage">清除本地保存</button>
              <button class="text-button storage-button" type="button" @click="restoreDefaultCharacterResource">恢复默认角色资源</button>
              <button class="text-button storage-button" type="button" :disabled="godotSyncState === 'syncing'" @click="syncCurrentResourcePackageToGodot">
                {{ godotSyncState === 'syncing' ? '同步中…' : '同步到 Godot' }}
              </button>
            </div>
          </div>

          <p v-if="importError" class="inline-message error">{{ importError }}</p>
          <p v-if="importNotice" class="inline-message notice">{{ importNotice }}</p>
          <p v-if="resourceStorageError" class="inline-message error">{{ resourceStorageError }}</p>
          <p v-if="godotSyncError" class="inline-message error">{{ godotSyncError }}</p>
          <p class="resource-storage-status">
            本机资源：
            <strong v-if="resourceStorageState === 'saving'">保存中</strong>
            <strong v-else-if="resourceStorageState === 'saved'">已保存</strong>
            <strong v-else-if="resourceStorageState === 'restored'">已恢复</strong>
            <strong v-else-if="resourceStorageState === 'error'">操作失败</strong>
            <strong v-else>未保存</strong>
          </p>
          <p class="resource-storage-status">
            Godot：
            <strong v-if="godotSyncState === 'syncing'">同步中</strong>
            <strong v-else-if="godotSyncState === 'synced'">已同步</strong>
            <strong v-else-if="godotSyncState === 'error'">同步失败</strong>
            <strong v-else>未同步</strong>
          </p>
          <div v-if="sourceImage" class="source-summary">
            <span>{{ currentSourceKey }} · {{ sourceImage.fileName }}</span>
            <span class="mono">{{ sourceImage.width }} × {{ sourceImage.height }} PX</span>
            <span class="mono">{{ spriteSheet?.frameCount ?? 0 }} FRAMES</span>
          </div>
          <div v-else class="empty-source">未导入资源或资源清单</div>

          <div class="config-grid">
            <label class="field-label">
              <span>单帧宽度</span>
              <input v-model.number="frameWidth" type="number" min="1" step="1" :disabled="!sourceImage">
            </label>
            <label class="field-label">
              <span>单帧高度</span>
              <input v-model.number="frameHeight" type="number" min="1" step="1" :disabled="!sourceImage">
            </label>
            <div class="readout-field">
              <span>网格</span>
              <strong>{{ spriteSheet?.columns ?? 0 }} × {{ spriteSheet?.rows ?? 0 }}</strong>
            </div>
          </div>
          <div class="config-grid frame-list-grid">
            <label class="field-label">
              <span>有效帧索引</span>
              <input v-model="validFramesText" type="text" placeholder="留空自动使用全部非空白帧">
            </label>
            <label class="field-label">
              <span>空白帧索引</span>
              <input v-model="blankFramesText" type="text" placeholder="例如 4, 9">
            </label>
            <div class="anchor-field">
              <span>锚点</span>
              <div class="anchor-segmented" role="group" aria-label="角色锚点">
                <button type="button" :class="{ active: anchorMode === 'bottom-center' }" @click="setAnchor('bottom-center')">底部居中</button>
                <button type="button" :class="{ active: anchorMode === 'center' }" @click="setAnchor('center')">居中</button>
              </div>
            </div>
          </div>

          <section v-if="spriteSheet && frameGridIndices.length" class="frame-calibrator" aria-labelledby="frame-calibrator-title">
            <div class="frame-calibrator-heading">
              <div>
                <p class="eyebrow">FRAME WORKBENCH</p>
                <h2 id="frame-calibrator-title">SpriteSheet 帧校准</h2>
              </div>
              <span class="mono">{{ frameGridIndices.length }} FRAMES</span>
            </div>
            <div class="frame-edit-modes" role="group" aria-label="帧编辑模式">
              <button type="button" :class="{ active: frameEditMode === 'action' }" @click="frameEditMode = 'action'">动作帧</button>
              <button type="button" :class="{ active: frameEditMode === 'valid' }" @click="frameEditMode = 'valid'">有效帧</button>
              <button type="button" :class="{ active: frameEditMode === 'blank' }" @click="frameEditMode = 'blank'">空白帧</button>
              <button class="frame-reset-button" type="button" @click="clearExactFrames(selectedConfig)">按区间重置</button>
            </div>
            <div class="frame-grid" :class="{ 'has-preview': Boolean(spriteSheet.src) }">
              <button
                v-for="frameIndex in frameGridIndices"
                :key="frameIndex"
                class="frame-cell"
                :class="{
                  selected: isActionFrame(frameIndex),
                  valid: isValidFrame(frameIndex),
                  blank: isBlankFrame(frameIndex),
                  playing: currentFrame === frameIndex,
                }"
                type="button"
                :aria-label="`帧 ${frameIndex + 1}，${frameStatus(frameIndex)}`"
                :title="`帧 ${frameIndex + 1}：${frameStatus(frameIndex)}`"
                @click="toggleFrameSelection(frameIndex)"
              >
                <span class="frame-thumbnail" :style="frameThumbnailStyle(frameIndex)" />
                <span class="frame-index">{{ String(frameIndex + 1).padStart(2, '0') }}</span>
                <span class="frame-state">{{ isBlankFrame(frameIndex) ? '空' : isActionFrame(frameIndex) ? '动' : isValidFrame(frameIndex) ? '可' : '—' }}</span>
              </button>
            </div>
            <p class="frame-workbench-note">{{ frameEditMode === 'action' ? `正在编辑 ${currentLabel} 的精确帧序列` : frameEditMode === 'valid' ? '点击帧以标记或取消可用状态' : '点击帧以标记或取消空白状态' }}</p>
          </section>
          <div class="action-editor">
            <div class="action-editor-heading">
              <span class="action-editor-name">{{ currentLabel }}</span>
              <span class="mono">{{ currentAction }}</span>
            </div>
            <div class="action-config-grid">
              <label class="field-label">
                <span>绑定资源</span>
                <select v-model="selectedConfig.sheet" @change="syncCurrentSource(currentAction)">
                  <option value="">自动选择</option>
                  <option v-for="([key, source]) in sourceEntries" :key="key" :value="key">{{ key }} · {{ source.fileName }}</option>
                </select>
              </label>
              <label class="field-label">
                <span>起始帧</span>
                <input v-model.number="selectedConfig.start" type="number" min="0" step="1" @input="clearExactFrames(selectedConfig)">
              </label>
              <label class="field-label">
                <span>结束帧</span>
                <input v-model.number="selectedConfig.end" type="number" min="0" step="1" @input="clearExactFrames(selectedConfig)">
              </label>
              <label class="field-label">
                <span>FPS</span>
                <input v-model.number="selectedConfig.fps" type="number" min="1" max="60" step="1">
              </label>
              <label class="toggle-field">
                <input v-model="selectedConfig.loop" type="checkbox">
                <span>循环播放</span>
              </label>
            </div>
          </div>

          <div class="validation" :class="{ invalid: !validation.valid }">
            <div class="validation-heading">
              <span>{{ validation.valid ? '清单校验通过' : '清单需要修正' }}</span>
              <span class="mono">{{ validation.errors.length }} ERR / {{ validation.warnings.length }} WARN</span>
            </div>
            <p v-for="message in validation.errors" :key="message" class="validation-error">{{ message }}</p>
            <p v-for="message in validation.warnings" :key="message" class="validation-warning">{{ message }}</p>
          </div>
        </section>

        <section class="persona-workbench" aria-labelledby="persona-workbench-title">
          <div class="rag-workbench-heading">
            <div>
              <p class="eyebrow">ACTIVE PERSONA</p>
              <h2 id="persona-workbench-title">当前人格 Profile</h2>
            </div>
            <div class="persona-active-state">
              <span class="rag-health-dot" :class="activePersona ? 'ready' : 'idle'" aria-hidden="true" />
              <span v-if="activePersona">已启用 · {{ activePersona.character_name }}</span>
              <span v-else>未启用（使用内置默认）</span>
            </div>
          </div>

          <p class="persona-hint">
            人格 Profile 是正式生效的角色配置，与下方 RAG 资料分离：RAG 仅提供可检索的补充资料，不会改变这里的正式人格。
          </p>

          <div class="persona-toolbar">
            <button class="text-button" type="button" :disabled="personaState === 'loading'" @click="refreshPersonas()">刷新列表</button>
            <button class="text-button" type="button" @click="startNewPersona">新建人格</button>
            <button class="text-button" type="button" :disabled="!activePersona || Boolean(personaBusyId)" @click="deactivatePersona">停用当前人格</button>
          </div>

          <div v-if="editingPersonaId" class="persona-editor">
            <div class="persona-editor-heading">
              <span>{{ editingPersonaId === 'new' ? '新建人格配置' : '编辑人格配置' }}</span>
              <button class="text-button" type="button" @click="cancelPersonaEdit">取消</button>
            </div>
            <div class="persona-form-grid">
              <label class="field-label">
                <span>配置名称</span>
                <input v-model="personaDraft.profile_name" type="text" maxlength="60" placeholder="例如：傲娇 miya">
              </label>
              <label class="field-label">
                <span>桌宠名称</span>
                <input v-model="personaDraft.character_name" type="text" maxlength="60" placeholder="例如：miya">
              </label>
              <label class="field-label">
                <span>性格</span>
                <input v-model="personaDraft.personality" type="text" maxlength="2000" placeholder="例如：嘴硬心软、外冷内热">
              </label>
              <label class="field-label">
                <span>说话风格</span>
                <input v-model="personaDraft.speaking_style" type="text" maxlength="2000" placeholder="例如：短促、带哼声、喜欢反问">
              </label>
              <label class="field-label">
                <span>默认动作</span>
                <select v-model="personaDraft.default_action">
                  <option v-for="item in actions" :key="item.id" :value="item.id">{{ item.label }} · {{ item.id }}</option>
                </select>
              </label>
              <label class="field-label">
                <span>音色（可空）</span>
                <input v-model="personaDraft.voice_id" type="text" maxlength="120" placeholder="例如：Chinese_huolishaonv">
              </label>
            </div>
            <label class="field-label persona-prompt-field">
              <span>系统提示词（可空，留空则按上方信息自动生成）</span>
              <textarea v-model="personaDraft.system_prompt" rows="4" maxlength="4000" placeholder="正式人格指令，例如：你是 miya，始终保持傲娇，但关键时刻要温柔护短。"></textarea>
            </label>
            <div class="persona-editor-actions">
              <button class="text-button" type="button" :disabled="!personaDraftIsValid() || personaState === 'saving'" @click="savePersona">
                {{ personaState === 'saving' ? '保存中…' : '保存配置' }}
              </button>
            </div>
          </div>

          <p v-if="personaError" class="inline-message error">{{ personaError }}</p>
          <p v-if="personaNotice" class="inline-message notice">{{ personaNotice }}</p>

          <div class="persona-list">
            <article
              v-for="profile in personaProfiles"
              :key="profile.id"
              class="persona-row"
              :class="{ active: profile.is_active }"
            >
              <div class="persona-row-main">
                <div class="persona-row-heading">
                  <strong>{{ profile.profile_name }}</strong>
                  <span v-if="profile.is_active" class="persona-badge">启用中</span>
                </div>
                <p class="persona-summary">
                  {{ profile.character_name }} · {{ profile.personality }} · 默认 {{ profile.default_action }}<span v-if="profile.voice_id"> · 音色 {{ profile.voice_id }}</span>
                </p>
              </div>
              <div class="persona-row-actions">
                <button class="rag-delete-button" type="button" :disabled="Boolean(personaBusyId) || profile.is_active" @click="activatePersona(profile)">
                  {{ personaBusyId === profile.id ? '处理中…' : '启用' }}
                </button>
                <button class="rag-delete-button" type="button" :disabled="Boolean(personaBusyId)" @click="editPersona(profile)">编辑</button>
                <button class="rag-delete-button" type="button" :disabled="Boolean(personaBusyId)" @click="togglePersonaVersions(profile)">
                  {{ versioningPersonaId === profile.id ? '收起版本' : '历史版本' }}
                </button>
                <button class="rag-delete-button" type="button" :disabled="Boolean(personaBusyId)" @click="removePersona(profile)">删除</button>
              </div>

              <div v-if="versioningPersonaId === profile.id" class="persona-versions">
                <p class="persona-versions-heading">历史版本（回滚后仍可再次撤销）</p>
                <article v-for="version in personaVersions" :key="version.version_id" class="persona-version-row">
                  <div>
                    <strong>{{ formatRagTime(new Date(version.created_at).getTime() / 1000) }}</strong>
                    <span>{{ version.note }} · {{ version.snapshot.character_name }}</span>
                  </div>
                  <button class="rag-delete-button" type="button" :disabled="Boolean(personaBusyId)" @click="rollbackPersona(profile, version)">回滚</button>
                </article>
                <p v-if="!personaVersions.length" class="rag-empty">该人格还没有历史版本。</p>
              </div>
            </article>
          </div>
        </section>

        <section class="rag-workbench" aria-labelledby="rag-workbench-title">
          <div class="rag-workbench-heading">
            <div>
              <p class="eyebrow">KNOWLEDGE BASE</p>
              <h2 id="rag-workbench-title">RAG 文档与检索</h2>
            </div>
            <div class="rag-health">
              <span class="rag-health-dot" :class="ragHealthState" aria-hidden="true" />
              <span>
                {{ ragHealthState === 'checking' ? '检查中' : ragHealthState === 'ready' ? '服务可用' : ragHealthState === 'error' ? '服务不可用' : '未检查' }}
              </span>
              <button class="text-button" type="button" :disabled="ragHealthState === 'checking'" @click="refreshRagHealth()">
                检查服务
              </button>
            </div>
          </div>
          <p v-if="ragHealthError" class="inline-message error">{{ ragHealthError }}</p>

          <div class="rag-collection-row">
            <label class="field-label">
              <span>知识集合</span>
              <select v-model="ragCollection">
                <option value="character_knowledge">角色知识</option>
                <option value="user_documents">用户文档</option>
              </select>
            </label>
            <p v-if="ragHealth" class="rag-service-meta">
              {{ ragHealth.store }} · {{ ragHealth.embedding_model }}
            </p>
          </div>

          <div class="rag-operation-grid">
            <form class="rag-operation" @submit.prevent="uploadRagDocument">
              <div class="rag-operation-heading">
                <span>写入文档</span>
                <span class="mono">{{ ragCollectionLabel(ragCollection) }}</span>
              </div>
              <label class="upload-control rag-file-control">
                <input type="file" accept=".txt,.md,.markdown,text/plain,text/markdown" @change="selectRagDocument">
                {{ ragFile ? ragFile.name : '选择 Markdown 或文本文件' }}
              </label>
              <label class="field-label">
                <span>来源标签（可选）</span>
                <input v-model="ragSourceLabel" type="text" maxlength="120" placeholder="例如：角色设定集">
              </label>
              <button class="text-button rag-submit" type="submit" :disabled="!ragFile || ragUploadState === 'uploading'">
                {{ ragUploadState === 'uploading' ? '写入中…' : '写入知识库' }}
              </button>
            </form>

            <form class="rag-operation" @submit.prevent="searchRagDocuments">
              <div class="rag-operation-heading">
                <span>检索片段</span>
                <span class="mono">{{ ragResults.length }} HITS</span>
              </div>
              <label class="field-label">
                <span>检索内容</span>
                <input v-model="ragQuery" type="search" maxlength="4000" placeholder="输入问题或关键词">
              </label>
              <button class="text-button rag-submit" type="submit" :disabled="!ragQuery.trim() || ragSearchState === 'searching'">
                {{ ragSearchState === 'searching' ? '检索中…' : '检索当前集合' }}
              </button>
            </form>
          </div>

          <p v-if="ragError" class="inline-message error">{{ ragError }}</p>
          <p v-if="ragNotice" class="inline-message notice">{{ ragNotice }}</p>

          <div class="rag-document-area">
            <section class="rag-document-column" aria-labelledby="rag-recent-title">
              <div class="rag-list-heading">
                <h3 id="rag-recent-title">已上传文档</h3>
                <span class="mono">{{ ragRecentDocuments.length }}</span>
              </div>
              <button
                v-if="ragRecentDocuments.length"
                class="rag-delete-button rag-clear-button"
                type="button"
                @click="clearRagCollection"
              >清空当前集合</button>
              <p v-if="!ragRecentDocuments.length" class="rag-empty">
                当前集合还没有上传文档。
              </p>
              <article v-for="document in ragRecentDocuments" :key="document.document_id" class="rag-document-row">
                <div>
                  <strong>{{ document.source_label }}</strong>
                  <span>{{ document.filename }} · {{ document.chunk_count }} 段 · {{ formatRagTime(document.updated_at) }}</span>
                </div>
                <button class="rag-delete-button" type="button" :disabled="Boolean(ragDeletingDocumentId)" @click="deleteRagDocument(document.document_id)">
                  {{ ragDeletingDocumentId === document.document_id ? '删除中…' : '删除' }}
                </button>
              </article>
            </section>

            <section class="rag-document-column" aria-labelledby="rag-results-title">
              <div class="rag-list-heading">
                <h3 id="rag-results-title">检索结果</h3>
                <span class="mono">{{ ragResults.length }}</span>
              </div>
              <p v-if="ragSearchState !== 'success'" class="rag-empty">输入内容后检索当前集合中的文本片段。</p>
              <p v-else-if="!ragResults.length" class="rag-empty">当前集合没有匹配的片段。</p>
              <article v-for="result in ragResults" :key="`${result.document_id}-${result.chunk_index}`" class="rag-result-row">
                <div class="rag-result-meta">
                  <strong>{{ result.source_label }}</strong>
                  <span>{{ result.filename }} · 第 {{ result.chunk_index + 1 }} 段 · {{ formatRagTime(result.updated_at) }}</span>
                </div>
                <span class="rag-score">相关度 {{ result.score.toFixed(3) }}</span>
                <p>{{ result.content }}</p>
                <button class="rag-delete-button" type="button" :disabled="Boolean(ragDeletingDocumentId)" @click="deleteRagDocument(result.document_id)">
                  {{ ragDeletingDocumentId === result.document_id ? '删除中…' : '删除文档' }}
                </button>
              </article>
            </section>
          </div>
        </section>
      </section>

      <aside class="panel inspector-panel">
        <div class="panel-heading">
          <div>
            <p class="eyebrow">INSPECTOR</p>
            <h2>当前状态</h2>
          </div>
          <span class="inspector-icon">✦</span>
        </div>
        <section class="runtime-diagnostics" aria-labelledby="runtime-diagnostics-title">
          <div class="runtime-diagnostics-heading">
            <div>
              <p class="eyebrow">LOCAL RUNTIME</p>
              <h2 id="runtime-diagnostics-title">运行诊断</h2>
            </div>
            <span class="tts-state" :class="gatewayHealthState === 'ready' ? 'success' : gatewayHealthState === 'error' ? 'error' : ''">
              {{ gatewayHealthState === 'checking' ? '检查中' : gatewayHealthState === 'ready' ? '已连接' : gatewayHealthState === 'error' ? '异常' : '待检查' }}
            </span>
          </div>
          <div class="runtime-status-list">
            <div class="runtime-status-row">
              <span class="runtime-status-dot" :class="{ ready: gatewayStatus.running || gatewayHealthState === 'ready', error: gatewayHealthState === 'error' }" />
              <div>
                <strong>本地网关</strong>
                <span>{{ isDesktopMode ? (gatewayStatus.running ? (gatewayStatus.reusedExisting ? '已复用现有服务' : '由桌面应用托管') : '未运行') : '浏览器连接模式' }}</span>
              </div>
              <span class="mono">{{ gatewayStatus.pid ? `PID ${gatewayStatus.pid}` : gatewayHealthState === 'ready' ? 'HTTP OK' : '—' }}</span>
            </div>
            <div class="runtime-status-row">
              <span class="runtime-status-dot" :class="{ ready: godotPetRunning, error: Boolean(godotPetError) }" />
              <div>
                <strong>Godot 桌宠</strong>
                <span>{{ isDesktopMode ? (godotPetRunning ? '桌面窗口运行中' : '未运行') : '浏览器画布预览' }}</span>
              </div>
              <span class="mono">{{ godotPetPid ? `PID ${godotPetPid}` : '—' }}</span>
            </div>
            <div class="runtime-status-row">
              <span class="runtime-status-dot" :class="{ ready: gatewayHealth?.ttsConfigured, error: gatewayHealthState === 'ready' && !gatewayHealth?.ttsConfigured }" />
              <div>
                <strong>语音合成</strong>
                <span>{{ gatewayHealth?.ttsConfigured ? `${gatewayHealth.provider} · ${gatewayHealth.model}` : '尚未配置' }}</span>
              </div>
              <span class="mono">{{ gatewayHealth?.ttsConfigured ? 'READY' : '—' }}</span>
            </div>
            <div class="runtime-status-row">
              <span class="runtime-status-dot" :class="{ ready: gatewayHealth?.doubaoAsrConfigured, error: gatewayHealthState === 'ready' && !gatewayHealth?.doubaoAsrConfigured }" />
              <div>
                <strong>豆包语音识别</strong>
                <span>{{ gatewayHealth?.doubaoAsrConfigured ? '单向流式配置已加载' : '尚未配置' }}</span>
              </div>
              <span class="mono">{{ gatewayHealth?.doubaoAsrConfigured ? 'READY' : '—' }}</span>
            </div>
            <div class="runtime-status-row">
              <span class="runtime-status-dot" :class="{ ready: gatewayHealth?.agentConfigured || gatewayHealth?.agentProvider === 'mock', error: gatewayHealthState === 'ready' && !gatewayHealth?.agentConfigured && gatewayHealth?.agentProvider !== 'mock' }" />
              <div>
                <strong>文本 Agent</strong>
                <span>{{ gatewayHealth ? `${gatewayHealth.agentProvider} · ${gatewayHealth.agentModel}` : '等待网关响应' }}</span>
              </div>
              <span class="mono">{{ gatewayHealth?.agentConfigured ? 'READY' : gatewayHealth?.agentProvider === 'mock' ? 'MOCK' : '—' }}</span>
            </div>
            <div class="runtime-status-row">
              <span class="runtime-status-dot" :class="{ ready: ragHealthState === 'ready', error: ragHealthState === 'error' }" />
              <div>
                <strong>RAG 知识库</strong>
                <span>{{ ragHealthState === 'ready' ? `${ragHealth?.store} · ${ragHealth?.embedding_model}` : ragHealthState === 'error' ? '服务不可用' : '等待检查' }}</span>
              </div>
              <span class="mono">{{ ragHealthState === 'ready' ? 'READY' : '—' }}</span>
            </div>
          </div>
          <div class="runtime-diagnostics-actions">
            <button class="text-button" type="button" :disabled="gatewayHealthState === 'checking'" @click="refreshRuntimeDiagnostics()">
              刷新诊断
            </button>
            <button v-if="isDesktopMode" class="text-button storage-button" type="button" @click="retryGateway">
              重试网关
            </button>
          </div>
          <p v-if="gatewayError || gatewayStatus.lastError || godotPetError" class="inline-message error">
            {{ gatewayError || gatewayStatus.lastError || godotPetError }}
          </p>
        </section>
        <div class="divider" />
        <div class="state-card">
          <span class="state-kicker">ACTIVE ACTION</span>
          <strong>{{ currentLabel }}</strong>
          <span class="mono">action.{{ currentAction }}</span>
        </div>
        <section class="identity-panel" aria-labelledby="identity-title">
          <div class="tts-heading">
            <div>
              <p class="eyebrow">IDENTITY GATE</p>
              <h2 id="identity-title">身份授权</h2>
            </div>
            <span class="tts-state" :class="identityState === 'error' || identitySnapshot?.status === 'guest' ? 'error' : identitySnapshot?.status === 'owner_verified' ? 'success' : ''">
              {{ identityState === 'loading' ? '处理中' : identityState === 'error' ? '认证失败' : identityStatusLabel(identitySnapshot?.status) }}
            </span>
          </div>
          <p v-if="identityTemporaryOpen" class="identity-temp-banner">
            临时开放模式：声纹认证完整落地前，已暂时开放主人权限；模拟认证不会改变当前权限。
          </p>
          <p class="identity-note">
            {{ identityTemporaryOpen
              ? '临时开放中：记忆、提醒、设置和受控工具均可使用。'
              : identitySnapshot?.can_read_private_memory
                ? '主人权限已开启，可访问本地长期记忆。'
                : '未验证身份时，只允许普通对话。' }}
          </p>
          <div class="identity-actions">
            <button type="button" :disabled="identityState === 'loading'" @click="refreshIdentity()">刷新身份</button>
            <button type="button" :disabled="identityState === 'loading'" @click="mockVerifyIdentity('owner')">模拟主人</button>
            <button type="button" :disabled="identityState === 'loading'" @click="mockVerifyIdentity('guest')">模拟访客</button>
            <button type="button" :disabled="identityState === 'loading' || identitySnapshot?.status === 'unknown'" @click="resetIdentity">重置</button>
          </div>

          <!-- 人脸识别 -->
          <div class="face-auth-section">
            <div class="voiceprint-enrollment-heading">
              <span>人脸识别</span>
              <span class="tts-state" :class="faceStatus?.has_profile ? 'success' : ''">
                {{ faceStatus?.has_profile ? '已注册' : '未注册' }}
              </span>
            </div>
            <p class="identity-note">
              本地离线识别，特征数据只保存在本机，不上传任何服务器。
              <span v-if="faceStatus">相似度阈值：{{ (faceStatus.similarity_threshold * 100).toFixed(0) }}%，需要 {{ faceStatus.min_samples }} 张参考照片</span>
            </p>

            <p v-if="faceError && faceMode === 'idle'" class="voiceprint-validation error">{{ faceError }}</p>

            <div v-if="faceMode === 'idle'" class="face-auth-actions">
              <button
                type="button"
                :disabled="faceStatusState === 'loading'"
                @click="() => faceStartCamera('register')"
              >
                {{ faceStatus?.has_profile ? '重新录入人脸' : '录入主人人脸' }}
              </button>
              <button
                type="button"
                :disabled="!faceStatus?.has_profile || faceStatusState === 'loading'"
                @click="() => faceStartCamera('verify')"
              >
                刷脸验证
              </button>
              <button
                type="button"
                class="text-button"
                :disabled="faceStatusState === 'loading'"
                @click="() => { faceInputMode = 'upload'; faceMode = 'register'; faceError = ''; faceUploadFiles = [] }"
              >
                上传图片录入
              </button>
              <button
                v-if="faceStatus?.has_profile"
                type="button"
                class="text-button"
                :disabled="faceStatusState === 'loading'"
                @click="() => { faceInputMode = 'upload'; faceMode = 'verify'; faceError = ''; faceUploadFiles = [] }"
              >
                上传图片验证
              </button>
              <button
                v-if="faceStatus?.has_profile"
                class="danger-link"
                type="button"
                @click="faceDeleteProfile"
              >
                删除档案
              </button>
            </div>

            <div v-else class="face-auth-working-panel">
              <!-- 模式切换条 -->
              <div class="face-mode-switch">
                <button
                  type="button"
                  :class="{ active: faceInputMode === 'camera' }"
                  @click="faceInputMode = 'camera'"
                >
                  摄像头抓拍
                </button>
                <button
                  type="button"
                  :class="{ active: faceInputMode === 'upload' }"
                  @click="faceInputMode = 'upload'"
                >
                  上传图片
                </button>
              </div>

              <!-- 摄像头模式 -->
              <div v-show="faceInputMode === 'camera'" class="face-camera-panel-inner">
                <div class="face-camera-wrapper">
                  <video ref="faceVideoRef" class="face-camera-video" muted playsinline></video>
                  <div v-if="faceMode === 'register'" class="face-camera-hint">
                    请正对摄像头，点击"抓拍"保存参考照片
                  </div>
                  <div v-else class="face-camera-hint">
                    请正对摄像头，点击"验证身份"
                  </div>
                </div>
                <p v-if="faceError" class="voiceprint-validation error">{{ faceError }}</p>
              </div>

              <!-- 上传图片模式 -->
              <div v-show="faceInputMode === 'upload'" class="face-upload-panel">
                <p v-if="faceMode === 'register'" class="identity-note">
                  上传 {{ faceStatus?.min_samples ?? 3 }} 张清晰的正面人脸照片，JPG/PNG 格式。
                </p>
                <p v-else class="identity-note">
                  上传 1 张正面人脸照片进行验证。
                </p>
                <button type="button" class="text-button" @click="triggerFaceFileSelect">
                  {{ faceUploadFiles.length ? '重新选择图片' : '选择图片文件' }}
                </button>
                <p v-if="faceUploadFiles.length" class="identity-note">
                  已选择 {{ faceUploadFiles.length }} 张：
                  {{ faceUploadFiles.map(f => f.name).join('、') }}
                </p>
                <p v-if="faceError && faceInputMode === 'upload'" class="voiceprint-validation error">{{ faceError }}</p>
              </div>

              <div v-if="faceMode === 'register' && faceInputMode === 'camera'" class="face-samples-row">
                <div
                  v-for="(sample, index) in faceCapturedSamples"
                  :key="index"
                  class="face-sample-thumb"
                >
                  <img :src="faceSampleUrl(sample)" alt="" />
                  <button type="button" class="face-sample-remove" @click="faceRemoveSample(index)">×</button>
                </div>
                <div
                  v-for="i in Math.max(0, (faceStatus?.min_samples ?? 3) - faceCapturedSamples.length)"
                  :key="'empty-' + i"
                  class="face-sample-thumb face-sample-empty"
                >
                  <span>待抓拍</span>
                </div>
              </div>

              <div class="face-camera-actions">
                <button
                  v-if="faceMode === 'register' && faceInputMode === 'camera'"
                  type="button"
                  :disabled="!faceCameraActive"
                  @click="faceCaptureSample"
                >
                  抓拍（{{ faceCapturedSamples.length }}/{{ faceStatus?.min_samples ?? 3 }}）
                </button>
                <button
                  v-if="faceMode === 'register'"
                  type="button"
                  class="text-button"
                  :disabled="(faceInputMode === 'camera' ? faceCapturedSamples.length : faceUploadFiles.length) < (faceStatus?.min_samples ?? 3)"
                  @click="faceRegisterSubmit"
                >
                  确认注册
                </button>
                <button
                  v-if="faceMode === 'verify'"
                  type="button"
                  class="text-button"
                  :disabled="(faceInputMode === 'camera' ? !faceCameraActive : !faceUploadFiles.length) || identityState === 'loading'"
                  @click="faceVerifySubmit"
                >
                  {{ identityState === 'loading' ? '验证中…' : '验证身份' }}
                </button>
                <button type="button" class="danger-link" @click="faceCancel">
                  取消
                </button>
              </div>
            </div>
          </div>

          <p v-if="identityError" class="inline-message error">{{ identityError }}</p>
        </section>
        <div class="divider" />
        <section class="reminder-panel" aria-labelledby="reminder-title">
          <div class="tts-heading">
            <div>
              <p class="eyebrow">LOCAL REMINDERS</p>
              <h2 id="reminder-title">提醒</h2>
            </div>
            <button class="agent-clear-button" type="button" :disabled="localStateStatus === 'loading' || !identitySnapshot?.can_read_private_memory" @click="refreshLocalState">
              {{ localStateStatus === 'loading' ? '刷新中…' : '刷新' }}
            </button>
          </div>
          <p class="memory-note">提醒到点只驱动桌宠的提醒动作，不执行任何电脑操作。</p>
          <p v-if="!identitySnapshot?.can_read_private_memory" class="memory-locked">
            提醒、设置和本地事件记录已锁定，请先完成主人身份验证。
          </p>
          <template v-else>
            <form class="reminder-form" @submit.prevent="createReminder">
              <label class="field-label">
                <span>内容</span>
                <input v-model="reminderTitle" type="text" maxlength="180" placeholder="例如：休息一下">
              </label>
              <label class="field-label">
                <span>时间</span>
                <input v-model="reminderAt" type="datetime-local">
              </label>
              <button class="text-button" type="submit" :disabled="localStateStatus === 'saving' || !reminderTitle.trim() || !reminderAt">
                {{ localStateStatus === 'saving' ? '保存中…' : '创建提醒' }}
              </button>
            </form>
            <div class="reminder-list">
              <div class="tool-list-heading">
                <span>待执行</span>
                <span class="mono">{{ reminders.length }}</span>
              </div>
              <p v-if="!reminders.length" class="memory-empty">当前没有待执行的提醒。</p>
              <article v-for="reminder in reminders" :key="reminder.id" class="reminder-row">
                <div>
                  <strong>{{ reminder.title }}</strong>
                  <span>{{ formatLocalStateTime(reminder.remind_at) }}</span>
                </div>
                <button class="danger-link" type="button" :disabled="Boolean(activeReminderId)" @click="cancelReminder(reminder.id)">
                  {{ activeReminderId === reminder.id ? '取消中…' : '取消' }}
                </button>
              </article>
            </div>
          </template>
        </section>
        <div class="divider" />
        <section class="settings-panel" aria-labelledby="settings-title">
          <div class="tts-heading">
            <div>
              <p class="eyebrow">LOCAL PREFERENCES</p>
              <h2 id="settings-title">设置</h2>
            </div>
            <span class="tts-state" :class="localStateStatus === 'error' ? 'error' : localStateStatus === 'ready' ? 'success' : ''">
              {{ localStateStatus === 'saving' ? '保存中' : localStateStatus === 'loading' ? '加载中' : localStateStatus === 'error' ? '异常' : '本机' }}
            </span>
          </div>
          <template v-if="desktopSettings && identitySnapshot?.can_read_private_memory">
            <div class="settings-grid">
              <label class="field-label">
                <span>默认语言</span>
                <select v-model="desktopSettings.language">
                  <option value="zh-CN">中文</option>
                  <option value="ja-JP">日本語</option>
                  <option value="en-US">English</option>
                </select>
              </label>
              <label class="field-label">
                <span>表达风格</span>
                <select v-model="desktopSettings.personality">
                  <option value="warm">温和</option>
                  <option value="balanced">平衡</option>
                  <option value="concise">简洁</option>
                </select>
              </label>
              <label class="field-label">
                <span>音色偏好</span>
                <select v-model="desktopSettings.voice_preference">
                  <option value="default">默认</option>
                  <option value="gentle">柔和</option>
                  <option value="lively">活泼</option>
                </select>
              </label>
              <label class="field-label">
                <span>记忆策略</span>
                <select v-model="desktopSettings.memory_policy">
                  <option value="ask_before_save">确认后保存</option>
                  <option value="disabled">不保存</option>
                </select>
              </label>
            </div>
            <label class="settings-toggle">
              <input v-model="desktopSettings.diagnostics_enabled" type="checkbox">
              <span>显示诊断状态</span>
            </label>
            <p class="settings-readonly">桌面权限：{{ desktopSettings.permission_mode === 'owner_confirmation' ? '主人验证与逐次确认' : desktopSettings.permission_mode }}</p>
            <button class="text-button" type="button" :disabled="localStateStatus === 'saving'" @click="saveDesktopSettings">
              保存设置
            </button>
          </template>
          <p v-if="localStateError" class="inline-message error">{{ localStateError }}</p>
          <p v-if="localStateNotice" class="inline-message notice">{{ localStateNotice }}</p>
        </section>
        <div class="divider" />
        <section class="local-log-panel" aria-labelledby="local-log-title">
          <div class="tool-list-heading">
            <span id="local-log-title">最近本地事件</span>
            <span class="mono">{{ systemLogs.length }}</span>
          </div>
          <p v-if="!identitySnapshot?.can_read_private_memory" class="memory-empty">完成主人验证后显示。</p>
          <p v-else-if="!systemLogs.length" class="memory-empty">暂无本地事件。</p>
          <div v-for="log in systemLogs.slice(0, 6)" :key="log.id" class="local-log-row">
            <span :class="log.status === 'failure' ? 'error' : log.status === 'success' ? 'ready' : 'pending'">{{ log.message }}</span>
            <span>{{ formatLocalStateTime(log.created_at) }}</span>
          </div>
        </section>
        <div class="divider" />
        <section class="tools-panel" aria-labelledby="tools-title">
          <div class="tts-heading">
            <div>
              <p class="eyebrow">CONTROLLED TOOLS</p>
              <h2 id="tools-title">受控桌面工具</h2>
            </div>
            <button class="agent-clear-button" type="button" :disabled="toolState === 'loading'" @click="refreshToolData">
              {{ toolState === 'loading' ? '刷新中…' : '刷新' }}
            </button>
          </div>
          <p class="tools-note">
            仅执行后端白名单内的操作；文件打开必须经过审批，系统命令不会被接受。
          </p>
          <div class="tool-definition-list">
            <div v-for="tool in toolDefinitions" :key="tool.name" class="tool-definition">
              <div>
                <strong>{{ tool.label }}</strong>
                <span>{{ tool.description }}</span>
              </div>
              <span class="tool-badge" :class="tool.enabled ? `risk-${tool.risk_level}` : 'disabled'">
                {{ tool.enabled ? tool.risk_level.toUpperCase() : '未配置' }}
              </span>
            </div>
          </div>
          <div class="tool-operations">
            <div class="tool-operation">
              <div class="tool-operation-heading">
                <span>查询时间</span>
                <span class="mono">{{ toolNameLabel('get_time') }}</span>
              </div>
              <button
                class="text-button"
                type="button"
                :disabled="toolState === 'loading' || toolDefinition('get_time')?.enabled === false"
                @click="executeControlledTool('get_time', {})"
              >
                执行
              </button>
            </div>
            <form class="tool-operation" @submit.prevent="executeControlledTool('search_files', { root_path: toolSearchRoot, pattern: toolSearchPattern, max_results: 20 })">
              <div class="tool-operation-heading">
                <span>授权目录查找</span>
                <span class="mono">{{ toolNameLabel('search_files') }}</span>
              </div>
              <label class="field-label">
                <span>目录</span>
                <input v-model="toolSearchRoot" type="text" maxlength="512" placeholder="例如：backend">
              </label>
              <label class="field-label">
                <span>文件名模式</span>
                <input v-model="toolSearchPattern" type="text" maxlength="120" placeholder="例如：*.md">
              </label>
              <button class="text-button" type="submit" :disabled="toolState === 'loading' || !identitySnapshot?.can_use_tools || toolDefinition('search_files')?.enabled === false">
                查找
              </button>
            </form>
            <form class="tool-operation" @submit.prevent="executeControlledTool('open_application', { app_name: toolAppName })">
              <div class="tool-operation-heading">
                <span>打开白名单应用</span>
                <span class="mono">{{ toolNameLabel('open_application') }}</span>
              </div>
              <label class="field-label">
                <span>应用名称</span>
                <input v-model="toolAppName" type="text" maxlength="80" placeholder="填写已配置的名称">
              </label>
              <button class="text-button" type="submit" :disabled="toolState === 'loading' || !identitySnapshot?.can_use_tools || !toolAppName.trim() || toolDefinition('open_application')?.enabled === false">
                打开
              </button>
            </form>
            <form class="tool-operation" @submit.prevent="executeControlledTool('open_file', { path: toolFilePath })">
              <div class="tool-operation-heading">
                <span>申请打开文件</span>
                <span class="mono">{{ toolNameLabel('open_file') }}</span>
              </div>
              <label class="field-label">
                <span>授权目录内文件路径</span>
                <input v-model="toolFilePath" type="text" maxlength="512" placeholder="填写完整文件路径">
              </label>
              <button class="text-button" type="submit" :disabled="toolState === 'loading' || !identitySnapshot?.can_use_tools || !toolFilePath.trim() || toolDefinition('open_file')?.enabled === false">
                提交审批
              </button>
            </form>
            <div class="tool-operation">
              <div class="tool-operation-heading">
                <span>QQ 音乐控制</span>
                <span class="mono">{{ toolNameLabel('control_music') }}</span>
              </div>
              <div class="music-control-actions">
                <button
                  class="text-button"
                  type="button"
                  :disabled="toolState === 'loading' || toolDefinition('control_music')?.enabled === false"
                  @click="executeControlledTool('control_music', { action: 'play' })"
                >
                  播放
                </button>
                <button
                  class="text-button"
                  type="button"
                  :disabled="toolState === 'loading' || toolDefinition('control_music')?.enabled === false"
                  @click="executeControlledTool('control_music', { action: 'pause' })"
                >
                  暂停
                </button>
              </div>
            </div>
          </div>
          <p v-if="!identitySnapshot?.can_use_tools" class="memory-locked">
            文件和应用工具已锁定，请先完成主人身份验证。
          </p>
          <p v-if="toolError" class="inline-message error">{{ toolError }}</p>
          <p v-if="toolNotice" class="inline-message notice">{{ toolNotice }}</p>
          <div v-if="toolLastResult" class="tool-result">
            <div class="tool-list-heading">
              <span>最近结果 · {{ toolNameLabel(toolLastResult.tool_name) }}</span>
              <span class="mono">{{ toolLastResult.status }}</span>
            </div>
            <pre>{{ toolJson(toolLastResult.result ?? { error: toolLastResult.error_message }) }}</pre>
          </div>
          <div class="tool-review">
            <div class="tool-list-heading">
              <span>待审批</span>
              <span class="mono">{{ toolApprovals.length }}</span>
            </div>
            <p v-if="!toolApprovals.length" class="memory-empty">当前没有待审批操作。</p>
            <article v-for="approval in toolApprovals" :key="approval.approval_id" class="tool-approval-row">
              <div>
                <strong>{{ toolNameLabel(approval.tool_name) }}</strong>
                <span>{{ approval.session_id }} · 截止 {{ new Date(approval.expires_at).toLocaleTimeString() }}</span>
                <pre>{{ toolJson(approval.arguments) }}</pre>
              </div>
              <div class="tool-approval-actions">
                <button type="button" class="confirm" :disabled="toolState === 'loading'" @click="resolveToolApproval(approval.approval_id, 'approve')">批准</button>
                <button type="button" class="danger" :disabled="toolState === 'loading'" @click="resolveToolApproval(approval.approval_id, 'reject')">拒绝</button>
              </div>
            </article>
          </div>
          <div class="tool-review">
            <div class="tool-list-heading">
              <span>最近审计</span>
              <span class="mono">{{ toolAudit.length }}</span>
            </div>
            <p v-if="!toolAudit.length" class="memory-empty">工具执行记录会显示在这里。</p>
            <div v-for="record in toolAudit.slice(0, 5)" :key="record.audit_id" class="tool-audit-row">
              <span>{{ toolNameLabel(record.tool_name) }}</span>
              <span :class="record.status === 'success' ? 'ready' : record.status === 'failure' ? 'error' : 'pending'">{{ record.status }}</span>
              <span>{{ record.speaker_identity }} · {{ record.error_code ?? '无错误' }}</span>
            </div>
          </div>
        </section>
        <div class="inspector-control-grid">
        <label class="control-label" for="fps">播放速度 <span>{{ selectedConfig.fps }} FPS</span></label>
        <input id="fps" v-model.number="selectedConfig.fps" class="range" type="range" min="1" max="30" step="1">
        <div class="range-scale"><span>1</span><span>30</span></div>

        <template v-if="isDesktopMode">
          <div class="divider" />
          <label class="control-label" for="pet-size">桌宠尺寸 <span>{{ petSize }} PX</span></label>
          <input
            id="pet-size"
            :value="petSize"
            class="range"
            type="range"
            min="120"
            max="480"
            step="1"
            @input="updatePetSize"
          >
          <div class="range-scale"><span>120</span><span>480</span></div>
        </template>

        <div class="divider" />
        <p class="control-label">口型状态</p>
        <div class="segmented">
          <button v-for="mode in ['closed', 'half-open', 'open']" :key="mode" type="button" :class="{ active: mouthMode === mode }" @click="mouthMode = mode as typeof mouthMode">
            {{ mode === 'closed' ? '闭合' : mode === 'half-open' ? '半开' : '张开' }}
          </button>
        </div>
        </div>

        <div class="divider" />
        <section class="agent-panel" aria-labelledby="agent-title">
          <div class="tts-heading">
            <div>
              <p class="eyebrow">TEXT AGENT</p>
              <h2 id="agent-title">文本对话</h2>
            </div>
            <span class="tts-state" :class="agentState">
              {{ agentState === 'thinking' ? '思考中' : agentState === 'success' ? '已回复' : agentState === 'error' ? '异常' : '待命' }}
            </span>
          </div>
          <div v-if="agentMessages.length" class="agent-messages" aria-live="polite">
            <div v-for="(message, index) in agentMessages" :key="`${message.role}-${index}-${message.traceId ?? ''}`" class="agent-message" :class="message.role">
              <span class="agent-message-role">{{ message.role === 'user' ? '你' : '桌宠' }}</span>
              <p>{{ message.text }}</p>
              <p v-if="message.role === 'assistant' && message.ragStatus" class="agent-rag-status">
                {{ agentRagStatusLabel(message.ragStatus, message.ragCollection) }}
              </p>
              <div v-if="message.role === 'assistant' && message.sources?.length" class="agent-sources" aria-label="参考来源">
                <span v-for="source in message.sources" :key="`${source.document_id}-${source.chunk_index}`">
                  {{ source.source_label }} · 第 {{ source.chunk_index + 1 }} 段
                </span>
              </div>
            </div>
          </div>
          <p v-else class="agent-empty">输入消息，测试文本 Agent 与动作事件联动</p>
          <textarea
            v-model="agentText"
            class="tts-input agent-input"
            rows="3"
            maxlength="4000"
            placeholder="输入消息后发送"
            :disabled="agentState === 'thinking'"
            @keydown.ctrl.enter.prevent="sendAgentMessage"
          />
          <div class="tts-controls">
            <label class="tts-language">
              <span>语言</span>
              <GlideSelect
                :model-value="agentLanguage"
                :options="languageGlideOptions"
                :menu-width="168"
                aria-label="文本对话语言"
                @update:model-value="agentLanguage = $event"
              />
            </label>
            <button class="tts-button" type="button" :disabled="agentState === 'thinking' || !agentText.trim()" @click="sendAgentMessage">
              {{ agentState === 'thinking' ? '思考中…' : '发送消息' }}
            </button>
          </div>
          <button v-if="agentMessages.length" class="agent-clear-button" type="button" @click="clearAgentConversation">清空对话</button>
          <p v-if="agentError" class="inline-message error">{{ agentError }}</p>
        </section>

        <div class="divider" />
        <section class="memory-panel" aria-labelledby="memory-title">
          <div class="tts-heading">
            <div>
              <p class="eyebrow">MEMORY REVIEW</p>
              <h2 id="memory-title">长期记忆</h2>
            </div>
            <button class="agent-clear-button" type="button" :disabled="memoryState === 'loading' || memoryState === 'saving' || !identitySnapshot?.can_read_private_memory" @click="refreshMemories">
              {{ memoryState === 'loading' ? '刷新中…' : '刷新' }}
            </button>
          </div>
          <p class="memory-note">候选不会自动保存；确认后才会在后续对话中作为个人资料参考。</p>
          <p v-if="!identitySnapshot?.can_read_private_memory" class="memory-locked">
            长期记忆已锁定，请先在右侧完成主人身份验证。
          </p>
          <template v-else>
          <div class="memory-group">
            <div class="memory-group-heading">
              <span>待确认</span>
              <span class="mono">{{ memoryCandidates.length }}</span>
            </div>
            <p v-if="!memoryCandidates.length" class="memory-empty">暂时没有待审核的记忆候选。</p>
            <article v-for="candidate in memoryCandidates" :key="candidate.id" class="memory-row">
              <input v-model="candidate.content" type="text" maxlength="300" aria-label="候选记忆内容">
              <div class="memory-controls">
                <select v-model="candidate.category" aria-label="候选记忆类型">
                  <option value="semantic">事实</option>
                  <option value="preference">偏好</option>
                  <option value="routine">习惯</option>
                </select>
                <button type="button" :disabled="Boolean(activeMemoryId)" @click="updateMemoryCandidate(candidate)">
                  {{ activeMemoryId === candidate.id ? '处理中…' : '更新' }}
                </button>
                <button type="button" class="confirm" :disabled="Boolean(activeMemoryId)" @click="confirmMemoryCandidate(candidate)">确认</button>
                <button type="button" class="danger" :disabled="Boolean(activeMemoryId)" @click="rejectMemoryCandidate(candidate.id)">拒绝</button>
              </div>
            </article>
          </div>
          <div class="memory-group">
            <div class="memory-group-heading">
              <span>已保存</span>
              <span class="mono">{{ confirmedMemories.length }}</span>
            </div>
            <p v-if="!confirmedMemories.length" class="memory-empty">已确认的信息会显示在这里。</p>
            <article v-for="memory in confirmedMemories" :key="memory.id" class="memory-row confirmed">
              <input v-model="memory.content" type="text" maxlength="300" aria-label="已确认记忆内容">
              <div class="memory-controls">
                <select v-model="memory.category" aria-label="已确认记忆类型">
                  <option value="semantic">事实</option>
                  <option value="preference">偏好</option>
                  <option value="routine">习惯</option>
                </select>
                <button type="button" :disabled="Boolean(activeMemoryId)" @click="updateConfirmedMemory(memory)">
                  {{ activeMemoryId === memory.id ? '处理中…' : '保存' }}
                </button>
                <button type="button" class="danger" :disabled="Boolean(activeMemoryId)" @click="deleteConfirmedMemory(memory.id)">删除</button>
              </div>
            </article>
          </div>
          </template>
          <p v-if="memoryError" class="inline-message error">{{ memoryError }}</p>
        </section>

        <div class="divider" />
        <section class="tts-panel" aria-labelledby="tts-title">
          <div class="tts-heading">
            <div>
              <p class="eyebrow">MINIMAX TTS</p>
              <h2 id="tts-title">语音播放</h2>
            </div>
            <span class="tts-state" :class="ttsState">{{ ttsState === 'synthesizing' ? '合成中' : ttsState === 'playing' ? '播放中' : ttsState === 'error' ? '异常' : '待命' }}</span>
          </div>
          <textarea
            v-model="ttsText"
            class="tts-input"
            rows="4"
            maxlength="10000"
            placeholder="输入要让桌宠说的话"
            :disabled="ttsState === 'synthesizing'"
          />
          <div class="tts-controls persona-controls">
            <label class="tts-language">
              <span>角色声线</span>
              <select v-model="selectedVoicePersonaId" @change="resetVoiceDebugOptions">
                <option v-for="persona in voicePersonas" :key="persona.id" :value="persona.id">【{{ persona.languageLabel }}】{{ persona.label }}</option>
              </select>
            </label>
            <label class="tts-language">
              <span>语言</span>
              <GlideSelect
                :model-value="ttsLanguage"
                :options="languageGlideOptions"
                :menu-width="168"
                aria-label="语音播放语言"
                @update:model-value="ttsLanguage = $event"
              />
            </label>
            <button class="tts-button" type="button" :disabled="!speechConfig.enabled || !ttsText.trim() || ttsState === 'synthesizing'" @click="speakText">
              {{ ttsState === 'synthesizing' ? '合成中…' : '合成并播放' }}
            </button>
            <button v-if="ttsState === 'playing'" class="tts-stop-button" type="button" aria-label="停止语音播放" @click="stopSpeech">停止</button>
          </div>
          <div class="voice-debug-panel">
            <div class="voice-debug-title">
              <span>声音调试台</span>
              <button type="button" class="voice-reset-button" @click="resetVoiceDebugOptions">参数重置</button>
            </div>
            <label class="voice-slider">
              <span><b>情绪</b><em>{{ ttsDebugEmotion }}</em></span>
              <select v-model="ttsDebugEmotion">
                <option value="happy">开心 / happy</option>
                <option value="neutral">中性 / neutral</option>
                <option value="angry">不悦 / angry</option>
                <option value="embarrassed">害羞 / embarrassed</option>
                <option value="sad">难过 / sad</option>
              </select>
            </label>
            <label class="voice-slider">
              <span><b>语速</b><em>{{ Math.round(Number(ttsDebugSpeed)) }}</em></span>
              <input v-model.number="ttsDebugSpeed" type="range" min="1" max="2" step="1" />
            </label>
            <label class="voice-slider">
              <span><b>声调</b><em>{{ Math.round(Number(ttsDebugPitch)) }}</em></span>
              <input v-model.number="ttsDebugPitch" type="range" min="-12" max="12" step="1" />
            </label>
            <label class="voice-slider">
              <span><b>音量</b><em>{{ Math.round(Number(ttsDebugVolume)) }}</em></span>
              <input v-model.number="ttsDebugVolume" type="range" min="1" max="3" step="1" />
            </label>
          </div>
          <p class="tts-note">当前声线：{{ currentVoicePersona.label }} · {{ currentVoicePersona.description }}</p>
          <p class="tts-note">推荐语种：{{ currentVoicePersona.languageLabel }}（{{ currentVoicePersona.languageCode }}）</p>
          <p v-if="ttsLanguage !== currentVoicePersona.languageCode" class="tts-note validation-warning">
            当前合成语言为{{ ttsLanguage === 'zh-CN' ? '中文' : ttsLanguage === 'ja-JP' ? '日语' : '英语' }}，与推荐语种不一致；仍可合成，但代表声线建议切换到{{ currentVoicePersona.languageLabel }}。
          </p>
          <p v-if="!speechConfig.enabled" class="tts-note">请在前端环境配置中启用语音网关</p>
          <p v-if="ttsError" class="inline-message error">{{ ttsError }}</p>
        </section>

        <div class="divider" />
        <section class="asr-panel" aria-labelledby="asr-title">
          <div class="tts-heading">
            <div>
              <p class="eyebrow">DOUBAO ASR</p>
              <h2 id="asr-title">语音识别</h2>
            </div>
            <span class="tts-state" :class="asrState">{{ asrState === 'recording' ? '录音中' : asrState === 'recognizing' ? '识别中' : asrState === 'success' ? '完成' : asrState === 'error' ? '异常' : '待命' }}</span>
          </div>
          <label class="continuous-voice-switch">
            <input
              type="checkbox"
              :checked="continuousConversationEnabled"
              @change="toggleContinuousConversation"
            />
            <span>
              <b>连续对话</b>
              <em>叫名字后进入30秒追问窗口，回复时自动避让麦克风</em>
            </span>
          </label>
          <label class="wake-word-switch">
            <input
              type="checkbox"
              v-model="wakeWordGateEnabled"
              @change="persistWakeWordGate"
            />
            <span>
              <b>唤醒词门控</b>
              <em>仅连续对话生效；唤醒词为米娅（ミーア / Miya），唤醒后30秒内可直接追问，手动录音不受限</em>
            </span>
          </label>
          <div class="tts-controls asr-controls">
            <label class="tts-language">
              <span>语言</span>
              <GlideSelect
                :model-value="asrLanguage"
                :options="languageGlideOptions"
                :menu-width="168"
                :disabled="continuousConversationEnabled"
                aria-label="语音识别语言"
                @update:model-value="asrLanguage = $event"
              />
            </label>
            <button class="tts-button asr-button" type="button" :disabled="continuousConversationEnabled || !speechConfig.enabled || !gatewayHealth?.doubaoAsrConfigured || ttsState !== 'idle' || asrState === 'recognizing' || agentState === 'thinking' || rtcVoiceprintAudioBusy" @click="toggleRecording">
              {{ asrState === 'recording' ? '立即停止并识别' : asrState === 'recognizing' ? '识别中…' : '手动录音' }}
            </button>
          </div>
          <p class="continuous-voice-status">{{ continuousConversationStatus }}</p>
          <div v-if="voicePipelineTrace.length" class="voice-pipeline-trace">
            <span v-for="trace in voicePipelineTrace" :key="trace">{{ trace }}</span>
          </div>
          <div v-if="asrState === 'recording' || asrState === 'recognizing'" class="voice-meter" aria-label="麦克风输入音量">
            <span :style="{ width: `${Math.max(2, voiceInputLevel)}%` }"></span>
          </div>
          <p class="asr-result">{{ asrText || '识别结果会显示在这里' }}</p>
          <p class="tts-note">豆包 ASR：{{ gatewayHealth?.doubaoAsrConfigured ? '已配置' : '未配置（需要 DOUBAO_API_KEY 或 APP_KEY/ACCESS_KEY）' }}</p>
          <p v-if="!speechConfig.enabled" class="tts-note">请在前端环境配置中启用语音网关</p>
          <p v-if="asrError" class="inline-message error">{{ asrError }}</p>
          <div class="debug-history-panel">
            <div class="debug-history-heading">
              <button type="button" class="voice-reset-button" @click="showDebugHistory = !showDebugHistory">
                {{ showDebugHistory ? '隐藏调试历史' : `调试历史（${debugHistoryRecords.length}）` }}
              </button>
              <button v-if="showDebugHistory && debugHistoryRecords.length" type="button" class="voice-reset-button danger-text" @click="clearDebugHistory">清空</button>
            </div>
            <div v-if="showDebugHistory" class="debug-history-list">
              <article v-for="record in debugHistoryRecords.slice(0, 20)" :key="record.id" class="debug-history-record" :class="record.status">
                <div class="debug-history-meta">
                  <b>{{ record.title }}</b>
                  <span>{{ formatDebugTime(record.startedAt) }}</span>
                </div>
                <p v-if="record.transcript">识别：{{ record.transcript }}</p>
                <p v-if="record.reply">回复：{{ record.reply }}</p>
                <details>
                  <summary>{{ record.events.length }} 个阶段 · {{ record.status }}</summary>
                  <ol>
                    <li v-for="(event, index) in record.events" :key="`${record.id}-${index}`">
                      {{ formatDebugTime(event.at) }} · {{ event.message }}
                    </li>
                  </ol>
                </details>
              </article>
              <p v-if="!debugHistoryRecords.length" class="tts-note">暂无本地调试历史。</p>
            </div>
          </div>
        </section>

        <div class="divider" />
        <div class="resource-row">
          <span class="resource-icon">◈</span>
          <div>
            <strong>{{ resourceMode }}</strong>
            <span>{{ sourceImage ? sourceImage.fileName : 'Canvas placeholder · ready' }}</span>
          </div>
          <span :class="resourceState === 'READY' ? 'ready' : 'pending'">{{ resourceState }}</span>
        </div>
        <div class="resource-row muted">
          <span class="resource-icon">＋</span>
          <div>
            <strong>动作清单</strong>
            <span>{{ validation.valid ? '可导入或导出 JSON' : '等待参数修正' }}</span>
          </div>
          <span :class="validation.valid ? 'ready' : 'pending'">{{ validation.valid ? 'VALID' : 'CHECK' }}</span>
        </div>
        <div class="resource-row muted">
          <span class="resource-icon">◌</span>
          <div>
            <strong>{{ speechConfig.model }}</strong>
            <span>{{ speechConfig.gatewayUrl }}</span>
          </div>
          <span :class="speechConfig.enabled ? 'ready' : 'pending'">{{ speechConfig.enabled ? 'READY' : 'OFF' }}</span>
        </div>
      </aside>
    </section>
  </main>
</template>
