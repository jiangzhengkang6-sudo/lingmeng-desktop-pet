# 语音调试台与 Docker Desktop 修复指南

更新时间：2026-09-14

## 1. 声音调试台

声音调试台位于应用界面的 **MINIMAX TTS / 语音播放** 区域，用于快速验证桌宠声线、情绪和发音参数，不需要重新打包应用。

### 已验证的角色声线

| 语种提示 | 角色声线 | MiniMax 音色 ID | 默认情绪 | 适用场景 |
| --- | --- | --- | --- | --- |
| 中文（`zh-CN`） | 赤红精灵·傲娇 | `Chinese_huolishaonv` | `happy` | 活泼、娇俏、带一点撒娇感 |
| 中文（`zh-CN`） | 赤红精灵·温柔 | `Chinese_wenrounvxing` | `neutral` | 柔和、舒缓、安静陪伴 |
| 中文（`zh-CN`） | 沉稳执行官 | `Chinese (Mandarin)_Reliable_Executive` | `neutral` | 低沉、可靠、专业的男声 |
| 中文（`zh-CN`） | 傲娇御姐 | `Chinese (Mandarin)_Mature_Woman` | `neutral` | 低沉沙哑、慵懒舒缓，适合成熟御姐或美艳角色 |
| 日语（`ja-JP`） | 雷厉千金 | `Japanese_DecisivePrincess` | `neutral` | 清脆透亮、节奏紧凑，适合强势少女或动漫角色 |
| 英语·英音（`en-GB`） | 灵动女声 | `English_compelling_lady1` | `neutral` | 英音女声、清脆明亮，适合旁白和剧情类解说 |

以上音色 ID 均已通过 MiniMax TTS 接口验证；后三个为本次新增的中、日、英代表声线。角色声线下拉框会显示语种前缀，当前声线说明中也会展示推荐语种。

### 可调参数

- **情绪**：`happy`、`neutral`、`angry`、`embarrassed`、`sad`。
- **语速**：整数，范围 `1–2`。
- **声调**：整数，范围 `-12–12`。
- **音量**：整数，范围 `1–3`，界面只开放安全且不易失真的调试范围。
- **参数重置**：恢复当前角色声线的默认参数。

> MiniMax `speech-2.8-hd` 对 `voice_setting.speed`、`pitch`、`vol` 使用整数类型。即使前端或旧配置传入小数，后端也会先四舍五入并限制到合法范围，避免出现 `invalid params, Mismatch type int64` 错误。

### 手动验收步骤

1. 打开桌面宠物应用。
2. 在 **语音播放** 中输入一句测试文本，例如：`你好，我是你的桌面伙伴。`
3. 选择角色声线和语言。
4. 在 **声音调试台** 中调整情绪、语速、声调和音量。
5. 点击 **合成并播放**。
6. 听到音频且状态从“合成中”变为“播放中”，最后回到“待命”，即表示链路正常。
7. 点击 **参数重置**，确认参数恢复为所选角色的默认值。

如果接口返回“声音不存在”，优先检查音色 ID 是否与 MiniMax 音色库完全一致；音色 ID 中空格、括号和大小写都必须匹配。

## 2. 语音识别说明

语音播放和语音识别是两条不同链路：

- 语音播放使用 MiniMax TTS，决定发音人的是音色 ID 和发音参数。
- 语音识别使用豆包 SAUC/Doubao ASR，主要依赖麦克风权限、输入语言、音频格式和豆包鉴权，不存在“男声/女声识别模型”切换。

应用健康状态中：

- `doubaoAsrConfigured: true` 表示当前流式豆包 ASR 所需鉴权已配置。
- 旧字段 `asrConfigured: false` 代表另一条非流式 HTTP ASR 路径，不影响当前使用的豆包流式识别。

识别失败时，应先确认界面中豆包 ASR 显示“已配置”，再检查系统麦克风权限、浏览器/WebView 麦克风授权和所选语言。

## 3. Docker Desktop 无法启动引擎

### 已确认现象

Docker Desktop 曾卡在：

```text
Starting the Docker Engine...
```

后台日志反复出现：

```text
still waiting for init control API
/ping context deadline exceeded
```

WSL 侧的 `docker-desktop` 发行版曾返回 HCS 错误：

```text
0x800705aa
```

该问题通常与 WSL2 虚拟机资源分配、休眠后的 VM 状态或 Docker Desktop/WSL 后端初始化有关。磁盘空间和物理内存当时均充足。

### 已写入的 WSL2 配置

当前用户目录下的 `C:\Users\j\.wslconfig` 使用保守资源限制：

```ini
[wsl2]
memory=8GB
processors=4
swap=2GB
localhostForwarding=true
debugConsole=false
vmIdleTimeout=60000

[experimental]
autoMemoryReclaim=gradual
sparseVhd=true
```

这样可以避免 WSL2 虚拟机一次性占用过多资源，并启用稀疏 VHD 和渐进式内存回收。

## 4. 一键安全修复

项目提供安全修复脚本：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\repair-docker-desktop.ps1
```

脚本会执行：

1. 停止 Docker Desktop 相关进程。
2. 执行 `wsl --shutdown` 清理异常 WSL 虚拟机状态。
3. 如果不存在 `.wslconfig`，写入保守资源配置。
4. 启动 Docker Desktop。
5. 等待 Docker Engine 就绪。
6. 输出 Docker 版本、容器数量和镜像数量。

脚本**不会删除**以下任何数据：

- Docker 容器
- Docker 镜像
- Docker 数据卷
- WSL 发行版
- `ext4.vhdx` 或其他 VHDX 虚拟磁盘文件

2026-09-14 复验结果：

```text
Server=29.4.3 Containers=13 Images=12
Docker Desktop is ready.
```

### 下次打开前的判断方式

正常启动后，以下命令应返回 Server 版本而不是管道连接错误：

```powershell
docker info --format 'Server={{.ServerVersion}} Containers={{.Containers}} Images={{.Images}} Driver={{.Driver}}'
```

如果再次卡在引擎启动页，先运行修复脚本；不要手动删除 Docker 的 VHDX 文件，否则可能造成镜像、容器或卷数据丢失。


## 语音控制完整闭环

当前语音控制链路为：

```text
豆包 ASR final
  → 前端自动提交 Agent（source=voice）
  → Agent 生成回复 / 执行受控工具
  → 返回 tool_calls、文本、动作和口型
  → MiniMax TTS 合成并播放
  → WebSocket 与 Tauri 预览状态同步到 Godot
```

### 自动语音对话

ASR 返回 final 文本后，不需要再手动复制到 Agent 输入框，前端会自动：

1. 将识别文本加入对话消息列表。
2. 使用识别语言向 `/api/agent/chat` 发起 `source: "voice"` 请求。
3. 将 Agent 回复加入对话消息列表。
4. 根据回复语言自动选择匹配语种的角色声线。
5. 合成并播放 TTS。
6. 将 Agent 返回的 `action_id`、`mouth_mode` 同步给 Godot。

英语识别如果使用 `en-GB`，前端会以 Agent 支持的 `en-US` 提交语义请求，但 TTS 仍可使用英音代表声线 `English_compelling_lady1`。

### 已接入的语音工具

语音 Agent 只执行明确、低歧义且仍受白名单/审计约束的工具：

| 语音指令示例 | 工具 | 动作 | 身份要求 |
| --- | --- | --- | --- |
| “现在几点？” / “What time is it?” / “今何時？” | `get_time` | `speaking` | 不需要主人验证 |
| “打开记事本” / “open Notepad” | `open_application` | 成功时 `open-app`，失败时 `displeased` | 需要主人验证，且应用必须在白名单中 |

工具不是由大模型直接执行的。本地网关会先做确定性语音意图识别，再交给 `ControlledToolService` 执行；工具服务仍会进行所有者校验、应用白名单校验和审计记录。

配置白名单应用示例：

```env
TOOLS_ALLOWED_APPLICATIONS=记事本=notepad.exe
```

Windows 多个配置使用分号分隔，例如：

```env
TOOLS_ALLOWED_APPLICATIONS=记事本=notepad.exe;计算器=calc.exe
```

未配置白名单时，“打开某应用”不会执行任何系统命令，只会按普通对话处理。这样可以避免语音识别误触发本机操作。



### 连续对话：直接对桌面桌宠说话

除了在面板中手动录音，也可以在 ASR 区域开启 **连续对话**。开启一次后即可直接对桌面上的 Godot 桌宠说话，不需要每轮点击录音按钮。

连续对话流程：

```text
进入 listening
→ 本地检测到持续人声
→ 停顿约 0.9 秒后自动断句
→ ASR final
→ Agent 思考与回复
→ TTS 播放时麦克风自动避让
→ 播放结束后自动重新 listening
```

当前本地断句参数：

| 参数 | 当前值 | 说明 |
| --- | --- | --- |
| 人声启动阈值 | RMS `0.018` | 持续超过阈值才认为开始说话 |
| 最短启动时长 | `180ms` | 避免短促噪音触发 |
| 停顿断句时长 | `900ms` | 句尾静音约 0.9 秒后自动提交 |
| 单句最长时长 | `15s` | 防止异常情况下一直录音 |
| 回复后恢复监听延迟 | `220ms` | 等待音频链路稳定 |

连续对话采用半双工：桌宠 TTS 回复前麦克风本轮已经关闭，播放期间不会提交新识别，回复结束后才重新进入监听。这样可以避免桌宠听到自己的声音形成循环。

如果连续 3 次没有听清或连续处理失败，应用会自动关闭连续对话并提示；重新点击开关即可再次开始。应用重启后不会静默启动麦克风，需要用户再次点击开关完成麦克风授权。


#### “有效语音”的定义


#### 自适应噪声阈值与唤醒词门控

连续对话会先采集约 `700ms` 环境底噪，随后使用“底噪 × 2.4 + 安全余量”的自适应阈值，并保留最低阈值与最高阈值保护。这样安静房间和风扇/空调环境不会共用同一个固定触发值。界面中的音量条仍会显示当前输入能量，状态文案会显示当前处于底噪校准、等待唤醒词还是听到人声。

唤醒词门控默认开启。连续对话中只有包含以下唤醒词的 ASR 文本才会提交 Agent：

- 中文：`小赤红`、`赤红`，并兼容常见误识别 `小刺红`、`小翅红`
- 英文：`Hey Crimson`、`Hi Crimson`、`Crimson`

例如：

- `小赤红，现在几点了？` → 去除唤醒词后提交 `现在几点了？`
- 背景中的 `下午好。` → 不提交 Agent，界面提示先说“小赤红”
- 只说 `小赤红` → 桌宠回应“我在，请说指令”，随后继续监听

唤醒词是本地文本门控，发生在 ASR 之后，不是声纹认证。它能减少背景人声和电视声误触发，但不能证明说话人是主人；敏感工具仍要求声纹 `owner_verified`。

连续对话里有两级判断：

1. **本地人声检测有效**：输入音量达到阈值，持续时间至少约 `180ms`，并且累计有效人声不少于 `320ms`。短促碰撞声、风扇噪声、键盘声等短噪声不会立即提交给 ASR。
2. **ASR 有效识别**：豆包 SAUC 在 final 结果中返回非空、去空白后仍有内容的文本。只有满足这一级，系统才会把内容提交给 Agent。

因此，界面出现“检测到停顿，正在识别…”只表示本地 VAD 触发过，并不代表豆包已经识别出文字。若随后提示“未识别到有效语音”，说明豆包 final 文本为空。新版界面会显示实时音量、累计人声毫秒和失败诊断，用来区分麦克风无输入、环境噪声误触发，还是 ASR 服务未识别。

声纹认证与连续 ASR 仍然分离：连续对话只表示“正在听语音命令”，不会自动提升为 `owner_verified`。打开白名单应用等敏感工具仍需完成声纹主人认证。

### Godot 动作同步

Godot 有两条收敛路径：

- Agent HTTP/WS 响应通过 `/api/pet/events` WebSocket 广播动作。
- Tauri 桌宠运行时通过 `preview.json` 同步当前动作、口型、暂停状态和尺寸。

普通回复会在 TTS 播放期间切换到 `speaking`，播放结束回到 `idle`。工具类回复（例如打开应用成功）会先朗读结果，TTS 口型播放结束后恢复为 Agent 指定的 `open-app` 动作。
