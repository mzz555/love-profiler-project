---
name: Project Overview
description: love-profiler 项目整体背景、业务目标和当前进度
type: project
originSessionId: 37a07b1b-9801-4dff-85a0-5791ff0e05fe
---
love-profiler 是一个面向抖音用户的 AI 恋爱性格测评小程序。

**业务流程：**
- 用户通过抖音自动登录（无手动登录）
- 进入首页后看到项目介绍 + 三种模式（快速/深度/配对）
- 目前只实现快速模式，其余两个留空
- 快速模式：AI 多轮对话测评 → 生成报告 → 付费解锁完整报告

**后端结构（FastAPI）：**
- `app/agents/` — agent1_chat（对话）、agent2_analysis（分析）
- `app/api/` — auth, chat, start, result, pay, unlock, ws_chat, history
- `app/services/` — llm_client, session_store, round_controller, json_validator, content_safety
- `app/models/` — User, Assessment, Order（SQLAlchemy）
- `app/middleware/auth.py` — 抖音 JWT 验证

**前端结构（字节跳动小程序）：**
- `miniprogram/pages/index/` — 首页/项目介绍
- `miniprogram/pages/chat/` — 对话页
- `miniprogram/pages/report/` — 报告页
- `miniprogram/pages/unlock/` — 解锁付费页
- `miniprogram/pages/history/` — 历史记录页

**Why:** 独立开发者构建的抖音生态变现产品，AI 测评 + 付费解锁模式。
**How to apply:** 新功能开发优先复用现有 agent/service 结构，付费逻辑走 order 模型。
