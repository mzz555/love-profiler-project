# 设计文档：Quiz 模式 + 开发登录修复

**日期：** 2026-04-28
**项目：** love-profiler 抖音小程序

---

## 一、背景与目标

本次改造包含两个独立任务：

1. **修复开发登录 404**：`.env` 未设 `DEV_MODE=true`，导致 `/auth/dev-login` 路由未注册，前端进首页即报 404。
2. **快速模式重构为题库问卷**：将原 AI 自由对话（7 轮）替换为结构化 30 题选择题问卷（5 维度 × 6 题），答完后看广告解锁，AI 生成详细恋爱测评报告。题库存储在 Supabase，去除 ¥9.9 付费解锁。

---

## 二、整体架构

```
前端 chat.js（quiz 模式）
  │
  ├─ 1. POST /quiz/start
  │       └─ 从 Supabase 拉 30 道题，返回给前端
  │
  ├─ 2. 前端本地展示题目（聊天气泡 + ABCD 选项按钮）
  │       └─ 每选一题，答案存本地 _answers[]，自动展示下一题
  │
  ├─ 3. 第 30 题选完
  │       └─ POST /quiz/submit（发送 30 个答案）
  │           └─ 后端算分 → 写入 assessment.dimension_scores → 返回 assessment_id
  │
  └─ 4. 弹出广告解锁提示
          └─ 看完广告 → POST /unlock/ad → 跳转 report 页

后端 POST /result
  └─ 读取 dimension_scores → 调用 Agent 2 → 生成人格报告
```

---

## 三、Supabase 题库

**项目：** `https://mkoonxulzilpucxeaoeu.supabase.co`

**`questions` 表结构：**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 自增主键 |
| question_id | TEXT UNIQUE | D1-Q01 … D5-Q06 |
| dimension | TEXT | 依恋/边界/冲突/情感/风格 |
| sub_dimension | TEXT | 仅 D4/D5 有值 |
| signal_code | TEXT | S1-S5 / T1-T5 |
| signal_name | TEXT | 信号人话名称 |
| question_type | TEXT | 核心题/验证题等 |
| stem | TEXT | 题干 |
| option_a/b/c/d | TEXT | 选项文本 |
| score_a/b/c/d | TEXT | 打分（+2/+1/-1/-2 或 T1+2 等） |
| option_e / score_e | TEXT | 仅 D4-Q01 使用 |
| source | TEXT | 素材来源 |
| design_notes | TEXT | 设计备注 |
| version | TEXT | 版本号 |
| status | TEXT | 审核状态 |
| sort_order | INTEGER | 展示顺序 1-30 |

---

## 四、后端改动

### 新增文件

**`app/services/supabase_client.py`**
- 封装 Supabase HTTP 请求（使用 `httpx`）
- 读取环境变量 `SUPABASE_URL` 和 `SUPABASE_KEY`
- 提供 `fetch_questions()` 方法，按 `sort_order` 返回 30 道题

**`app/services/quiz_scorer.py`**
- 接收 30 个答案（`[{question_id, chosen_option}]`）
- 从题目数据中取对应选项分值，按维度分类计算：

| 维度 | 计算 | 输出 |
|------|------|------|
| D1 依恋 | 6题分值求和 | `attachment`: -12～+12 |
| D2 边界 | 6题分值求和 | `boundary`: -12～+12 |
| D3 冲突 | 6题分值求和（D3-Q06 C/D 均为 -2） | `conflict`: -12～+12 |
| D4 情感 | T1-T5 各自累加，找最高 | `love_language: {T1..T5, primary}` |
| D5 风格 | S1=Q01-03求和，S2=Q04-06求和 | `style: {directness, sharing}` |

- 输出 `dimension_scores` JSON：
```json
{
  "attachment": 6,
  "boundary": 4,
  "conflict": -2,
  "love_language": {"T1": 6, "T2": 4, "T3": 2, "T4": 6, "T5": 4, "primary": "T1"},
  "style": {"directness": 4, "sharing": -2}
}
```

**`app/api/quiz.py`**
- `POST /quiz/start`：从 Supabase 拉 30 题，创建 assessment 记录（mode=quiz），返回题目列表 + assessment_id
- `POST /quiz/submit`：接收 30 个答案，调用 quiz_scorer，将 dimension_scores 写入 assessment，返回 assessment_id

### 修改文件

**`app/models/assessment.py`**
- 新增 `mode` 字段（VARCHAR，默认 `chat`，quiz 模式为 `quiz`）
- 新增 `dimension_scores` 字段（TEXT，存 JSON）

**`app/agents/agent2_analysis.py`**
- 支持接收 `dimension_scores`（quiz 模式）生成报告
- 原有 `signals`（chat 模式）路径保持不变

**`app/api/result.py`**
- quiz 模式时从 `assessment.dimension_scores` 取数据传给 Agent 2
- chat 模式保持不变（从 `signals` 取数据）

**`app/main.py`**
- 注册 `quiz.router`

### 环境变量新增（`.env`）
```
DEV_MODE=true
SUPABASE_URL=https://mkoonxulzilpucxeaoeu.supabase.co
SUPABASE_KEY=<anon key>
```

---

## 五、前端改动

### `miniprogram/pages/chat/chat.js`

- `onLoad`：调用 `POST /quiz/start`，一次性获取全部 30 道题，存入页面内部 `_questions[]`
- 移除 WebSocket 连接逻辑（quiz 模式不需要流式 AI）
- 每题以 AI 气泡显示题干，底部显示对应选项按钮（A/B/C/D，D4-Q01 为 A-E）
- 用户点选后：选项文字以用户气泡显示，答案存入 `_answers[]`，自动推进下一题
- 进度条文案改为 `第 X / 30 题`
- 第 30 题选完后：调用 `POST /quiz/submit` → 弹出广告解锁提示 → 跳转 unlock 页

### `miniprogram/pages/unlock/unlock.js` + `unlock.ttml`

- 移除 ¥9.9 付费入口，只保留「看广告解锁」
- 看完广告 → `POST /unlock/ad` → 跳转 `report` 页

### 不改动

`index.js`、`report.js`、`history.js`、`app.js`

---

## 六、算分与报告生成

用户解锁后调用 `POST /result`，后端：

1. 查 assessment，若 `mode=quiz` 则读取 `dimension_scores`
2. 将维度分数传给 Agent 2，提示词包含：
   - 依恋分 → 安全型（≥8）/ 中等（0-7）/ 焦虑回避（<0）倾向
   - 边界 + 冲突分 → 关系模式分析
   - 主导爱的语言 → 情感需求
   - 风格两轴 → 沟通定位
3. Agent 2 输出 `personality_type`（如"有边界感的安全型"）+ 详细 `report_text`

---

## 七、不在本次范围内

- 历史记录页功能完善
- chat 模式（原 AI 自由对话）的任何改动
- 深度模式、配对模式
- 生产环境部署、PostgreSQL 切换

---

## 八、开发顺序

1. 修复 `.env` DEV_MODE=true（5 分钟）
2. 新增 assessment 字段（migration）
3. 实现 supabase_client + quiz_scorer + quiz.py
4. 修改 agent2_analysis + result.py
5. 注册路由（main.py）
6. 改造 chat.js（quiz 模式）
7. 简化 unlock 页
8. 端到端联调测试
