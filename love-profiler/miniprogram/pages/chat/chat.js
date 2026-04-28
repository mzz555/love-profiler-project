const app = getApp();

Page({
  data: {
    messages: [],
    starting: true,
    sending: false,
    scrollId: '',
    options: [],
    questionNum: 0,
    totalQuestions: 30,
    isComplete: false,
  },

  _questions: [],
  _answers: [],
  _sessionId: null,
  _currentIdx: 0,

  onLoad() {
    if (!app.globalData.token) {
      tt.redirectTo({ url: '/pages/index/index' });
      return;
    }
    this._startQuiz();
  },

  async _startQuiz() {
    try {
      const res = await app.request({ url: '/quiz/start' });
      this._questions = res.questions;
      this._sessionId = res.session_id;
      app.setSession(res.session_id, res.assessment_id);
      this.setData({ starting: false });
      this._showQuestion(0);
    } catch (_) {
      tt.showToast({ title: '加载题目失败，请重试', icon: 'none' });
      this.setData({ starting: false });
    }
  },

  _showQuestion(idx) {
    if (idx >= this._questions.length) {
      this._submitAnswers();
      return;
    }
    const q = this._questions[idx];
    const options = ['a', 'b', 'c', 'd', 'e']
      .filter(l => q[`option_${l}`])
      .map(l => ({ letter: l, text: q[`option_${l}`] }));

    const newMsgIdx = this.data.messages.length;
    this.setData({
      messages: [...this.data.messages, { role: 'assistant', content: q.stem }],
      options,
      questionNum: idx + 1,
      scrollId: 'msg-' + newMsgIdx,
    });
  },

  pickOption(e) {
    if (this.data.isComplete || this.data.sending) return;
    const { letter, text } = e.currentTarget.dataset;
    const q = this._questions[this._currentIdx];
    this._answers.push({ question_id: q.question_id, chosen_option: letter });

    const newMsgIdx = this.data.messages.length;
    this.setData({
      messages: [...this.data.messages, { role: 'user', content: text }],
      options: [],
      scrollId: 'msg-' + newMsgIdx,
    });
    this._currentIdx++;
    setTimeout(() => this._showQuestion(this._currentIdx), 400);
  },

  async _submitAnswers() {
    this.setData({ sending: true, isComplete: true });
    try {
      await app.request({
        url: '/quiz/submit',
        data: { session_id: this._sessionId, answers: this._answers },
      });
      const doneIdx = this.data.messages.length;
      this.setData({
        messages: [
          ...this.data.messages,
          { role: 'assistant', content: '✨ 30 道题全部完成！你的恋爱人格画像正在生成中...' },
        ],
        sending: false,
        scrollId: 'msg-' + doneIdx,
      });
      setTimeout(() => tt.navigateTo({ url: '/pages/unlock/unlock' }), 1500);
    } catch (_) {
      tt.showToast({ title: '提交失败，请重试', icon: 'none' });
      this.setData({ sending: false, isComplete: false });
      this._currentIdx--;
      this._showQuestion(this._currentIdx);
    }
  },
});
