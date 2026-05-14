# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

抖音小程序全栈项目，用于 AI 恋爱人格测评（快速模式）。用户完成 30 道固定选择题（一答一问），Agent A 做结构化诊断，Agent B 生成人格报告，用户通过看激励视频广告解锁报告。

仓库包含两个子项目：
- **后端**：`love-profiler/` — FastAPI + SQLAlchemy + 本地 Supabase CLI
- **前端**：`love-profiler/miniprogram/` — 抖音小程序（TTML/TTSS/JS）

## 常用命令

### 后端

```bash
# 安装依赖（在 love-profiler/ 目录下）
pip install -r requirements.txt

# 复制并填写环境变量
cp .env.example .env

# 开发模式启动（热重载）
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 生产模式启动
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# 运行全部测试
pytest

# 运行单个测试文件
pytest tests/api/test_chat.py -v

# 带覆盖率报告
pytest --cov=app --cov-report=term-missing
```

所有测试命令在 `love-profiler/` 目录下执行。测试使用内存 SQLite，无需 `.env`（环境变量已在 `tests/conftest.py` 中设置）。

### 前端

用**字节跳动开发者工具**打开 `miniprogram/` 目录。本地联调时在设置中开启「不校验合法域名」以访问 `localhost:8000`。

## 架构

### 快速模式双 Agent 流程

```
POST /quiz/start  →  从 Supabase 拉 30 道题，返回 session_id + questions
前端本地逐题展示（一答一问，选项按钮，30 题选完）
POST /quiz/submit →  answer_package_builder 组装答题包
                      Agent A (LLM, temp=0.1) → 诊断包 JSON
                      写入 assessment: answers_json / diagnosis_json / status="analyzed"
用户看广告 → POST /unlock/ad → 解锁
POST /result      →  Agent B (LLM, temp=0.6) 读取 diagnosis_json → 报告 JSON
                      写入 assessment: report_json / report_text / personality_type / status="complete"
                      重复调用直接返回缓存（status=="complete"）
```

### 核心服务职责

| 文件 | 职责 |
|------|------|
| `app/agents/agent_a.py` | 接收答题包 → LLM 诊断 → 输出结构化诊断 JSON（含跨维度审查）|
| `app/agents/agent_b.py` | 接收诊断包 → LLM 写报告 → 输出报告 JSON（report_text + sections）|
| `app/services/answer_package_builder.py` | 组装答题包：解析分值字符串、标记 D3-Q06 追逃亚型、注入题目元数据 |
| `app/services/llm_client.py` | 豆包（字节跳动火山引擎）API 的异步封装，含计时和全链路日志 |
| `app/services/llm_logger.py` | AI 调用日志写入 `logs/ai_calls.jsonl`（system_prompt/messages/response/token 全记录）|
| `app/services/supabase_client.py` | 从本地 Supabase REST API 拉取题目列表 |
| `app/middleware/auth.py` | JWT 创建与验证（HS256），以 FastAPI 依赖注入方式使用 |

### 数据库模型

本地 Supabase CLI（localhost:54322 PostgreSQL，localhost:54321 REST API）。

**三张业务表（SQLAlchemy 管理）：**
- `users`（openid）
- `assessments`（answers_json / diagnosis_json / report_json / personality_type / report_text / status）
- `orders`（out_trade_no、amount、status: pending/paid/failed）

**一张题库表（Supabase migrations 管理）：**
- `questions`（question_id / dimension / signal_code / signal_name / question_type / stem / score_a~e / version / notes）

Assessment status 流转：`pending` → `analyzed`（Agent A 成功后）→ `complete`（Agent B 成功后）

应用启动时 SQLAlchemy 自动建表（业务表）；questions 表由 `supabase db push` 管理。

### 评分规则（Agent A 逻辑基础）

完整规则见 `docs/superpowers/specs/2026-04-30-scoring-rules.md`，核心摘要：

**5 个维度的打分模型：**

| 维度 | 模型 | 输出 |
|------|------|------|
| D1 依恋 / D2 边界 / D3 冲突 | 强度型：A=+2, B=+1, C=-1, D=-2，累加后映射 5 类标签 | raw_total [-12,+12] |
| D4 情感需求 | 类型偏好型：按选项指向的爱的语言累加，归一化后取 top2 | T1-T5 偏好排序 |
| D5 风格表达 | 双子面型：S1 直接性（Q01-03）/ S2 分享欲（Q04-06）独立算分 | 2x2 象限 |

**强度型标签映射：**
```
≥ 6   → 健康端（安全 / 清晰 / 健康）
3~5   → 中度健康
-2~2  → 混合
-5~-3 → 中度问题端（中度焦虑 / 模糊）
≤ -6  → 问题端（焦虑 / 冲突问题）
```

**D3-Q06 特殊规则（⚠️ 代码层面必须处理）：**
- 选项 C（追的角色）：score_value=-2，`score_meta={"pursue_avoid":"pursue"}`
- 选项 D（逃的角色）：score_value=-2，`score_meta={"pursue_avoid":"avoid"}`
- 选项 A/B 正常打分，score_meta={}

**D4 归一化（⚠️ Agent A 必须执行，否则 T3 用户被系统性低估）：**

| 类型 | 最大可能得分 |
|------|------------|
| T1 言语肯定 | 9 |
| T2 精心时刻 | 8 |
| T3 用心小惊喜 | **6** |
| T4 服务行动 | 9 |
| T5 身体接触 | 8 |

归一化 = 原始得分 ÷ 最大可能得分，取归一化后 top2。

**16 类核心分型：** 依恋（4 类：S/MS/MA/A）× 边界（2 类：CL/BL）× 冲突（2 类：H/P）= 16 类  
type_code 示例：`"MA-CL-MH"`，D4/D5 作为子画像不进入主类型。

**跨维度审查（Agent A 必须全部执行）：**
- 层级1 维度内：D1-S4 一致性、D2-S1 觉察缺口、D3-S1 压力韧性
- 层级2 维度间：D2D3-S1 外强内弱、D1D5-S2 焦虑型回避伪装、D2D5-S1 自我溶解
- 层级3 全局：awareness_gap_global / pursue_avoid_role / stable_personality / love_language_self_awareness

### DEV_MODE

`DEV_MODE=true` 时注册两条额外路由：`POST /auth/dev-login`（跳过抖音 OAuth）和 `POST /pay/dev-callback`（模拟支付回调）。小程序 `pages/index/index.js` 在开发模式下自动调用 `/auth/dev-login`。**生产环境必须设为 `false` 或不设置。**

### 后台管理系统

两个独立面板：

- `/admin` → SPA（`static/admin/index.html`）：覆盖全部 11 张表的数据浏览、搜索、详情面板；可编辑表（base_love_type / highlights / base_dimension_meta / base_segment_decode / base_D4_type / base_D5_quadrant）支持内联编辑；assessments 支持 `generating → analyzed` 状态重置。
- `/admin/logs` → AI 调用监控（旧面板保留）：今日统计 + 调用列表 + 控制台日志。

后端通过 `app/api/admin.py` 的 `TABLE_CONFIG` 字典驱动通用 helper（`_query_table` / `_get_row` / `_update_row`），所有 SQL 标识符在启动时正则校验为安全标识符。

访问：`DEV_MODE=true` 时直接打开；生产用 `.env` 设 `ADMIN_TOKEN=xxx`，访问 `/admin?token=xxx` 或带 `X-Admin-Token` 头。

### Agent B 流式输出格式

Agent B 输出**强制带 `--Section--` 标记的纯文本**（不是 JSON），后端 `app/api/ws_result.py` 的 `_SectionStreamer` 实时检测标记并通过 WebSocket 发送结构化消息：

```
--Title--      → 类型名（书名号）
--Opening--    → 开篇画像
--D1-- ~ --D5--→ 五维度展开
--Highlight--  → High_1: ... High_2: ... 子项
--Suggestion-- → 收尾建议
```

WebSocket 消息类型：`meta` / `section_start` / `section_chunk` / `section_end` / `done` / `error`。旧格式（无 `--Section--` 标记）通过 `portrait_chunk` 兜底回放。前端 `report.js` 按 section 字段路由到对应 `sec.{Title/Opening/D1...}` 数据槽。

完整提示词在 `docs/agent-b-system-prompt.md`。

### 限流

`slowapi` 按 IP 限流：login 10次/分钟、start 5次/分钟、chat 30次/分钟、result 10次/分钟。

### Pytest Fixtures（`tests/conftest.py`）

- `db_engine` — 内存 SQLite + StaticPool（TestClient 多线程场景下必须使用 StaticPool 以共享同一连接）
- `client` — FastAPI TestClient，DB 依赖已替换为测试引擎
- `auth_headers` — 创建测试用户并返回有效的 `Authorization: Bearer ...` 头
- `user_id` — 创建测试用户并返回其整数 id
