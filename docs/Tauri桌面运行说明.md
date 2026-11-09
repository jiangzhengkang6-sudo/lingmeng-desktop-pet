# Tauri 桌面运行

项目使用 Tauri v2 作为调试界面桌面壳，前端由 Vue + Vite 提供；正式桌宠窗口由
随应用打包的 Godot 进程负责。Tauri 不再创建独立的 `pet` WebView 窗口。

## 本地开发

先安装 Rust、Visual Studio Build Tools 的 MSVC 组件和 WebView2，然后在项目目录执行：

```powershell
npm install
npm run desktop:dev
```

开发窗口会使用 `http://127.0.0.1:5174` 的 Vite 服务。

## 构建 Windows 安装包

```powershell
npm run desktop:build
```

构建结果位于 `src-tauri/.tauri-target-user/release/bundle/msi/`。构建脚本会先构建本地网关，再临时映射 ASCII 盘符，以避开 WiX 对当前项目目录特殊字符的兼容问题，随后自动清理该映射。

## 语音网关

桌面调试界面通过本地 FastAPI 网关访问语音服务。安装包启动时会自动启动网关；
退出应用时会结束由它启动的网关进程。若 8000 端口已存在可用网关，应用只复用它，
不会结束外部进程。

开发环境的 API 密钥只放在项目根目录 `.env`，不要放入前端环境文件。安装版不会
携带该文件：首次启动会将随包提供的 `.env.example` 复制为
`%LOCALAPPDATA%\LingMengDesktopPet\.env`，由用户在该位置填写密钥。SQLite
等本地运行数据保存在同一目录下的 `data`，不会写入安装目录。

服务端 `.env` 的 `CORS_ORIGINS` 需要包含 `http://tauri.localhost`；示例配置已包含
该来源。

为确保退出时能可靠回收网关，发布版使用 PyInstaller 的目录式运行时。不要将
`backend/dist/desktop-pet-gateway/` 手动替换为 onefile 单文件可执行文件。

## Godot 桌宠

安装包启动后，主界面的“打开桌宠”按钮会启动随应用提供的 Godot 运行时和
`pet_client` 项目；“关闭桌宠”会结束该 Godot 进程。主界面的 Canvas 只用于
资源配置和动作调试预览，不是正式桌宠窗口。

请确认使用最新生成的 MSI 安装包。旧版本可能仍显示 `Canvas Pet Lab`，也不会
反映当前 Godot 唯一运行路径。
