# RTC 声纹 RTS live 验收交接（2026-09-13）

## 当前结论

- 本地已补齐火山官方 RTS HTTP 回调链路：POST/GET `/api/identity/rtc/rts/messages`。
- 支持官方外层 `{message, signature}`、Base64、`subv/stat` 二进制帧；`stat` 不授权，完整真人 `subv` 字幕才进入身份判定。
- StartVoiceChat 运行时注入 `ServerMessageURLForRTS`、`ServerMessageSignatureForRTS`、`EnableConversationStateCallback=true`、`SubtitleConfig.SubtitleMode=0`。
- 新增受限公网代理脚本 `scripts/rts_public_proxy.py`，Cloudflare Quick Tunnel 只放行 RTS 路径。
- 旧 JSONL worker 保留给离线脱敏样本，不能作为 live 验收。

## 已验证

- StartVoiceChat 与 StopVoiceChat 成功。
- Cloudflare GET/POST 隧道到本地成功；错误签名返回 401；非 RTS 路径公网 404。
- 前端 92 项测试、后端 127 项测试、前端构建、diff 检查通过。
- live 未完成：真人 RTC 客户端未入房/未产生 subv POST。阻塞点是客户端 Token/AppKey，不是本地回调代码。

## 仍需

- 在 Full access/Computer Use 的新 Codex 桌面线程中操作火山控制台，或由用户提供 RTC AppKey 到本地 .env（不要发到聊天）。
- 临时 Token 参数：RoomId=`desktop-pet-identity`，UserId=`desktop-owner`，需发布麦克风和订阅音频权限。
- 重启本地服务/隧道后继续：启动 live 会话 -> 官方客户端入房说话 -> 等待 RTS subv -> owner_verified/guest -> 停止会话与旧回调重放检查。

## 本轮代码/文档位置

- `backend/app/rtc_rts.py`
- `backend/app/main.py`
- `backend/app/volcengine_rtc.py`
- `scripts/rts_public_proxy.py`
- `scripts/verify_rtc_voiceprint_e2e.py`
- `docs/智能体声纹配置与验收指南.md`
- `backend/README.md`
