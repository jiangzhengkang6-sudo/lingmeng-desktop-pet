from pathlib import Path
from textwrap import dedent
content = r'''# 灵梦桌宠智能体产品需求文档（PRD）

**版本：** v0.4 当前实现版  
**更新日期：** 2026-09-18  
**产品状态：** Tauri 桌宠安装包、本地 FastAPI 网关、Godot 渲染、豆包 ASR、MiniMax TTS、Qwen Agent、受控工具、本地调试历史均已进入联调/实测阶段；RTC 声纹主人验证仍处于官方云端链路实测与收敛阶段。  
**产品名称：** 灵梦桌宠

---

## 1. 产品定位

本产品是一款运行在 Windows 桌面的二次元 AI 桌宠。它不是单一聊天机器人，而是由 **Tauri 桌面前端、本地 FastAPI 网关、Godot 桌宠渲染器、云端语音/大模型服务、本地 SQLite 数据、受控桌面工具和身份权限系统** 组成的桌面智能伙伴。

用户可以通过文本或语音与桌宠对话，让桌宠根据语义切换聆听、思考、说话、拒绝等动作；也可以让桌宠查询时间、打开白名单应用、检索授权目录文件、设置本地提醒，并在通过主人身份验证后访问更高权限能力。

产品核心原则：

1. **人格稳定**：角色语气、称呼、偏好和禁忌通过系统提示词与配置保持一致。
2. **本地优先**：配置、调试历史、工具审批、本地状态和密钥尽量保存在用户本机。
3. **权限受控**：模型不能直接执行任意命令，工具必须走白名单、Schema、审批和审计。
4. **链路可观测**：ASR、Agent、TTS、工具、RTC 身份等关键环节都有状态或本地历史记录。
5. **可替换服务**：语音、模型和身份服务通过网关适配，避免前端绑定单一供应商。

---

## 2. v0.4 当前范围与完成状态

| 模块 | 当前状态 | 说明 |
|---|---|---|
| Tauri 桌面壳 | 已完成并可打包 MSI | v0.4.0 安装包，支持本地网关随应用启动 |
| Vue3 控制台 | 已完成 | 包含身份、RTC、TTS、ASR、Agent、记忆、工具、提醒、资源调试等面板 |
| Godot 桌宠 | 已接入 | Tauri 通过 preview.json 同步动作与口型 |
| SpriteSheet 资源 | 已完成基础链路 | 支持 manifest、切帧、底部锚点、待机/聆听/思考/说话等动作 |
| 豆包流式 ASR | 已完成 | WebSocket SAUC，支持 WAV 流式识别、日语/英语/中文 |
| MiniMax TTS | 已完成 | 支持日语、英语、中文及多角色音色 |
| Qwen Agent | 已接入 | HTTP 文本 Agent，普通聊天与本地时间工具可用 |
| 本地工具 | 部分完成 | get_time 稳定；白名单应用、授权目录文件查找、本地提醒具备代码与 UI 基础 |
| 本地记忆 | 基础完成 | SQLite/记忆候选/确认机制具备，RAG 与 Milvus 仍需实测收敛 |
| RTC 声纹 | 联调中 | StartVoiceChat、RTS 回调、场景文件、官方 SDK 已打通到入房阶段；Token/云端应用配置仍在实测 |
| 调试历史 | 已完成 | localStorage 保存 ASR/Agent/TTS/工具等阶段历史，重启后可查看 |
| 打包发布 | 已完成 | PyInstaller + Vite + Tauri MSI，本地用户目录运行配置 |

---

## 3. 用户与核心场景

### 3.1 目标用户

- 喜欢二次元角色、希望桌面具备陪伴感的个人用户。
- 需要语音快捷操作、时间查询、简单桌面自动化的效率用户。
- 希望 AI 有稳定人设、可配置声线、可见动作反馈的用户。
- 对本地隐私、工具权限和审计有要求的高级用户。

### 3.2 核心使用场景

1. **桌面陪伴**：桌宠在桌面待机动画中轻微摆动，用户随时点击或语音唤起。
2. **文本问答**：用户在 TEXT AGENT 面板输入问题，桌宠切换思考/说话动作并回答。
3. **语音控制**：用户连续对话或手动录音，豆包 ASR 转写后交给 Agent。
4. **多语言交流**：中文、日语、英语识别与对应 TTS 声线回复。
5. **本地工具**：询问时间、打开白名单应用、查询授权目录文件、设置提醒。
6. **资源调试**：导入 SpriteSheet，查看动作帧、切帧结果、manifest 与 Godot 预览。
7. **身份授权**：通过 RTC 声纹识别主人，通过后开放受控工具和私有能力。
8. **问题排查**：在调试历史中查看每次 ASR、Agent、TTS、工具请求的阶段状态。

---

## 4. 产品架构

### 4.1 桌面端

- **Tauri v2**：桌面窗口、应用生命周期、本地资源、Godot 进程管理。
- **Vue 3 + TypeScript + Vite**：控制台、表单、状态展示、调试面板。
- **@volcengine/rtc**：官方 RTC Web SDK，用于声纹验证时加入 VoiceChat 房间并发布麦克风。
- **localStorage**：保存本地调试历史和轻量前端状态。

### 4.2 本地网关

- **FastAPI**：提供 REST 与 WebSocket API。
- **PyInstaller**：将 Python 网关打包到 MSI 资源中。
- **运行目录**：`%LOCALAPPDATA%\LingMengDesktopPet`
- **关键接口**：
  - `/api/health`
  - `/api/speech/asr/stream`
  - `/api/speech/tts`
  - `/api/agent/chat`
  - `/api/tools/execute`
  - `/api/identity/*`
  - `/api/identity/rtc/sessions`
  - `/api/identity/rtc/client-token`
  - `/api/identity/rtc/rts/messages`

### 4.3 桌宠渲染

- **Godot 4.7**：透明桌面窗口、角色 SpriteSheet 播放、动作状态机。
- **preview.json**：Tauri 写入动作、口型、暂停和尺寸，Godot 轮询读取。
- **动作资源协议**：统一 PetAction / MouthMode，避免 Agent 直接操作渲染器。

### 4.4 云端能力

- **豆包 SAUC ASR**：实时语音识别。
- **MiniMax TTS**：多语言语音合成。
- **Qwen 文本 Agent**：对话、意图判断、工具选择。
- **火山引擎 RTC / AI 音视频互动方案**：StartVoiceChat、RTS 回调、VoicePrint、官方 RTC SDK。

### 4.5 本地数据

- SQLite：本地工具、提醒、记忆候选与审计。
- JSON：RTC 声纹场景、Godot 资源 manifest。
- localStorage：前端调试历史。
- `.env`：本地网关密钥和供应商配置，不写入仓库。

---

## 5. 功能需求

### 5.1 桌宠显示与动作

**必须满足：**

- 支持待机、聆听、思考、说话、不悦、害羞、打开应用等动作。
- SpriteSheet 按 manifest 切帧并循环播放。
- 角色锚点稳定，切换动作时不明显跳动。
- Tauri 可启动/关闭 Godot，并同步 preview.json。
- 缺少资源时回退到 Canvas 占位动画或 idle。

**验收标准：**

- 切换不同动作时 Godot 窗口中角色动作立即变化。
- 动作播放期间口型可随 TTS 能量切换 closed / half-open / open。
- 重启应用后资源和动作状态可恢复。

### 5.2 文本 Agent

**必须满足：**

- 支持中、日、英多轮对话。
- 请求超时、供应商失败时有明确错误文案。
- 普通聊天不应误触发工具。
- 时间类问题优先使用本地 `get_time`，减少远程模型延迟。
- Agent 返回动作字段，前端据此切换桌宠状态。

**验收标准：**

- “现在几点了？”在 1 秒级返回本地时间。
- 普通闲聊可返回 TTS 或文本回复。
- 工具失败时返回 `success=false` 与错误原因，不伪装成功。

### 5.3 语音识别与合成

**ASR：**

- 采集 16 kHz、16-bit、单声道 PCM/WAV。
- 支持连续对话和手动录音。
- VAD 自动停顿断句，手动录音可点击停止。
- partial 与 final 事件区分显示。
- 豆包重复 final 不再重复提交 Agent。

**TTS：**

- 支持中文傲娇、温柔、御姐、日语雷厉千金、英语灵动女声等音色。
- WebAudio 播放，HTMLAudio 作为兜底。
- 播放期间同步桌宠说话动作和口型。

**验收标准：**

- 中文、日语、英语各至少完成一次识别和播放闭环。
- TTS 返回有效音频时桌宠进入 speaking。
- 音频播放失败时显示错误，不影响文本对话。

### 5.4 连续对话

- 默认加入唤醒词“小赤红”。
- 唤醒词仅为本地文本门控，不等同声纹主人认证。
- 支持连续对话、唤醒词开关、手动录音独立路径。
- 识别 final 后进入 Agent；Agent/TTS 期间避免重复提交。
- 支持阶段状态显示：等待、聆听、识别、提交 Agent、TTS、完成、错误。

### 5.5 本地调试历史

- 每次语音/工具/Agent/TTS 链路生成本地历史记录。
- 记录保存在 localStorage，重启后仍可查看。
- 支持查看阶段、时间、消息、转录文本、回复文本和错误。
- 支持清空历史。

### 5.6 工具与权限

工具必须遵守四层安全边界：

1. 前端只调用本地网关。
2. 网关使用 Pydantic Schema 校验参数。
3. 服务通过白名单和审批策略判断是否可执行。
4. 执行结果写入审计记录。

当前工具范围：

- `get_time`：低风险，可自动执行。
- `search_files`：仅检索授权根目录。
- `open_application`：仅启动登记应用。
- `open_file`：需要授权和审批。
- 本地提醒：创建、触发、延后、取消。

### 5.7 RTC 声纹身份

**目标：** 通过火山 AI 音视频互动方案识别当前说话人是否为注册主人。

**已实现：**

- 本地 RTC 场景文件 `voiceprint-rtc-scene.json`。
- RegisterVoicePrint 注册样本并写入 VoicePrintId。
- StartVoiceChat / StopVoiceChat 会话控制。
- RTS HTTP 回调验签、解析 subv/stat、消费首个有效身份事件。
- 官方 Web SDK 入房、麦克风采集和发布。
- 临时 Token 调试输入与 client-token 接口。

**待完成：**

- 确认 AI 音视频互动控制台使用的 AppId/AppKey 与 StartVoiceChat 应用一致。
- 完成官方 SDK 入房成功，而不是仅创建 VoiceChat 任务。
- 收到主人声纹回调后将身份切换为 `owner_verified`。
- 处理 guest、低分、非目标用户、回调过期与重放。

---

## 6. 安全与隐私要求

1. API Key、AppKey、Secret 不进入前端包、日志和截图。
2. 模型不能直接访问 Shell、注册表、系统目录或任意进程。
3. 工具必须按名称白名单和参数 Schema 执行。
4. 高风险操作必须人工确认。
5. 主人声纹不是绝对安全，不能单独作为支付、系统管理员等高敏操作授权。
6. 调试历史中不应记录密钥原文。
7. 用户可以清除 localStorage、本地数据库和运行配置。
8. 原始录音默认不永久保存。

---

## 7. 非功能需求

### 7.1 性能

- 本地 get_time：P95 ≤ 1 秒。
- 桌宠动作切换：≤ 300 ms。
- Agent 普通回复：目标 P95 ≤ 10 秒，具体取决于云端模型。
- TTS 首音频：目标 P95 ≤ 2 秒，MiniMax 实测以网络为准。
- MSI 冷启动：网关健康检查应在 10 秒内完成。

### 7.2 稳定性

- 外部服务失败时保留文本输入能力。
- WebSocket 断开时给出明确状态，不无限等待。
- Godot 崩溃不影响控制台健康检查。
- 任一工具失败不得破坏其他功能。
- 安装包升级不覆盖用户运行时 `.env`。

### 7.3 可维护性

- 前端供应商客户端集中在 `src/voice`、`src/agent`、`src/identity`。
- 后端供应商适配集中在 provider 模块。
- 所有外部服务通过本地网关代理。
- 单元测试覆盖 Token、ASR 协议、Agent 工具、身份事件、资源 manifest 等关键逻辑。

---

## 8. 当前测试基线

- 前端 Vitest：34 个测试文件、120 个测试通过。
- 后端 Pytest：143 个测试通过。
- MSI 安装包可安装、启动并通过 `/api/health`。
- TTS 已使用真实 MiniMax 接口返回音频。
- ASR 已使用真实豆包 SAUC WAV 完成识别。
- StartVoiceChat 可返回 TaskId。
- RTC Token 可生成/解包，但官方 SDK 入房仍需云端配置最终确认。

---

## 9. 里程碑

### M1：桌面与角色基础（已完成）

- Tauri 应用、Godot 窗口、SpriteSheet、动作切换、preview.json。

### M2：本地网关与语音闭环（已完成基础版）

- FastAPI、豆包 ASR、MiniMax TTS、Qwen Agent、健康检查。

### M3：工具、记忆与调试（基础完成）

- get_time、本地工具框架、提醒、调试历史、记忆候选。

### M4：RTC 主人身份（进行中）

- 声纹注册、StartVoiceChat、RTS 回调、官方 SDK 入房、身份提升。

### M5：发布体验优化（下一步）

- 安装配置向导、供应商配置检查、错误诊断、权限引导、首屏 onboarding。

---

## 10. 发布前必须关闭的问题

1. RTC SDK 入房 `INVALID_TOKEN`：确认 AI 音视频互动应用、AppKey、RoomId、UserId 与 Token 生成方式。
2. 主人声纹 live 回调尚未完成端到端 `owner_verified` 验收。
3. 工具白名单应用和授权目录需要提供默认配置或界面配置流程。
4. RAG/Milvus 在当前安装版中未作为必需默认依赖，需明确“本地记忆/云端知识库”的产品边界。
5. 首次运行需要配置向导，避免用户手动编辑 `.env`。
6. PPT/汇报材料需要同步当前实际进度，不再将未完成的 RTC 声纹表述为已完成。

---

## 11. 最终验收清单

- [ ] MSI 全新安装后自动启动网关和控制台。
- [ ] Godot 桌宠可见并能响应动作切换。
- [ ] 中文、日语、英语语音识别和 TTS 均成功。
- [ ] “现在几点了”走本地工具并快速回复。
- [ ] 普通聊天与工具调用链路互不干扰。
- [ ] 调试历史可记录并在重启后恢复。
- [ ] 非主人不能使用高权限工具。
- [ ] 主人 RTC 声纹验证成功后身份变为 `owner_verified`。
- [ ] 工具审批、拒绝、失败均有审计记录。
- [ ] 前端 120 个测试、后端 143 个测试全部通过。
- [ ] 卸载/重装不泄露或覆盖用户密钥配置。
'''
Path('灵梦桌宠智能体PRD初稿.md').write_text(content, encoding='utf-8')
print('PRD updated chars', len(content))
