# 双人模式前端 — 设计文档

- 日期：2026-06-27
- 分支：feat/couple-mode
- 状态：设计已确认，待落实现
- 平台：抖音小程序（`miniprogram/`，tt API）

## 1. 背景与目标

双人落差测评的**后端核心闭环**已完成（`feat/couple-mode`，428 测试绿），但缺前端。本设计交付**完整前端闭环**，让真实用户能走通：

> A 发起 → 邀请 B → 双方各自「双轮作答」→ 异步等待 → 各自查看 7 段双人报告。

后端 4 接口已就绪，前端只做胶水与交互：

| 接口 | 请求 | 响应 |
|---|---|---|
| `POST /couple/create` | — | `{session_id, pairing_token, questions}` |
| `POST /couple/join` | `{pairing_token}` | `{session_id, questions}` |
| `POST /couple/answer` | `{session_id, self[], predicted[], skipped[]}` | `{status}` |
| `GET /couple/result` | `?session_id` | `409` / `{status:generating}` / `{status:complete, report}` |

沿用现有 token 鉴权与 `app.request`（401 自动跳 index）。

## 2. 范围

**本期（一个 spec）**：配对分享、双轮作答、等待轮询、7 段报告页，端到端可跑通。

**非目标（各自后续独立 spec）**：支付墙、流式 WS 报告、DRSA 真实校准、断点续答、小程序码配对、admin 编辑双人题库。

## 3. 页面架构与用户旅程

新增 4 页 + index 微调（join 是一次 API 调用，不单独立页）：

```
pages/
├─ index/          【微调】首页加两入口：「发起双人测评」｜「我有邀请码」
├─ couple-invite/  【新】A 发起：create → 分享卡片 + 邀请码 → 「开始我的作答」
├─ couple-quiz/    【新】双轮作答：① self 全题 ② predicted 仅互猜题 → 提交
├─ couple-wait/    【新】等待页：轮询 result（等对方 / 等报告）
└─ couple-report/  【新】7 段报告渲染（盲区卡片为主菜）
```

**两条用户旅程：**

```
A（发起方）                          B（加入方）
─────────                          ─────────
index「发起」                       路径①：点 A 分享卡片 → 小程序带 token 启动
  ↓ POST /couple/create                    index onLoad 取 token → POST /couple/join
couple-invite                       路径②：index「我有邀请码」→ 粘贴 → join
  分享卡片 / 复制邀请码 ───────────────────────────┘
  ↓ 「开始我的作答」
couple-quiz（self + predicted）  ← 两人各自独立作答（异步，互不等待）
  ↓ POST /couple/answer → {status}
couple-wait（轮询 GET /couple/result）
  ↓ 后端：双方 done → computing → generating → complete
couple-report（status=complete 时渲染 report）
```

**关键点：**

- 配对与作答**完全异步**——A 发起后可立即作答，不必等 B；谁后完成谁触发计算（后端「只点火一次」已实现）。
- 两人走**同一套** couple-quiz / couple-wait / couple-report，仅入口不同。
- 登录沿用现有 token；无 token 先跳 index。

## 4. couple-quiz 双轮作答（技术核心）

**题目数据**（create/join 已返回；`reverse` 是后端归一化用的，前端不碰）：

| 字段 | 用途 |
|---|---|
| `question_id` | 提交时回传 |
| `item_type` | `slider`→连续条 / `likert7`→七档 |
| `stem` | 题干 |
| `anchor_low` / `anchor_high` | slider 左右锚文案；likert7 为空 |
| `apply_prediction` | 是否进入「猜对方」段 |

**两段式状态机：**

```
phase = 'self'                       phase = 'predicted'
全部题，逐题作答      ──全答完──▶     仅 apply_prediction 且 self 未跳过的题
进度：第 i / N         自动切换        问法变「你猜 TA 会怎么选？」
                                      进度：第 j / M
                                         │ 最后一题完成
                                         ▼
                           一次性 POST /couple/answer
                           { self:[…], predicted:[…], skipped:[…] }
                                         ▼ {status} → 跳 couple-wait
```

**两种作答控件：**

- `slider`（传 0–100，初始居中 50）：题干 + 左锚 `anchor_low` ●——拖动——`anchor_high` 右锚。
- `likert7`（传 1–7，无默认值）：题干（陈述句）+ ①②③④⑤⑥⑦ 七档，「很不同意 ← → 非常同意」，必须点选或跳过。

**skip 规则**：每题可「跳过」→ 该 `question_id` 进 `skipped[]`；**self 跳过的题，predicted 段不再出现**（不能猜一个自己都没答的题）。

**前端内存结构：**

```js
_questions[]              // 按 sort_order
_phase                   // 'self' | 'predicted'
_idx                     // 当前题序
_self[]      = [{question_id, value}]
_predicted[] = [{question_id, value}]
_skipped[]   = [question_id]
```

**文件拆分（守 500 行）**：`couple-quiz.js` 只管流程（加载/切段/提交）；slider 拖动手势 + likert 取值 + 两段切换/skip 过滤等纯逻辑拆进 `couple-quiz-input.js`（参照单人 `report-utils.js`）。`.ttml`/`.ttss` 各一份。

## 5. couple-invite / couple-wait / couple-report

**couple-invite（A 发起）**

- onLoad → `POST /couple/create` → 缓存 `session_id`+`questions`（带给 quiz，避免重复请求）。
- 展示：分享卡片按钮（`onShareAppMessage` 返回 `path=/pages/index/index?invite_token=<token>`）＋ 邀请码文本＋复制按钮。
- 「开始我的作答」→ `navigateTo couple-quiz?session_id=…`。

**B 加入（不单独立页）**

- 路径①分享卡片：index `onLoad` 检测 `invite_token` → `POST /couple/join` → 进 quiz。
- 路径②手输：index「我有邀请码」弹输入 → `join` → 进 quiz。
- join 错误文案对齐后端：404 邀请无效 / 409 不能和自己配对 / 409 已有搭档。

**couple-wait（轮询）**

```
每 3s  GET /couple/result?session_id
 ├ 409 (waiting_partner/computing) → 「等待对方完成…」
 ├ {generating}                    → 「正在生成报告…」
 └ {complete, report}              → 缓存 → redirectTo couple-report
```

- A 先答完、B 未答 → 长时间 waiting：友好文案 +「稍后再来看」可退出（不死等）。
- 网络失败：继续重试不中断；达可见轮询上限后提示稍后回来。

**couple-report（7 段渲染）**

- opening / how_to_read / **blindspot_cards（卡片列表，主菜）** / landscape / strengths / next_steps（含 invitations）/ closing。
- **空段优雅跳过**（MVP 下 landscape、strengths 常为空 → 不渲染）。
- `quality_warnings` 仅 dev 可见，生产不展示。

## 6. 错误处理（横切）

| 场景 | 处理 |
|---|---|
| token 失效 401 | 沿用 `app.request` 统一跳 index |
| create/join 网络失败 | toast 提示重试 |
| join 业务错误 404/409 | 对应中文文案，停留在入口 |
| answer 502 计算失败 | toast「计算失败」，可重试提交 |
| result 轮询网络失败 | 继续重试不中断 |
| 入口防重 | 进 quiz 前若该 session 已 complete，直接去 report（不重复作答） |

## 7. 测试策略

前端**无自动化测试框架**（纯 tt 小程序）。策略：

1. 可纯函数化的逻辑（两段切换、skip 过滤 predicted、答案聚合、分享 path 构造）抽进 `couple-quiz-input.js` 等模块，用 **node 跑断言**（复用可视化页 `verify_engine.js` 的路子）。
2. UI 交互**手动验收**；dev 模式提供「随机填答」按钮快速跑通整条闭环。
3. 后端 4 接口已有 pytest 覆盖（428 绿），前端只验证胶水层。

## 8. 文件清单与约束

新增/修改（每文件守 500 行；超则按上述拆分）：

```
miniprogram/app.json                      改：注册 4 个新页
miniprogram/pages/index/index.{js,ttml,ttss}  改：两入口 + invite_token 检测 + join
miniprogram/pages/couple-invite/*         新：发起 + 分享 + 邀请码
miniprogram/pages/couple-quiz/*           新：双轮作答（含 couple-quiz-input.js）
miniprogram/pages/couple-wait/*           新：轮询等待
miniprogram/pages/couple-report/*         新：7 段报告
scripts/ 或 tests 内 node 断言脚本         新：纯逻辑验证
```

视觉沿用现有 app 风格（深色 `#08080F`），交互手感参照单人 chat 的滑块；精细视觉留给实现阶段的 frontend-design。

## 9. 决策记录（用户已确认）

- **范围**：完整闭环一个 spec。
- **配对分享**：分享卡片 + 复制码兜底。
- **互猜轮**：两段式（先全答自己，再统一猜对方）。
- **报告页**：新建页，先做 7 段清晰版（海报/精美视觉后续）。
