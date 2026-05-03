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
    this._ad = ad;
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
    await this._ad.show().catch(() => {
      this.setData({ watching: false });
    });
  },
});
