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
