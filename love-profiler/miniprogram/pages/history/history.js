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
