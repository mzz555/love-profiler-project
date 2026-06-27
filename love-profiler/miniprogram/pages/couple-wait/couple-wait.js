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
