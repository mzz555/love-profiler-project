const app = getApp();
const WS_URL = app.isDev
  ? 'ws://localhost:8000/ws/chat'
  : 'wss://your-production-domain.com/ws/chat';

Page({
  data: {
    messages: [], inputValue: '', sessionId: null,
    roundNum: 0, isComplete: false, sending: false, starting: true, scrollId: '',
    options: [],
    isTyping: false, currentTyping: '',
  },

  // Internal state — not in data to avoid setData overhead
  _ws: null,
  _chunkQueue: [],      // chars waiting to be rendered
  _isProcessing: false, // whether the queue consumer is running

  onLoad() {
    if (!app.globalData.token) {
      tt.redirectTo({ url: '/pages/index/index' });
      return;
    }
    if (app.globalData.sessionId) {
      this.setData({
        sessionId: app.globalData.sessionId,
        starting: false,
        messages: [{ role: 'assistant', content: '欢迎回来！继续我们上次的对话吧。' }],
      });
      this._connectWS();
      tt.showToast({ title: '已恢复上次对话', icon: 'none' });
    } else {
      this._startSession();
    }
  },

  onUnload() {
    if (this._ws) {
      this._ws.close();
      this._ws = null;
    }
  },

  // ─── Session setup ─────────────────────────────────────────────────────────

  async _startSession() {
    try {
      const res = await app.request({ url: '/start' });
      app.setSession(res.session_id, res.assessment_id);
      this.setData({
        sessionId: res.session_id, roundNum: res.round_num, starting: false,
        messages: [{ role: 'assistant', content: res.message }],
        options: res.options || [],
      });
      this._scrollToBottom();
      this._connectWS();
    } catch (_) {
      tt.showToast({ title: '启动失败，请重试', icon: 'none' });
      this.setData({ starting: false });
    }
  },

  // ─── WebSocket ─────────────────────────────────────────────────────────────

  _connectWS() {
    const token = app.globalData.token;
    if (!token) return;
    this._ws = tt.connectSocket({
      url: `${WS_URL}?token=${token}`,
    });
    this._ws.onMessage(({ data }) => {
      try {
        const msg = JSON.parse(data);
        if (msg.type === 'chunk') this._appendChunk(msg.text);
        else if (msg.type === 'done') this._handleDone(msg);
        else if (msg.type === 'error') this._handleWSError(msg);
      } catch (_) {}
    });
    this._ws.onError(() => {
      tt.showToast({ title: '连接异常，请刷新重试', icon: 'none', duration: 2500 });
      this.setData({ sending: false });
    });
    this._ws.onClose(() => { this._ws = null; });
  },

  // ─── Chunk queue — renders characters with punctuation-aware rhythm ─────────

  _appendChunk(text) {
    for (const char of text) this._chunkQueue.push(char);
    if (!this._isProcessing) this._processQueue();
  },

  _processQueue() {
    if (this._chunkQueue.length === 0) {
      this._isProcessing = false;
      return;
    }
    this._isProcessing = true;
    const char = this._chunkQueue.shift();
    this.setData({
      isTyping: true,
      currentTyping: this.data.currentTyping + char,
      scrollId: 'typing-bubble',
    });
    let delay = 60;
    if ('。！？…'.includes(char)) delay = 380;
    else if ('，；：、'.includes(char)) delay = 130;
    setTimeout(() => this._processQueue(), delay);
  },

  _handleDone(msg) {
    // Wait for queue to drain before finalising
    if (this._chunkQueue.length > 0 || this._isProcessing) {
      setTimeout(() => this._handleDone(msg), 50);
      return;
    }
    const fullText = this.data.currentTyping;
    const newMsgIdx = this.data.messages.length;
    this.setData({
      messages: [...this.data.messages, { role: 'assistant', content: fullText }],
      isTyping: false,
      currentTyping: '',
      roundNum: msg.round_num,
      isComplete: msg.is_complete,
      scrollId: 'msg-' + newMsgIdx,
      sending: false,
    });
    if (msg.is_complete) this._onComplete();
  },

  _handleWSError(msg) {
    this.setData({ sending: false, isTyping: false, currentTyping: '' });
    this._chunkQueue = [];
    this._isProcessing = false;
    const code = msg.code;
    if (code === 404) {
      app.clearSession();
      tt.showModal({
        title: '会话已过期', content: '上次对话已失效，需要重新开始', showCancel: false,
        success: () => {
          this.setData({ messages: [], starting: true });
          this._startSession();
        },
      });
    } else {
      const tip = code === 422 ? '消息包含不安全内容，请重新输入' : 'AI 服务暂时不可用，请稍后再试';
      tt.showToast({ title: tip, icon: 'none', duration: 2500 });
    }
  },

  // ─── User input ────────────────────────────────────────────────────────────

  onInput(e) { this.setData({ inputValue: e.detail.value }); },

  pickOption(e) {
    const text = e.currentTarget.dataset.text;
    if (!text || this.data.sending) return;
    this.setData({ options: [] });
    this._sendText(text);
  },

  sendMessage() {
    const text = (this.data.inputValue || '').trim();
    if (!text || this.data.sending || this.data.isComplete) return;
    this.setData({ inputValue: '' });
    this._sendText(text);
  },

  _sendText(text) {
    if (!this._ws) {
      tt.showToast({ title: '连接中，请稍候', icon: 'none' });
      return;
    }
    this.setData({
      messages: [...this.data.messages, { role: 'user', content: text }],
      sending: true,
      currentTyping: '',
    });
    this._chunkQueue = [];
    this._scrollToBottom();
    this._ws.send({
      data: JSON.stringify({ session_id: this.data.sessionId, message: text }),
    });
  },

  // ─── Completion & navigation ───────────────────────────────────────────────

  _onComplete() {
    setTimeout(() => {
      tt.showModal({
        title: '测评完成 🎉',
        content: '你的恋爱人格分析已生成，是否立即查看？',
        confirmText: '查看报告', cancelText: '稍后再看',
        success: ({ confirm }) => {
          if (confirm) tt.navigateTo({ url: '/pages/unlock/unlock' });
        },
      });
    }, 800);
  },

  _scrollToBottom() {
    if (this.data.isTyping) {
      this.setData({ scrollId: 'typing-bubble' });
      return;
    }
    setTimeout(() => {
      this.setData({ scrollId: 'msg-' + (this.data.messages.length - 1) });
    }, 50);
  },
});
