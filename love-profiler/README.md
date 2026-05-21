# 恋爱人格测评系统 — 操作手册

抖音小程序全栈项目。用户完成 30 道固定选择题，**scoring engine（纯 Python 确定性评分）**生成结构化诊断，**report writer（LLM）**基于诊断生成恋爱人格报告，用户通过 ¥9.9 付费或激励视频广告解锁报告。

**仓库包含两个独立子项目：**

| 子项目 | 路径 | 说明 |
|--------|------|------|
| 后端 API | `love-profiler/` | FastAPI + SQLAlchemy + 本地 Supabase CLI |
| 小程序前端 | `love-profiler/miniprogram/` | 抖音小程序（TTML/TTSS/JS） |

---

## 目录

- [技术架构](#技术架构)
- [目录结构](#目录结构)
- [后端 — 环境准备](#后端--环境准备)
- [后端 — 配置说明](#后端--配置说明)
- [后端 — 启动服务](#后端--启动服务)
- [API 接口](#api-接口)
- [业务流程](#业务流程)
- [运行测试](#运行测试)
- [数据库](#数据库)
- [后台管理](#后台管理)
- [小程序前端](#小程序前端)
- [生产部署](#生产部署)

---

## 技术架构

| 层级 | 技术 |
|------|------|
| Web 框架 | FastAPI + Uvicorn |
| 数据库 | 本地 Supabase CLI（PostgreSQL 54322 / REST 54321）|
| ORM | SQLAlchemy 2.x |
| 数据校验 | Pydantic v2 |
| AI 大模型 | 豆包（字节跳动火山引擎）|
| 认证 | 抖音 tt.login → JWT (HS256) |
| 支付 | 字节跳动小程序支付 ECPay |
| 流式输出 | WebSocket（`/ws/result`）|
| HTTP 客户端 | httpx (async) |
| 限流 | slowapi（按 IP） |
| 测试框架 | pytest + pytest-asyncio + respx |
| 小程序前端 | 抖音小程序（TTML / TTSS / JS） |

### 双引擎架构（scoring engine + report writer）

```
30 道选择题 ─┐
            ├─► scoring engine（纯 Python 评分）─► 结构化诊断 JSON
答题包构造 ─┘                                    （type_code / 5 维度 / 跨维度审查 highlights）
                                                       │
                                                       ▼
                                  report writer（LLM, temp=0.6）─► 人格报告（流式）
                                                       │
                                                       ▼
                              WebSocket --Section-- 分段下发，前端按 section 路由
```

- **scoring engine**（`app/agents/scoring_engine.py`，原 Agent A）是纯 Python 确定性计算，**无 LLM 调用**——5 维度算分 + 16 类分型 + 三层跨维度审查
- **report writer**（`app/agents/report_writer.py`，原 Agent B）接收 scoring engine 的诊断 JSON，按系统提示词生成 8 段式报告（Title / Opening / D1–D5 / Highlight / Suggestion）

完整评分规则见 `docs/superpowers/specs/2026-04-30-scoring-rules.md`；report writer 提示词见 `docs/agent-b-system-prompt.md`；16 类人格速查见 `docs/love-types-reference.md`。

---

## 目录结构

```
love-profiler/
├── app/
│   ├── main.py                      # FastAPI 入口、lifespan、路由注册
│   ├── database.py                  # SQLAlchemy 引擎 & 会话
│   ├── limiter.py                   # slowapi 限流器
│   ├── api/
│   │   ├── auth.py                  # POST /auth/login（抖音换 JWT）
│   │   ├── quiz.py                  # POST /quiz/start, /quiz/submit
│   │   ├── result.py                # POST /result, /result/stream
│   │   ├── ws_result.py             # WebSocket /ws/result（report writer 流式）
│   │   ├── unlock.py                # POST /unlock/ad
│   │   ├── pay.py                   # POST /pay/*
│   │   ├── history.py               # GET /history
│   │   ├── admin.py                 # /admin SPA + /admin/logs
│   │   ├── dev_auth.py              # POST /auth/dev-login（DEV_MODE）
│   │   └── dev_pay.py               # POST /pay/dev-callback（DEV_MODE）
│   ├── agents/
│   │   ├── scoring_engine.py        # 纯 Python 评分引擎（原 agent_a.py）
│   │   └── report_writer.py         # LLM 报告生成（原 agent_b.py）
│   ├── services/
│   │   ├── llm_client.py            # 豆包 API 异步封装 + 计时日志
│   │   ├── llm_logger.py            # AI 调用日志写入 logs/ai_calls.jsonl
│   │   ├── supabase_client.py       # 从本地 Supabase REST 拉题目
│   │   ├── answer_package_builder.py# 组装答题包
│   │   ├── report_writer_runner.py  # report writer 调用编排（原 agent_b_runner.py）
│   │   └── access_control.py        # 付费/广告解锁守卫
│   ├── models/
│   │   ├── user.py                  # users 表
│   │   ├── assessment.py            # assessments 表
│   │   ├── order.py                 # orders 表
│   │   └── ai_call_log.py           # ai_call_logs 表
│   └── middleware/
│       └── auth.py                  # JWT 创建 & 验证（FastAPI 依赖）
├── miniprogram/                     # 抖音小程序前端
│   ├── app.js / app.json / app.ttss
│   ├── project.config.json          # AppID 配置
│   └── pages/
│       ├── index/                   # 登录页
│       ├── chat/                    # 30 题 5 球滑动选择页
│       ├── unlock/                  # 解锁页（付费 / 广告）
│       └── report/                  # 报告页（WebSocket 流式 + 三类图表）
├── static/
│   ├── admin/index.html             # 后台管理 SPA
│   ├── personalities/               # 16 × 2 = 32 张人格头像
│   └── addtional/                   # 附加人物图（注：拼写错误是历史遗留，请保持）
├── docs/
│   ├── agent-b-system-prompt.md     # report writer 系统提示词（文件名保留以兼容代码路径）
│   ├── love-types-reference.md      # 16 类人格速查
│   └── superpowers/{specs,plans}    # spec-driven 工作流文档
├── scripts/
│   └── list_types.py                # 从数据库导出人格类型清单
├── supabase/                        # Supabase CLI 配置 + migrations
├── tests/
│   ├── conftest.py                  # 共享 fixtures
│   ├── api/                         # API 集成测试
│   ├── agents/                      # scoring engine 与 report writer 单元测试
│   ├── services/                    # Service 单元测试
│   └── models/                      # 模型测试
├── .env.example                     # 环境变量模板
├── CLAUDE.md                        # Claude Code 工作指引
├── pytest.ini                       # pytest 配置
└── requirements.txt                 # Python 依赖
```

---

## 后端 — 环境准备

### 1. Python 版本

要求 Python 3.10+（推荐 3.12）。

```bash
python --version
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 启动本地 Supabase

需要先安装 Supabase CLI，然后在 `love-profiler/` 下：

```bash
supabase start                 # 启动本地 PG (54322) + REST (54321)
supabase db push               # 推送 questions 表 migration
```

### 4. 创建环境变量文件

```bash
cp .env.example .env
```

填入真实值（见下节）。

---

## 后端 — 配置说明

| 变量 | 必填 | 说明 |
|------|------|------|
| `DEV_MODE` | 否 | `true` 启用开发专用接口（`/auth/dev-login`、`/pay/dev-callback`）、管理后台免鉴权。**生产必须 false 或不设置** |
| `SUPABASE_URL` | 是 | 本地 Supabase REST URL，默认 `http://127.0.0.1:54321` |
| `SUPABASE_KEY` | 是 | 本地 Supabase publishable key（`supabase start` 输出里复制） |
| `DOUBAO_API_KEY` | 是 | 豆包大模型 API Key |
| `DOUBAO_MODEL` | 是 | 默认 `doubao-pro-32k` |
| `DOUYIN_APP_ID` | 是（生产） | 抖音小程序 AppID |
| `DOUYIN_APP_SECRET` | 是（生产） | 抖音小程序 AppSecret |
| `DOUYIN_PAY_TOKEN` | 否 | 支付回调签名 Token |
| `DOUYIN_AD_SECRET` | 否 | 激励广告验证密钥（不填则跳过验证） |
| `JWT_SECRET` | 是 | JWT 签名密钥（生产用 32 字节随机串） |
| `DATABASE_URL` | 是 | 业务表数据库 URL，开发指向本地 Supabase PG (`postgresql://postgres:postgres@127.0.0.1:54322/postgres`) |
| `ADMIN_TOKEN` | 生产必填 | 管理后台访问令牌；`DEV_MODE=true` 时可留空 |

生成安全 JWT_SECRET：

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 后端 — 启动服务

### 开发模式（热重载）

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

启动日志：

```
00:00:01 [INFO] app.main: 启动中 [DEV mode] — 初始化数据库表...
00:00:01 [INFO] app.main: 数据库就绪，服务启动完成
```

### 生产模式

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

- Swagger UI：`http://localhost:8000/docs`
- 健康检查：`GET /health` → `{"status": "ok"}`

### 无抖音凭据时的开发绕过

设 `DEV_MODE=true`，前端 `pages/index/index.js` 自动调用 `POST /auth/dev-login` 跳过抖音 OAuth。

---

## API 接口

需要登录的接口在请求头携带：

```
Authorization: Bearer <token>
```

### 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/login` | 抖音 tt.login() code 换 JWT |
| POST | `/auth/dev-login` | DEV_MODE 专用，无需 code，直接返回测试用户 JWT |

### 测评流程

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/quiz/start` | 拉 30 道题 + 创建 assessment，返回 `session_id` / `assessment_id` / `questions[]` |
| POST | `/quiz/submit` | 提交 30 题答案 → scoring engine 评分 → 写入 `diagnosis_json`，状态 `pending → analyzed` |
| POST | `/unlock/ad` | 看完激励视频后解锁 |
| POST | `/result` | 拉取报告（已缓存则直接返回） |
| WS | `/ws/result` | report writer 流式生成报告，按 `--Section--` 分段下发 |
| POST | `/result/stream` | HTTP 流式版本（备用） |
| GET | `/history` | 当前用户历史报告列表 |

### Assessment status 流转

```
pending  →  analyzed  →  generating  →  complete
   (scoring engine)  (开始流式)   (report writer 完成)
```

### 支付

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/pay/create_order` | 创建 ¥9.9 订单，返回 `out_trade_no` + 字节支付参数 |
| POST | `/pay/callback` | 字节跳动异步回调（验签 → status=paid） |
| POST | `/pay/query` | 前端轮询订单状态 |
| POST | `/pay/dev-callback` | DEV_MODE 专用，模拟支付成功 |

---

## 业务流程

```
小程序端                                  后端
──────────────────────────────────────────────────────────────
tt.login() → code
  POST /auth/login(code)              →  JWT token

  POST /quiz/start                    →  session_id + 30 道题
  本地逐题展示（5 球滑动选择，30 题）
  POST /quiz/submit(answers)          →  scoring engine 评分（纯 Python）
                                          status=analyzed

  ── 付费路径 ──
  POST /pay/create_order              →  out_trade_no + order_info
  tt.pay(order_info)                  →  拉起收银台
  字节跳动异步回调                    POST /pay/callback (status=paid)

  ── 广告路径 ──
  tt.createRewardedVideoAd            →  看完广告
  POST /unlock/ad(ad_token)           →  unlocked=true

  WebSocket /ws/result                →  report writer 流式生成报告
                                         按 --Section-- 分段下发
                                         section_start / section_chunk / section_end / done
  POST /result（缓存命中直接返）     →  完整报告
```

---

## 运行测试

```bash
# 全部测试
pytest

# 带覆盖率报告
pytest --cov=app --cov-report=term-missing

# 只跑某一模块
pytest tests/api/test_quiz.py -v
```

> **已知 flaky**：`tests/api/test_quiz.py::test_quiz_submit_runs_agent_a` 单独失败属于已知 SQLAlchemy fixture 问题，与代码无关。看到「1 failed, 其余 passed」即视为绿灯。

| 模块 | 测试文件 |
|------|----------|
| API 接口 | `tests/api/test_auth.py` `test_quiz.py` `test_result.py` `test_pay.py` `test_health.py` `test_history.py` `test_admin_api.py` |
| 评分与报告引擎 | `tests/agents/test_scoring_engine.py` `test_report_writer.py` |
| 服务层 | `tests/services/test_llm_client.py` `test_llm_logger.py` `test_answer_package_builder.py` |
| 数据模型 | `tests/models/test_models.py` |

---

## 数据库

业务表由 SQLAlchemy 自动建（`users` / `assessments` / `orders` / `ai_call_logs`）；题库表 `questions` + 静态配置表（`base_love_type` / `highlights` / `base_dimension_meta` / `base_segment_decode` / `base_D4_type` / `base_D5_quadrant`）由 Supabase migrations 管理。

**`assessments` 表关键字段：**

| 字段 | 说明 |
|------|------|
| user_id | 关联用户 |
| session_id | 测评会话 ID（quiz 模式下唯一） |
| answers_json | 30 题原始答案 |
| diagnosis_json | scoring engine 输出的结构化诊断 |
| report_json | report writer 输出的结构化报告 |
| report_text | report writer 输出的原始流式文本（含 --Section-- 标记） |
| personality_type | type_code（如 `MA-CL-MH`） |
| status | pending / analyzed / generating / complete |

切换生产 PG：修改 `.env` 的 `DATABASE_URL`，启动时自动建表。

---

## 后台管理

两个独立面板：

- **`/admin`** → 11 张表的浏览/搜索/编辑面板（`static/admin/index.html`），含深/浅主题切换
- **`/admin/logs`** → AI 调用监控（今日统计 + 调用列表）

**访问方式：**

- 本地：`DEV_MODE=true` 时直接打开 `http://localhost:8000/admin`
- 生产：`.env` 设 `ADMIN_TOKEN=xxx`，访问 `/admin?token=xxx` 或带 `X-Admin-Token` 头

---

## 小程序前端

### 开发工具

使用**字节跳动开发者工具**打开 `miniprogram/` 目录。

下载：[developer.open-douyin.com](https://developer.open-douyin.com/docs/resource/zh-CN/mini-app/develop/tools/downloads/index)

### 首次配置

1. `miniprogram/project.config.json` 改 `appid` 为真实 AppID
2. `miniprogram/app.js` 改 `BASE_URL` 为后端地址（本地用 `http://localhost:8000`）
3. `miniprogram/pages/unlock/unlock.js` 改 `adUnitId` 为真实广告位

### 页面说明

| 页面 | 路径 | 功能 |
|------|------|------|
| 登录页 | `pages/index/` | DEV：`/auth/dev-login`；生产：`tt.login()` → `/auth/login` |
| 答题页 | `pages/chat/` | 30 题 5 球滑动选择，本地状态管理 |
| 解锁页 | `pages/unlock/` | 付费（¥9.9）/ 广告 二选一 |
| 报告页 | `pages/report/` | WebSocket 流式接收报告，三类图表（D1-D3 仪表盘 / D4 五边形雷达 / D5 象限） |

### 本地联调

开发者工具中设置**不校验合法域名**（设置 → 项目设置），即可访问 `localhost:8000`。

---

## 生产部署

### 上线前检查清单

**后端：**
- [ ] `JWT_SECRET` 已替换为 32 字节以上随机字符串
- [ ] `ADMIN_TOKEN` 已设为强随机串
- [ ] `DEV_MODE` 未设或为 false
- [ ] `DOUBAO_API_KEY` 已填入真实密钥
- [ ] `DOUYIN_APP_ID` / `DOUYIN_APP_SECRET` 已填入
- [ ] `DOUYIN_PAY_TOKEN` 已配置（支付回调验签）
- [ ] `DATABASE_URL` 已切换到生产 PostgreSQL
- [ ] Supabase 静态配置表（`base_love_type` 等）已 migrate 到生产
- [ ] 字节跳动开发者后台已配置支付回调地址：`https://your-domain.com/pay/callback`
- [ ] 服务已启用 HTTPS（支付回调强制要求）

**小程序前端：**
- [ ] `project.config.json` 中 `appid` 已填入真实 AppID
- [ ] `app.js` 中 `BASE_URL` 已改为生产域名（必须 HTTPS）
- [ ] `unlock.js` 中 `adUnitId` 已填入真实广告位 ID
- [ ] 在字节跳动开发者后台完成域名白名单配置
- [ ] 上传代码并提交审核

### Docker 部署

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

```bash
docker build -t love-profiler .
docker run -d --env-file .env -p 8000:8000 love-profiler
```

> 注意：生产部署还需保证 Supabase（或独立 PostgreSQL）可达，且静态配置表已 seed 数据。
