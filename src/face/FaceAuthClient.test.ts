import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  deleteFaceProfile,
  getFaceStatus,
  registerFace,
  verifyFace,
  type FaceDiagnostics,
} from './FaceAuthClient'

const diagnostics: FaceDiagnostics = {
  backend: 'sface',
  models: {
    detector_yunet: {
      path: 'C:/gateway/models/face_detection_yunet_2023mar.onnx',
      size_bytes: 232589,
      candidates: [
        {
          source: 'PyInstaller：exe 同目录 models',
          path: 'C:/gateway/models/face_detection_yunet_2023mar.onnx',
          exists: true,
          size_bytes: 232589,
        },
      ],
    },
    recognizer_sface: {
      path: 'C:/gateway/models/face_recognition_sface_2021dec.onnx',
      size_bytes: 38696353,
      candidates: [
        {
          source: 'PyInstaller：exe 同目录 models',
          path: 'C:/gateway/models/face_recognition_sface_2021dec.onnx',
          exists: true,
          size_bytes: 38696353,
        },
      ],
    },
  },
  dependencies: {
    cv2: { module: 'cv2', available: true, version: '5.0.0', error: null },
  },
  runtime: {
    cwd: 'C:/ProgramData',
    frozen: true,
    executable: 'C:/gateway/desktop-pet-gateway.exe',
    meipass: null,
    config_directory: 'C:/Users/owner/AppData/Local/LingMengDesktopPet',
  },
}

describe('FaceAuthClient', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('读取人脸状态并保留诊断字段', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      enabled: true,
      configured: true,
      has_profile: false,
      similarity_threshold: 0.93,
      min_samples: 3,
      diagnostics,
    }), { status: 200 }))
    vi.stubGlobal('fetch', fetchImpl)

    const status = await getFaceStatus()

    expect(status.configured).toBe(true)
    expect(status.diagnostics?.backend).toBe('sface')
    expect(status.diagnostics?.models.recognizer_sface.size_bytes).toBe(38696353)
    expect(status.diagnostics?.dependencies.cv2.available).toBe(true)
    expect(fetchImpl).toHaveBeenCalledWith('http://127.0.0.1:8000/api/face/status')
  })

  it('注册时以 multipart 提交姓名和全部图片', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      name: 'owner',
      sample_count: 3,
      created_at: 123,
    }), { status: 200 }))
    vi.stubGlobal('fetch', fetchImpl)
    const images = [
      new Blob(['a'], { type: 'image/jpeg' }),
      new Blob(['b'], { type: 'image/jpeg' }),
      new Blob(['c'], { type: 'image/jpeg' }),
    ]

    const profile = await registerFace('owner', images)

    expect(profile.sample_count).toBe(3)
    const [url, init] = fetchImpl.mock.calls[0]
    expect(url).toBe('http://127.0.0.1:8000/api/face/register')
    expect(init.method).toBe('POST')
    const form = init.body as FormData
    expect(form.get('name')).toBe('owner')
    expect(form.getAll('images')).toHaveLength(3)
  })

  it('验证成功时返回身份快照', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      status: 'owner_verified',
      adapter: 'mediapipe-face',
      can_read_private_memory: true,
      can_use_tools: true,
    }), { status: 200 }))
    vi.stubGlobal('fetch', fetchImpl)

    const snapshot = await verifyFace(new Blob(['face'], { type: 'image/jpeg' }))

    expect(snapshot.status).toBe('owner_verified')
    expect(snapshot.can_use_tools).toBe(true)
    const [url, init] = fetchImpl.mock.calls[0]
    expect(url).toBe('http://127.0.0.1:8000/api/face/verify')
    expect(init.method).toBe('POST')
    expect((init.body as FormData).get('image')).toBeInstanceOf(Blob)
  })

  it('删除人脸档案', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }))
    vi.stubGlobal('fetch', fetchImpl)

    await expect(deleteFaceProfile()).resolves.toBeUndefined()
    expect(fetchImpl.mock.calls[0]).toEqual([
      'http://127.0.0.1:8000/api/face/profile',
      expect.objectContaining({ method: 'DELETE' }),
    ])
  })

  it.each([
    ['获取人脸状态失败', getFaceStatus],
    ['删除人脸档案失败', deleteFaceProfile],
  ])('网关报错时透出中文原因：%s', async (_label, action) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: { code: 'FACE_MODEL_MISSING', message: '人脸模型文件不存在' },
    }), { status: 503 })))

    await expect(action()).rejects.toThrow('人脸模型文件不存在')
  })
})
