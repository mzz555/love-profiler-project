# UI Sprint 设计规格：Unlock 页 + History 页

**日期**：2026-05-03  
**范围**：仅 UI 收尾冲刺，不含新功能  
**设计主题**：Midnight Romance（与 chat 页、report 页保持一致）

---

## 一、背景与目标

当前 unlock 页使用亮粉色浅色主题（#FFF5F8），history 页同样是浅色系，与已完成深色改版的 chat 页、report 页风格断裂。本次冲刺目标：

1. **Unlock 页**：统一深色主题 + 加入报告预览转化优化，提升用户点击广告的动力
2. **History 页**：统一深色主题 + 展示人格名称（而非仅类型码），提升列表信息密度

---

## 二、改动文件清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `miniprogram/pages/unlock/unlock.ttml` | 重写 | 新结构：预览卡 + 维度标签 + 价值行 + CTA |
| `miniprogram/pages/unlock/unlock.ttss` | 重写 | Midnight Romance 深色主题 |
| `miniprogram/pages/unlock/unlock.js` | 小改 | `onLoad` 中新增一行 `setData({ personalityType })` |
| `miniprogram/pages/history/history.ttml` | 重写 | 新结构：页头 + 富信息卡片列表 + 升级空状态 |
| `miniprogram/pages/history/history.ttss` | 重写 | Midnight Romance 深色主题 |
| `miniprogram/pages/history/history.js` | **不改** | 逻辑不变 |
| `app/api/history.py` | 小改 | HistoryItem 新增 `type_name` 字段 |

---

## 三、Unlock 页详细设计

### 3.1 页面结构（从上到下）

```
container
├── bg-orb × 3            # 与其他页一致的氛围光球
├── header                # ✨ 图标 + 标题「你的专属报告已生成」+ 副标题
├── preview-card          # 报告预览卡（核心转化模块）
│   ├── 🔒 报告已就绪 badge
│   ├── 人格名称（清晰显示）
│   ├── 类型码 + 「5 大维度深度解读」
│   └── 报告摘要文字（CSS blur 模糊）+ 渐变遮罩
├── dim-chips             # 5 个维度标签（颜色与 report 页一致）
├── value-row             # 「5维度 · AI专属 · 永久保存」三列数字
├── cta-btn               # 「🎬 免费观看广告 · 立即解锁」渐变按钮
├── note                  # 「约 15 秒短视频 · 看完即解锁」
└── dev-section           # DEV_MODE 才显示的直接解锁按钮（保留）
```

### 3.2 数据来源

| 展示内容 | 来源 |
|---------|------|
| 人格名称（如「矛盾守护者」） | `app.globalData.personalityType`（已存储于 app.js） |
| 报告摘要预览文字 | 暂用固定占位文字（无法在解锁前拿到 report_text） |

> **说明**：解锁前用户尚未生成报告，摘要文字用固定文案（「解锁后查看你在五大维度上的专属解读…」），模糊效果本身已足够制造悬念，无需展示真实内容。

### 3.3 JS 改动（unlock.js）

仅需在 `onLoad` 中增加一行读取并 setData：

```js
onLoad() {
  if (!app.globalData.assessmentId) {
    tt.redirectTo({ url: '/pages/index/index' });
    return;
  }
  this.setData({
    isDev: app.isDev || false,
    personalityType: app.globalData.personalityType || '',  // 新增
  });
},
```

### 3.4 样式规范

- 背景：`linear-gradient(160deg, #12002A 0%, #260042 35%, #1C0038 65%, #0D001E 100%)`
- 报告预览卡背景：`linear-gradient(135deg, rgba(194,24,91,0.12), rgba(123,31,162,0.08))`，边框 `rgba(255,64,129,0.2)`
- 模糊效果：`filter: blur(3.5rpx)`（TTSS 单位为 rpx）
- 渐变遮罩：`linear-gradient(180deg, transparent 15%, rgba(15,0,32,0.92) 70%)`
- 维度标签颜色：与 report.ttss 中 `.dim-item` 完全一致（5种颜色）
- CTA 按钮：`linear-gradient(135deg, #FF4081, #C2185B)`，`box-shadow: 0 6rpx 24rpx rgba(255,64,129,0.45)`

---

## 四、History 页详细设计

### 4.1 页面结构（从上到下）

```
container
├── bg-orb × 3            # 氛围光球
├── 加载状态              # 与 report 页加载态风格一致（脉冲环 + 心形）
├── 空状态                # 💌 图标 + 引导文案 + 「开始测评」按钮
└── 列表（scroll-view）
    ├── page-header        # 「历史测评记录」标题 + 「共 N 次」badge
    └── hist-card × N
        ├── 卡片顶行：人格名称 | 「查看报告 →」按钮
        ├── 副行：类型码 · 日期时间
        ├── 分隔线
        └── 摘要文字（一两行）
```

### 4.2 卡片视觉层级

| 条件 | 卡片样式 | 按钮样式 |
|------|---------|---------|
| 列表第一条（最新） | 粉→紫渐变边框背景 `rgba(194,24,91,0.14)` | 渐变主色按钮 |
| 其他历史记录 | 低调玻璃卡 `rgba(255,255,255,0.04)` | ghost 按钮 |

在 TTML 中通过 `tt:for` 的 `index` 判断：`class="hist-card {{index === 0 ? 'latest' : 'older'}}"`

### 4.3 type_name Fallback

模板：`{{item.type_name || item.personality_type}}`

- type_name 有值（新数据）：显示「矛盾守护者」
- type_name 为空字符串（旧数据 report_text 缺失）：fallback 显示类型码「MA-CL-MH」

### 4.4 空状态升级

```
💌
还没有测评记录
完成第一次测评后，报告会保存在这里

[开始测评]  →  bindtap 调用 tt.reLaunch({ url: '/pages/chat/chat' })
```

---

## 五、后端改动：history.py

### 5.1 新增工具函数

```python
import re

def _extract_type_name(report_text: str | None) -> str:
    if not report_text:
        return ""
    m = re.search(r'你是[「『"""](.+?)[」』"""]', report_text)
    return m.group(1) if m else ""
```

> 该正则与前端 `report.js` 中 `_parseReport` 使用的逻辑完全一致，已验证可靠。

### 5.2 HistoryItem 新增字段

```python
class HistoryItem(BaseModel):
    id: int
    session_id: str
    personality_type: str
    type_name: str          # 新增
    summary: str
    created_at: str
```

### 5.3 构造处新增一行

```python
HistoryItem(
    ...
    personality_type=a.personality_type or "未知",
    type_name=_extract_type_name(a.report_text),   # 新增
    summary=...,
    ...
)
```

---

## 六、错误处理

| 场景 | 处理方式 |
|------|---------|
| `type_name` 提取失败 | 返回空字符串，前端 fallback 显示 `personality_type` |
| `app.globalData.personalityType` 为空 | unlock 页人格名称区域不显示名称，仍正常渲染其余内容 |
| history 接口请求失败 | 沿用现有 toast 提示，不变 |

---

## 七、不在本次范围内

- unlock.js 广告逻辑（watchAd、onClose 等）不改动
- history.js 路由跳转逻辑不改动
- 不新增 API 端点
- 不修改数据库 schema
- 不改动 index 页、chat 页、report 页

---

## 八、完成标准

- [ ] unlock 页在字节跳动开发者工具中渲染正常，深色背景，预览卡模糊效果可见
- [ ] unlock 页「免费观看广告」按钮 loading 状态正常（unlock.js 已有逻辑）
- [ ] history 页列表第一条高亮，旧记录低调
- [ ] history 页 type_name 显示正常，fallback 到类型码时不报错
- [ ] history 页空状态「开始测评」按钮可跳转
- [ ] `/history` 接口返回的 JSON 包含 `type_name` 字段
