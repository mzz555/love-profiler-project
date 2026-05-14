# UI Sprint: Unlock 页 + History 页 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 unlock 页和 history 页从亮粉色浅色主题统一为 Midnight Romance 深色主题，同时为 unlock 页加入报告预览转化优化，为 history 页加入人格名称展示。

**Architecture:** 后端 history.py 新增 `_extract_type_name` 纯函数，从 `report_text` 正则提取人格名称写入 HistoryItem；前端两页各自重写 ttml/ttss，共享与 chat 页、report 页一致的 Midnight Romance 样式语言（深紫渐变背景 + 氛围光球 + 半透明玻璃卡片）。

**Tech Stack:** FastAPI / Pydantic（后端）、抖音小程序 TTML/TTSS/JS（前端）、pytest（测试）

---

## 文件结构

```
love-profiler/
├── app/api/history.py                    # 修改：加 _extract_type_name + type_name 字段
├── tests/api/test_history.py             # 新建：纯函数测试 + 端点集成测试
├── miniprogram/pages/unlock/
│   ├── unlock.js                         # 小改：data 加 personalityType，onLoad 读取
│   ├── unlock.ttml                       # 重写：新结构
│   └── unlock.ttss                       # 重写：深色主题
└── miniprogram/pages/history/
    ├── history.js                        # 小改：加 goStart 方法
    ├── history.ttml                      # 重写：新结构
    └── history.ttss                      # 重写：深色主题
```

---

## Task 1：后端 — history.py 加 type_name 字段

**Files:**
- Modify: `app/api/history.py`
- Create: `tests/api/test_history.py`

- [ ] **Step 1：写失败测试**

新建文件 `tests/api/test_history.py`，内容如下：

```python
"""
Tests for GET /history and _extract_type_name helper.
"""

import pytest

from app.api.history import _extract_type_name
from app.models.assessment import Assessment
from app.models.user import User


# ── 纯函数测试 ────────────────────────────────────────────────────────────────

def test_extract_type_name_chinese_corner_bracket():
    assert _extract_type_name('你是「矛盾守护者」，在感情中') == '矛盾守护者'

def test_extract_type_name_white_corner_bracket():
    assert _extract_type_name('你是『安稳探索者』，拥有') == '安稳探索者'

def test_extract_type_name_curly_quotes():
    assert _extract_type_name('你是“细腻感知者”，') == '细腻感知者'

def test_extract_type_name_none_input():
    assert _extract_type_name(None) == ''

def test_extract_type_name_empty_string():
    assert _extract_type_name('') == ''

def test_extract_type_name_no_match():
    assert _extract_type_name('这是一段没有类型名的普通文字') == ''


# ── 端点集成测试 ──────────────────────────────────────────────────────────────

def _make_user_and_headers(db_session, openid="o_history_test"):
    from app.middleware.auth import create_access_token
    user = User(openid=openid)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(user.id)
    return user, {"Authorization": f"Bearer {token}"}


def test_history_returns_type_name(client, db_session):
    user, headers = _make_user_and_headers(db_session)
    assessment = Assessment(
        user_id=user.id,
        session_id="sess-hist-1",
        signals="{}",
        status="complete",
        personality_type="MA-CL-MH",
        report_text='你是「矛盾守护者」，在感情中展现出矛盾性。',
    )
    db_session.add(assessment)
    db_session.commit()

    response = client.get("/history", headers=headers)

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["type_name"] == "矛盾守护者"
    assert items[0]["personality_type"] == "MA-CL-MH"


def test_history_type_name_empty_when_report_text_missing(client, db_session):
    user, headers = _make_user_and_headers(db_session, "o_history_empty")
    assessment = Assessment(
        user_id=user.id,
        session_id="sess-hist-2",
        signals="{}",
        status="complete",
        personality_type="S-BL-HP",
        report_text=None,
    )
    db_session.add(assessment)
    db_session.commit()

    response = client.get("/history", headers=headers)

    assert response.status_code == 200
    items = response.json()
    assert items[0]["type_name"] == ""


def test_history_only_returns_complete_assessments(client, db_session):
    user, headers = _make_user_and_headers(db_session, "o_history_status")
    db_session.add(Assessment(
        user_id=user.id, session_id="sess-pending",
        signals="{}", status="pending",
    ))
    db_session.add(Assessment(
        user_id=user.id, session_id="sess-complete",
        signals="{}", status="complete",
        personality_type="S-BL-HP",
        report_text='你是「稳定者」。',
    ))
    db_session.commit()

    response = client.get("/history", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["session_id"] == "sess-complete"


def test_history_requires_auth(client):
    response = client.get("/history")
    assert response.status_code in (401, 403)
```

- [ ] **Step 2：运行测试，确认全部失败**

```
cd love-profiler
pytest tests/api/test_history.py -v
```

期望输出：`ImportError` 或 `FAILED`（`_extract_type_name` 和 `type_name` 字段尚不存在）

- [ ] **Step 3：实现 history.py 改动**

将 `app/api/history.py` 完整替换为以下内容：

```python
"""
History API — return the authenticated user's completed assessments.
GET /history  →  list[HistoryItem]
"""

import logging
import re

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.limiter import limiter
from app.middleware.auth import get_current_user_id
from app.models.assessment import Assessment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/history", tags=["history"])


def _extract_type_name(report_text: str | None) -> str:
    if not report_text:
        return ""
    m = re.search(r'你是[「『“”"](.+?)[」』“”"]', report_text)
    return m.group(1) if m else ""


class HistoryItem(BaseModel):
    id: int
    session_id: str
    personality_type: str
    type_name: str
    summary: str
    created_at: str


@router.get("", response_model=list[HistoryItem])
@limiter.limit("20/minute")
async def get_history(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[HistoryItem]:
    """Return the last 20 completed assessments for the authenticated user."""
    assessments = (
        db.query(Assessment)
        .filter(Assessment.user_id == user_id, Assessment.status == "complete")
        .order_by(Assessment.created_at.desc())
        .limit(20)
        .all()
    )
    logger.info("[/history] user_id=%s 查询历史 count=%d", user_id, len(assessments))
    return [
        HistoryItem(
            id=a.id,
            session_id=a.session_id,
            personality_type=a.personality_type or "未知",
            type_name=_extract_type_name(a.report_text),
            summary=a.summary or (
                a.report_text.split("。")[0] + "。"
                if a.report_text and "。" in a.report_text
                else (a.report_text or "")[:50]
            ),
            created_at=a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "",
        )
        for a in assessments
    ]
```

- [ ] **Step 4：运行测试，确认全部通过**

```
pytest tests/api/test_history.py -v
```

期望输出：所有测试 `PASSED`

- [ ] **Step 5：提交**

```bash
git add app/api/history.py tests/api/test_history.py
git commit -m "feat: add type_name to /history response via regex extraction"
```

---

## Task 2：Unlock 页完整改版

**Files:**
- Modify: `miniprogram/pages/unlock/unlock.js`
- Modify: `miniprogram/pages/unlock/unlock.ttml`
- Modify: `miniprogram/pages/unlock/unlock.ttss`

前端无自动化测试框架，完成后在字节跳动开发者工具中目视验证。

- [ ] **Step 1：改 unlock.js（加 personalityType）**

将 `miniprogram/pages/unlock/unlock.js` 完整替换为：

```js
const app = getApp();

Page({
  data: { watching: false, isDev: false, personalityType: '' },

  onLoad() {
    if (!app.globalData.assessmentId) {
      tt.redirectTo({ url: '/pages/index/index' });
      return;
    }
    this.setData({
      isDev: app.isDev || false,
      personalityType: app.globalData.personalityType || '',
    });
  },

  async devUnlock() {
    if (!app.isDev) return;
    try {
      await app.request({
        url: '/unlock/ad',
        data: { assessment_id: app.globalData.assessmentId, ad_token: 'dev-bypass' },
      });
      tt.navigateTo({ url: '/pages/report/report' });
    } catch (_) {
      tt.showToast({ title: '解锁失败，请检查服务是否运行', icon: 'none' });
    }
  },

  async watchAd() {
    if (this.data.watching) return;
    this.setData({ watching: true });
    const ad = tt.createRewardedVideoAd({ adUnitId: 'your-ad-unit-id' });
    ad.onError(() => {
      tt.showToast({ title: '广告加载失败，请稍后再试', icon: 'none' });
      this.setData({ watching: false });
    });
    ad.onClose(async ({ isEnded }) => {
      if (!isEnded) {
        tt.showToast({ title: '请看完广告再解锁哦', icon: 'none' });
        this.setData({ watching: false });
        return;
      }
      try {
        await app.request({
          url: '/unlock/ad',
          data: { assessment_id: app.globalData.assessmentId, ad_token: 'ad-complete' },
        });
        tt.navigateTo({ url: '/pages/report/report' });
      } catch (_) {
        tt.showToast({ title: '解锁失败，请重试', icon: 'none' });
      } finally {
        this.setData({ watching: false });
      }
    });
    await ad.show().catch(() => {
      tt.showToast({ title: '广告暂时不可用', icon: 'none' });
      this.setData({ watching: false });
    });
  },
});
```

- [ ] **Step 2：重写 unlock.ttml**

将 `miniprogram/pages/unlock/unlock.ttml` 完整替换为：

```xml
<view class="container">
  <view class="bg-orb bg-orb-1" />
  <view class="bg-orb bg-orb-2" />
  <view class="bg-orb bg-orb-3" />

  <view class="unlock-header">
    <text class="unlock-icon">✨</text>
    <text class="unlock-title">你的专属报告已生成</text>
    <text class="unlock-sub">观看一则短视频广告，即可免费查看你的恋爱人格分析</text>
  </view>

  <view class="preview-card">
    <view class="preview-lock-bar">
      <text class="lock-badge">🔒 报告已就绪</text>
    </view>
    <text class="preview-type-name">{{personalityType || '你的恋爱人格'}}</text>
    <text class="preview-type-code">5 大维度深度解读</text>
    <view class="preview-text-wrap">
      <text class="preview-text">解锁后查看你在五大维度上的专属解读，了解你在亲密关系中的依恋风格、边界感知、冲突应对模式、情感需求倾向与表达风格……</text>
      <view class="preview-fade">
        <text class="preview-fade-hint">解锁后查看完整报告</text>
      </view>
    </view>
  </view>

  <view class="dim-chips">
    <text class="chip chip-red">🫂 依恋风格</text>
    <text class="chip chip-blue">🌊 边界感</text>
    <text class="chip chip-purple">⚡ 冲突模式</text>
    <text class="chip chip-pink">💝 情感需求</text>
    <text class="chip chip-yellow">🎭 表达风格</text>
  </view>

  <view class="value-row">
    <view class="value-item">
      <text class="value-num">5</text>
      <text class="value-label">维度解读</text>
    </view>
    <view class="value-item">
      <text class="value-num">AI</text>
      <text class="value-label">专属分析</text>
    </view>
    <view class="value-item">
      <text class="value-num">永久</text>
      <text class="value-label">保存可回看</text>
    </view>
  </view>

  <button class="cta-btn" loading="{{watching}}" bindtap="watchAd">🎬 免费观看广告 · 立即解锁</button>
  <text class="note-text">约 15 秒短视频 · 看完即解锁</text>

  <view tt:if="{{isDev}}" class="dev-section">
    <button class="dev-btn" bindtap="devUnlock">🛠 开发模式直接解锁</button>
  </view>
</view>
```

- [ ] **Step 3：重写 unlock.ttss**

将 `miniprogram/pages/unlock/unlock.ttss` 完整替换为：

```css
page { background: #12002A; }

.container {
  min-height: 100vh;
  background: linear-gradient(160deg, #12002A 0%, #260042 35%, #1C0038 65%, #0D001E 100%);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 60rpx 40rpx 60rpx;
  position: relative;
}

/* ── Ambient Orbs ───────────────────────────────── */
.bg-orb { position: fixed; border-radius: 50%; pointer-events: none; z-index: 0; }
.bg-orb-1 { width: 600rpx; height: 600rpx; top: -100rpx; right: -150rpx; background: radial-gradient(circle, rgba(194,24,91,0.20) 0%, transparent 70%); }
.bg-orb-2 { width: 500rpx; height: 500rpx; bottom: 240rpx; left: -140rpx; background: radial-gradient(circle, rgba(123,31,162,0.16) 0%, transparent 70%); }
.bg-orb-3 { width: 360rpx; height: 360rpx; bottom: -60rpx; right: -60rpx; background: radial-gradient(circle, rgba(255,64,129,0.12) 0%, transparent 70%); }

/* ── Header ─────────────────────────────────────── */
.unlock-header {
  position: relative; z-index: 1;
  display: flex; flex-direction: column; align-items: center;
  margin-bottom: 36rpx;
}
.unlock-icon { font-size: 72rpx; margin-bottom: 16rpx; }
.unlock-title { font-size: 38rpx; font-weight: 700; color: #fff; letter-spacing: 1rpx; margin-bottom: 12rpx; }
.unlock-sub { font-size: 26rpx; color: rgba(248,187,208,0.6); text-align: center; line-height: 1.6; }

/* ── Preview Card ────────────────────────────────── */
.preview-card {
  position: relative; z-index: 1; width: 100%;
  background: linear-gradient(135deg, rgba(194,24,91,0.12), rgba(123,31,162,0.08));
  border: 1rpx solid rgba(255,64,129,0.2);
  border-radius: 24rpx; padding: 28rpx;
  margin-bottom: 28rpx;
  display: flex; flex-direction: column; gap: 12rpx;
}
.preview-lock-bar { display: flex; align-items: center; }
.lock-badge {
  background: rgba(255,64,129,0.15);
  border: 1rpx solid rgba(255,64,129,0.35);
  border-radius: 20rpx; padding: 4rpx 18rpx;
  font-size: 22rpx; color: #FF6B9D; font-weight: 600;
}
.preview-type-name { font-size: 36rpx; font-weight: 700; color: #fff; }
.preview-type-code { font-size: 22rpx; color: rgba(255,255,255,0.35); }
.preview-text-wrap { position: relative; overflow: hidden; border-radius: 8rpx; }
.preview-text {
  display: block;
  font-size: 26rpx; color: rgba(255,255,255,0.22);
  line-height: 1.7; padding-bottom: 60rpx;
}
.preview-fade {
  position: absolute; bottom: 0; left: 0; right: 0; height: 130rpx;
  background: linear-gradient(180deg, transparent 0%, rgba(13,0,30,0.97) 65%);
  display: flex; align-items: flex-end; justify-content: center; padding-bottom: 12rpx;
}
.preview-fade-hint { font-size: 20rpx; color: rgba(255,255,255,0.28); letter-spacing: 1rpx; }

/* ── Dimension Chips ─────────────────────────────── */
.dim-chips {
  position: relative; z-index: 1; width: 100%;
  display: flex; flex-wrap: wrap; gap: 12rpx; justify-content: center;
  margin-bottom: 32rpx;
}
.chip { border-radius: 20rpx; padding: 6rpx 20rpx; font-size: 22rpx; font-weight: 500; }
.chip-red    { background: rgba(255,123,110,0.12); border: 1rpx solid rgba(255,123,110,0.3); color: #FF7B6E; }
.chip-blue   { background: rgba(79,195,247,0.12);  border: 1rpx solid rgba(79,195,247,0.3);  color: #4FC3F7; }
.chip-purple { background: rgba(206,147,216,0.12); border: 1rpx solid rgba(206,147,216,0.3); color: #CE93D8; }
.chip-pink   { background: rgba(244,143,177,0.12); border: 1rpx solid rgba(244,143,177,0.3); color: #F48FB1; }
.chip-yellow { background: rgba(255,183,77,0.12);  border: 1rpx solid rgba(255,183,77,0.3);  color: #FFB74D; }

/* ── Value Row ───────────────────────────────────── */
.value-row {
  position: relative; z-index: 1; width: 100%;
  display: flex; justify-content: center; gap: 60rpx;
  margin-bottom: 36rpx;
}
.value-item { display: flex; flex-direction: column; align-items: center; gap: 6rpx; }
.value-num  { font-size: 36rpx; font-weight: 700; color: #FF4081; }
.value-label { font-size: 20rpx; color: rgba(255,255,255,0.35); }

/* ── CTA Button ──────────────────────────────────── */
.cta-btn {
  position: relative; z-index: 1; width: 100%;
  background: linear-gradient(135deg, #FF4081, #C2185B);
  color: #fff; border-radius: 50rpx;
  height: 96rpx; line-height: 96rpx;
  font-size: 32rpx; font-weight: 700; border: none;
  box-shadow: 0 6rpx 24rpx rgba(255,64,129,0.45);
  margin-bottom: 16rpx;
}
.note-text {
  position: relative; z-index: 1;
  font-size: 22rpx; color: rgba(255,255,255,0.25);
  margin-bottom: 40rpx;
}

/* ── Dev Section ─────────────────────────────────── */
.dev-section { position: relative; z-index: 1; width: 100%; }
.dev-btn {
  width: 100%; height: 72rpx; line-height: 72rpx;
  background: transparent; color: rgba(255,255,255,0.25);
  border-radius: 36rpx; font-size: 26rpx;
  border: 1rpx dashed rgba(255,255,255,0.15);
}
```

- [ ] **Step 4：在开发者工具中目视验证**

打开字节跳动开发者工具，导航到 unlock 页，检查：
- 深色渐变背景可见，氛围光球存在
- 报告预览卡有「🔒 报告已就绪」badge，类型名显示（若 personalityType 为空显示「你的恋爱人格」）
- 预览文字颜色极浅，渐变遮罩覆盖文字底部，「解锁后查看完整报告」提示可见
- 5 个维度标签彩色显示
- CTA 按钮渐变粉色，点击有 loading 状态（需广告 SDK 才能实际触发，开发者工具中 loading 属性响应即可）
- DEV_MODE 时开发模式按钮可见，非 DEV_MODE 时不显示

- [ ] **Step 5：提交**

```bash
git add miniprogram/pages/unlock/unlock.js miniprogram/pages/unlock/unlock.ttml miniprogram/pages/unlock/unlock.ttss
git commit -m "feat: unlock page — Midnight Romance theme + report preview conversion design"
```

---

## Task 3：History 页完整改版

**Files:**
- Modify: `miniprogram/pages/history/history.js`
- Modify: `miniprogram/pages/history/history.ttml`
- Modify: `miniprogram/pages/history/history.ttss`

- [ ] **Step 1：改 history.js（加 goStart 方法）**

将 `miniprogram/pages/history/history.js` 完整替换为：

```js
const app = getApp();

Page({
  data: { loading: true, list: [] },

  onLoad() {
    if (!app.globalData.token) {
      tt.redirectTo({ url: '/pages/index/index' });
      return;
    }
    this._loadHistory();
  },

  async _loadHistory() {
    try {
      const list = await app.request({ url: '/history', method: 'GET' });
      this.setData({ loading: false, list });
    } catch (_) {
      tt.showToast({ title: '加载失败，请重试', icon: 'none' });
      this.setData({ loading: false });
    }
  },

  viewReport(e) {
    const sessionId = e.currentTarget.dataset.sessionId;
    tt.navigateTo({ url: '/pages/report/report?session_id=' + sessionId });
  },

  goStart() {
    tt.reLaunch({ url: '/pages/chat/chat' });
  },
});
```

- [ ] **Step 2：重写 history.ttml**

将 `miniprogram/pages/history/history.ttml` 完整替换为：

```xml
<view class="container">
  <view class="bg-orb bg-orb-1" />
  <view class="bg-orb bg-orb-2" />
  <view class="bg-orb bg-orb-3" />

  <!-- Loading -->
  <view tt:if="{{loading}}" class="state-wrap">
    <view class="loading-pulse-ring" />
    <view class="loading-pulse-ring loading-ring-delay" />
    <text class="loading-heart">💗</text>
    <text class="state-text">加载中…</text>
  </view>

  <!-- Empty state -->
  <view tt:elif="{{list.length === 0}}" class="state-wrap">
    <text class="state-emoji">💌</text>
    <text class="state-title">还没有测评记录</text>
    <text class="state-text">完成第一次测评后，报告会保存在这里</text>
    <button class="start-btn" bindtap="goStart">开始测评</button>
  </view>

  <!-- List -->
  <block tt:else>
    <view class="page-header">
      <text class="page-title">历史测评记录</text>
      <text class="count-badge">共 {{list.length}} 次</text>
    </view>
    <scroll-view scroll-y class="list">
      <view
        tt:for="{{list}}"
        tt:key="id"
        class="hist-card {{index === 0 ? 'latest' : 'older'}}"
        bindtap="viewReport"
        data-session-id="{{item.session_id}}"
      >
        <view class="card-top">
          <view class="card-left">
            <text class="type-name">{{item.type_name || item.personality_type}}</text>
            <text class="type-meta">{{item.personality_type}} · {{item.created_at}}</text>
          </view>
          <text class="view-btn {{index === 0 ? 'primary' : 'ghost'}}">查看报告 →</text>
        </view>
        <view class="card-divider" />
        <text class="card-summary">{{item.summary}}</text>
      </view>
      <view class="list-bottom-pad" />
    </scroll-view>
  </block>
</view>
```

- [ ] **Step 3：重写 history.ttss**

将 `miniprogram/pages/history/history.ttss` 完整替换为：

```css
page { background: #12002A; }

.container {
  height: 100vh;
  background: linear-gradient(160deg, #12002A 0%, #260042 35%, #1C0038 65%, #0D001E 100%);
  display: flex;
  flex-direction: column;
  position: relative;
}

/* ── Ambient Orbs ───────────────────────────────── */
.bg-orb { position: fixed; border-radius: 50%; pointer-events: none; z-index: 0; }
.bg-orb-1 { width: 600rpx; height: 600rpx; top: -100rpx; right: -150rpx; background: radial-gradient(circle, rgba(194,24,91,0.18) 0%, transparent 70%); }
.bg-orb-2 { width: 500rpx; height: 500rpx; bottom: 200rpx; left: -140rpx; background: radial-gradient(circle, rgba(123,31,162,0.14) 0%, transparent 70%); }
.bg-orb-3 { width: 360rpx; height: 360rpx; bottom: -60rpx; right: -60rpx; background: radial-gradient(circle, rgba(255,64,129,0.10) 0%, transparent 70%); }

/* ── Loading / Empty State ───────────────────────── */
.state-wrap {
  flex: 1; min-height: 0;
  position: relative; z-index: 1;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 16rpx;
}
.loading-pulse-ring {
  position: absolute;
  width: 140rpx; height: 140rpx; border-radius: 50%;
  border: 2rpx solid rgba(255,64,129,0.4);
  animation: pulse-expand 2s ease-out infinite;
}
.loading-ring-delay { animation-delay: 1s; }
@keyframes pulse-expand {
  0%   { transform: scale(0.8); opacity: 0.8; }
  100% { transform: scale(2.4); opacity: 0; }
}
.loading-heart { font-size: 56rpx; animation: heart-beat 1.4s ease-in-out infinite; }
@keyframes heart-beat {
  0%, 100% { transform: scale(1); }
  50%       { transform: scale(1.15); }
}

/* ── Empty State ─────────────────────────────────── */
.state-emoji { font-size: 80rpx; opacity: 0.7; }
.state-title { font-size: 32rpx; font-weight: 600; color: #F8BBD0; }
.state-text  { font-size: 26rpx; color: rgba(255,255,255,0.35); text-align: center; line-height: 1.7; padding: 0 48rpx; }
.start-btn {
  margin-top: 16rpx;
  background: linear-gradient(135deg, #FF4081, #C2185B);
  color: #fff; border-radius: 40rpx;
  height: 80rpx; line-height: 80rpx;
  font-size: 28rpx; font-weight: 600; border: none;
  padding: 0 48rpx;
  box-shadow: 0 4rpx 16rpx rgba(255,64,129,0.35);
}

/* ── Page Header ─────────────────────────────────── */
.page-header {
  flex-shrink: 0; position: relative; z-index: 2;
  padding: 24rpx 32rpx 16rpx;
  background: rgba(18,0,42,0.75);
  border-bottom: 1rpx solid rgba(255,255,255,0.06);
  display: flex; justify-content: space-between; align-items: center;
}
.page-title { font-size: 34rpx; font-weight: 700; color: #fff; letter-spacing: 0.5rpx; }
.count-badge {
  background: rgba(255,64,129,0.12);
  border: 1rpx solid rgba(255,64,129,0.25);
  border-radius: 20rpx; padding: 4rpx 16rpx;
  font-size: 22rpx; color: #FF6B9D;
}

/* ── List ────────────────────────────────────────── */
.list { flex: 1; min-height: 0; }
.list-bottom-pad { height: 40rpx; }

/* ── History Card ────────────────────────────────── */
.hist-card {
  margin: 16rpx 24rpx 0;
  border-radius: 20rpx; padding: 24rpx 24rpx 20rpx;
  display: flex; flex-direction: column; gap: 14rpx;
}
.hist-card.latest {
  background: linear-gradient(135deg, rgba(194,24,91,0.14), rgba(123,31,162,0.10));
  border: 1rpx solid rgba(255,64,129,0.25);
}
.hist-card.older {
  background: rgba(255,255,255,0.04);
  border: 1rpx solid rgba(255,255,255,0.07);
}

/* ── Card Top Row ────────────────────────────────── */
.card-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 16rpx; }
.card-left { flex: 1; display: flex; flex-direction: column; gap: 6rpx; }
.type-name { font-size: 30rpx; font-weight: 700; color: #fff; }
.type-meta { font-size: 20rpx; color: rgba(255,255,255,0.3); }
.view-btn {
  flex-shrink: 0; border-radius: 20rpx; padding: 6rpx 18rpx;
  font-size: 22rpx; font-weight: 600; white-space: nowrap;
}
.view-btn.primary {
  background: linear-gradient(135deg, #FF4081, #7B1FA2); color: #fff;
}
.view-btn.ghost {
  background: rgba(255,255,255,0.06);
  border: 1rpx solid rgba(255,255,255,0.1);
  color: rgba(255,255,255,0.4);
}

/* ── Card Divider & Summary ──────────────────────── */
.card-divider { height: 1rpx; background: rgba(255,255,255,0.07); }
.card-summary { font-size: 24rpx; color: rgba(255,255,255,0.42); line-height: 1.7; display: block; }
```

- [ ] **Step 4：在开发者工具中目视验证**

导航到 history 页，分别验证三种状态：

**加载状态**（在 `_loadHistory` 前手动延迟可触发）：深色背景，脉冲环 + 心形 loading

**空状态**（无历史记录时）：💌 图标，引导文案，「开始测评」渐变按钮可点击并跳转至 chat 页

**列表状态**（有记录时）：
- 第一条为粉色渐变边框高亮卡，其余为低调玻璃卡
- 人格名称（如「矛盾守护者」）显示在类型码之上
- 旧数据无 type_name 时 fallback 显示类型码，不报错
- 「查看报告 →」按钮第一条为渐变主色，其余为 ghost 样式
- 点击卡片可跳转到对应报告页

- [ ] **Step 5：提交**

```bash
git add miniprogram/pages/history/history.js miniprogram/pages/history/history.ttml miniprogram/pages/history/history.ttss
git commit -m "feat: history page — Midnight Romance theme + type_name rich cards + empty state upgrade"
```

---

## 完成验收清单

对应 spec 第八节：

- [ ] unlock 页深色背景渲染正常，预览卡渐变遮罩可见
- [ ] unlock 页「免费观看广告」按钮 loading 状态正常
- [ ] history 页第一条记录高亮，旧记录低调样式
- [ ] history 页 type_name 有值时显示人格名称，为空时 fallback 到类型码，不报错
- [ ] history 页空状态「开始测评」按钮跳转到 chat 页
- [ ] `pytest tests/api/test_history.py -v` 全部通过
