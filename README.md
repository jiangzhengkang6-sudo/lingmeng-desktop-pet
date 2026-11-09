# 灵梦桌宠

**灵梦桌宠**是一个 Windows 桌面 AI 桌宠项目，包含可视化控制台、本地 FastAPI 网关、Godot 桌宠渲染窗口，以及语音、RAG、长期记忆、人格配置和受控工具能力。

项目采用渐进式迭代：保留原有稳定链路，同时逐步将复杂工作流迁移到 LangGraph。

> 当前打包与验证主要面向 Windows 10/11 x64。

## 功能概览

- Vue 3 + TypeScript + Vite 控制台；
- Tauri 2 桌面壳与 NSIS 安装包；
- Godot 透明桌宠窗口，支持待机、行走、聆听、思考、说话、害羞和不悦等动作；
- FastAPI 本地网关，第三方服务密钥只保存在服务端；
- MiniMax TTS、豆包 ASR、Qwen/OpenAI 兼容文本模型；
- 三语唤醒词门控：`米娅 / ミーア / Miya`；
- 唤醒后 30 秒内可连续追问，无需每句话重复唤醒词；
- 人格配置热更新，并自动隔离旧人格的短期会话历史；
- 本地长期记忆与待确认记忆；
- RAG 文档检索，支持 sqlite-vec；Milvus 作为可选的大规模向量数据库方案；
- 受控工具、工具审批和审计记录；
- 人脸/声纹相关身份能力。

## 技术栈

| 模块 | 技术 |
| --- | --- |
| 前端控制台 | Vue 3、TypeScript、Vite |
| 桌面壳 | Tauri 2、Rust、NSIS |
| 本地网关 | FastAPI、Uvicorn、Pydantic |
| 桌宠渲染 | Godot 4.x |
| 工作流 | 原顺序链路 + LangGraph 渐进迁移 |
| 向量检索 | sqlite-vec，可选 Milvus |
| 语音能力 | MiniMax TTS、豆包 ASR |

## 目录结构

```text
.
├── src/             # Vue 前端、语音/RAG/身份等客户端
├── backend/         # FastAPI 网关与服务逻辑
├── godot/           # Godot 桌宠工程
├── src-tauri/       # Tauri/Rust 桌面壳
├── scripts/         # 构建、下载、验证和运维脚本
├── infra/           # Docker 等基础设施配置
└── docs/            # 项目文档
```

## 环境要求

- Windows 10/11 x64；
- Node.js 20 或更高版本；
- Python 3.12（人脸相关依赖暂不推荐 Python 3.13）；
- Rust Stable（Tauri 桌面开发/构建需要）；
- Docker Desktop 仅在使用 Milvus 等容器服务时需要。

## 快速开始

### 1. 获取前端依赖

```powershell
npm install
```

### 2. 准备 Python 环境

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```
### 3. 配置环境变量

复制服务端示例配置：

```powershell
Copy-Item .env.example .env
```

在 `.env` 中填入你自己的服务地址和密钥。示例：

```env
SPEECH_API_KEY=你的 MiniMax Key
AGENT_PROVIDER=qwen
AGENT_API_BASE_URL=https://your-openai-compatible-endpoint/v1
AGENT_API_KEY=你的文本模型 Key
DOUBAO_API_KEY=你的豆包 Key
```

复制前端示例配置：

```powershell
Copy-Item .env.frontend.example .env.frontend
```

前端配置只允许保存本地网关地址和功能开关，**不要把第三方密钥放进 `VITE_` 变量**。

### 4. 下载人脸识别模型

```powershell
python scripts/download_face_models.py
```

模型文件默认下载到 `backend/models/`，不会提交到 Git。

### 5. 启动本地网关

```powershell
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

### 6. 启动前端

```powershell
npm run dev
```

浏览器访问：

```text
http://127.0.0.1:5174
```

也可以使用 Tauri 开发模式：

```powershell
npm run desktop:dev
```

## 桌面打包

项目路径包含特殊字符，打包请统一使用项目脚本：

```powershell
npm run desktop:build
```

脚本会依次完成：

1. PyInstaller 网关构建；
2. ASCII 盘符映射；
3. Tauri NSIS 安装包构建。

安装包输出路径通常为：

```text
src-tauri/.tauri-target-user/release/bundle/nsis/
```

## 配置说明

| 配置 | 说明 |
| --- | --- |
| `.env` | 服务端密钥、模型、数据库和网关配置，已被 Git 忽略 |
| `.env.frontend` | 浏览器端本地网关地址和功能开关，已被 Git 忽略 |
| `.env.example` | 服务端安全示例，不包含真实密钥 |
| `.env.frontend.example` | 前端示例配置 |

### RAG 存储

- 轻量本地使用可设置 `RAG_STORE=sqlite-vec`；
- 需要大规模向量检索时可选择 Milvus，并通过 `infra/milvus/docker-compose.yml` 启动；
- RAG 文档在系统中作为“不可信参考资料”处理，只能提供事实上下文，不能覆盖系统规则或执行指令。

## 本地数据

桌面运行时数据默认位于：

```text
C:\Users\<用户名>\AppData\Local\LingMengDesktopPet\
```

其中通常包含：

- `data/desktop-pet.sqlite3`：人格配置、长期记忆和本地状态；
- `data/rag.sqlite3`：本地 RAG 文档与向量；
- `logs/gateway.log`：本地网关日志；
- `godot-resource-package/`：同步给 Godot 的资源包。

这些本地数据不会提交到 Git。

## 测试

前端测试：

```powershell
npm test
```

前端生产构建：

```powershell
npm run build
```

后端测试：

```powershell
python -m pytest backend/tests
```

## 安全注意事项

- 永远不要提交 `.env`、真实 API Key、Cookie、访问令牌或私有数据库；
- 不要把服务端密钥写入 `VITE_` 前端变量；
- 本地网关默认监听 `127.0.0.1`，不要在未增加认证的情况下暴露到公网；
- 上传到 RAG 的文档只作为数据处理，不作为指令执行；
- 长期记忆内容需要用户确认，敏感信息不应保存；
- 如果密钥曾被提交到 Git，即使后续删除，也应立即轮换密钥并清理 Git 历史；
- 安全问题请勿在公开 Issue 中贴出密钥或完整日志，建议通过 GitHub 的私密漏洞报告功能联系维护者。

## 开源许可

本项目代码基于 [MIT License](LICENSE) 开源。

项目中涉及的第三方素材、角色形象、声音模型或其他资源，其权利归原权利人所有。若权利人认为资源存在侵权问题，请联系维护者处理。

