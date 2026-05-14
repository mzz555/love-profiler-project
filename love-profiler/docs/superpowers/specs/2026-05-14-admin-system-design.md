# 设计文档：后台管理系统

**日期：** 2026-05-14
**项目：** love-profiler 抖音小程序
**范围：** 覆盖全部 11 张数据库表的只读/可编辑管理面板

---

## 一、背景与目标

现有 `/admin/logs` 仅覆盖 AI 调用日志和控制台日志。随着项目进入商业化阶段，需要一套完整的后台管理系统，支持：

1. 业务数据总览（用户、测评、订单）
2. 所有表的数据浏览与搜索
3. 静态配置表的在线编辑（人格类型名称、洞察标签、维度描述等）
4. 问题记录的状态修复（assessments 卡死状态重置）

---

## 二、整体架构

### 技术选型

- **后端**：扩展现有 `app/api/admin.py`，新增 REST API 端点
- **前端**：`static/admin/index.html`，单 HTML 文件，原生 JS + CSS，无框架依赖
- **数据库**：统一通过 `SessionLocal`（PostgreSQL）访问，业务表走 SQLAlchemy ORM，Supabase 静态表走 `text()` 直接查询
- **认证**：复用现有 `require_admin`（`DEV_MODE=true` 或 `X-Admin-Token` 请求头）

### 文件变更清单

```
新增：
  static/admin/index.html          — 前端单页应用
  static/admin/                    — 目录（FastAPI 挂载为静态路由）

修改：
  app/api/admin.py                 — 新增 API 端点 + 静态文件路由
  app/main.py                      — 挂载 /static/admin 静态目录（如未挂载）
```

### 路由结构

```
GET  /admin                        → 重定向到 /static/admin/index.html
GET  /admin/api/overview           → 各表统计数据
GET  /admin/api/{table}            → 分页列表 + 搜索
GET  /admin/api/{table}/{id}       → 单条完整记录
PUT  /admin/api/{table}/{id}       → 字段编辑（受权限限制）
现有路由保持不变：
GET  /admin/logs                   → 原 AI 调用面板（不删除，侧边栏直接链接）
GET  /admin/logs/api
GET  /admin/logs/api/{id}
GET  /admin/console
```

---

## 三、数据访问层

### 支持的表与权限

| 表名 | 数据库 | 权限 | 可编辑字段 |
|------|--------|------|-----------|
| `users` | SQLite/PG（业务） | 只读 | — |
| `assessments` | SQLite/PG（业务） | 状态可改 | `status`（仅允许 `generating→analyzed` 重置） |
| `orders` | SQLite/PG（业务） | 只读 | — |
| `ai_call_logs` | SQLite/PG（业务） | 只读 | — |
| `base_love_type` | Supabase PG | 可编辑 | `type_name`、`tagline` |
| `highlights` | Supabase PG | 可编辑 | `name_cn`、`severity`、`is_positive` |
| `base_dimension_meta` | Supabase PG | 可编辑 | `name_cn`、`description`、`radar_label` |
| `base_segment_decode` | Supabase PG | 可编辑 | `label_cn`、`description`、`score_range` |
| `base_D4_type` | Supabase PG | 可编辑 | `love_languages_name`、`love_languages_detail` |
| `base_D5_quadrant` | Supabase PG | 可编辑 | `style_name`、`description`、`guide` |
| `questions` | Supabase PG | 只读 | — |

### API 规范

#### `GET /admin/api/overview`
```json
{
  "tables": {
    "users":        { "total": 120, "today": 8 },
    "assessments":  { "total": 98, "today": 6,
                      "by_status": { "pending": 2, "analyzed": 10, "complete": 86 } },
    "orders":       { "total": 45, "today": 3,
                      "by_status": { "pending": 1, "paid": 42, "failed": 2 } },
    "ai_call_logs": { "total": 312, "today": 24 }
  },
  "recent_assessments": [ ... ]   // 最近 5 条
}
```

#### `GET /admin/api/{table}?page=1&limit=50&q=`
```json
{
  "total": 120,
  "page": 1,
  "limit": 50,
  "rows": [ { "id": 1, ... }, ... ]
}
```
- `q` 参数：对文本类列做 `ILIKE %q%` 模糊搜索（每张表配置搜索列白名单）
- 大字段（`diagnosis_json`、`report_text`、`messages_json`、`guide`）截断为前 100 字符

#### `GET /admin/api/{table}/{id}`
返回完整记录，大字段不截断。

#### `PUT /admin/api/{table}/{id}`
```json
{ "field1": "value1", "field2": "value2" }
```
- 服务端校验：字段名必须在该表的可编辑白名单中，否则 400
- 只读表返回 403
- `assessments` 的 `status` 字段：只允许从 `generating` 改为 `analyzed`，其他改法返回 422

### 搜索列白名单（每表）

| 表 | 搜索列 |
|---|---|
| `users` | `openid` |
| `assessments` | `personality_type`、`status`、`session_id` |
| `orders` | `out_trade_no`、`status` |
| `ai_call_logs` | `agent`、`status`、`session_id` |
| `base_love_type` | `type_code`、`type_name` |
| `highlights` | `code`、`name_cn` |
| `base_dimension_meta` | `code`、`name_cn` |
| `base_segment_decode` | `dimension`、`code`、`label_cn` |
| `base_D4_type` | `love_languages_code`、`love_languages_name` |
| `base_D5_quadrant` | `quadrant`、`style_name` |
| `questions` | `dimension`、`signal_code`、`stem` |

---

## 四、前端设计

### 整体布局

```
┌─────────────────────────────────────────────────┐
│  顶部栏：项目名 · 版本 · [刷新] [AI监控↗]         │
├───────────┬─────────────────────────────────────┤
│           │                                     │
│  侧边栏   │           主内容区                   │
│  (220px)  │    概览卡片 / 表格 / 详情面板          │
│           │                                     │
└───────────┴─────────────────────────────────────┘
```

**侧边栏分组：**
```
📊  概览
─── 业务数据 ───
👤  用户
📋  测评记录
💳  订单
─── AI 监控 ───
🤖  AI 调用日志（链接到 /admin/logs）
─── 静态配置 ───
🎭  人格类型
💡  深度洞察
📐  维度元信息
🔑  段落解码
❤️   爱的语言
🌐  表达象限
📝  题库
```

### 概览页

- 4 张大卡片：users / assessments / orders / ai_call_logs（总数 + 今日新增）
- assessments 状态分布横条（pending 灰 / analyzed 蓝 / complete 绿）
- orders 付款率环形进度（paid / total）
- 下方：最近 5 条 assessments 表格（时间、类型、状态）

### 通用表格浏览器

**布局：**
```
[搜索框________________] [每页: 50▼]  共 120 条
┌──────────────────────────────────────┐
│ id │ 字段1 │ 字段2 │ 字段3 │ 操作   │
├──────────────────────────────────────┤
│ 1  │  ...  │  ...  │  ...  │  [详情] │
│ 2  │  ...  │  ...  │  ...  │  [详情] │  ← 可编辑行：[编辑]
└──────────────────────────────────────┘
  [← 上一页]  第 1 / 3 页  [下一页 →]
```

**点击行 → 右侧滑出详情面板（400px 宽）**
- 完整字段展示
- JSON 字段（`diagnosis_json`、`report_text` 等）用 `<details>` 折叠块，点击展开格式化 JSON
- 面板顶部：`[×关闭]` + 表名 + ID

### 内联编辑（可编辑表）

1. 表格行末尾有 `✏️` 按钮（只读表不显示）
2. 点击 → 该行可编辑字段变为 `<input>` / `<textarea>`，末尾出现 `[保存] [取消]`
3. `[保存]` → `PUT /admin/api/{table}/{id}` → 成功：行闪绿；失败：行闪红 + toast
4. `[取消]` → 恢复原始值

### assessments 特殊操作

详情面板底部显示：
- 当前 status 徽章
- 若 status = `generating`：显示橙色「重置为 analyzed」按钮，点击弹确认对话框

### 视觉风格

- 深色系，与现有 `/admin/logs` 一致：背景 `#0f1117`，卡片 `#161b27`，边框 `#1e2535`
- 侧边栏当前项：左侧 3px 蓝色竖线 + 浅蓝背景
- 响应式：视口宽度 < 900px 时侧边栏折叠为 48px 图标条

---

## 五、安全边界

- 所有 `/admin/api/*` 端点通过 `require_admin` 依赖鉴权
- PUT 端点：服务端二次校验字段白名单，不依赖前端传来的字段名
- `assessments.status` 写操作：只允许 `generating → analyzed`，硬编码在服务端，前端无法绕过
- SQL 注入防护：`q` 参数通过 SQLAlchemy 参数化查询，不拼接原始字符串

---

## 六、不在范围内

- 删除记录（任何表）
- 创建新记录（任何表）
- `questions` 表编辑（由 supabase migrations 管理）
- 用户封禁 / 退款操作
- 邮件 / 推送通知

---

## 七、实现顺序

1. `admin.py`：新增 overview + 通用 table list/detail/update 端点
2. `static/admin/index.html`：侧边栏 + 概览页
3. 通用表格浏览器组件（复用于所有只读表）
4. 可编辑表格扩展（静态配置表）
5. assessments 状态重置功能
6. `app/main.py`：挂载静态目录
