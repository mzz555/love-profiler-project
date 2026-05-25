const app = getApp();

Page({
  data: { watching: false, isDev: false, personalityType: '' },
  _ad: null,

  onLoad() {
    if (!app.globalData.assessmentId) {
      tt.redirectTo({ url: '/pages/index/index' });
      return;
    }
    this.setData({
      isDev: app.isDev || false,
      personalityType: app.globalData.personalityType || '',
    });
    this._initAd();
  },

  onUnload() {
    this.setData({ watching: false });
  },

  _initAd() {
    // TODO: 上线前替换为真实 adUnitId
    const ad = tt.createRewardedVideoAd({ adUnitId: 'your-ad-unit-id' });
    ad.onError(() => {
      tt.showToast({ title: '广告加载失败，请稍后再试', icon: 'none' });
      this.setData({ watching: false });
    });
    ad.onClose(async (res) => {
      if (!res.isEnded) {
        tt.showToast({ title: '请看完广告再解锁哦', icon: 'none' });
        this.setData({ watching: false });
        return;
      }
      const transId = (res && res.transId) || ('client-' + Date.now());
      try {
        await app.request({
          url: '/unlock/ad',
          data: {
            assessment_id: app.globalData.assessmentId,
            ad_token: transId,
            signature: this._signToken(transId),
          },
        });
        tt.navigateTo({ url: '/pages/report/report' });
      } catch (_) {
        tt.showToast({ title: '解锁失败，请重试', icon: 'none' });
      } finally {
        this.setData({ watching: false });
      }
    });
    this._ad = ad;
  },

  _signToken(token) {
    // TODO: 长期应改为服务端到服务端回调，不依赖客户端签名
    // 当前用简单 hash 占位，后端 DEV_MODE 时跳过验签
    return 'client-sig-' + token.slice(0, 8);
  },

  async devUnlock() {
    if (!app.isDev) return;
    try {
      await app.request({
        url: '/unlock/ad',
        data: { assessment_id: app.globalData.assessmentId, ad_token: 'dev-bypass', signature: '' },
      });
      tt.navigateTo({ url: '/pages/report/report' });
    } catch (_) {
      tt.showToast({ title: '解锁失败，请检查服务是否运行', icon: 'none' });
    }
  },

  async watchAd() {
    if (this.data.watching) return;
    this.setData({ watching: true });
    await this._ad.show().catch(() => {
      this.setData({ watching: false });
    });
  },
});
