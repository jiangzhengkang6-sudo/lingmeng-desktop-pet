# LangGraph 渐进式迭代手动验收清单

验收日期：2026-11-02  
适用版本：LangGraph 主工作流、SQLite 检查点、`open_file` 审批中断图。

## 一、验收原则

- 默认配置必须保持旧链路可用；
- 所有新能力必须显式开关启用；
- HTTP 和 WebSocket 响应契约不能破坏；
- 模型不能直接执行桌面操作；
- 审批、授权目录、主人身份和审计仍由原安全模块负责；
- 任一阶段异常时可切回旧链路。

## 二、自动化基线

| 项目 | 命令 | 结果 |
|---|---|---|
| 后端测试 | `python -m pytest backend/tests -q` | 196 个全部通过 |
| 前端测试 | `npm test` | 76 个文件、279 个测试全部通过 |
| 前端构建 | `npm run build` | 构建成功，仅有原有 chunk 提示 |
| 网关打包 | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-gateway.ps1` | 打包成功，1133 个文件、248.4 MB |
| 完整桌宠安装包 | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-desktop.ps1` | 打包成功；已安装到 `C:\Program Files\灵梦桌宠` |

## 三、默认旧链路验收

配置：

```env
AGENT_WORKFLOW_ENGINE=legacy
LANGGRAPH_CHECKPOINT_ENABLED=false
LANGGRAPH_APPROVAL_INTERRUPT_ENABLED=false
```

| 编号 | 验收项 | 预期结果 | 结果 |
|---|---|---|---|
| L-01 | 启动网关 | `/api/health` 返回 200 | 待验收 |
| L-02 | 提交文字消息 | 响应结构与旧版本一致 | 待验收 |
| L-03 | 提交语音时间请求 | 原语音路径正常 | 待验收 |
| L-04 | 提交 `open_file` | 原审批接口正常 | 待验收 |
| L-05 | 检查数据目录 | 不生成 LangGraph SQLite 检查点 | 待验收 |

## 四、LangGraph 主工作流验收

配置：

```env
AGENT_WORKFLOW_ENGINE=langgraph
LANGGRAPH_CHECKPOINT_ENABLED=false
```

| 编号 | 验收项 | 预期结果 | 结果 |
|---|---|---|---|
| G-01 | Mock 文字请求 | 返回正常 `AgentResponse` | 自动化覆盖 |
| G-02 | 远程模型请求 | 正常调用远程提供方 | 待手动验收 |
| G-03 | 远程模型超时 | 按配置降级或显式报错 | 自动化覆盖 |
| G-04 | 不支持的提供方 | 按配置降级或返回 503 | 自动化覆盖 |
| G-05 | 语音时间请求 | 命中 `get_time` 并返回成功 | 自动化覆盖 |
| G-06 | 语音白名单应用 | 只能打开已登记应用 | 自动化覆盖 |
| G-07 | 未验证主人身份 | 工具请求返回可朗读失败 | 自动化覆盖 |
| G-08 | 语音空闲响应 | 转换为可朗读动作和口型 | 自动化覆盖 |

## 五、SQLite 检查点验收

配置：

```env
AGENT_WORKFLOW_ENGINE=langgraph
LANGGRAPH_CHECKPOINT_ENABLED=true
```

| 编号 | 验收项 | 预期结果 | 结果 |
|---|---|---|---|
| C-01 | 首次请求后检查路径 | 自动创建检查点数据库 | 自动化覆盖 |
| C-02 | 查询检查点摘要 | 返回路径、大小、线程数、检查点数 | 自动化覆盖 |
| C-03 | 包含运行时状态 | 已完成线程 `pending=false` | 自动化覆盖 |
| C-04 | 待审批线程 | `pending=true`，默认清理时保留 | 自动化覆盖 |
| C-05 | 默认清理 | 仅删除已完成线程 | 自动化覆盖 |
| C-06 | 强制清空 | 必须传 `confirm=DELETE_ALL` | 自动化覆盖 |
| C-07 | 关闭网关 | 检查点连接正常释放 | 自动化覆盖 |

## 六、`open_file` 审批中断验收

配置：

```env
LANGGRAPH_APPROVAL_INTERRUPT_ENABLED=true
```

| 编号 | 验收项 | 预期结果 | 结果 |
|---|---|---|---|
| A-01 | 请求授权目录内文件 | 返回 `pending` | 自动化覆盖 |
| A-02 | 请求授权目录外文件 | 被授权目录校验拒绝 | 待手动验收 |
| A-03 | 未验证主人身份 | 返回主人验证错误 | 自动化覆盖 |
| A-04 | 批准请求 | 仅打开一次目标文件 | 最新打包冒烟通过 |
| A-05 | 拒绝请求 | 状态为 `rejected`，不打开文件 | 打包冒烟通过 |
| A-06 | 审批后重复批准/拒绝 | 返回 409，不重复执行 | 自动化/打包冒烟覆盖 |
| A-07 | 相同幂等键重复发起 | 复用调用标识、审批单和审计记录 | 自动化覆盖 |
| A-08 | 不同幂等键 | 创建独立审批线程 | 待手动验收 |
| A-09 | 内存检查点重启后恢复 | 回退原审批方法，审批单仍可处理 | 自动化覆盖 |

## 七、RAG 与降级验收

| 编号 | 验收项 | 预期结果 | 结果 |
|---|---|---|---|
| R-01 | 有 RAG 命中 | 响应包含来源元数据 | 待手动验收 |
| R-02 | RAG 超时 | 不阻塞主响应，状态明确 | 待手动验收 |
| R-03 | 未验证主人身份 | 不读取私有记忆 | 自动化覆盖 |
| R-04 | 远程模型失败且允许 Mock | 返回本地降级应答 | 自动化覆盖 |
| R-05 | 远程模型失败且要求远程 | 返回明确错误，不写入会话历史 | 自动化覆盖 |

## 八、SQLite Vec 本地知识库验收

配置：

```env
RAG_STORE=sqlite-vec
```

| 编号 | 验收项 | 预期结果 | 结果 |
|---|---|---|---|
| V-01 | 健康检查 | `/api/rag/health` 返回 `ok=true`、`store=sqlite-vec` | 待手动验收 |
| V-02 | 数据文件隔离 | 生成独立 `rag.sqlite3`，不写入 `desktop-pet.sqlite3` | 自动化覆盖 |
| V-03 | 上传 Markdown | 文档、分块和向量写入成功 | 自动化覆盖 |
| V-04 | 相似度检索 | 返回正确正文、来源标签和相似度分数 | 自动化覆盖 |
| V-05 | 集合隔离 | `character_knowledge` 与 `user_documents` 不串数据 | 自动化覆盖 |
| V-06 | 内容去重 | 相同内容重复上传只保留一个文档 | 自动化覆盖 |
| V-07 | 删除文档 | 文档列表、分块和向量同步删除 | 自动化覆盖 |
| V-08 | 重启恢复 | 重新打开桌宠后仍可检索已有文档 | 自动化覆盖 |
| V-09 | 维度变化 | 已存在数据库维度不一致时返回明确配置错误 | 自动化覆盖 |
| V-10 | 回滚 Milvus | 设置 `RAG_STORE=milvus` 后仍走旧链路 | 待手动验收 |

## 九、HTTP 与 WebSocket 契约验收

| 编号 | 验收项 | 预期结果 | 结果 |
|---|---|---|---|
| W-01 | `/api/agent/chat` | 请求和响应字段保持兼容 | 待手动验收 |
| W-02 | `/api/tools/execute` | 不传幂等键时请求体兼容 | 自动化覆盖 |
| W-03 | 工具审批接口 | 返回 `ToolCallResult` | 自动化覆盖 |
| W-04 | 桌宠事件 WebSocket | 动作、情绪、口型事件正常 | 待手动验收 |
| W-05 | 错误响应 | 保持 `{code,message}` 结构 | 自动化覆盖 |

## 十、回滚验收

| 编号 | 验收项 | 预期结果 | 结果 |
|---|---|---|---|
| B-01 | 设置 `AGENT_WORKFLOW_ENGINE=legacy` | 立即恢复旧链路 | 自动化覆盖 |
| B-02 | 设置 `LANGGRAPH_APPROVAL_INTERRUPT_ENABLED=false` | 工具审批恢复旧接口 | 自动化覆盖 |
| B-03 | 设置 `LANGGRAPH_CHECKPOINT_ENABLED=false` | 使用内存检查点 | 自动化覆盖 |
| B-04 | 设置 `RAG_STORE=milvus` | RAG 恢复旧 Milvus 链路 | 待手动验收 |
| B-05 | 使用迭代前备份 | 可完整回退到接入前状态 | 备份已保留 |

## 十一、验收结论

全部标为“自动化覆盖”或“待手动验收/待打包冒烟”的项目完成，并确认无回归后，才能将 LangGraph 设为默认路径。旧链路至少保留一个稳定观察周期，确认无问题后再删除。
