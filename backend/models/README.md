# 人脸模型目录

本目录的模型文件是大型二进制，**不纳入 Git**，请通过脚本下载：

```powershell
# 在项目根目录执行
python scripts/download_face_models.py
```

身份识别链路（P1-2 起）使用：

| 文件 | 用途 | 来源 |
|---|---|---|
| `face_detection_yunet_2023mar.onnx` | YuNet 人脸检测（提供对齐关键点） | opencv_zoo（Apache-2.0） |
| `face_recognition_sface_2021dec.onnx` | SFace 128 维身份嵌入 | opencv_zoo（Apache-2.0） |

`face_landmarker.task`（MediaPipe）为旧的几何关键点方案，实测无身份区分度，
身份认证已不再使用；仅在未来做实时表情/注意力感知时才需要，默认打包不含它。
