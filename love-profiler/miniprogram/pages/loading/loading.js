const app = getApp();

const STATUS_TEXTS = [
  { text: '正在分析你的答题偏好...',   sub: 'AI 解析中 · 维度计算' },
  { text: '正在生成你的专属报告...',   sub: '深度分析中 · 人格画像' },
  { text: '即将为你揭晓...',           sub: '最后准备中 · 马上就好' },
];

Page({
  data: {
    statusText: STATUS_TEXTS[0].text,
    statusSub: STATUS_TEXTS[0].sub,
    progressPct: 15,
    imageUrl: '/images/result-placeholder.png',
    imageReady: false,
  },

  _sessionId: '',
  _pollTimer: null,
  _minDuration: 3000,
  _startTime: 0,
  _reportReady: false,

  onLoad(options) {
    const sessionId = options.session_id || app.globalData.sessionId;
    if (!sessionId) {
      tt.redirectTo({ url: '/pages/index/index' });
      return;
    }
    this._sessionId = sessionId;
    if (options.img_path) {
      const paths = decodeURIComponent(options.img_path).split(',');
      // paths[0] = man, paths[1] = woman
      const idx = (options.gender === 'male') ? 0 : 1;
      const imgUrl = 'http://localhost:8000' + (paths[idx] || paths[0]);
      this.setData({ imageUrl: imgUrl });
    }
    this._startTime = Date.now();
    this._startAnimation();
    this._pollResult();
  },

  onUnload() {
    this._cleanup();
  },

  _cleanup() {
    if (this._pollTimer) {
      clearTimeout(this._pollTimer);
      this._pollTimer = null;
    }
    if (this._animTimer) {
      clearInterval(this._animTimer);
      this._animTimer = null;
    }
  },

  /* ── 3s loading animation ─────────────────────── */

  _startAnimation() {
    this._animTimer = setInterval(() => {
      const elapsed = (Date.now() - this._startTime) / 1000;
      if (elapsed >= this._minDuration / 1000) return;
      let idx = 0;
      if (elapsed >= 2) idx = 2;
      else if (elapsed >= 1) idx = 1;
      this.setData({
        statusText: STATUS_TEXTS[idx].text,
        statusSub: STATUS_TEXTS[idx].sub,
        progressPct: Math.min(90, 15 + elapsed * 25),
      });
    }, 500);

    // 最短加载时间后无论如何都展示图片
    setTimeout(() => {
      if (this._animTimer) {
        clearInterval(this._animTimer);
        this._animTimer = null;
      }
      this.setData({
        statusText: '✨ 报告已生成',
        statusSub: '',
        progressPct: 100,
        imageReady: true,
      });
    }, this._minDuration);
  },

  /* ── Poll /result 后台异步 ────────────────────── */

  async _pollResult() {
    if (this._reportReady) return;

    try {
      const res = await app.request({
        url: '/result',
        data: { session_id: this._sessionId },
      });
      if (res.status === 'complete') {
        this._reportReady = true;
        return;
      }
    } catch (e) {
      console.log('[loading] /result error, will retry', e);
    }

    this._pollTimer = setTimeout(() => this._pollResult(), 1000);
  },

  /* ── Navigate to full report ──────────────────── */

  viewReport() {
    tt.navigateTo({ url: '/pages/report/report?session_id=' + this._sessionId });
  },
});
