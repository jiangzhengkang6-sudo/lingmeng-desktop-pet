# -*- mode: python ; coding: utf-8 -*-
"""
桌面网关唯一打包入口（迭代方案 P2-1：收敛双轨制）。

scripts/build-gateway.ps1 必须通过本 spec 打包，不再在命令行使用
--collect-all，避免“改了 spec 不生效”和无关依赖被整包收入。

精简策略：
- pymilvus 保留 collect_all（grpc/动态依赖较多，宁可保守）；
- LangGraph 及其 SDK 保留 collect_all，避免状态图、序列化和动态导入遗漏；
- 身份识别走 OpenCV YuNet + SFace（P1-2 标定后切换），不再打包 mediapipe；
- cv2 不 collect_all：人脸链路只用 imdecode/DNN，交给 PyInstaller 官方
  hook，并剔除视频编解码 ffmpeg 动态库（约 29MB，图片识别不需要）；
- 排除 matplotlib/PIL/tkinter/mediapipe/sounddevice 等无人脸链路使用的重依赖；
- pandas 不能排除：当前 pymilvus 初始化阶段会导入 pandas。

模型文件（YuNet/SFace ONNX）与 .env.example 由 build-gateway.ps1 复制到
exe 同目录，不写进 datas，保证线上布局与开发解析路径一致。
"""
import os

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []

# pymilvus 依赖链复杂（grpc、各类动态库），保持整包收集。
tmp_ret = collect_all("pymilvus")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

for package_name in ("langgraph", "langgraph_sdk", "sqlite_vec"):
    tmp_ret = collect_all(package_name)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

hiddenimports += [
    "aiosqlite",
]

excludes = [
    "matplotlib",
    "PIL",
    "tkinter",
    "mediapipe",
    "sounddevice",
]


a = Analysis(
    [os.path.join(SPECPATH, "gateway_entry.py")],
    # SPECPATH 是 backend/，项目根是其上一级（backend.app.* 的导入根）。
    pathex=[os.path.dirname(os.path.dirname(SPECPATH))],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

# 剔除 OpenCV 视频编解码库：本地人脸链路只做图片识别，不需要 29MB 的 ffmpeg。
a.binaries = [
    entry for entry in a.binaries
    if "videoio_ffmpeg" not in os.path.basename(entry[0]).lower()
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="desktop-pet-gateway",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="desktop-pet-gateway",
)
