# 恋爱人格测评系统 — 操作手册

抖音小程序全栈项目。用户通过 7 轮对话完成心理信号采集，AI 生成专属恋爱人格报告，支持 ¥9.9 付费解锁或激励视频广告解锁。

**仓库包含两个独立子项目：**

| 子项目 | 路径 | 说明 |
|--------|------|------|
| 后端 API | `love-profiler/` | FastAPI + SQLAlchemy |
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
- [小程序前端](#小程序前端)
- [生产部署](#生产部署)

---

## 技术架构

| 层级 | 技术 |
|------|------|
| Web 框架 | FastAPI 0.110 + Uvicorn |
| 数据库 (开发) | SQLite |
| 数据库 (生产) | PostgreSQL |
| ORM | SQLAlchemy 2.x |
| 数据校验 | Pydantic v2 |
| AI 大模型 | 豆包 (Doubao) API |
| 认证 | 抖音 tt.login → JWT (HS256) |
| 支付 | 字节跳动小程序支付 ECPay |
| HTTP 客户端 | httpx (async) |
| 测试框架 | pytest + pytest-asyncio + respx |
| 小程序前端 | 抖音小程序（TTML / TTSS / JS） |

### 双 Agent 架构

```
用户 → [Agent 1] 7 轮对话引导 → 提取 5 项心理信号
                                        ↓
                              [Agent 2] 评分 + 报告生成
                                        ↓
                              personality_type + report_text
```

**5 项心理信号**：`attachment_signal` / `conflict_signal` / `need_signal` / `boundary_signal` / `expression_signal`

---

## 目录结构

```
love-profiler/
├── app/
│   ├── main.py               # FastAPI 入口，lifespan 注册路由
│   ├── database.py           # SQLAlchemy 引擎 & 会话
│   ├── api/
│   │   ├── auth.py           # POST /auth/login
│   │   ├── start.py          # POST /start  → session_id + assessment_id
│   │   ├── chat.py           # POST /chat
│   │   ├── result.py         # POST /result
│   │   ├── pay.py            # POST /pay/*
│   │   └── unlock.py         # POST /unlock/ad
│   ├── agents/
│   │   ├── agent1_chat.py    # 7 轮对话控制器
│   │   └── agent2_analysis.py# 人格分析报告生成
│   ├── services/
│   │   ├── llm_client.py     # 豆包 API 封装
│   │   ├── session_store.py  # 内存会话管理
│   │   ├── round_controller.py # 轮次指令注入
│   │   ├── content_safety.py # 内容安全过滤
│   │   └── json_validator.py # 最终轮 JSON 提取与校验
│   ├── models/
│   │   ├── user.py           # User 表
│   │   ├── assessment.py     # Assessment 表
│   │   └── order.py          # Order 表
│   └── middleware/
│       └── auth.py           # JWT 创建 & 验证
├── miniprogram/              # 抖音小程序前端
│   ├── app.js                # 全局入口，token 管理，统一 HTTP 请求
│   ├── app.json              # 页面注册，全局窗口配置
│   ├── app.ttss              # 全局样式
│   ├── project.config.json   # 开发者工具配置（填 AppID）
│   └── pages/
│       ├── index/            # 登录页
│       ├── chat/             # 7 轮对话页（核心）
│       ├── unlock/           # 解锁页（付费 / 广告）
│       └── report/           # 报告展示页
├── tests/
│   ├── conftest.py           # 共享 fixtures (db, client, auth_headers)
│   ├── api/                  # API 集成测试
│   ├── agents/               # Agent 单元测试
│   ├── services/             # Service 单元测试
│   └── models/               # 模型测试
├── .env.example              # 环境变量模板
├── pytest.ini                # pytest 配置
└── requirements.txt          # Python 依赖
```

---

## 后端 — 环境准备

### 1. Python 版本

要求 Python 3.10+（推荐 3.12 / 3.14）。

```bash
python --version
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 创建环境变量文件

```bash
cp .env.example .env
```

然后编辑 `.env`，填入真实值（见下节）。

---

## 后端 — 配置说明

| 变量 | 必填 | 说明 |
|------|------|------|
| `DOUBAO_API_KEY` | 是 | 豆包大模型 API Key（字节跳动火山引擎控制台获取） |
| `DOUBAO_MODEL` | 是 | 模型名称，默认 `doubao-pro-32k` |
| `DOUYIN_APP_ID` | 是（生产） | 抖音小程序 AppID，DEV_MODE 下可留占位符 |
| `DOUYIN_APP_SECRET` | 是（生产） | 抖音小程序 AppSecret，DEV_MODE 下可留占位符 |
| `DOUYIN_PAY_TOKEN` | 否 | 支付回调签名 Token（字节跳动开发者后台配置） |
| `DOUYIN_AD_SECRET` | 否 | 激励广告验证密钥（不填则跳过验证，仅开发用） |
| `JWT_SECRET` | 是 | JWT 签名密钥，生产环境使用 32 字节以上随机字符串 |
| `DATABASE_URL` | 是 | 数据库连接串，开发用 `sqlite:///./love_profiler.db`，生产用 PostgreSQL URL |
| `DEV_MODE` | 否 | 设为 `true` 启用开发专用接口（`POST /auth/dev-login`），**生产环境必须为 false 或不设置** |

**生成安全的 JWT_SECRET**：

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 后端 — 启动服务

### 开发模式（热重载）

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

启动后终端应输出类似日志：

```
00:00:01 [INFO] app.main: 启动中 [DEV mode] — 初始化数据库表...
00:00:01 [INFO] app.main: 数据库就绪，服务启动完成
```

后续每次请求也会输出关键日志，例如：

```
[INFO] app.api.dev_auth: [/auth/dev-login] DEV登录成功 user_id=1
[INFO] app.api.start:    [/start] user_id=1 开始新测评
[INFO] app.api.start:    [/start] session_id=abc123 assessment_id=1 创建成功
[INFO] app.api.chat:     [/chat] session=abc123 round=2 complete=False
[INFO] app.api.chat:     [/chat] 7轮完成，信号已写库 signals={...}
[INFO] app.api.result:   [/result] 报告生成完成 personality_type=安全型依恋
```

### 无抖音凭据时的开发绕过

没有抖音 AppID/Secret 时，设置 `DEV_MODE=true` 可跳过抖音登录：

1. 确认 `.env` 中有 `DEV_MODE=true`
2. 重启 uvicorn（会自动注册 `/auth/dev-login` 路由）
3. 小程序前端自动调用 `POST /auth/dev-login` 替代 `tt.login()`

> **生产上线前**务必将 `DEV_MODE` 删除或改为 `false`，并将 `index.js` 登录逻辑切换回 `tt.login()` 流程。

### 生产模式

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

服务启动后：

- 接口文档（Swagger UI）：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/health` → `{"status": "ok"}`

---

## API 接口

所有需要登录的接口请在请求头中携带：

```
Authorization: Bearer <token>
```

### 认证

#### `POST /auth/login`

抖音小程序登录，换取 JWT。

```json
// 请求
{ "code": "抖音 tt.login() 返回的 code" }

// 响应
{ "token": "eyJ..." }
```

---

### 测评流程

#### `POST /start`

开启一次新的测评会话，返回 Agent 1 的开场白。需要 Authorization 头。

```json
// 响应
{
  "session_id": "uuid-...",
  "assessment_id": 1,
  "message": "你好，我是你的恋爱顾问...",
  "round_num": 1
}
```

> `assessment_id` 由小程序存入全局变量，后续创建订单时使用。

#### `POST /chat`

发送用户消息，推进对话（共 7 轮）。需要 Authorization 头。

```json
// 请求
{
  "session_id": "uuid-...",
  "message": "我喜欢和她一起安静地待着"
}

// 响应
{
  "message": "听起来你很享受那份宁静...",
  "round_num": 2,
  "is_complete": false
}
```

第 7 轮时 `is_complete` 为 `true`，信号提取完成，可调用 `/result`。

**错误码**：

| 状态码 | 原因 |
|--------|------|
| 404 | session_id 不存在或已过期 |
| 422 | 消息包含不安全内容 |
| 502 | AI 服务暂时不可用 |

#### `POST /result`

生成专属人格报告（已缓存，重复调用不重新生成）。需要 Authorization 头；需先完成全部 7 轮对话。

```json
// 请求
{ "session_id": "uuid-..." }

// 响应
{
  "personality_type": "安全型依恋",
  "report_text": "你在亲密关系中展现出...",
  "summary": "你在亲密关系中展现出..."
}
```

---

### 支付

#### `POST /pay/create_order`

创建支付订单（¥9.90）。需要 Authorization 头。

```json
// 请求
{ "assessment_id": 1 }

// 响应
{
  "out_trade_no": "LP3A9F...",
  "order_info": { "...字节跳动返回的订单信息..." }
}
```

#### `POST /pay/callback`

字节跳动支付异步回调（**无需鉴权**，由字节跳动服务器调用）。

```json
// 字节跳动下发的回调 Body
{
  "out_trade_no": "LP3A9F...",
  "status": "PAY_SUCCESS"
}
```

回调通过 `DOUYIN_PAY_TOKEN` 验签后将订单状态置为 `paid`。

#### `POST /pay/query`

查询订单状态。需要 Authorization 头。

```json
// 请求
{ "out_trade_no": "LP3A9F..." }

// 响应
{ "status": "paid" }   // pending | paid | failed
```

---

### 广告解锁

#### `POST /unlock/ad`

激励视频广告看完后解锁报告（免费路径）。需要 Authorization 头。

```json
// 请求
{
  "assessment_id": 1,
  "ad_token": "抖音广告回调 token"
}

// 响应
{ "unlocked": true }
```

---

## 业务流程

```
小程序端                              后端
──────────────────────────────────────────────────────────
tt.login() → code
  POST /auth/login(code)         →  换取 JWT token

  POST /start                    →  session_id + 开场白
  POST /chat × 7                 →  对话推进
                                     第 7 轮 is_complete=true
  POST /result                   →  personality_type + report_text

  ── 付费路径 ──
  POST /pay/create_order         →  out_trade_no + order_info
  tt.pay(order_info)             →  拉起收银台
  字节跳动异步回调               POST /pay/callback  (状态→paid)
  前端轮询                       POST /pay/query

  ── 广告路径 ──
  tt.createRewardedVideoAd       →  用户看完广告
  POST /unlock/ad(ad_token)      →  解锁报告
```

---

## 运行测试

```bash
# 全部测试
pytest

# 带覆盖率报告
pytest --cov=app --cov-report=term-missing

# 只跑某一模块
pytest tests/api/test_chat.py -v
```

当前状态：**123 passed**，无错误。

| 模块 | 测试文件 |
|------|----------|
| API 接口 | `tests/api/test_auth.py` `test_chat.py` `test_result.py` `test_pay.py` `test_health.py` |
| Agent 逻辑 | `tests/agents/test_agent1_chat.py` `test_agent2_analysis.py` |
| 服务层 | `tests/services/test_llm_client.py` `test_session_store.py` `test_round_controller.py` `test_json_validator.py` `test_content_safety.py` |
| 数据模型 | `tests/models/test_models.py` |

---

## 数据库

### 表结构

**`users`**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| openid | VARCHAR UNIQUE | 抖音 openid |
| created_at | DATETIME | 注册时间 |

**`assessments`**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| user_id | INTEGER FK | 关联用户 |
| session_id | VARCHAR | 对话会话 ID |
| signals | TEXT | Agent 1 提取的 JSON 信号（5 个字段） |
| status | VARCHAR | `pending` / `complete` |
| personality_type | VARCHAR | Agent 2 输出的人格类型 |
| report_text | TEXT | Agent 2 输出的报告正文 |
| created_at | DATETIME | 创建时间 |

**`orders`**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| user_id | INTEGER FK | 关联用户 |
| assessment_id | INTEGER FK | 关联测评 |
| out_trade_no | VARCHAR UNIQUE | 商户订单号 |
| amount | INTEGER | 金额（分），广告解锁为 0 |
| status | VARCHAR | `pending` / `paid` / `failed` |
| created_at | DATETIME | 创建时间 |

### 切换到 PostgreSQL

修改 `.env`：

```
DATABASE_URL=postgresql://user:password@host:5432/love_profiler
```

首次启动时 SQLAlchemy 自动建表，无需手动执行迁移脚本。

---

## 小程序前端

### 开发工具

使用**字节跳动开发者工具**打开 `miniprogram/` 目录。

下载地址：[developer.open-douyin.com](https://developer.open-douyin.com/docs/resource/zh-CN/mini-app/develop/tools/downloads/index)

### 首次配置

1. 打开 `miniprogram/project.config.json`，将 `appid` 改为你的抖音小程序 AppID：

```json
{ "appid": "tt1234567890abcdef" }
```

2. 打开 `miniprogram/app.js`，将 `BASE_URL` 改为后端地址：

```js
const BASE_URL = 'https://your-domain.com';  // 开发时用 http://localhost:8000
```

3. 打开 `miniprogram/pages/unlock/unlock.js`，将广告位 ID 改为后台申请的真实 ID：

```js
tt.createRewardedVideoAd({ adUnitId: 'your-real-ad-unit-id' })
```

### 页面说明

| 页面 | 路径 | 功能 |
|------|------|------|
| 登录页 | `pages/index/` | DEV 模式：`POST /auth/dev-login`；生产：`tt.login()` → `POST /auth/login` → 存 token |
| 对话页 | `pages/chat/` | 7 轮对话，实时进度条，打字动画 |
| 解锁页 | `pages/unlock/` | 付费（¥9.9）/ 广告 二选一 |
| 报告页 | `pages/report/` | 展示人格类型和详细分析，支持分享 |

### 本地联调

后端启动后，开发者工具中设置**不校验合法域名**（设置 → 项目设置），即可访问 `localhost:8000`。

---

## 待改进事项（按优先级）

| 优先级 | 问题 | 影响 | 难度 |
|--------|------|------|------|
| ✅ P0 | ~~**付费墙后端无守卫**~~ — 已完成：`/result` 生产环境强制检查 `Order.status="paid"`，DEV_MODE 下跳过 | — | — |
| ✅ P0 | ~~**接口无限流**~~ — 已完成：slowapi 限流（login 10次/分钟、start 5次/分钟、chat 30次/分钟、result 10次/分钟，按 IP） | — | — |
| ✅ P1 | ~~**会话存内存**~~ — 已完成：session 改为 JSON 文件持久化（`sessions/` 目录），重启不丢失；`SESSIONS_DIR` 环境变量可自定义路径 | — | — |
| ✅ P1 | ~~**前端 globalData 不持久化**~~ — 已完成：`sessionId`/`assessmentId` 写入 Storage，重启后自动恢复；session 过期则提示并重新开始 | — | — |
| 🟡 P2 | **无历史记录页** — 报告仅当次会话可见，数据库有数据但前端没有入口 | 留存率低 | 中 |
| ✅ P2 | ~~**无日志 / 错误监控**~~ — 已完成：关键接口均已加 `logging` 输出（启动、登录、对话、报告、支付） | — | — |
| 🟢 P3 | **`/start` 阻塞等待 LLM** — 打开对话页有明显白屏，影响第一印象 | 体验 | 中 |
| 🟢 P3 | **分享海报** — 纯文字转发，裂变效果弱 | 增长 | 高 |
| 🟢 P3 | **历史测评对比** — 不支持多次测评横向对比 | 锦上添花 | 高 |

建议实施顺序：`P0 付费墙守卫 → P0 限流 → P1 前端持久化 → P1 Redis session → P2 历史记录 → P2 监控`

---

## 生产部署

### 上线前检查清单

**后端：**
- [ ] `JWT_SECRET` 已替换为 32 字节以上随机字符串
- [ ] `DOUBAO_API_KEY` 已填入真实密钥
- [ ] `DOUYIN_APP_ID` / `DOUYIN_APP_SECRET` 已填入
- [ ] `DOUYIN_PAY_TOKEN` 已配置（支付回调验签）
- [ ] `DATABASE_URL` 已切换到 PostgreSQL
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
