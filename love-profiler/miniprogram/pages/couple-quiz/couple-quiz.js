const app = getApp();
const { predictedQuestions, posToValue } = require('./couple-quiz-input.js');

Page({
  data: {
    loading: true, submitting: false,
    phase: 'self', isPredicted: false,
    q: null, idx: 0, total: 0,
    sliderValue: 50, likertValue: 0,
    isDev: app.isDev,
  },

  onLoad(options) {
    if (!app.globalData.token) { tt.redirectTo({ url: '/pages/index/index' }); return; }
    const couple = app.globalData.couple;
    if (!couple || !couple.questions || !couple.questions.length) {
      tt.showToast({ title: '会话已失效，请重新开始', icon: 'none' });
      setTimeout(() => tt.redirectTo({ url: '/pages/index/index' }), 1500);
      return;
    }
    this._sessionId = (options && options.session_id) || couple.sessionId;
    this._questions = couple.questions.slice().sort((a, b) => a.sort_order - b.sort_order);
    this._predictedQs = [];
    this._self = []; this._predicted = []; this._skipped = [];
    this._phase = 'self'; this._idx = 0;
    this._trackWidth = 0;
    this.setData({ loading: false });
    this._renderCurrent();
  },

  onReady() { this._captureTrackWidth(); },

  _captureTrackWidth() {
    tt.createSelectorQuery().select('#cp-track')
      .boundingClientRect(r => { if (r && r.width > 0) this._trackWidth = r.width; }).exec();
  },

  _renderCurrent() {
    const list = this._phase === 'self' ? this._questions : this._predictedQs;
    if (this._idx >= list.length) { this._advancePhaseOrSubmit(); return; }
    const q = list[this._idx];
    this.setData({
      q, idx: this._idx + 1, total: list.length,
      phase: this._phase, isPredicted: this._phase === 'predicted',
      sliderValue: 50, likertValue: 0,
    });
    setTimeout(() => this._captureTrackWidth(), 100);
  },

  onNext() {
    const q = this.data.q;
    let value;
    if (q.item_type === 'slider') {
      value = this.data.sliderValue;
    } else {
      if (!this.data.likertValue) { tt.showToast({ title: '请先选择', icon: 'none' }); return; }
      value = this.data.likertValue;
    }
    if (this._phase === 'self') this._self.push({ question_id: q.question_id, value });
    else this._predicted.push({ question_id: q.question_id, value });
    this._idx++;
    this._renderCurrent();
  },

  onSkip() {
    const q = this.data.q;
    if (this._phase === 'self') this._skipped.push(q.question_id);
    this._idx++;
    this._renderCurrent();
  },

  _advancePhaseOrSubmit() {
    if (this._phase === 'self') {
      this._predictedQs = predictedQuestions(this._questions, this._skipped);
      if (this._predictedQs.length) {
        this._phase = 'predicted'; this._idx = 0; this._renderCurrent(); return;
      }
    }
    this._submit();
  },

  async _submit() {
    if (this.data.submitting) return;
    this.setData({ submitting: true });
    try {
      await app.request({ url: '/couple/answer', data: {
        session_id: this._sessionId, self: this._self,
        predicted: this._predicted, skipped: this._skipped,
      } });
      tt.redirectTo({ url: '/pages/couple-wait/couple-wait?session_id=' + this._sessionId });
    } catch (e) {
      const msg = (e && e.data && e.data.detail) || '提交失败，请重试';
      tt.showToast({ title: msg, icon: 'none', duration: 2500 });
      this.setData({ submitting: false });
    }
  },

  onSliderTouchStart(e) {
    this._touchStartX = e.touches[0].clientX;
    this._startValue = this.data.sliderValue;
    if (!this._trackWidth) this._captureTrackWidth();
  },

  onSliderTouchMove(e) {
    if (!this._trackWidth) return;
    const deltaX = e.touches[0].clientX - this._touchStartX;
    const v = posToValue(this._startValue, deltaX, this._trackWidth);
    if (v !== this.data.sliderValue) this.setData({ sliderValue: v });
  },

  onLikertTap(e) {
    const v = parseInt(e.currentTarget.dataset.v, 10);
    if (v >= 1 && v <= 7) this.setData({ likertValue: v });
  },

  randomFill() {
    if (!app.isDev) return;
    const rnd = (q) => ({
      question_id: q.question_id,
      value: q.item_type === 'slider' ? Math.floor(Math.random() * 101) : (1 + Math.floor(Math.random() * 7)),
    });
    this._self = this._questions.map(rnd);
    this._skipped = [];
    this._predictedQs = predictedQuestions(this._questions, this._skipped);
    this._predicted = this._predictedQs.map(rnd);
    this._submit();
  },
});
