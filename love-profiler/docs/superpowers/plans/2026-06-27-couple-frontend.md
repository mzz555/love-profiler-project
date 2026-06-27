# 双人模式前端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为已完成的双人落差测评后端补齐抖音小程序前端，端到端跑通「A 发起 → 邀请 B → 双方双轮作答 → 异步等待 → 各自查看 7 段报告」。

**Architecture:** 新增 4 个 tt 小程序页面（couple-invite / couple-quiz / couple-wait / couple-report）+ index 微调；作答页的纯逻辑抽进可单测的 `couple-quiz-input.js`；其余为调用 4 个现成后端接口的交互胶水，沿用 `app.request` 与 token 鉴权。

**Tech Stack:** 抖音小程序（tt API，CommonJS）；后端 FastAPI（已就绪）；纯逻辑用 node 跑断言（无前端测试框架）。

## Global Constraints

- 平台：抖音小程序，使用 `tt.*` API；页面文件命名 `pages/<name>/<name>.{js,ttml,ttss,json}`。
- 代码文件 ≤ 500 行（.js/.ttml/.ttss）；超则拆模块。
- 沿用 `app.request({url, method, data})`：返回 Promise<data>，401 自动跳 index。
- 视觉沿用现有深色风格（`#08080F`），滑块手感参照 `pages/chat/chat.js`。
- 后端接口契约（不可改）：
  - `POST /couple/create` → `{session_id, pairing_token, questions}`
  - `POST /couple/join {pairing_token}` → `{session_id, questions}`
  - `POST /couple/answer {session_id, self:[{question_id,value}], predicted:[…], skipped:[id]}` → `{status}`
  - `GET /couple/result?session_id` → `409`（对方未完成）/ `{status:"generating"}` / `{status:"complete", report}`
- 题目字段：`question_id, item_type('slider'|'likert7'), stem, anchor_low, anchor_high, apply_prediction, sort_order`。
- value 取值：slider 传 0–100；likert7 传 1–7。
- 提交文案/键名 verbatim：请求体键为 `self`/`predicted`/`skipped`（注意 `self` 是后端 alias）。

---

### Task 1: 作答页纯逻辑模块 + node 单测

唯一能真正自动化测试的部分：第二段题集过滤规则、slider 拖动数学。抽成不依赖 tt 的 CommonJS 模块。

**Files:**
- Create: `miniprogram/pages/couple-quiz/couple-quiz-input.js`
- Test: `miniprogram/pages/couple-quiz/couple-quiz-input.test.js`

**Interfaces:**
- Produces:
  - `predictedQuestions(questions, skippedIds) -> question[]`：保留 `apply_prediction===true` 且 `question_id` 不在 `skippedIds` 内的题，顺序不变。
  - `posToValue(startValue, deltaX, trackWidth) -> number`：slider 拖动新值，`round(startValue + deltaX/trackWidth*100)` 再 clamp 到 [0,100]；`trackWidth` 为 0 时返回 `startValue`。

- [ ] **Step 1: 写失败测试**

```js
// couple-quiz-input.test.js
const assert = require('assert');
const { predictedQuestions, posToValue } = require('./couple-quiz-input.js');

const qs = [
  { question_id: 'A1-1', apply_prediction: true },
  { question_id: 'B1-1', apply_prediction: false },
  { question_id: 'A2-1', apply_prediction: true },
];
assert.deepStrictEqual(predictedQuestions(qs, []).map(q => q.question_id),
  ['A1-1', 'A2-1'], 'predicted 应仅含 apply_prediction');
assert.deepStrictEqual(predictedQuestions(qs, ['A1-1']).map(q => q.question_id),
  ['A2-1'], 'self 跳过的题不进 predicted');

assert.strictEqual(posToValue(50, 0, 300), 50, '无位移=原值');
assert.strictEqual(posToValue(50, 150, 300), 100, '右拖半屏 +50 clamp 100');
assert.strictEqual(posToValue(50, -300, 300), 0, '左拖满屏 clamp 0');
assert.strictEqual(posToValue(0, 0, 0), 0, 'trackWidth 0 安全返回原值');
console.log('couple-quiz-input: 全部通过');
```

- [ ] **Step 2: 跑测试确认失败**

Run: `node miniprogram/pages/couple-quiz/couple-quiz-input.test.js`
Expected: FAIL，`Cannot find module './couple-quiz-input.js'`

- [ ] **Step 3: 写最小实现**

```js
// couple-quiz-input.js — 双轮作答纯逻辑（不依赖 tt，可 node 单测）
function predictedQuestions(questions, skippedIds) {
  const skipped = new Set(skippedIds || []);
  return (questions || []).filter(q => q.apply_prediction && !skipped.has(q.question_id));
}

function posToValue(startValue, deltaX, trackWidth) {
  if (!trackWidth) return startValue;
  const v = Math.round(startValue + (deltaX / trackWidth) * 100);
  return Math.max(0, Math.min(100, v));
}

module.exports = { predictedQuestions, posToValue };
```

- [ ] **Step 4: 跑测试确认通过**

Run: `node miniprogram/pages/couple-quiz/couple-quiz-input.test.js`
Expected: PASS，输出 `couple-quiz-input: 全部通过`，exit 0

- [ ] **Step 5: 提交**

```bash
git add miniprogram/pages/couple-quiz/couple-quiz-input.js miniprogram/pages/couple-quiz/couple-quiz-input.test.js
git commit -m "feat(couple-fe): 作答页纯逻辑 predictedQuestions/posToValue + node 单测"
```

---

### Task 2: 注册新页 + index 双人入口与分享落地

注册 4 个新页；首页加「双人模式」卡片（发起 / 我有邀请码）；处理 B 点分享卡片冷启动带的 `invite_token`（自动 join）。题目经 `app.globalData.couple = {sessionId, questions}` 传给后续页。

**Files:**
- Modify: `miniprogram/app.json`（pages 数组）
- Modify: `miniprogram/pages/index/index.js`
- Modify: `miniprogram/pages/index/index.ttml`
- Modify: `miniprogram/pages/index/index.ttss`

**Interfaces:**
- Consumes: `app.request`、后端 `/couple/join`。
- Produces: `app.globalData.couple = { sessionId, questions }`（Task 4 quiz 读取）；首页方法 `goCoupleInvite/goCoupleJoin/_joinByToken`。

- [ ] **Step 1: app.json 注册 4 页**

在 `pages` 数组末尾加入：

```json
    "pages/couple-invite/couple-invite",
    "pages/couple-quiz/couple-quiz",
    "pages/couple-wait/couple-wait",
    "pages/couple-report/couple-report"
```

- [ ] **Step 2: index.js — onLoad 接收 options 并在登录后处理 invite_token**

把 `async onLoad() {` 改为 `async onLoad(options) {`，并在函数第一行存：

```js
    this._inviteToken = (options && options.invite_token) || '';
```

将原本三处「登录成功」收尾（`this.setData({ loginReady: true }); this._loadPortraits();`）统一替换为调用：

```js
    this._enterAfterLogin();
```

（OAuth 失败分支保留 `this.setData({ loginReady: true });` 不变，不进双人流程。）

- [ ] **Step 3: index.js — 新增方法**

在 `goHistory()` 之后、`Page({...})` 闭合前加入：

```js
  _enterAfterLogin() {
    this.setData({ loginReady: true });
    if (this._inviteToken) {
      this._joinByToken(this._inviteToken);
      return;
    }
    this._loadPortraits();
  },

  goCoupleInvite() {
    if (!app.globalData.token) {
      tt.showToast({ title: '登录失败，请重启小程序', icon: 'none' });
      return;
    }
    tt.navigateTo({ url: '/pages/couple-invite/couple-invite' });
  },

  goCoupleJoin() {
    if (!app.globalData.token) {
      tt.showToast({ title: '登录失败，请重启小程序', icon: 'none' });
      return;
    }
    tt.navigateTo({ url: '/pages/couple-invite/couple-invite?mode=join' });
  },

  async _joinByToken(token) {
    try {
      const res = await app.request({ url: '/couple/join', data: { pairing_token: token } });
      app.globalData.couple = { sessionId: res.session_id, questions: res.questions };
      tt.redirectTo({ url: '/pages/couple-quiz/couple-quiz?session_id=' + res.session_id });
    } catch (e) {
      const msg = (e && e.data && e.data.detail) || '加入失败，请重试';
      tt.showToast({ title: msg, icon: 'none', duration: 2500 });
      this._loadPortraits();
    }
  },
```

- [ ] **Step 4: index.ttml — 在「标准版」card 之后、footer 之前插入双人卡片**

```html
    <view class="card card-couple">
      <view class="card-top">
        <view class="card-left">
          <text class="card-title">双人模式</text>
          <text class="card-desc">和 TA 一起测，看看你们最该聊的几件事</text>
        </view>
      </view>
      <view class="couple-actions">
        <view class="couple-btn couple-btn-primary" bindtap="goCoupleInvite"><text>发起测评</text></view>
        <view class="couple-btn couple-btn-ghost" bindtap="goCoupleJoin"><text>我有邀请码</text></view>
      </view>
    </view>
```

- [ ] **Step 5: index.ttss — 追加样式**

```css
.card-couple { margin-top: 24rpx; }
.couple-actions { display: flex; gap: 20rpx; margin-top: 20rpx; }
.couple-btn { flex: 1; height: 84rpx; display: flex; align-items: center; justify-content: center; border-radius: 16rpx; font-size: 30rpx; }
.couple-btn-primary { background: #3A8A8A; color: #fff; }
.couple-btn-ghost { border: 2rpx solid #3A8A8A; color: #3A8A8A; }
```

- [ ] **Step 6: 校验语法并提交**

Run: `node -c miniprogram/pages/index/index.js`
Expected: 无输出（语法 OK）

```bash
git add miniprogram/app.json miniprogram/pages/index/
git commit -m "feat(couple-fe): 首页双人入口 + 分享落地 join + 注册新页"
```

---

### Task 3: couple-invite 页（create + join 两模式）

A 发起：create → 分享卡片 + 邀请码 + 开始作答。B 手输：join 模式 input → 加入。

**Files:**
- Create: `miniprogram/pages/couple-invite/couple-invite.js`
- Create: `miniprogram/pages/couple-invite/couple-invite.ttml`
- Create: `miniprogram/pages/couple-invite/couple-invite.ttss`
- Create: `miniprogram/pages/couple-invite/couple-invite.json`

**Interfaces:**
- Consumes: `app.request`、`/couple/create`、`/couple/join`。
- Produces: `app.globalData.couple = {sessionId, questions}`；redirect 到 `couple-quiz?session_id=`。

- [ ] **Step 1: couple-invite.js**

```js
const app = getApp();

Page({
  data: { mode: 'create', loading: true, pairingToken: '', sessionId: '', joinInput: '' },

  onLoad(options) {
    if (!app.globalData.token) { tt.redirectTo({ url: '/pages/index/index' }); return; }
    const mode = (options && options.mode) === 'join' ? 'join' : 'create';
    this.setData({ mode });
    if (mode === 'create') this._create();
    else this.setData({ loading: false });
  },

  async _create() {
    try {
      const res = await app.request({ url: '/couple/create' });
      app.globalData.couple = { sessionId: res.session_id, questions: res.questions };
      this.setData({ loading: false, pairingToken: res.pairing_token, sessionId: res.session_id });
    } catch (e) {
      tt.showToast({ title: '创建失败，请重试', icon: 'none' });
      this.setData({ loading: false });
    }
  },

  onShareAppMessage() {
    return {
      title: '我做了个双人测评，来和我一起看看我们最该聊啥',
      path: '/pages/index/index?invite_token=' + encodeURIComponent(this.data.pairingToken),
    };
  },

  copyToken() {
    tt.setClipboardData({
      data: this.data.pairingToken,
      success: () => tt.showToast({ title: '邀请码已复制', icon: 'none' }),
    });
  },

  startAnswer() {
    tt.redirectTo({ url: '/pages/couple-quiz/couple-quiz?session_id=' + this.data.sessionId });
  },

  onJoinInput(e) { this.setData({ joinInput: e.detail.value }); },

  async submitJoin() {
    const token = (this.data.joinInput || '').trim();
    if (!token) { tt.showToast({ title: '请输入邀请码', icon: 'none' }); return; }
    try {
      const res = await app.request({ url: '/couple/join', data: { pairing_token: token } });
      app.globalData.couple = { sessionId: res.session_id, questions: res.questions };
      tt.redirectTo({ url: '/pages/couple-quiz/couple-quiz?session_id=' + res.session_id });
    } catch (e) {
      const msg = (e && e.data && e.data.detail) || '加入失败，请重试';
      tt.showToast({ title: msg, icon: 'none', duration: 2500 });
    }
  },
});
```

- [ ] **Step 2: couple-invite.json**

```json
{ "navigationBarTitleText": "双人测评" }
```

- [ ] **Step 3: couple-invite.ttml**

```html
<view class="page">
  <view class="loading" tt:if="{{loading}}"><text>加载中…</text></view>

  <view class="invite" tt:if="{{!loading && mode === 'create'}}">
    <text class="title">邀请 TA 一起测</text>
    <text class="desc">把邀请发给对方，你也可以现在先开始作答。</text>
    <button class="btn btn-primary" open-type="share">分享给 TA</button>
    <view class="token-box">
      <text class="token-label">邀请码</text>
      <text class="token-val">{{pairingToken}}</text>
      <view class="btn-copy" bindtap="copyToken"><text>复制</text></view>
    </view>
    <view class="btn btn-ghost" bindtap="startAnswer"><text>开始我的作答</text></view>
  </view>

  <view class="invite" tt:if="{{!loading && mode === 'join'}}">
    <text class="title">输入邀请码</text>
    <text class="desc">粘贴对方给你的邀请码，加入这次双人测评。</text>
    <input class="join-input" placeholder="粘贴邀请码" value="{{joinInput}}" bindinput="onJoinInput" />
    <view class="btn btn-primary" bindtap="submitJoin"><text>加入</text></view>
  </view>
</view>
```

- [ ] **Step 4: couple-invite.ttss**

```css
.page { min-height: 100vh; background: #08080F; padding: 48rpx 40rpx; box-sizing: border-box; }
.loading { color: #9aa; text-align: center; margin-top: 200rpx; }
.invite { display: flex; flex-direction: column; gap: 28rpx; margin-top: 80rpx; }
.title { color: #fff; font-size: 44rpx; font-weight: 600; }
.desc { color: #9aa; font-size: 28rpx; line-height: 1.6; }
.btn { height: 92rpx; border-radius: 18rpx; display: flex; align-items: center; justify-content: center; font-size: 32rpx; }
.btn-primary { background: #3A8A8A; color: #fff; }
.btn-ghost { border: 2rpx solid #3A8A8A; color: #3A8A8A; background: transparent; }
.token-box { display: flex; align-items: center; gap: 16rpx; background: #14141f; border-radius: 16rpx; padding: 24rpx; }
.token-label { color: #9aa; font-size: 26rpx; }
.token-val { color: #ffd24a; font-size: 30rpx; flex: 1; word-break: break-all; }
.btn-copy { color: #3A8A8A; font-size: 28rpx; padding: 8rpx 16rpx; }
.join-input { background: #14141f; color: #fff; border-radius: 16rpx; padding: 28rpx; font-size: 30rpx; }
```

- [ ] **Step 5: 校验并提交**

Run: `node -c miniprogram/pages/couple-invite/couple-invite.js`
Expected: 无输出

手动验收（抖音开发者工具）：首页「发起测评」→ 显示邀请码 + 分享按钮 +「开始我的作答」；「我有邀请码」→ 输入框 + 加入。

```bash
git add miniprogram/pages/couple-invite/
git commit -m "feat(couple-fe): couple-invite 页（create 分享 + join 输入）"
```

---

### Task 4: couple-quiz 双轮作答页（核心）

从 `app.globalData.couple` 取题，两段式作答（self 全题 → predicted 仅互猜题），slider/likert 两控件，skip，最后一次性提交。

**Files:**
- Create: `miniprogram/pages/couple-quiz/couple-quiz.js`
- Create: `miniprogram/pages/couple-quiz/couple-quiz.ttml`
- Create: `miniprogram/pages/couple-quiz/couple-quiz.ttss`
- Create: `miniprogram/pages/couple-quiz/couple-quiz.json`
- (复用 Task 1 的 `couple-quiz-input.js`)

**Interfaces:**
- Consumes: `predictedQuestions`、`posToValue`（Task 1）；`app.globalData.couple`（Task 2/3）；`/couple/answer`。
- Produces: redirect 到 `couple-wait?session_id=`。

- [ ] **Step 1: couple-quiz.js（流程 + 提交）**

```js
const app = getApp();
const { predictedQuestions, posToValue } = require('./couple-quiz-input.js');

Page({
  data: {
    loading: true, submitting: false,
    phase: 'self', isPredicted: false,
    q: null, idx: 0, total: 0,
    sliderValue: 50, likertValue: 0,
    isDev: app.isDev,
  },

  onLoad(options) {
    if (!app.globalData.token) { tt.redirectTo({ url: '/pages/index/index' }); return; }
    const couple = app.globalData.couple;
    if (!couple || !couple.questions || !couple.questions.length) {
      tt.showToast({ title: '会话已失效，请重新开始', icon: 'none' });
      setTimeout(() => tt.redirectTo({ url: '/pages/index/index' }), 1500);
      return;
    }
    this._sessionId = (options && options.session_id) || couple.sessionId;
    this._questions = couple.questions.slice().sort((a, b) => a.sort_order - b.sort_order);
    this._predictedQs = [];
    this._self = []; this._predicted = []; this._skipped = [];
    this._phase = 'self'; this._idx = 0;
    this._trackWidth = 0;
    this.setData({ loading: false });
    this._renderCurrent();
  },

  onReady() { this._captureTrackWidth(); },

  _captureTrackWidth() {
    tt.createSelectorQuery().select('#cp-track')
      .boundingClientRect(r => { if (r && r.width > 0) this._trackWidth = r.width; }).exec();
  },

  _renderCurrent() {
    const list = this._phase === 'self' ? this._questions : this._predictedQs;
    if (this._idx >= list.length) { this._advancePhaseOrSubmit(); return; }
    const q = list[this._idx];
    this.setData({
      q, idx: this._idx + 1, total: list.length,
      phase: this._phase, isPredicted: this._phase === 'predicted',
      sliderValue: 50, likertValue: 0,
    });
    setTimeout(() => this._captureTrackWidth(), 100);
  },

  onNext() {
    const q = this.data.q;
    let value;
    if (q.item_type === 'slider') {
      value = this.data.sliderValue;
    } else {
      if (!this.data.likertValue) { tt.showToast({ title: '请先选择', icon: 'none' }); return; }
      value = this.data.likertValue;
    }
    if (this._phase === 'self') this._self.push({ question_id: q.question_id, value });
    else this._predicted.push({ question_id: q.question_id, value });
    this._idx++;
    this._renderCurrent();
  },

  onSkip() {
    const q = this.data.q;
    if (this._phase === 'self') this._skipped.push(q.question_id);
    this._idx++;
    this._renderCurrent();
  },

  _advancePhaseOrSubmit() {
    if (this._phase === 'self') {
      this._predictedQs = predictedQuestions(this._questions, this._skipped);
      if (this._predictedQs.length) {
        this._phase = 'predicted'; this._idx = 0; this._renderCurrent(); return;
      }
    }
    this._submit();
  },

  async _submit() {
    if (this.data.submitting) return;
    this.setData({ submitting: true });
    try {
      await app.request({ url: '/couple/answer', data: {
        session_id: this._sessionId, self: this._self,
        predicted: this._predicted, skipped: this._skipped,
      } });
      tt.redirectTo({ url: '/pages/couple-wait/couple-wait?session_id=' + this._sessionId });
    } catch (e) {
      const msg = (e && e.data && e.data.detail) || '提交失败，请重试';
      tt.showToast({ title: msg, icon: 'none', duration: 2500 });
      this.setData({ submitting: false });
    }
  },
});
```

> 注：上面 `Page({...})` 末尾的 `});` 在 Step 2 加入手势/likert/dev 方法时，需把这些方法插入到 `_submit` 之后、`});` 之前。

- [ ] **Step 2: couple-quiz.js — 插入手势 / likert / dev 方法（在 `_submit` 之后）**

```js
  onSliderTouchStart(e) {
    this._touchStartX = e.touches[0].clientX;
    this._startValue = this.data.sliderValue;
    if (!this._trackWidth) this._captureTrackWidth();
  },

  onSliderTouchMove(e) {
    if (!this._trackWidth) return;
    const deltaX = e.touches[0].clientX - this._touchStartX;
    const v = posToValue(this._startValue, deltaX, this._trackWidth);
    if (v !== this.data.sliderValue) this.setData({ sliderValue: v });
  },

  onLikertTap(e) {
    const v = parseInt(e.currentTarget.dataset.v, 10);
    if (v >= 1 && v <= 7) this.setData({ likertValue: v });
  },

  randomFill() {
    if (!app.isDev) return;
    const rnd = (q) => ({
      question_id: q.question_id,
      value: q.item_type === 'slider' ? Math.floor(Math.random() * 101) : (1 + Math.floor(Math.random() * 7)),
    });
    this._self = this._questions.map(rnd);
    this._skipped = [];
    this._predictedQs = predictedQuestions(this._questions, this._skipped);
    this._predicted = this._predictedQs.map(rnd);
    this._submit();
  },
```

- [ ] **Step 3: couple-quiz.ttml**

```html
<view class="page">
  <view class="loading" tt:if="{{loading}}"><text>加载中…</text></view>

  <view class="quiz" tt:if="{{!loading && q}}">
    <view class="topbar">
      <text class="phase-tag">{{isPredicted ? '猜猜 TA' : '关于你自己'}}</text>
      <text class="progress">{{idx}} / {{total}}</text>
    </view>

    <text class="stem">{{isPredicted ? '你猜 TA 会怎么选：' : ''}}{{q.stem}}</text>

    <view class="ctrl-slider" tt:if="{{q.item_type === 'slider'}}">
      <view class="anchors"><text>{{q.anchor_low}}</text><text>{{q.anchor_high}}</text></view>
      <view class="track" id="cp-track">
        <view class="track-fill" style="width:{{sliderValue}}%;" />
        <view class="thumb" style="left:{{sliderValue}}%;"
          bindtouchstart="onSliderTouchStart" catchtouchmove="onSliderTouchMove" />
      </view>
    </view>

    <view class="ctrl-likert" tt:if="{{q.item_type === 'likert7'}}">
      <view class="likert-row">
        <view class="dot {{likertValue === item ? 'dot-on' : ''}}"
          tt:for="{{[1,2,3,4,5,6,7]}}" tt:key="*this" data-v="{{item}}" bindtap="onLikertTap">
          <text>{{item}}</text>
        </view>
      </view>
      <view class="likert-ends"><text>很不同意</text><text>非常同意</text></view>
    </view>

    <view class="actions">
      <view class="btn btn-ghost" bindtap="onSkip"><text>跳过</text></view>
      <view class="btn btn-primary {{submitting ? 'btn-disabled' : ''}}" bindtap="onNext"><text>下一题</text></view>
    </view>

    <view class="dev-fill" tt:if="{{isDev}}" bindtap="randomFill"><text>「DEV」随机填答并提交</text></view>
  </view>
</view>
```

- [ ] **Step 4: couple-quiz.json**

```json
{ "navigationBarTitleText": "双人作答", "disableScroll": true }
```

- [ ] **Step 5: couple-quiz.ttss**

```css
.page { min-height: 100vh; background: #08080F; padding: 48rpx 40rpx; box-sizing: border-box; }
.loading { color: #9aa; text-align: center; margin-top: 200rpx; }
.quiz { display: flex; flex-direction: column; min-height: 80vh; }
.topbar { display: flex; justify-content: space-between; align-items: center; }
.phase-tag { color: #3A8A8A; font-size: 26rpx; }
.progress { color: #9aa; font-size: 26rpx; }
.stem { color: #fff; font-size: 40rpx; line-height: 1.5; margin: 80rpx 0 100rpx; }
.anchors { display: flex; justify-content: space-between; color: #9aa; font-size: 26rpx; }
.track { position: relative; height: 8rpx; background: #2a2a3a; border-radius: 8rpx; margin: 48rpx 0; }
.track-fill { position: absolute; height: 100%; background: #3A8A8A; border-radius: 8rpx; }
.thumb { position: absolute; top: 50%; width: 56rpx; height: 56rpx; margin-left: -28rpx; margin-top: -28rpx; background: #35d6e6; border-radius: 50%; }
.likert-row { display: flex; justify-content: space-between; }
.dot { width: 72rpx; height: 72rpx; border-radius: 50%; border: 2rpx solid #3A8A8A; color: #3A8A8A; display: flex; align-items: center; justify-content: center; font-size: 28rpx; }
.dot-on { background: #3A8A8A; color: #fff; }
.likert-ends { display: flex; justify-content: space-between; color: #9aa; font-size: 24rpx; margin-top: 20rpx; }
.actions { display: flex; gap: 24rpx; margin-top: auto; padding-top: 80rpx; }
.btn { flex: 1; height: 92rpx; border-radius: 18rpx; display: flex; align-items: center; justify-content: center; font-size: 32rpx; }
.btn-primary { background: #3A8A8A; color: #fff; }
.btn-ghost { border: 2rpx solid #3A8A8A; color: #3A8A8A; }
.btn-disabled { opacity: 0.5; }
.dev-fill { text-align: center; color: #ffd24a; font-size: 24rpx; margin-top: 32rpx; }
```

- [ ] **Step 6: 校验、回归、提交**

Run: `node -c miniprogram/pages/couple-quiz/couple-quiz.js`
Expected: 无输出

Run: `node miniprogram/pages/couple-quiz/couple-quiz-input.test.js`
Expected: PASS（回归绿）

手动验收（抖音开发者工具）：slider 可拖动、likert 可点选、跳过生效；self 段答完自动进 predicted 段（问法变「你猜 TA」）；最后提交跳 couple-wait；dev「随机填答」一键跑通。

```bash
git add miniprogram/pages/couple-quiz/
git commit -m "feat(couple-fe): couple-quiz 双轮作答页（slider/likert + 两段 + 提交）"
```

---

### Task 5: couple-wait 等待轮询页

每 3s 轮询 result：409→等对方；generating→等报告；complete→缓存 report 跳 report 页。可退出。

**Files:**
- Create: `miniprogram/pages/couple-wait/couple-wait.{js,ttml,ttss,json}`

**Interfaces:**
- Consumes: `/couple/result`。
- Produces: `app.globalData.coupleReport`；redirect 到 `couple-report?session_id=`。

- [ ] **Step 1: couple-wait.js**

```js
const app = getApp();
const POLL_INTERVAL = 3000;
const MAX_POLLS = 100;

Page({
  data: { statusText: '正在同步…', canExit: false },

  onLoad(options) {
    if (!app.globalData.token) { tt.redirectTo({ url: '/pages/index/index' }); return; }
    this._sessionId = (options && options.session_id)
      || (app.globalData.couple && app.globalData.couple.sessionId);
    if (!this._sessionId) { tt.redirectTo({ url: '/pages/index/index' }); return; }
    this._polls = 0;
    this._poll();
  },

  onUnload() { this._stop(); },
  _stop() { if (this._timer) { clearTimeout(this._timer); this._timer = null; } },

  async _poll() {
    this._polls++;
    try {
      const res = await app.request({
        url: '/couple/result', method: 'GET', data: { session_id: this._sessionId },
      });
      if (res && res.status === 'complete') {
        app.globalData.coupleReport = res.report;
        tt.redirectTo({ url: '/pages/couple-report/couple-report?session_id=' + this._sessionId });
        return;
      }
      this.setData({ statusText: '正在生成报告…' });
    } catch (e) {
      if (e && e.statusCode === 409) {
        this.setData({ statusText: '等待对方完成作答…', canExit: true });
      }
      // 其它网络错误：静默重试
    }
    if (this._polls >= MAX_POLLS) {
      this.setData({ statusText: '还在处理中，你可以稍后再回来看', canExit: true });
      return;
    }
    this._timer = setTimeout(() => this._poll(), POLL_INTERVAL);
  },

  exitWait() { tt.redirectTo({ url: '/pages/index/index' }); },
});
```

- [ ] **Step 2: couple-wait.ttml**

```html
<view class="page">
  <view class="wait">
    <view class="spinner" />
    <text class="status">{{statusText}}</text>
    <view class="btn-exit" tt:if="{{canExit}}" bindtap="exitWait"><text>稍后再来看</text></view>
  </view>
</view>
```

- [ ] **Step 3: couple-wait.ttss**

```css
.page { min-height: 100vh; background: #08080F; }
.wait { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; gap: 40rpx; }
.spinner { width: 72rpx; height: 72rpx; border: 6rpx solid #2a2a3a; border-top-color: #35d6e6; border-radius: 50%; animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.status { color: #cdd; font-size: 30rpx; }
.btn-exit { margin-top: 20rpx; border: 2rpx solid #3A8A8A; color: #3A8A8A; padding: 18rpx 48rpx; border-radius: 16rpx; font-size: 28rpx; }
```

- [ ] **Step 4: couple-wait.json**

```json
{ "navigationBarTitleText": "等待结果" }
```

- [ ] **Step 5: 校验并提交**

Run: `node -c miniprogram/pages/couple-wait/couple-wait.js`
Expected: 无输出

手动验收：A 先提交后停在「等待对方完成作答…」并出现「稍后再来看」；B 提交后转「正在生成报告…」→ 跳 couple-report。

```bash
git add miniprogram/pages/couple-wait/
git commit -m "feat(couple-fe): couple-wait 轮询等待页"
```

---

### Task 6: couple-report 7 段报告页

渲染 report 7 段，盲区卡片为主菜，空段（MVP 的 landscape/strengths）优雅跳过；优先用 `app.globalData.coupleReport`，无则按 session_id 兜底拉取。

**Files:**
- Create: `miniprogram/pages/couple-report/couple-report.{js,ttml,ttss,json}`

**Interfaces:**
- Consumes: `app.globalData.coupleReport`（Task 5）；兜底 `/couple/result`。
- report 形状：`opening{headline,body}` / `how_to_read{body}` / `blindspot_cards[{title,body,talk_prompt}]` / `landscape[{title,body}]` / `strengths{body}` / `next_steps{body,invitations[]}` / `closing{body}` / `quality_warnings[]`。

- [ ] **Step 1: couple-report.js**

```js
const app = getApp();

Page({
  data: { loading: true, report: null, isDev: app.isDev },

  onLoad(options) {
    if (!app.globalData.token) { tt.redirectTo({ url: '/pages/index/index' }); return; }
    const cached = app.globalData.coupleReport;
    if (cached) { this.setData({ loading: false, report: cached }); return; }
    this._sessionId = options && options.session_id;
    if (this._sessionId) this._fetch();
    else tt.redirectTo({ url: '/pages/index/index' });
  },

  async _fetch() {
    try {
      const res = await app.request({
        url: '/couple/result', method: 'GET', data: { session_id: this._sessionId },
      });
      if (res && res.status === 'complete') this.setData({ loading: false, report: res.report });
      else tt.redirectTo({ url: '/pages/couple-wait/couple-wait?session_id=' + this._sessionId });
    } catch (e) {
      tt.showToast({ title: '报告加载失败，请重试', icon: 'none' });
      this.setData({ loading: false });
    }
  },

  backHome() { tt.redirectTo({ url: '/pages/index/index' }); },
});
```

- [ ] **Step 2: couple-report.json**

```json
{ "navigationBarTitleText": "双人报告" }
```

- [ ] **Step 3: couple-report.ttml**

```html
<view class="page">
  <view class="loading" tt:if="{{loading}}"><text>加载中…</text></view>

  <scroll-view scroll-y class="report" tt:if="{{!loading && report}}">
    <view class="sec sec-opening">
      <text class="headline">{{report.opening.headline}}</text>
      <text class="body">{{report.opening.body}}</text>
    </view>

    <view class="sec" tt:if="{{report.how_to_read.body}}">
      <text class="body dim">{{report.how_to_read.body}}</text>
    </view>

    <view class="sec">
      <text class="sec-title">最值得聊的几件事</text>
      <view class="card" tt:for="{{report.blindspot_cards}}" tt:key="dimension_id">
        <text class="card-title">{{item.title}}</text>
        <text class="card-body">{{item.body}}</text>
        <view class="talk" tt:if="{{item.talk_prompt}}"><text>💬 {{item.talk_prompt}}</text></view>
      </view>
    </view>

    <view class="sec" tt:if="{{report.landscape.length}}">
      <text class="sec-title">你们的关系地形</text>
      <view class="land" tt:for="{{report.landscape}}" tt:key="supercluster">
        <text class="land-title">{{item.title}}</text>
        <text class="body">{{item.body}}</text>
      </view>
    </view>

    <view class="sec" tt:if="{{report.strengths.body}}">
      <text class="sec-title">你们的互补面</text>
      <text class="body">{{report.strengths.body}}</text>
    </view>

    <view class="sec" tt:if="{{report.next_steps.body}}">
      <text class="sec-title">可以从这里聊起</text>
      <text class="body">{{report.next_steps.body}}</text>
      <view class="invite-item" tt:for="{{report.next_steps.invitations}}" tt:key="*this"><text>· {{item}}</text></view>
    </view>

    <view class="sec sec-closing" tt:if="{{report.closing.body}}">
      <text class="body dim">{{report.closing.body}}</text>
    </view>

    <view class="sec warn" tt:if="{{isDev && report.quality_warnings.length}}">
      <text class="warn-title">「DEV」质检告警</text>
      <text class="body" tt:for="{{report.quality_warnings}}" tt:key="*this">{{item}}</text>
    </view>

    <view class="btn-home" bindtap="backHome"><text>回到首页</text></view>
  </scroll-view>
</view>
```

- [ ] **Step 4: couple-report.ttss**

```css
.page { min-height: 100vh; background: #08080F; }
.loading { color: #9aa; text-align: center; margin-top: 200rpx; }
.report { height: 100vh; padding: 48rpx 40rpx; box-sizing: border-box; }
.sec { margin-bottom: 56rpx; }
.sec-opening .headline { color: #fff; font-size: 46rpx; font-weight: 600; display: block; margin-bottom: 24rpx; }
.body { color: #cdd; font-size: 30rpx; line-height: 1.7; display: block; }
.dim { color: #9aa; font-size: 28rpx; }
.sec-title { color: #35d6e6; font-size: 34rpx; font-weight: 600; display: block; margin-bottom: 28rpx; }
.card { background: #14141f; border-radius: 20rpx; padding: 32rpx; margin-bottom: 28rpx; }
.card-title { color: #ffd24a; font-size: 32rpx; font-weight: 600; display: block; margin-bottom: 18rpx; }
.card-body { color: #ddd; font-size: 29rpx; line-height: 1.7; display: block; }
.talk { margin-top: 24rpx; padding: 20rpx; background: #0f2a2a; border-radius: 14rpx; color: #9fe; font-size: 27rpx; }
.land-title { color: #fff; font-size: 30rpx; display: block; margin-bottom: 12rpx; }
.invite-item { color: #cdd; font-size: 28rpx; margin-top: 16rpx; }
.sec-closing { margin-top: 40rpx; }
.warn { border: 2rpx dashed #ffd24a; border-radius: 14rpx; padding: 24rpx; }
.warn-title { color: #ffd24a; font-size: 26rpx; display: block; margin-bottom: 12rpx; }
.btn-home { text-align: center; color: #3A8A8A; border: 2rpx solid #3A8A8A; border-radius: 18rpx; padding: 24rpx; font-size: 30rpx; margin: 40rpx 0 80rpx; }
```

- [ ] **Step 5: 校验并提交**

Run: `node -c miniprogram/pages/couple-report/couple-report.js`
Expected: 无输出

手动验收：从 couple-wait 自动跳入，7 段按序渲染，盲区卡片含「💬 talk_prompt」；MVP 下 landscape/strengths 不出现（空段跳过）；dev 下显示质检告警。

```bash
git add miniprogram/pages/couple-report/
git commit -m "feat(couple-fe): couple-report 7 段报告页"
```

---

### Task 7: 端到端联调与收尾

把能自动化的全部跑绿，给出真机/工具手动验收脚本，记录双账号限制。

**Files:** 无新增（仅联调修复）。

- [ ] **Step 1: 全量语法检查**

Run:
```bash
node -c miniprogram/pages/index/index.js
node -c miniprogram/pages/couple-invite/couple-invite.js
node -c miniprogram/pages/couple-quiz/couple-quiz.js
node -c miniprogram/pages/couple-quiz/couple-quiz-input.js
node -c miniprogram/pages/couple-wait/couple-wait.js
node -c miniprogram/pages/couple-report/couple-report.js
```
Expected: 全部无输出。

- [ ] **Step 2: 纯逻辑回归**

Run: `node miniprogram/pages/couple-quiz/couple-quiz-input.test.js`
Expected: `couple-quiz-input: 全部通过`

- [ ] **Step 3: 手动端到端验收（抖音开发者工具）**

单账号可验证：
1. 首页见「双人模式」卡片。
2. 「发起测评」→ couple-invite 显示邀请码 + 「分享给 TA」+「开始我的作答」。
3. 作答：self 段 slider 可拖、likert 可选、可跳过；自动进 predicted 段（问法变「你猜 TA」）；提交后 couple-wait 停在「等待对方完成作答…」。
4. dev「随机填答并提交」一键直达 couple-wait。

需第二账号（A≠B，后端 `/couple/join` 拒绝自我配对）：
5. 第二账号点 A 的分享卡片（带 `invite_token`）或在「我有邀请码」粘贴 → join → 作答 → 提交。
6. 双方完成 → couple-wait 转「正在生成报告…」→ 跳 couple-report，7 段按序渲染、盲区卡片为主菜。

> **已知限制（验收用）**：完整「双方完成→报告」需两个不同用户；单账号 dev-login 通常固定同一 user_id，无法独自走完。建议两台设备 / 两个抖音号，或临时在后端 dev 造第二方答案。couple-report 页可单独验证：dev 下临时把一份 report 赋给 `app.globalData.coupleReport` 再进入该页。

- [ ] **Step 4: 收尾提交（若联调有改动）**

```bash
git add -A
git commit -m "fix(couple-fe): 端到端联调修复"
```

---

## 验收与交付口径

- **可由 agent 自动验证**：全部新 js `node -c` 语法、`couple-quiz-input` node 单测、ttml 标签配平。
- **需人工（抖音开发者工具/真机）**：所有 UI 渲染与交互、双账号端到端闭环。环境无 GUI 浏览器/小程序模拟器，agent 无法代跑这部分。
- 后端 4 接口已有 pytest 覆盖（428 绿），前端只新增胶水，不改后端。
