const app = getApp();

Page({
  data: { paying: false, watching: false, isDev: false },

  onLoad() {
    if (!app.globalData.sessionId) {
      tt.redirectTo({ url: '/pages/index/index' });
      return;
    }
    this.setData({ isDev: app.isDev || false });
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

  async payWithMoney() {
    if (this.data.paying) return;
    const assessmentId = app.globalData.assessmentId;
    if (!assessmentId) {
      tt.showToast({ title: '订单信息有误，请重试', icon: 'none' });
      return;
    }
    this.setData({ paying: true });
    try {
      const res = await app.request({ url: '/pay/create_order', data: { assessment_id: assessmentId } });
      tt.pay({
        orderInfo: res.order_info,
        success: () => this._pollPayment(res.out_trade_no),
        fail: () => tt.showToast({ title: '支付已取消', icon: 'none' }),
      });
    } catch (_) {
      tt.showToast({ title: '创建订单失败，请重试', icon: 'none' });
    } finally {
      this.setData({ paying: false });
    }
  },

  async _pollPayment(outTradeNo) {
    // DEV_MODE：直接调模拟接口将订单置为已支付（生产环境此接口不存在，静默忽略）
    try { await app.request({ url: `/dev/pay-success?out_trade_no=${outTradeNo}` }); } catch (_) {}

    for (let i = 0; i < 5; i++) {
      await new Promise(r => setTimeout(r, 1500));
      try {
        const res = await app.request({ url: '/pay/query', data: { out_trade_no: outTradeNo } });
        if (res.status === 'paid') {
          tt.navigateTo({ url: '/pages/report/report' });
          return;
        }
      } catch (_) {}
    }
    tt.showToast({ title: '支付确认超时，稍后进入可重新查看', icon: 'none', duration: 3000 });
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
