# 设计文档：快速模式 + Supabase 数据库迁移 + AI 全链路日志

**日期：** 2026-04-29
**项目：** love-profiler 抖音小程序

---

## 一、背景与目标

需求变更：

1. **三模式架构**：产品分为快速（quick）、深度（deep）、心动（heartbeat）三种测评模式，本次只实现快速模式。
2. **Supabase 作为开发数据库**：所有业务数据（users / assessments / orders）迁至 Supabase PostgreSQL，不再使用 SQLite。题库（questions）已在 Supabase，保持不变。
3. **AI 全链路日志**：记录每次豆包 API 调用的完整 system_prompt、messages、response 原文、耗时、token 用量，便于排查问题和分析性能。

---

## 二、整体架构（不变部分）

```
小程序前端
  ├─ POST /quiz/start   →  从 Supabase 拉 30 道题，返回 session_id + questions
  ├─ 前端本地逐题展示（一答一问，选项按钮）
  ├─ POST /quiz/submit  →  提交 30 个答案，后端算分写入 assessment.dimension_scores
  ├─ POST /unlock/ad    →  看广告解锁
  └─ POST /result       →  Agent 2 读取 dimension_scores → 生成报告
```

快速模式完整流程与现有 quiz 骨架一致，本次变更不涉及前端和 Agent 2 逻辑。

---

## 三、变更一：Supabase PostgreSQL 数据库

### 改动文件

**`app/database.py`**

Supabase 要求 SSL 连接，需按数据库类型分别设置 `connect_args`：

```python
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, connect_args={"sslmode": "require"})
```

ORM 模型、查询、会话管理**零改动**。

**`.env`**

```
DATABASE_URL=postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
```

Supabase 连接串从控制台 → Settings → Database → Connection string（Transaction pooler 模式，端口 6543）获取。

**`.env.example`**

```
DATABASE_URL=postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
```

### 建表方式

应用启动时 SQLAlchemy 自动调用 `create_tables()`，在 Supabase 上建出 users / assessments / orders 三张表，无需手动执行 SQL。

### 依赖

需要安装 `psycopg2-binary`（SQLAlchemy PostgreSQL 驱动）：

```
psycopg2-binary==2.9.9   # 加入 requirements.txt
```

---

## 四、变更二：模式命名规范化

`assessment.mode` 字段值统一为产品三模式名称：`quick` / `deep` / `heartbeat`。

| 文件 | 改动 |
|------|------|
| `app/api/quiz.py` | `mode="quiz"` → `mode="quick"` |
| `app/api/result.py` | `if assessment.mode == "quiz"` → `if assessment.mode == "quick"` |

其余文件（scorer、agent2、前端）不涉及 mode 字符串。

---

## 五、变更三：AI 全链路日志系统

### 日志文件结构

```
logs/                         ← 根目录下，加入 .gitignore
├── app.log                   ← 通用应用日志（RotatingFileHandler，10MB × 5）
└── ai_calls.jsonl            ← AI 调用详情（JSON Lines，追加写入，不轮转）
```

### 新增：`app/services/llm_logger.py`

职责：将 AI 调用记录写入 `logs/ai_calls.jsonl`，每次调用一行 JSON。

**成功调用记录格式：**

```json
{
  "ts": "2026-04-29T12:34:56.789123Z",
  "call_id": "550e8400-e29b-41d4-a716-446655440000",
  "type": "completion",
  "model": "doubao-pro-32k",
  "ok": true,
  "elapsed_ms": 1823,
  "prompt_tokens": 856,
  "completion_tokens": 342,
  "total_tokens": 1198,
  "system_prompt": "【角色】你是一位...",
  "messages": [{"role": "user", "content": "..."}],
  "response": "AI 完整回复原文"
}
```

**失败调用记录格式：**

```json
{
  "ts": "2026-04-29T12:35:01.123456Z",
  "call_id": "...",
  "type": "completion",
  "model": "doubao-pro-32k",
  "ok": false,
  "elapsed_ms": 5001,
  "error": "API error 429",
  "system_prompt": "...",
  "messages": [...]
}
```

**流式调用记录格式：**

```json
{
  "ts": "...",
  "call_id": "...",
  "type": "stream",
  "model": "doubao-pro-32k",
  "ok": true,
  "elapsed_ms": 3456,
  "response": "流式输出累积全文（chunk 拼接）"
}
```

> 注：Doubao 流式接口不返回 token 用量，故流式日志无 token 字段。

`llm_logger.py` 接口：

```python
def log_ai_call(
    call_id: str,
    call_type: str,          # "completion" | "stream"
    model: str,
    ok: bool,
    elapsed_ms: int,
    system_prompt: str,
    messages: list[dict],
    response: str | None = None,
    error: str | None = None,
    usage: dict | None = None,   # {"prompt_tokens": N, "completion_tokens": N, "total_tokens": N}
) -> None: ...
```

写入失败时静默忽略（不影响主流程）。

### 修改：`app/services/llm_client.py`

**`chat_completion()`**：
- 调用前生成 `call_id = uuid4()`，记录 `start = time.perf_counter()`
- 成功：从 `response.json()["usage"]` 提取 token 用量，调用 `log_ai_call(ok=True, ...)`
- 失败：在 raise LLMError 之前调用 `log_ai_call(ok=False, error=..., ...)`

**`stream_chat_completion()`**：
- 调用前记录开始时间
- 累积所有 chunk 到 `accumulated` 列表
- 流结束（或出错）后调用 `log_ai_call(type="stream", ...)`
- 仍然 `yield` 每个 chunk，外部调用行为不变

### 修改：`app/main.py`

在 lifespan 启动时配置文件日志：

```python
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

def _setup_file_logging() -> None:
    Path("logs").mkdir(exist_ok=True)
    handler = RotatingFileHandler(
        "logs/app.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S"
    ))
    logging.getLogger().addHandler(handler)
```

在 lifespan 的 `yield` 之前调用 `_setup_file_logging()`。

### `.gitignore`

追加：

```
logs/
```

---

## 六、文件变更清单

| 操作 | 文件 |
|------|------|
| 修改 | `app/database.py` |
| 修改 | `app/api/quiz.py` |
| 修改 | `app/api/result.py` |
| 修改 | `app/services/llm_client.py` |
| 修改 | `app/main.py` |
| 新增 | `app/services/llm_logger.py` |
| 修改 | `requirements.txt` |
| 修改 | `.env` |
| 修改 | `.env.example` |
| 修改 | `.gitignore` |

---

## 七、不在本次范围内

- 深度模式（deep）、心动模式（heartbeat）的任何实现
- 前端改动（快速模式前端已在上一版实现）
- Agent 2 报告生成逻辑改动
- 生产环境部署配置
- 历史记录页

---

## 八、实施顺序

1. 安装 psycopg2-binary，更新 requirements.txt
2. 修改 database.py 加 SSL 支持，更新 .env DATABASE_URL
3. 启动验证：Supabase 上自动建表
4. 修改 quiz.py / result.py 的 mode 字符串
5. 新增 llm_logger.py
6. 修改 llm_client.py 加埋点
7. 修改 main.py 加文件日志
8. 更新 .gitignore
9. 全量测试 pytest
