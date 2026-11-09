/**
 * 人脸识别身份认证客户端。
 * 与后端 /api/face/* 接口交互。
 */

/**
 * 网关基址。人脸界面运行在 Tauri webview（tauri.localhost）或 Vite 开发端口下，
 * 相对路径 /api 到不了 8000 网关，因此与其它客户端统一使用绝对地址。
 * 优先级：人脸专用变量 -> 桌面事件网关变量 -> 本地默认。
 */
// 与其他客户端保持一致，优先使用 Agent 网关地址（即本地桌面网关），
// 确保人脸接口与文本/语音等功能走同一个后端实例。
const GATEWAY_URL = (
  import.meta.env.VITE_FACE_GATEWAY_URL
  || import.meta.env.VITE_AGENT_GATEWAY_URL
  || import.meta.env.VITE_PET_EVENT_GATEWAY_URL
  || import.meta.env.VITE_SPEECH_GATEWAY_URL
  || 'http://127.0.0.1:8000'
).replace(/\/+$/, '')

function faceUrl(path: string): string {
  return `${GATEWAY_URL}${path}`
}

export type FaceStatus = {
  enabled: boolean
  configured: boolean
  has_profile: boolean
  similarity_threshold: number
  min_samples: number
  diagnostics?: FaceDiagnostics
}

export type FaceDependencyDiagnostics = {
  module: string
  available: boolean
  version: string | null
  error: string | null
}

export type FaceModelCandidateDiagnostics = {
  source: string
  path: string
  exists: boolean
  size_bytes: number | null
}

export type FaceModelDiagnostics = {
  path: string | null
  size_bytes: number | null
  candidates: FaceModelCandidateDiagnostics[]
}

export type FaceDiagnostics = {
  backend: string
  models: {
    detector_yunet: FaceModelDiagnostics
    recognizer_sface: FaceModelDiagnostics
    landmarker_mediapipe?: FaceModelDiagnostics
  }
  dependencies: {
    cv2: FaceDependencyDiagnostics
    mediapipe?: FaceDependencyDiagnostics
  }
  runtime: {
    cwd: string
    frozen: boolean
    executable: string
    meipass: string | null
    config_directory: string | null
  }
}

export type FaceProfile = {
  name: string
  sample_count: number
  created_at: number
}

export async function getFaceStatus(): Promise<FaceStatus> {
  const resp = await fetch(faceUrl('/api/face/status'))
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}))
    throw new Error(err?.detail?.message || '获取人脸状态失败')
  }
  return resp.json()
}

export async function registerFace(
  name: string,
  images: Blob[],
): Promise<FaceProfile> {
  const form = new FormData()
  form.append('name', name)
  for (const img of images) {
    form.append('images', img, 'face.jpg')
  }
  const resp = await fetch(faceUrl('/api/face/register'), {
    method: 'POST',
    body: form,
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}))
    throw new Error(err?.detail?.message || '人脸注册失败')
  }
  return resp.json()
}

export async function verifyFace(image: Blob): Promise<{
  status: string
  adapter: string
  can_read_private_memory: boolean
  can_use_tools: boolean
}> {
  const form = new FormData()
  form.append('image', image, 'verify.jpg')
  const resp = await fetch(faceUrl('/api/face/verify'), {
    method: 'POST',
    body: form,
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}))
    throw new Error(err?.detail?.message || '人脸验证失败')
  }
  return resp.json()
}

export async function deleteFaceProfile(): Promise<void> {
  const resp = await fetch(faceUrl('/api/face/profile'), {
    method: 'DELETE',
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}))
    throw new Error(err?.detail?.message || '删除人脸档案失败')
  }
}

/**
 * 从视频流中捕获一帧画面，返回 JPEG Blob。
 */
export function captureFrame(video: HTMLVideoElement, quality = 0.92): Blob {
  const canvas = document.createElement('canvas')
  canvas.width = video.videoWidth
  canvas.height = video.videoHeight
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Canvas 上下文不可用')
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
  let result: Blob | null = null
  // 用同步方式取 blob（这里用 toDataURL 兜底）
  const dataUrl = canvas.toDataURL('image/jpeg', quality)
  const byteString = atob(dataUrl.split(',')[1])
  const mimeString = dataUrl.split(';')[0].split(':')[1]
  const ab = new ArrayBuffer(byteString.length)
  const ia = new Uint8Array(ab)
  for (let i = 0; i < byteString.length; i++) {
    ia[i] = byteString.charCodeAt(i)
  }
  result = new Blob([ab], { type: mimeString })
  return result
}

/**
 * 打开摄像头并将画面渲染到指定 video 元素。
 * 返回关闭摄像头的函数。
 */
export async function startCamera(
  video: HTMLVideoElement,
  constraints: MediaStreamConstraints = { video: { width: 640, height: 480, facingMode: 'user' } },
): Promise<() => void> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error('当前环境不支持摄像头（navigator.mediaDevices 不可用）')
  }
  let stream: MediaStream
  try {
    stream = await navigator.mediaDevices.getUserMedia(constraints)
  } catch (err) {
    if (err instanceof DOMException) {
      if (err.name === 'NotAllowedError' || err.name === 'SecurityError') {
        throw new Error('摄像头权限被拒绝。请检查：1) Windows 系统设置 → 隐私和安全性 → 相机，确保已允许桌面应用访问摄像头；2) 若仍无反应，可使用下方"上传图片"方式进行注册/验证')
      }
      if (err.name === 'NotFoundError' || err.name === 'OverconstrainedError') {
        throw new Error('未找到可用摄像头。请确认电脑已连接摄像头，或使用下方"上传图片"方式进行注册/验证')
      }
      if (err.name === 'NotReadableError') {
        throw new Error('摄像头被其他程序占用，请关闭占用摄像头的应用后重试')
      }
      if (err.name === 'TypeError') {
        throw new Error('当前环境为不安全上下文，无法使用摄像头。请在本地应用内使用')
      }
      throw new Error(`打开摄像头失败：${err.name} ${err.message}`)
    }
    throw err
  }
  video.srcObject = stream
  await video.play()
  return () => {
    stream.getTracks().forEach((track) => track.stop())
    video.srcObject = null
  }
}

/**
 * 快速检测摄像头是否可用（不实际打开预览，只申请权限并立即释放）。
 * 返回 true 表示可以使用，抛出错误表示不可用。
 */
export async function probeCamera(): Promise<boolean> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error('当前环境不支持摄像头 API')
  }
  let stream: MediaStream | null = null
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { width: 320, height: 240 } })
    return true
  } finally {
    if (stream) {
      stream.getTracks().forEach((t) => t.stop())
    }
  }
}

/**
 * 从文件输入读取图片为 Blob。
 */
export async function fileToBlob(file: File): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      resolve(new Blob([reader.result as ArrayBuffer], { type: file.type || 'image/jpeg' }))
    }
    reader.onerror = () => reject(new Error('读取文件失败'))
    reader.readAsArrayBuffer(file)
  })
}
