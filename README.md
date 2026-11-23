# 企业 AI 知识库助手

面向企业内部资料与合同审核的一站式知识助手。覆盖四类核心场景：企业制度问答、信息系统答疑、合同审核辅助、运营资料查询。前端 React + TypeScript，后端 FastAPI + SQLite，默认离线可运行；配置 OpenAI 兼容接口后可切换真实大模型与向量模型。

## 功能概览

- **制度问答 / 系统答疑 / 运营资料查询**：自然语言提问，混合检索企业文档，基于原文生成答案，并展示来源文档、所属章节、页码与可定位原文。
- **合同审核辅助**：上传合同后自动切片识别条款、抽取关键字段，按企业合同规范执行规则校验，输出风险分级；支持逐项处置与人工复核（通过 / 退回修改 / 拒绝），存在未处置高风险时禁止直接通过。
- **知识库管理**：知识库与文档上传、解析（PDF / DOCX / TXT / Markdown）、切片、向量化、重建索引、删除；支持指定知识库范围提问。
- **身份与权限**：管理员 / 人事 / 财务 / 法务 / 普通员工五种角色；知识库 `public / internal / restricted` 三级可见性，可对用户、角色、部门单独授权读写。
- **可追溯**：答案引用可点击查看原文，并高亮对应片段；合同审核全流程记录审计日志。

## 快速开始

环境要求：Python 3.10+、Node.js 18+（仅首次构建前端需要）。

```bash
# 一键启动（首次会自动安装依赖并构建前端）
./start.sh            # 默认 8000 端口
./start.sh 8080       # 指定端口
```

启动后访问 <http://127.0.0.1:8000>。首次启动会自动创建数据库并写入演示数据（5 个用户、5 个知识库、制度文档、15 条合同审核规则、1 份高风险示例合同）。

### 演示账号

| 账号 | 密码 | 角色 | 可见范围 |
| --- | --- | --- | --- |
| `admin` | `admin123` | 系统管理员 | 全部知识库、全部合同、规则管理、用户管理 |
| `hr` | `hr123` | 人事 | 全部门制度库（可写人力资源库） |
| `fin` | `fin123` | 财务 | 制度库 + 合同库只读 |
| `legal` | `legal123` | 法务 | 全部知识库（可写合同规范库）、合同复核 |
| `emp` | `emp123` | 普通员工 | 公共/内部知识库，看不到受限的法务库与合同 |

### 开发模式

```bash
# 后端
cd backend && python -m uvicorn app.main:app --reload --port 8000

# 前端（另开终端，Vite 会代理 /api 到 8000）
cd frontend && npm install && npm run dev
```

## 目录结构

```
backend/
  app/
    main.py            # FastAPI 入口、静态资源与 SPA 托管
    config.py          # 环境变量配置
    models.py          # 用户/知识库/文档/切片/会话/合同/规则等模型
    security.py        # JWT 认证与角色校验
    seed.py            # 演示数据
    routers/           # auth / kb / chat / contracts / admin
    services/
      parser.py        # PDF/DOCX/TXT/MD 解析，保留页码
      chunker.py       # 标题感知切片，保留章节与字符偏移
      embedding.py     # OpenAI 兼容向量 / 本地哈希向量兜底
      retrieval.py     # BM25 + 向量混合检索
      llm.py           # 流式回答与本地抽取式兜底
      contracts.py     # 条款抽取、字段抽取、规则引擎、风险评分
      permissions.py   # 知识库与合同权限
      ingestion.py     # 文档入库与删除
frontend/
  src/
    pages/             # 登录 / 问答 / 知识库 / 合同列表与详情 / 管理
    components/        # 布局、富文本引用、原文抽屉、弹窗
    api.ts, auth.tsx, types.ts, styles.css
start.sh               # 一键启动
```

## 技术方案

### RAG 流程

1. **解析**：PDF 使用 pypdf，DOCX 使用 python-docx，纯文本直接读取；保留页码用于来源定位。
2. **切片**：按 Markdown / 中文标题层级切节，再按约 480 字聚合，重叠 80 字；每个切片记录章节路径与原文起止字符偏移。
3. **向量化**：配置 `EMBEDDING_BASE_URL` 时调用 OpenAI 兼容 `/embeddings`；否则使用本地 512 维哈希向量（jieba 分词 + 字符二元组 + 有符号哈希），完全离线可用。
4. **检索**：BM25 与向量余弦归一化融合；本地向量模式下以 BM25 为主，真实向量模式下提高语义权重；每篇文档最多保留 2 个切片，过滤明显低分结果。
5. **生成**：配置 `LLM_BASE_URL` 时流式调用大模型，并强制只依据参考资料作答、使用 `[n]` 标注来源；未配置时使用本地抽取式回答，保证离线演示可用。
6. **引用**：返回文档标题、知识库、章节、页码、片段及字符区间，前端可打开原文抽屉并高亮定位。

### 合同审核流程

1. **上传**：PDF/DOCX/TXT/MD，限制 25MB，解析失败或正文过少会拒绝。
2. **结构化抽取**：按标题切分条款，关键词分类到 10 类条款（主体、标的、价款、期限、违约、保密、争议、验收、知识产权、终止）；正则抽取金额、账期、违约金比例、预付比例、合同编号、相对方、签署日期；配置 LLM 时追加结构化 JSON 抽取。
3. **规则校验**：数据库驱动的规则引擎，支持 `required_clause`、`keyword_any`、`keyword_none`、`max_number`、`min_number`、`clause_keyword_none` 六种规则类型；演示内置 15 条企业合同规范。
4. **风险评分**：高风险 30 分、中风险 15 分、低风险 5 分，累计封顶 100；输出高 / 中 / 低风险等级与摘要。
5. **人工复核**：法务或管理员可对每项风险标记「接受 / 已修复 / 忽略」并填写说明；提交复核时支持通过、退回修改、拒绝，存在未处置高风险时禁止通过，退回或拒绝必须填写意见。全流程写入审计日志。

## API 摘要

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/login` | 登录获取 JWT |
| GET | `/api/auth/me` | 当前用户信息 |
| GET/POST | `/api/kbs` | 知识库列表 / 创建 |
| PATCH/DELETE | `/api/kbs/{id}` | 更新 / 删除知识库 |
| GET/POST | `/api/kbs/{id}/documents` | 文档列表 / 上传（自动解析切片向量化） |
| DELETE | `/api/documents/{id}` | 删除文档及其切片 |
| POST | `/api/documents/{id}/reindex` | 重建索引 |
| GET | `/api/documents/{id}/text` | 获取原文（来源定位） |
| GET/POST/DELETE | `/api/kbs/{id}/permissions` | 权限查看 / 授权 / 撤销 |
| POST | `/api/chat/ask` | 同步问答 |
| POST | `/api/chat/stream` | SSE 流式问答（`meta/citations/token/done`） |
| GET/DELETE | `/api/conversations[/{id}]` | 会话历史 |
| POST/GET | `/api/contracts` | 上传合同 / 合同列表 |
| GET | `/api/contracts/{id}` | 合同详情（条款、风险、复核记录） |
| POST | `/api/contracts/{id}/reanalyze` | 重新分析 |
| PATCH | `/api/contracts/{id}/risks/{risk_id}` | 处置风险项 |
| POST | `/api/contracts/{id}/review` | 提交复核结论 |
| GET/POST/PATCH | `/api/rules[/{id}]` | 审核规则管理 |
| GET/POST/PATCH | `/api/admin/users[/{id}]` | 用户管理（管理员） |
| GET | `/api/admin/audit` | 审计日志 |
| GET | `/api/system/status` | 模型模式与数据统计 |

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATA_DIR` | `backend/data` | 数据目录（数据库、上传文件、解析文本） |
| `DB_PATH` | `DATA_DIR/app.db` | SQLite 路径 |
| `SECRET_KEY` | 自动生成并持久化 | JWT 密钥 |
| `TOKEN_TTL_HOURS` | `12` | 登录有效期 |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | 空 / 空 / `gpt-4o-mini` | OpenAI 兼容对话接口；`LLM_API_KEY` 可留空（Ollama 等本地服务），`LLM_BASE_URL` 留空则使用本地回答 |
| `LLM_TIMEOUT` | `300` | 大模型请求超时（秒），本地 CPU 推理可适当调大 |
| `EMBEDDING_BASE_URL` / `EMBEDDING_API_KEY` / `EMBEDDING_MODEL` | 跟随 LLM | 向量接口；留空使用本地向量 |
| `EMBEDDING_DIM` | `512` | 本地哈希向量维度 |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `480` / `80` | 切片长度与重叠 |
| `RETRIEVAL_TOP_K` | `6` | 检索返回切片数 |

示例：

```bash
export LLM_BASE_URL=https://api.openai.com/v1
export LLM_API_KEY=sk-xxx
export LLM_MODEL=gpt-4o-mini
export EMBEDDING_MODEL=text-embedding-3-small
./start.sh
```

### 接入本地大模型（Ollama）

```bash
# 1. 在模型所在机器启动 Ollama 并拉取模型
ollama pull qwen2.5:7b-instruct
ollama serve                       # 默认监听 127.0.0.1:11434

# 2. 在与项目同机启动时
export LLM_BASE_URL=http://127.0.0.1:11434/v1
export LLM_MODEL=qwen2.5:7b-instruct
./start.sh
```

- 本地 OpenAI 兼容服务可不设置 `LLM_API_KEY`；只要 `LLM_BASE_URL` 非空即启用大模型。
- 仅切换对话模型时向量仍使用本地哈希，无需重建索引；启动后在「系统管理」可看到“大模型已连接”。
- 若 Ollama 在另一台机器，将 `127.0.0.1` 换成该机器可达 IP，并确保 11434 端口可访问。

## 测试

```bash
cd backend
python -m pytest tests -q
```

测试使用独立临时数据目录，不会影响演示数据；覆盖登录认证、知识库权限、问答引用、流式事件、合同风险拦截与人工复核、文档上传检索删除等 23 个用例。

## 重置演示数据

```bash
rm -f backend/data/app.db backend/data/app.db-wal backend/data/app.db-shm
rm -rf backend/data/uploads backend/data/parsed
# 重启服务后自动重新写入演示数据
```
