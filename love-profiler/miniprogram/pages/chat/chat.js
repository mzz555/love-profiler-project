const app = getApp();

Page({
  data: {
    starting: true,
    isComplete: false,
    sending: false,
    isDev: app.isDev,

    questionNum: 0,
    totalQuestions: 30,
    currentStem: '',
    options: [],
    orbDists: [],

    sliderPos: 0,
    displayText: '',
    isDragging: false,
    questionKey: 0,
    contentAnimClass: 'anim-a',
  },

  _questions: [],
  _answers: [],
  _sessionId: null,
  _currentIdx: 0,
  _gender: 'female',
  _trackWidth: 0,
  _touchStartX: 0,
  _startPos: 0,

  onLoad(options) {
    if (!app.globalData.token) {
      tt.redirectTo({ url: '/pages/index/index' });
      return;
    }
    if (options.gender) this._gender = options.gender;
    this._startQuiz();
  },

  onReady() {
    this._captureTrackWidth();
  },

  noop() {},

  _captureTrackWidth() {
    tt.createSelectorQuery()
      .select('#orb-track')
      .boundingClientRect(rect => {
        if (rect && rect.width > 0) this._trackWidth = rect.width;
      })
      .exec();
  },

  _computeOrbDists(pos, n) {
    const d = [];
    for (let i = 0; i < n; i++) d.push(Math.abs(i - pos));
    return d;
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
    // 4选项：a,b 在左(0,1)，中间补位(2)空，c,d 在右(3,4)
    // 5选项：a,b,c,d,e 依次填满五个位置
    const raw = ['a', 'b', 'c', 'd', 'e'].map(l => q[`option_${l}`] || '');
    const has5 = !!raw[4];
    const options = has5
      ? raw.map((text, i) => ({ letter: String.fromCharCode(65 + i), text }))
      : [
          { letter: 'A', text: raw[0] },
          { letter: 'B', text: raw[1] },
          { letter: '',  text: '' },
          { letter: 'C', text: raw[2] },
          { letter: 'D', text: raw[3] },
        ];

    const initPos = 2; // 始终居中

    this.setData({
      currentStem: q.stem,
      options,
      orbDists: this._computeOrbDists(initPos, 5),
      questionNum: idx + 1,
      sliderPos: initPos,
      displayText: options[initPos]?.text || '',
      isDragging: false,
      questionKey: this.data.questionKey + 1,
      contentAnimClass: 'anim-a',
    });

    setTimeout(() => this._captureTrackWidth(), 120);
  },

  _updateSliderTo(pos, triggerAnim = false) {
    const { options } = this.data;
    const update = {
      sliderPos: pos,
      orbDists: this._computeOrbDists(pos, 5),
      displayText: options[pos].text,
    };
    if (triggerAnim) {
      update.contentAnimClass = this.data.contentAnimClass === 'anim-a' ? 'anim-b' : 'anim-a';
    }
    this.setData(update);
  },

  onSliderTouchStart(e) {
    this._touchStartX = e.touches[0].clientX;
    this._startPos = this.data.sliderPos;
    if (!this._trackWidth) this._captureTrackWidth();
    this.setData({ isDragging: true });
  },

  onSliderTouchMove(e) {
    if (!this._trackWidth) return;
    const deltaX = e.touches[0].clientX - this._touchStartX;
    let newPos = Math.round(this._startPos + deltaX * 4 / this._trackWidth);
    newPos = Math.max(0, Math.min(4, newPos));
    if (newPos !== this.data.sliderPos) {
      this._updateSliderTo(newPos, false);
    }
  },

  onSliderTouchEnd() {
    this.setData({ isDragging: false });
    this.setData({
      contentAnimClass: this.data.contentAnimClass === 'anim-a' ? 'anim-b' : 'anim-a',
    });
  },

  onOrbTap(e) {
    const idx = parseInt(e.currentTarget.dataset.idx, 10);
    if (!isNaN(idx)) this._updateSliderTo(idx, true);
  },

  onConfirm() {
    if (this.data.isComplete || this.data.sending) return;
    const { options, sliderPos } = this.data;
    const option = options[sliderPos];
    if (!option || !option.letter) return; // 补位无答案，不可提交
    const q = this._questions[this._currentIdx];
    this._answers.push({ question_id: q.question_id, chosen_option: option.letter.toLowerCase() });
    this._currentIdx++;
    this._showQuestion(this._currentIdx);
  },

  goToPrevQuestion() {
    if (this._currentIdx <= 0) return;
    this._answers.pop();
    this._currentIdx--;
    this._showQuestion(this._currentIdx);
  },

  randomPick() {
    if (!getApp().isDev) return;
    if (this.data.isComplete || this.data.sending || !this._questions.length) return;
    for (let i = this._currentIdx; i < this._questions.length; i++) {
      const q = this._questions[i];
      const opts = ['a', 'b', 'c', 'd', 'e'].filter(l => q[`option_${l}`]);
      if (opts.length) {
        const pick = opts[Math.floor(Math.random() * opts.length)];
        this._answers.push({ question_id: q.question_id, chosen_option: pick });
      }
    }
    this._currentIdx = this._questions.length;
    this.setData({ options: [], questionNum: this._questions.length });
    this._submitAnswers();
  },

  async _submitAnswers() {
    this.setData({ isComplete: true, sending: true });
    try {
      const res = await app.request({
        url: '/quiz/submit',
        data: { session_id: this._sessionId, answers: this._answers },
      });
      const imgPath = (res && res.img_path) ? encodeURIComponent(res.img_path) : '';
      setTimeout(() => tt.navigateTo({
        url: '/pages/report/report?session_id=' + this._sessionId + '&img_path=' + imgPath + '&gender=' + this._gender,
      }), 800);
    } catch (err) {
      const msg = (err && err.data && err.data.detail) ? err.data.detail : '提交失败，请重试';
      tt.showToast({ title: msg, icon: 'none', duration: 3000 });
      this.setData({ sending: false, isComplete: false });
      this._currentIdx--;
      this._showQuestion(this._currentIdx);
    }
  },

  goBack() {
    tt.navigateBack();
  },

  closeQuiz() {
    if (this.data.isComplete || this.data.sending) return;
    tt.redirectTo({ url: '/pages/index/index' });
  },
});
