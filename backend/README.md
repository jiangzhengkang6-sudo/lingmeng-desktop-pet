# Local Speech Gateway

The gateway keeps provider credentials on the server side. The frontend only calls
the local endpoints:

- `GET /api/health`
- `POST /api/speech/tts`
- `POST /api/speech/asr`
- `WS /api/speech/asr/stream`
- `POST /api/pet/events`
- `WS /api/pet/events`
- `POST /api/agent/chat`
- `WS /api/agent/events`
- `GET /api/identity`
- `POST /api/identity/mock/verify`
- `POST /api/identity/verify`
- `POST /api/identity/rtc/voiceprint-observations`
- `POST /api/identity/rtc/voiceprints/register`
- `GET /api/identity/rtc/bridge`
- `POST /api/identity/rtc/sessions`
- `DELETE /api/identity/rtc/sessions/{task_id}`
- `POST /api/identity/reset`
- `GET /api/face/status`
- `POST /api/face/register`
- `POST /api/face/verify`
- `DELETE /api/face/profile`
- `GET /api/reminders`
- `POST /api/reminders`
- `PATCH /api/reminders/{reminder_id}`
- `DELETE /api/reminders/{reminder_id}`
- `GET /api/settings`
- `PATCH /api/settings`
- `GET /api/system/logs`
- `GET /api/tools`
- `POST /api/tools/execute`
- `GET /api/tools/approvals`
- `POST /api/tools/approvals/{approval_id}/approve`
- `POST /api/tools/approvals/{approval_id}/reject`
- `GET /api/tools/audit`
- `GET /api/memories/candidates`
- `PATCH /api/memories/candidates/{candidate_id}`
- `POST /api/memories/candidates/{candidate_id}/confirm`
- `DELETE /api/memories/candidates/{candidate_id}`
- `GET /api/memories`
- `PATCH /api/memories/{memory_id}`
- `DELETE /api/memories/{memory_id}`
- `GET /api/rag/health`
- `POST /api/rag/documents`
- `POST /api/rag/search`
- `DELETE /api/rag/documents/{collection}/{document_id}`

Run from the project root:

```powershell
# 必须使用 Python 3.12（MediaPipe 官方 wheel 暂不支持 Python 3.13）
python -m pip install -r requirements.txt
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

### 本地人脸识别开发

人脸功能的代码问题统一在开发模式（`uvicorn` + `npm run dev`）中修复，不要通过
反复 PyInstaller 打包和热替换来调试。首次准备环境时确认：

```powershell
python --version  # 应为 Python 3.12.x
python -c "import cv2; print(cv2.__version__)"
```

身份识别链路是 **OpenCV YuNet 人脸检测 + SFace 身份嵌入**（完全离线，
128 维特征），需要两个 ONNX 模型，首次准备时下载：

```powershell
python scripts/download_face_models.py
# 产物：backend/models/face_detection_yunet_2023mar.onnx
#       backend/models/face_recognition_sface_2021dec.onnx
```

旧的 MediaPipe `face_landmarker.task` 几何关键点方案经实测没有身份区分度
（主人/他人分数重叠，gap 为负），已不再用于身份认证，只保留引擎代码给未来
实时表情/注意力感知用，默认打包也不含 mediapipe。模型路径解析按
“配置路径 → exe 同目录 `models/` → `_internal/models/` → `_MEIPASS/models/`”
依次尝试。`GET /api/face/status` 的 `diagnostics.models` 会分别返回
YuNet/SFace/Landmarker 的全部候选路径、存在性、字节数，`dependencies`
给出 cv2（必需）与 mediapipe（可选）的导入结果；模型缺失时 503 也携带同一诊断。

 热更新安装目录前必须先停止 `desktop-pet-gateway` 和
`lingmeng-desktop-pet`，再以管理员身份执行 `scripts/hot-update.ps1`。脚本会在
复制后校验网关 exe 与 YuNet/SFace 模型的 SHA256 和字节数，校验失败立即报错。

### 阈值标定实验（P1-1）

身份特征用 SFace 余弦相似度判定，阈值必须用真实样本标定。
准备主人 5 张以上（不同表情、角度、光照）和非主人 5 张以上照片后执行：

```powershell
python scripts/face_threshold_calibration.py `
  --owner samples/face/owner `
  --others samples/face/others `
  --report runtime/logs/face-calibration.json
```

脚本采用留一法计算主人分布、与全部主人样本比最高相似度得到他人分布，
输出两者的 min/max/mean/std、gap 与建议阈值（两类边界中点）。gap 不足
（分布重叠）时退出码为 1，应增加样本复标；仍不可分则换更强的嵌入
（如 InsightFace）。

当前实测（主人 3 张、他人 5 张）：几何关键点 gap=−0.0086（不可分，
已废弃）；SFace 主人最低 0.6543、他人最高 0.2447、gap=+0.4096，
默认阈值取 0.45（见 `runtime/logs/face-calibration-sface.json`）。

### 打包与发布

唯一打包通道是 `backend/desktop-pet-gateway.spec`，不要在命令行追加
`--collect-all`（`scripts/build-gateway.ps1` 已固定调用该 spec）：

- pymilvus 保留整包收集（grpc 动态依赖复杂）；
- 身份链路只依赖 OpenCV（YuNet+SFace），不打包 mediapipe；
- 不打包 matplotlib/pandas/PIL/tkinter/sounddevice，并剔除 OpenCV 的 ffmpeg 视频库；
- 模型与 `.env.example` 由构建脚本复制到 exe 同目录，构建结束自校验
  exe/模型/配置模板的存在性与模型 SHA256。

精简后网关产物约 236MB / 882 个文件（最初约 374MB / 2400 个文件）。
打包后用冒烟脚本验证模型解析、`configured=true`，设置环境变量后还会用
真实照片在打包 exe 上跑注册/主人通过/他人拒绝：

```powershell
powershell -File scripts/build-gateway.ps1
python scripts/smoke_face_gateway.py
# 可选真实推理冒烟：
$env:SMOKE_OWNER_DIR="C:\Users\你\Desktop\我的人脸样本"
$env:SMOKE_OTHER_DIR="C:\Users\你\Desktop\他人的人脸样本"
python scripts/smoke_face_gateway.py
```

桌面安装包统一走 NSIS（`tauri.conf.json` 的 `bundle.targets=["nsis"]`，
`scripts/build-desktop.ps1` 使用 `--bundles nsis`），不再使用在 600MB+
规模下会内存崩溃的 32 位 WiX MSI 通道。

`SPEECH_MODEL=speech-2.8-hd` and `https://api.minimax.io/v1/t2a_v2` are the
defaults. The gateway requests non-streaming hex audio and returns it as
`audioHex` to the frontend. Set `SPEECH_API_KEY` and `SPEECH_VOICE_ID` in
`.env`. ASR uses a separate `SPEECH_ASR_ENDPOINT`; `speech-2.8-hd` is not
treated as an ASR model.

Doubao SAUC is the separate streaming ASR provider. Configure
`DOUBAO_API_KEY` or the legacy `DOUBAO_APP_KEY` and `DOUBAO_ACCESS_KEY` pair,
plus `DOUBAO_RESOURCE_ID`, in `.env`. The browser sends JSON
`{"type":"start","language":"zh-CN"}`, binary 16 kHz mono PCM s16le chunks,
then `{"type":"stop"}` to the WebSocket route. It receives `ready`,
`partial`, `final`, `error`, and `closed` events. The SAUC connection is
created per browser stream and never shares credentials or state with MiniMax.

Text Agent defaults to a deterministic local Mock Agent. To use Qwen or another
OpenAI-compatible endpoint, set `AGENT_PROVIDER=qwen` (or
`openai-compatible`), `AGENT_MODEL`, `AGENT_API_BASE_URL`, and
`AGENT_API_KEY` in `.env`; the default endpoint becomes
`/chat/completions`. `AGENT_FALLBACK_TO_MOCK=true` keeps text chat usable when
the remote Agent is unavailable or returns an invalid structured response.
Provider keys never enter `.env.frontend`.

The Agent WebSocket accepts `agent.message` events with a `request_id` and
`session_id`. It responds with `agent.status`, `agent.response`, `pet.action`,
and either a final `agent.status` or `agent.error`. The existing HTTP endpoint
remains available as a fallback for older packaged gateways.

### Agent + RAG E2E 验收

项目根目录提供了非破坏性的端到端验收脚本
`scripts/verify_agent_rag_e2e.py`。它会依次检查网关健康、临时 RAG 文档
上传、HTTP Agent 回复、Agent WebSocket 事件、`pet.action` 广播和 RAG
降级；结束时无论成功或失败，都会尝试删除本次生成的临时文档。脚本不会
读取或输出 `.env` 中的密钥，也不会删除已有的 `user_documents` 或
`character_knowledge` 文档。

先启动网关（默认地址为 `http://127.0.0.1:8000`），再从项目根目录运行：

```powershell
python scripts/verify_agent_rag_e2e.py
```

常用参数：

```powershell
# 指定已运行的网关地址和超时
python scripts/verify_agent_rag_e2e.py `
  --base-url http://127.0.0.1:8001 `
  --timeout 30

# 跳过 RAG 空库/不可用探测
python scripts/verify_agent_rag_e2e.py --skip-degradation

# 要求本次运行必须观察到 empty 或 unavailable
python scripts/verify_agent_rag_e2e.py --require-degradation

# 验收真实 Qwen/OpenAI-compatible Agent，不允许静默回退到 Mock
python scripts/verify_agent_rag_e2e.py --require-remote-agent
```

脚本最后输出一个 JSON 对象。顶层 `passed: true` 且每个
`checks[].ok` 都为 `true` 才算通过。正常通过时至少应看到以下检查：
`网关健康检查`、`RAG 临时文档上传`、`Agent HTTP + RAG 来源`、
`Agent WebSocket + Pet 动作广播`、`RAG 临时数据清理`。若环境已有
`user_documents`，降级探测可能观察到 `used`；默认会将此视为非破坏性探测
并通过，只有使用 `--require-degradation` 时才要求真实观察到
`empty/unavailable`。

真实远程 Agent 验收步骤：

1. 在服务端 `.env` 设置 `AGENT_PROVIDER=qwen`（或
   `openai-compatible`）、`AGENT_MODEL`、`AGENT_API_BASE_URL`、
   `AGENT_API_KEY`；也可以直接设置 `AGENT_CHAT_ENDPOINT`。
2. 将 `AGENT_FALLBACK_TO_MOCK=false`，重启网关，让新配置生效。
3. 先确认 `GET /api/health` 返回 `agentConfigured: true`，再运行
   `python scripts/verify_agent_rag_e2e.py --require-remote-agent`。
4. 如果远程服务返回超时、非结构化 JSON 或不符合动作清单的结果，脚本会
   失败；这时不会伪装成 Mock 成功。排查完成后，开发环境可暂时恢复
   `AGENT_FALLBACK_TO_MOCK=true`，但这不等于真实模型验收通过。

`Agent HTTP + RAG 来源` 和 `Agent WebSocket + Pet 动作广播` 两项只检查
协议字段、来源元数据和动作一致性，不把 RAG 文档正文返回给前端。RAG
临时文档的内容只用于确认检索链路，脚本结束后的清理检查用于避免污染
本地 Milvus 或内存存储。

The gateway keeps only short-term, in-process conversation context per
`session_id`. Set `AGENT_CONTEXT_TURN_LIMIT` to control the number of recent
user/assistant rounds retained (default `6`); context is discarded when the
gateway restarts. Call `DELETE /api/agent/sessions/{session_id}` to remove it
immediately. This context never writes to Milvus or long-term memory.

## Controlled desktop tools

Desktop actions are exposed only through explicit tool definitions. The gateway
never accepts arbitrary shell commands, executable arguments, or paths outside
the configured allowlist. `get_time` is low-risk and available without owner
verification. File search and allowlisted application launch require the owner
identity. Opening a file is a medium-risk action and creates a pending approval
that must be approved in the debug interface within 10 minutes.

Configure these values in the server-side `.env`:

```env
TOOLS_DATABASE_PATH=backend/data/desktop-pet.sqlite3
TOOLS_ALLOWED_DIRECTORIES=backend;docs
TOOLS_ALLOWED_APPLICATIONS=记事本=notepad.exe
```

Leave the allowlists empty until the intended directories and applications have
been reviewed. Approval and execution outcomes are written to the local SQLite
audit table without storing credentials. The service does not expose an
arbitrary Shell or command execution tool.

## Identity boundary

The gateway starts in `unknown` identity state. Ordinary chat remains available,
but all memory endpoints return `403 OWNER_VERIFICATION_REQUIRED` until the
owner is verified. The current development adapter is deterministic and local:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/identity
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/identity/mock/verify `
  -ContentType 'application/json' -Body '{"sample":"owner"}'
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/identity/reset
```

Use `sample=guest` to enter guest mode. The mock route is only a development
placeholder; it does not authenticate a real speaker. The `VoiceprintAdapter`
boundary is kept independent so a future speaker-verification provider cannot
change memory or tool policy by itself.

`POST /api/identity/verify` is reserved for real audio verification. It accepts
one `audio` multipart file in memory, rejects non-audio content and oversized
samples, and never writes biometric audio to the local database. While
`VOICEPRINT_PROVIDER=mock` (the default), the route returns
`503 VOICEPRINT_NOT_CONFIGURED` rather than granting access. This keeps the
existing debug-only mock controls working without pretending they verify a real
person.

Do not enable a non-mock provider until its official enrollment and
verification API contract is available. The dialogue-agent console's ASR/TTS
configuration is not a substitute for a speaker-verification API.

### Volcengine RTC voiceprint bridge

Volcengine RTC voiceprint is part of the AI audio-video interaction task. The
local gateway keeps `/api/identity/verify` closed for the RTC provider, but it
can register one explicitly confirmed owner sample through the official
server-side `RegisterVoicePrint` API. Registration is separate from the later
recognition event bridge.

Set `VOICEPRINT_PROVIDER=volcengine-rtc`, configure
`VOICEPRINT_RTC_OWNER_NAME`, set `VOICEPRINT_RTC_SCORE_THRESHOLD=50` as the
initial value (RTC scores are in the inclusive `1–100` range), and create a
high-entropy `VOICEPRINT_RTC_BRIDGE_SECRET`. To register, send one WAV file
with multipart field `audio` and `confirmed=true` to:

```text
POST /api/identity/rtc/voiceprints/register
```

The route accepts only uncompressed PCM WAV audio at 16 kHz, 16-bit, mono, and
15–30 seconds. It validates the upload in memory and rejects files above
1.5 MB. A call sends the sample to the configured RTC cloud account, so the
caller must always make the confirmation explicit. The backend never writes
the raw recording to disk. On success it writes only the returned
`VoicePrintId` to the ignored
`backend/config/voiceprint-rtc-scene.json`, configuring pre-registered
recognition with `Mode: 2`, `IdList`, score `50`, and ASR `StreamMode: 0`.

The RTC cloud callback/event integration remains separate. A trusted RTC
bridge must normalize the recognition result and post it to this local route:

```text
POST /api/identity/rtc/voiceprint-observations
X-Desktop-Pet-Voiceprint-Timestamp: unix-seconds
X-Desktop-Pet-Voiceprint-Signature: hex(HMAC-SHA256(secret, timestamp + "." + raw-body))
Content-Type: application/json

{"task_id":"rtc-task-id","voiceprint_name":"registered-audio-name","voiceprint_score":52}
```

The gateway accepts only a valid, short-lived HMAC and grants owner status only
when both the registered name and local score threshold match. It does not save
the source audio, bridge secret, or raw RTC callback. A verified identity still
does not bypass a pending desktop-tool approval.

### RTC event bridge transport

The project now includes `backend/app/rtc_event_bridge.py` as the server-side
transport layer for a trusted RTC worker. It accepts only this already
normalized internal shape:

```json
{
  "task_id": "rtc-task-id",
  "voiceprint_name": "registered-audio-name",
  "voiceprint_score": 52
}
```

The bridge trims and validates these exact fields, signs the exact compact JSON
bytes with `VOICEPRINT_RTC_BRIDGE_SECRET`, and forwards them to the local
observation route. It deliberately does not guess provider callback field
names or parse an unverified official event payload. A provider-specific RTC
worker/SDK must perform that mapping after the official event contract has been
confirmed.

For transport-only diagnostics, the repository also provides:

```powershell
python scripts/submit_rtc_voiceprint_observation.py `
  --task-id "<real-rtc-task-id>" `
  --voiceprint-name "<provider-returned-name>" `
  --score 52
```

The script reads the bridge secret from the server-side `.env`; it never
accepts secrets on the command line. This command is only a transport check
with a real normalized observation from a trusted RTC worker. It is not a
mock verification route and does not grant owner access when the RTC gateway
is not configured or the observation does not meet the configured threshold.

For a long-running local worker process, use the JSON Lines entrypoint:

```powershell
Get-Content .\rtc-observations.jsonl | `
  python scripts/rtc_event_bridge_worker.py
```

Each non-empty line must be one normalized event with exactly the fields shown
above. The worker performs a startup request to
`GET /api/identity/rtc/bridge`, reads the bridge secret only from the server
`.env`, and exits with a non-zero code on configuration errors, malformed JSON,
invalid event fields, network failures, or gateway rejection. Use
`--check-only` to run the startup check without submitting an event.

This is an input/transport boundary for an external RTC worker. It does not
join an RTC room, read provider callbacks, or invent a recognition result. The
external worker remains responsible for using the official RTC client/SDK and
mapping its confirmed event schema to the normalized internal fields.

The provider boundary is implemented in
`backend/app/rtc_provider_adapter.py`. It is fail-closed: a provider must
register an explicit mapper before any callback can enter the identity bridge.

### 火山 RTS 官方实时回调

真实 live 验收使用火山 RTS 服务端 HTTP 回调，不再要求官方客户端把事件手工写入 JSONL。

服务端启动 `StartVoiceChat` 时注入以下运行时字段：

- `AgentConfig.ServerMessageURLForRTS`
- `AgentConfig.ServerMessageSignatureForRTS`
- `AgentConfig.EnableConversationStateCallback=true`
- `Config.SubtitleConfig.SubtitleMode=0`

回调固定进入：

```text
POST/GET /api/identity/rtc/rts/messages
```

POST 外层为：

```json
{
  "message": "Base64(subv 或 stat 二进制帧)",
  "signature": "ServerMessageSignatureForRTS 的共享密钥"
}
```

二进制帧格式为：

```text
4 字节 magic + 4 字节大端长度 + UTF-8 JSON
```

`stat` 只表示声纹功能状态，不授予身份；`subv` 必须是当前唯一活动 RTC 任务中、`TargetUserId` 真人用户的完整句（`definite=true` 且 `paragraph=true`），且 `voiceprintName`、`voiceprintId` 与 `voiceprintScore` 完整，才可能进入主人判定。原始字幕文本、完整声纹 ID 和回调密钥不会出现在接口响应或系统日志中。

本地开发可使用 Cloudflare Quick Tunnel 将 `http://127.0.0.1:8000` 临时映射成公网 HTTPS。受限代理只放行 RTS 回调路径，不暴露其他本地 API：

```powershell
python scripts\rts_public_proxy.py --listen-host 127.0.0.1 --port 8001
tools\cloudflared.exe tunnel --url http://127.0.0.1:8001 --no-autoupdate
```

### 离线脱敏 JSONL 映射

`rtc_event_bridge_worker.py` 仍可用于检查已经解包的官方脱敏 `subtitle` JSON，但它使用本地 HMAC 桥，不能替代云端 RTS live 验收：

```powershell
python scripts/rtc_event_bridge_worker.py `
  --provider volcengine-rtc `
  --task-id "<real-rtc-task-id>" `
  --input-file ".\rtc-callbacks-redacted.jsonl"
```

离线 worker 不会加入 RTC 房间、生成声纹分数，也不会猜测任务号。SAUC ASR 文本仍然不能作为声纹认证证据。

### Inspecting an official RTC callback safely

Before implementing the Volcengine mapper, obtain one callback sample from the
official RTC client/SDK or provider logging. Do not paste credentials, access
signatures, raw audio, or full transcript text into the repository. Save the
sample outside the project, or pass it through standard input:

```powershell
Get-Content C:\path\rtc-callback.json -Raw |
  python scripts/inspect_rtc_event.py
```

The diagnostic command prints only JSON-pointer-like field paths and primitive
types, for example `$/Result/VoicePrint/Score: number`. It does not print
values, call the local gateway, sign an observation, or modify identity state.
Use the output to identify the confirmed task ID, registered voiceprint name or
ID, and score fields. A mapper may be added only after those paths are verified
against the official event contract and a real callback sample.

### RTC task control

The local backend can also call the official RTC VoiceChat OpenAPI for
`StartVoiceChat` and `StopVoiceChat`. It uses Volcengine HMAC request signing
with the server-only values below:

```env
VOICEPRINT_RTC_ACCESS_KEY_ID=
VOICEPRINT_RTC_SECRET_ACCESS_KEY=
VOICEPRINT_RTC_APP_ID=
VOICEPRINT_RTC_APP_KEY=
VOICEPRINT_RTC_REGION=cn-north-1
VOICEPRINT_RTC_API_VERSION=2025-06-01
VOICEPRINT_RTC_SCENE_PATH=backend/config/voiceprint-rtc-scene.json
VOICEPRINT_RTC_SESSION_TTL_SECONDS=3600
```

Copy `backend/config/voiceprint-rtc-scene.example.json` to the ignored
`backend/config/voiceprint-rtc-scene.json`, then fill its provider-side
VoiceChat configuration from the RTC console and the matching official
documentation. The backend provides the runtime `AppId`, `RoomId`, `TaskId`,
`AgentConfig.UserId`, and `AgentConfig.TargetUserId`; the scene file is
deliberately rejected when it tries to override them.

`GET /api/identity/rtc/bridge` reports readiness, including the selected API
version, without exposing credentials or the scene. The startup route is intentionally limited to the explicit
`identity_verification` purpose. It does not grant owner access itself; only a
subsequent signed RTC observation can change the identity state:

```text
POST /api/identity/rtc/sessions
{"roomId":"room-1","agentUserId":"pet-agent","targetUserIds":["desktop-owner"],"confirmed":true}
```

This starts or stops the provider task only. It does not replace the official
RTC client that joins the room, nor does it fabricate a voiceprint result.
在本地验证会话启动后，前端通过
`POST /api/identity/rtc/client-token` 获取仅限当前任务目标用户的短期 Web SDK
Token。Token 由服务端使用 `VOICEPRINT_RTC_APP_ID` 和
`VOICEPRINT_RTC_APP_KEY` 签发，AppKey 永不下发浏览器；浏览器随后使用官方
`@volcengine/rtc` SDK 加入同一房间并发布麦克风。
官方客户端只需加入真实房间；火山云端会把 RTS 消息直接 POST 到
`/api/identity/rtc/rts/messages`。离线脱敏样本仍可通过本地 HMAC worker 提交到
`/api/identity/rtc/voiceprint-observations`，但不能作为 live 验收证据。

The gateway keeps the TaskId returned by a successful `StartVoiceChat` call in
an in-memory active-session registry. A callback is accepted only while that
TaskId is active and within `VOICEPRINT_RTC_SESSION_TTL_SECONDS` (default one
hour). A successful `StopVoiceChat`, process restart, or TTL expiry invalidates
the TaskId, so an old callback cannot change identity state.

## User-confirmed memory

Long-term memory is a separate local SQLite database configured by
`MEMORY_DATABASE_PATH`. It stores only candidates that the user explicitly
confirms in the debug interface; it does not copy full conversations, RAG
documents, or credentials. Pending candidates can be edited, confirmed, or
rejected. Confirmed entries can be edited or permanently deleted through the
memory endpoints. `MEMORY_CONTEXT_LIMIT` controls how many of the most recently
updated confirmed entries may be supplied to the text Agent (default `12`).

Both candidates and confirmed entries remain local to this installation. They
are presented to the Agent as factual profile data, never as executable
instructions, and they are not written to Milvus in this phase. Content that
looks like a password, API key, secret, bank-card number, or identity number is
rejected before storage.

## Reminders, settings, and local logs

One-time reminders are stored in local SQLite using `LOCAL_STATE_DATABASE_PATH`.
They require the owner identity, remain after a local gateway restart, and
dispatch only a `reminder` pet-action event when due. A reminder never launches
an application, opens a file, or runs a command. Use an ISO 8601 timestamp with
a timezone when calling `POST /api/reminders`.

`GET/PATCH /api/settings` stores display preferences for language, personality,
voice preference, memory policy, and diagnostics. The permission mode is
display-only and remains `owner_confirmation`; settings cannot grant desktop
access. `GET /api/system/logs` is owner-only and intentionally contains only
safe event summaries. Tool audit records remain in their separate endpoint and
are not copied into this log.

Send
`{"message":"你好","language":"zh-CN","session_id":"demo-session","rag_collection":"character_knowledge"}`
to `/api/agent/chat`. `rag_collection` is optional and only accepts
`character_knowledge` or `user_documents`. When present, the gateway retrieves
up to three matching chunks before asking the Agent for a response. The response
contains `text`, `language`, `emotion`, `action_id`, `mouth_mode`,
`requires_confirmation`, `tool_calls`, `trace_id`, display-only `sources`, and
`rag_status` (`used`, `empty`, `unavailable`, or `disabled`). The gateway uses
JSON Schema plus local Pydantic validation before broadcasting the returned
action as a `pet.action` event. `tool_calls` remains empty until controlled
tools are added.

## Basic RAG

The first RAG phase uses separate Milvus collections named
`character_knowledge` and `user_documents`. It intentionally does not create
long-term memory, user profiles, system-policy storage, tools, or automatic
Agent prompt injection.

Start Milvus from the project root after Docker Desktop is ready:

```powershell
docker compose -f infra/milvus/docker-compose.yml up -d
```

Check `GET /api/rag/health`. Upload only UTF-8 `.txt`, `.md`, or `.markdown`
files with `POST /api/rag/documents` multipart fields `collection`,
`source_label` (optional), and `document`. The response returns the generated
`document_id`, source label, update time, and chunk count. Query a single
collection with `POST /api/rag/search`, then remove all of a document's chunks
through the delete endpoint.

`RAG_EMBEDDING_PROVIDER=hash` is the local deterministic development default.
It makes offline insert/search validation possible but is not suitable for
production-quality semantic recall. When an embedding API is available, set
`RAG_EMBEDDING_PROVIDER=openai-compatible`, its model, endpoint, API key, and
matching vector dimension in the server-side `.env`.

Uploaded documents are untrusted reference material. Retrieved content is
explicitly marked as data for the remote Agent and cannot add instructions,
policies, tool calls, permissions, or change safety rules. A missing or
unavailable RAG service does not block chat: the response reports `rag_status`
and falls back to ordinary dialogue.

The Vite frontend uses a separate `.env.frontend` file containing only the
local gateway URL, model display name, and enable flags. `VITE_PET_EVENT_ENABLED`
controls whether action changes are published to the local pet event route. Start
it from the project root with:

```powershell
npm run dev
```
