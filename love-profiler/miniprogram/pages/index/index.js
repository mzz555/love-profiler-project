const app = getApp();

const PHRASES = [
  '你知道自己在感情里是什么样的人吗？',
  '为什么你总是被同一类型的人吸引？',
  '你的依恋风格，决定了你如何去爱',
  '了解自己，才能遇见真正合适的人',
  '90%的情感困扰，源于不了解自己',
  '你是焦虑型、回避型，还是安全型？',
  '测一测，发现你不知道的自己',
];

Page({
  data: {
    loginReady: false,
    typewriterText: '',
    showCursor: true,
  },

  _twTimer: null,
  _cursorTimer: null,
  _phraseIdx: 0,
  _charIdx: 0,
  _deleting: false,

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
    this._startTypewriter();
    this._startCursor();
  },

  onUnload() {
    clearTimeout(this._twTimer);
    clearInterval(this._cursorTimer);
  },

  _tick() {
    const phrase = PHRASES[this._phraseIdx];
    if (!this._deleting) {
      this._charIdx++;
      this.setData({ typewriterText: phrase.slice(0, this._charIdx) });
      if (this._charIdx === phrase.length) {
        this._deleting = true;
        this._twTimer = setTimeout(() => this._tick(), 2400);
      } else {
        this._twTimer = setTimeout(() => this._tick(), 88);
      }
    } else {
      this._charIdx--;
      this.setData({ typewriterText: phrase.slice(0, this._charIdx) });
      if (this._charIdx === 0) {
        this._deleting = false;
        this._phraseIdx = (this._phraseIdx + 1) % PHRASES.length;
        this._twTimer = setTimeout(() => this._tick(), 480);
      } else {
        this._twTimer = setTimeout(() => this._tick(), 40);
      }
    }
  },

  _startTypewriter() {
    this._twTimer = setTimeout(() => this._tick(), 900);
  },

  _startCursor() {
    this._cursorTimer = setInterval(() => {
      this.setData({ showCursor: !this.data.showCursor });
    }, 530);
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
