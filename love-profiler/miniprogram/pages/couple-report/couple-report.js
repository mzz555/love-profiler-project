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
