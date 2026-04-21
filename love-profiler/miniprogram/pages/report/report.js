const app = getApp();

function _roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.arcTo(x + w, y, x + w, y + r, r);
  ctx.lineTo(x + w, y + h - r);
  ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
  ctx.lineTo(x + r, y + h);
  ctx.arcTo(x, y + h, x, y + h - r, r);
  ctx.lineTo(x, y + r);
  ctx.arcTo(x, y, x + r, y, r);
  ctx.closePath();
}

function _wrapText(ctx, text, maxWidth) {
  const lines = [];
  let line = '';
  for (const char of text) {
    const test = line + char;
    if (ctx.measureText(test).width > maxWidth && line) {
      lines.push(line);
      line = char;
    } else {
      line = test;
    }
  }
  if (line) lines.push(line);
  return lines;
}

Page({
  data: {
    loading: true,
    personalityType: '',
    reportText: '',
    sessionId: '',
    isHistory: false,
    showPoster: false,
    posterPath: '',
  },

  onLoad(options) {
    const sessionId = options.session_id || app.globalData.sessionId;
    if (!sessionId) {
      tt.redirectTo({ url: '/pages/index/index' });
      return;
    }
    this.setData({ sessionId, isHistory: !!options.session_id });
    this._loadReport(sessionId);
  },

  async _loadReport(sessionId) {
    try {
      const res = await app.request({ url: '/result', data: { session_id: sessionId } });
      this.setData({ loading: false, personalityType: res.personality_type, reportText: res.report_text });
    } catch (err) {
      this.setData({ loading: false });
      const code = err && err.statusCode;
      if (code === 402) {
        tt.showModal({
          title: '报告未解锁',
          content: '请先完成解锁步骤（付费或观看广告）',
          showCancel: false,
          success: () => tt.navigateBack(),
        });
      } else if (code === 400) {
        tt.showToast({ title: '测评尚未完成，请继续作答', icon: 'none', duration: 3000 });
        setTimeout(() => tt.navigateBack(), 1500);
      } else {
        tt.showToast({ title: 'AI服务暂时不可用，请稍后重试', icon: 'none', duration: 3000 });
      }
    }
  },

  restart() {
    app.clearSession();
    tt.reLaunch({ url: '/pages/chat/chat' });
  },

  goHistory() {
    tt.navigateTo({ url: '/pages/history/history' });
  },

  generatePoster() {
    tt.showLoading({ title: '生成中...' });
    const { personalityType, reportText } = this.data;
    const summary = reportText.includes('。')
      ? reportText.split('。')[0] + '。'
      : reportText.slice(0, 60);

    const ctx = tt.createCanvasContext('poster', this);
    const W = 375, H = 600;

    // 背景渐变
    const bg = ctx.createLinearGradient(0, 0, 0, H);
    bg.addColorStop(0, '#FF6B9D');
    bg.addColorStop(1, '#C2185B');
    ctx.setFillStyle(bg);
    ctx.fillRect(0, 0, W, H);

    // 右上装饰圆
    ctx.setFillStyle('rgba(255,255,255,0.1)');
    ctx.beginPath();
    ctx.arc(W - 30, 50, 90, 0, Math.PI * 2);
    ctx.fill();

    // 白色卡片
    ctx.setFillStyle('#fff');
    ctx.setShadow(0, 8, 20, 'rgba(0,0,0,0.15)');
    _roundRect(ctx, 20, 140, W - 40, 330, 20);
    ctx.fill();
    ctx.setShadow(0, 0, 0, 'transparent');

    // Emoji
    ctx.setTextAlign('center');
    ctx.setFontSize(52);
    ctx.setFillStyle('#fff');
    ctx.fillText('💝', W / 2, 68);

    // 应用名
    ctx.setFillStyle('rgba(255,255,255,0.92)');
    ctx.font = '500 20px sans-serif';
    ctx.fillText('恋爱人格测评', W / 2, 110);

    // 卡片：副标签
    ctx.setFillStyle('#bbb');
    ctx.font = '400 13px sans-serif';
    ctx.fillText('你的恋爱人格是', W / 2, 185);

    // 人格类型
    ctx.setFillStyle('#FF6B9D');
    ctx.font = '700 42px sans-serif';
    ctx.fillText(personalityType, W / 2, 242);

    // 分割线
    ctx.setStrokeStyle('#FFD6E5');
    ctx.setLineWidth(1);
    ctx.beginPath();
    ctx.moveTo(55, 264);
    ctx.lineTo(W - 55, 264);
    ctx.stroke();

    // 摘要文字（自动换行）
    ctx.setFillStyle('#666');
    ctx.font = '400 13px sans-serif';
    const lines = _wrapText(ctx, summary, W - 80);
    lines.slice(0, 6).forEach((line, i) => {
      ctx.fillText(line, W / 2, 294 + i * 22);
    });

    // 底部说明
    ctx.setFillStyle('rgba(255,255,255,0.82)');
    ctx.font = '400 13px sans-serif';
    ctx.fillText('💕 恋爱人格测评小程序', W / 2, 512);
    ctx.setFillStyle('rgba(255,255,255,0.55)');
    ctx.font = '400 11px sans-serif';
    ctx.fillText('长按图片保存，分享给朋友', W / 2, 538);

    ctx.draw(false, () => {
      tt.canvasToTempFilePath({
        canvasId: 'poster',
        destWidth: W * 2,
        destHeight: H * 2,
        success: (res) => {
          tt.hideLoading();
          this.setData({ posterPath: res.tempFilePath, showPoster: true });
        },
        fail: () => {
          tt.hideLoading();
          tt.showToast({ title: '海报生成失败，请重试', icon: 'none' });
        },
      }, this);
    });
  },

  savePoster() {
    tt.saveImageToPhotosAlbum({
      filePath: this.data.posterPath,
      success: () => tt.showToast({ title: '已保存到相册', icon: 'success' }),
      fail: () => tt.showToast({ title: '保存失败，请授权相册权限', icon: 'none' }),
    });
  },

  closePoster() {
    this.setData({ showPoster: false });
  },

  onShareAppMessage() {
    return {
      title: '我的恋爱人格是「' + this.data.personalityType + '」，来测测你的～',
      path: '/pages/index/index',
    };
  },
});
