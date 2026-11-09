# SQLite Vec 本地知识库迭代记录

更新日期：2026-11-02

## 1. 迭代目标

本次迭代在不破坏现有 Milvus RAG 链路的前提下，新增一套可随桌宠本地运行的 `sqlite-vec` 知识库：

- 默认继续使用 Milvus，保证旧版本行为可回滚；
- 通过 `RAG_STORE=sqlite-vec` 显式启用本地向量库；
- RAG 文档元数据和向量使用独立的 `rag.sqlite3`；
- 不混入现有 `desktop-pet.sqlite3` 记忆、人格和本地状态库；
- 保持 `RagService` 上层接口不变，避免影响 HTTP/WebSocket、Agent 引用检索和前端页面。

## 2. 数据库文件边界

本地运行时数据按职责拆分为：

| 文件 | 职责 |
| --- | --- |
| `desktop-pet.sqlite3` | 长期记忆、人格、本地设置、工具和业务状态 |
| `rag.sqlite3` | RAG 文档元数据、文档分块和 `sqlite-vec` 向量 |
| `langgraph-checkpoints.sqlite3` | LangGraph 会话检查点与审批恢复状态 |

默认位置由桌面运行时的数据目录决定；开发环境默认位于：

```text
backend/data/rag.sqlite3
```

也可以通过环境变量覆盖：

```env
RAG_SQLITE_PATH=/path/to/rag.sqlite3
```

## 3. 配置方式

迁移期间支持两种存储：

```env
# 保留旧链路，默认值
RAG_STORE=milvus

# 启用本地 sqlite-vec
RAG_STORE=sqlite-vec
```

相关配置：

```env
RAG_STORE=sqlite-vec
RAG_SQLITE_PATH=
RAG_TIMEOUT_SECONDS=10
RAG_EMBEDDING_PROVIDER=hash
RAG_EMBEDDING_MODEL=local-hash-v1
RAG_EMBEDDING_DIMENSION=384
```

未知的 `RAG_STORE` 值会回退为 `milvus`，避免错误配置导致启动时出现未知存储行为。

## 4. `rag.sqlite3` 表结构

### 4.1 普通 SQLite 表

`documents` 保存文档级元数据：

- `collection`
- `document_id`
- `filename`
- `source_label`
- `content_hash`
- `chunk_count`
- `updated_at`

`chunks` 保存文档分块和正文：

- SQLite 自增 `rowid`
- `collection`
- `document_id`
- `chunk_id`
- `chunk_index`
- `content`
- `content_hash`
- `updated_at`

`rag_metadata` 保存本地向量库自身的元信息，例如：

- `embedding_dimension`

如果已有数据库记录的向量维度与当前 `RAG_EMBEDDING_DIMENSION` 不一致，服务会返回明确的配置错误，避免把不同维度的向量写入同一张向量表。

### 4.2 sqlite-vec 虚拟表

每个知识集合使用一张独立向量表：

| 集合 | 向量表 |
| --- | --- |
| `character_knowledge` | `rag_vec_character_knowledge` |
| `user_documents` | `rag_vec_user_documents` |

向量表通过 `chunks.rowid` 与普通分块表关联，使用余弦距离检索；接口返回时转换为“分数越高越相似”的形式。

## 5. 已实现能力

`SqliteVecRagStore` 已实现与 Milvus 存储相同的核心协议：

- 健康检查；
- 文档写入；
- 文档分块向量写入；
- 相似度检索；
- 按文档 ID 删除；
- 文档列表；
- 按内容哈希查重；
- 网关重启后从独立数据库恢复；
- 不同知识集合之间的数据隔离。

上层 `RagService` 负责继续复用原有逻辑：

- UTF-8 文本/Markdown 解码；
- 文件大小限制；
- 文档分块；
- embedding 生成；
- 内容哈希去重；
- UUID 文档 ID；
- RAG API 响应模型。

## 6. 与 Milvus 的切换和回滚

启用本地库：

```env
RAG_STORE=sqlite-vec
```

回滚旧链路：

```env
RAG_STORE=milvus
RAG_MILVUS_URI=http://127.0.0.1:19530
```

当前阶段不自动迁移 Milvus 中已有文档。原因是：

- 现有本地数据规模较小；
- 自动迁移需要同时处理 Milvus 分页、正文完整性和 embedding 维度；
- 直接重新上传 Markdown/TXT 更简单、可验证；
- 避免在第一次双轨迭代中误改 Milvus 数据。

后续如果确认需要迁移，可单独增加只读迁移工具，在备份 Milvus 和 `rag.sqlite3` 后执行。

## 7. 打包注意事项

`sqlite-vec` 除 Python 模块外还依赖随包分发的 `vec0.dll`。打包配置已改为整包收集：

```python
collect_all("sqlite_vec")
```

不能只把 `sqlite_vec` 放入 `hiddenimports`，否则可能出现 Python 模块存在、SQLite 扩展动态库缺失的问题。

## 8. 验收建议

启用 `RAG_STORE=sqlite-vec` 后，至少验证：

1. `GET /api/rag/health` 返回 `ok=true` 且 `store=sqlite-vec`；
2. 首次启动时未写入文档的集合显示为 `false`；
3. 向角色知识集合上传 Markdown 后，该集合显示为 `true`；
4. 重复上传相同内容不会产生重复文档；
5. 检索能够返回正确片段和来源标签；
6. `character_knowledge` 与 `user_documents` 不串数据；
7. 删除文档后检索结果和文档列表同步消失；
8. 重启桌宠后文档仍可检索；
9. `desktop-pet.sqlite3` 中没有 RAG 向量表；
10. 切回 `RAG_STORE=milvus` 后旧链路仍可使用。

## 9. 当前阶段结论

当前代码已经具备双轨能力，但默认值仍保持 `milvus`。建议在本机使用 `RAG_STORE=sqlite-vec` 完成真实文档验收，并观察一个版本周期；确认稳定后，再考虑把默认存储切换为 `sqlite-vec`。
