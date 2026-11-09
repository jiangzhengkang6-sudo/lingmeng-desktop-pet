# Godot 桌宠运行说明

## 当前目的

Godot 是唯一的正式桌宠渲染进程，Tauri/Vue 只负责配置资源、选择动作和控制
桌宠进程。Canvas 只保留在调试界面中作为资源预览，不再创建旧的 Tauri `pet`
桌宠窗口。

## 当前能力

- 使用 Windows 免安装版 Godot。
- 透明、无边框、置顶窗口。
- 左键拖动窗口。
- 根据 manifest 驱动资源包播放动作；每个动作可以绑定独立的 SpriteSheet，
  播放器会缓存已加载的纹理，缺失动作或纹理时回退到 `idle`。
- 默认角色的 `idle` 使用 32 帧待机资源；从待机切换到前右行走时，会先播放
  `transition-idle-to-walk-front-right` 的 16 帧非循环过渡，再进入
  `walk-front-right` 循环动作。
- 按数字键 `1` 至 `5` 可切换测试动作，按 `6` 可验证缺失动作回退到 `idle`。
- 按 `F1` 至 `F6` 可在 Godot 窗口中依次检查向左、向右、前左、前右、后左、后右
  的六个行走动作。它们当前只用于资源播放校验，自动移动逻辑将在后续独立实现。
- 鼠标滚轮调整桌宠窗口大小，范围为 120px 至 480px；拖动结束后会自动吸附到
  附近的屏幕边缘。
- 跳过测试精灵图中已确认的第 25 格空白帧。
- 在 Tauri 调试界面点击“同步到 Godot”后，Godot 会检测并加载
  `%LOCALAPPDATA%\LingMengDesktopPet\godot-resource-package\manifest.json`；资源图会
  与清单一同写入该受控目录，原有测试资源保留为同步前的回退。
- Tauri 调试界面的动作、口型和暂停状态会写入同目录的 `preview.json`，Godot
  以低延迟轮询方式应用这些状态，不依赖前端窗口事件。
- FastAPI 的 Agent 回复会通过 `WS /api/pet/events` 驱动 Godot 的结构化动作；
  TTS 播放期间，调试界面通过 `preview.json` 同步 `speaking` 和三档嘴型，
  播放结束后恢复 `idle` 与闭合口型。

## 启动

在项目根目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run-godot-pet.ps1
```

启动编辑器：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run-godot-pet.ps1 -Editor
```

## 验收检查

1. 桌面上仅看到角色像素，不出现黑色方形底色。
2. 左键按住角色窗口后可以移动。
3. 窗口始终位于普通应用窗口上方。
4. 待机动作连续循环，不短暂显示透明空帧。
5. 通过调试界面的“打开桌宠/关闭桌宠”可以启动和销毁 Godot 进程。
6. 安装包启动后，主界面标题显示“灵梦桌宠”，点击“打开桌宠”
   后 Godot 运行时和 `pet_client` 项目可以从应用资源目录正常找到。

## 当前边界

本阶段已完成多动作、多 SpriteSheet manifest 的 Godot 读取、纹理缓存、动作
锚点、idle 回退，以及 Tauri 调试界面到 Godot 的本地预览状态同步。Agent 动作
事件和 TTS 播放生命周期已经接入 Godot；RAG、桌面工具和身份逻辑仍由前端/本地
网关负责，不直接让 Godot 执行业务或系统操作。
