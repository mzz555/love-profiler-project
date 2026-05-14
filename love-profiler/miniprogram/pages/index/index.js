const app = getApp();

Page({
  data: {
    loginReady: false,
  },

  async onLoad() {
    if (app.globalData.token) {
      this.setData({ loginReady: true });
    } else {
      try {
        const res = await app.request({ url: '/auth/dev-login' });
        app.setToken(res.token);
      } catch (_) {}
      this.setData({ loginReady: true });
    }
  },

  startQuick() {
    if (!app.globalData.token) {
      tt.showToast({ title: '登录中，请稍候', icon: 'none' });
      return;
    }
    tt.navigateTo({ url: '/pages/chat/chat' });
  },

  comingSoon() {
    tt.showToast({ title: '敬请期待', icon: 'none', duration: 1500 });
  },

  goHistory() {
    tt.navigateTo({ url: '/pages/history/history' });
  },
});
