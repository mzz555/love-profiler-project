const app = getApp();

const DIM_CONFIGS = [
  { emoji: '🫂', color: '#FF7B6E', bg: 'rgba(255,123,110,0.12)', key: '依恋' },
  { emoji: '🌊', color: '#4FC3F7', bg: 'rgba(79,195,247,0.12)', key: '边界' },
  { emoji: '⚡', color: '#CE93D8', bg: 'rgba(206,147,216,0.12)', key: '冲突' },
  { emoji: '💝', color: '#F48FB1', bg: 'rgba(244,143,177,0.12)', key: '情感需求' },
  { emoji: '🎭', color: '#FFB74D', bg: 'rgba(255,183,77,0.12)', key: '风格表达' },
];

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

function _stripMd(str) {
  if (!str) return '';
  return str
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\*(.+?)\*/g, '$1')
    .replace(/__(.+?)__/g, '$1')
    .replace(/_(.+?)_/g, '$1')
    .trim();
}

function _emptyParsed() {
  return {
    typeName: '', typeTagline: '',
    portrait: { title: '专属报告', text: '' },
    dimensions: [], dimsRaw: '',
    insights: { title: '深层洞察', text: '', hasContent: false },
    advice: { title: '关系建议', items: [] },
    ending: { title: '写在最后', text: '' },
  };
}

function _makeDim(cfg, name, text, index) {
  return { name, text, emoji: cfg.emoji, color: cfg.color, bg: cfg.bg, index };
}

function _parseReport(reportText) {
  if (!reportText) return _emptyParsed();

  const lines = reportText.split('\n');
  const result = _emptyParsed();
  result.portrait.title = '开篇画像';

  let state = '';
  let currentDim = null;
  let buffer = [];

  const flushBuf = () => {
    const t = buffer.filter(l => l.trim()).join('\n');
    buffer = [];
    return _stripMd(t);
  };

  for (const line of lines) {
    if (line.startsWith('## ')) {
      // Flush previous buffer
      if (state === 'portrait') result.portrait.text = flushBuf();
      else if (state === 'dimensions') {
        if (currentDim) {
          currentDim.text = flushBuf();
          result.dimensions.push(currentDim);
          currentDim = null;
        } else {
          result.dimsRaw = buffer.filter(l => l.trim()).join('\n').trim();
          buffer = [];
        }
      } else if (state === 'insights') result.insights.text = flushBuf();
      else if (state === 'ending') result.ending.text = flushBuf();

      const titleFull = line.replace('## ', '').trim();
      const title = titleFull.replace(/^Section\s*\d+[：:]\s*/i, '').trim();

      if (/开篇|Section\s*1/i.test(titleFull)) {
        state = 'portrait';
        result.portrait.title = title || '开篇画像';
      } else if (/五维度|维度|Section\s*2/i.test(titleFull)) {
        state = 'dimensions';
      } else if (/洞察|Section\s*3/i.test(titleFull)) {
        state = 'insights';
        result.insights.title = title || '深层洞察';
      } else if (/建议|Section\s*4/i.test(titleFull)) {
        state = 'advice';
        result.advice.title = title || '关系建议';
      } else if (/结尾|Section\s*5/i.test(titleFull)) {
        state = 'ending';
        result.ending.title = title || '写在最后';
      }
    } else if (line.startsWith('### ') && state === 'dimensions') {
      if (currentDim) {
        currentDim.text = flushBuf();
        result.dimensions.push(currentDim);
      } else {
        buffer = [];
      }
      const idx = result.dimensions.length;
      const cfg = DIM_CONFIGS[idx] || DIM_CONFIGS[0];
      currentDim = _makeDim(cfg, line.replace('### ', '').trim(), '', idx);
    } else if (state === 'advice') {
      const numbered = line.match(/^[\d]+[\.、\)]\s*(.+)/);
      const bulleted = line.match(/^[-*·]\s*(.+)/);
      const nextNum = result.advice.items.length + 1;
      if (numbered) {
        result.advice.items.push({ num: nextNum, text: _stripMd(numbered[1]) });
      } else if (bulleted) {
        result.advice.items.push({ num: nextNum, text: _stripMd(bulleted[1]) });
      } else {
        const stripped = _stripMd(line.trim());
        if (stripped && result.advice.items.length > 0) {
          result.advice.items[result.advice.items.length - 1].text += stripped;
        } else if (stripped) {
          result.advice.items.push({ num: nextNum, text: stripped });
        }
      }
    } else if (state === 'portrait' || state === 'insights' || state === 'ending' || state === 'dimensions') {
      buffer.push(line);
    }
  }

  // Final flush
  if (state === 'portrait') result.portrait.text = flushBuf();
  else if (state === 'dimensions') {
    if (currentDim) {
      currentDim.text = flushBuf();
      result.dimensions.push(currentDim);
    } else {
      result.dimsRaw = buffer.filter(l => l.trim()).join('\n').trim();
    }
  } else if (state === 'insights') result.insights.text = flushBuf();
  else if (state === 'ending') result.ending.text = flushBuf();

  // If no ### sub-sections found, split dimsRaw by paragraphs
  if (result.dimensions.length === 0 && result.dimsRaw) {
    const paras = result.dimsRaw.split(/\n\n+/).filter(p => p.trim());
    paras.forEach((para, i) => {
      const cfg = DIM_CONFIGS[i] || DIM_CONFIGS[4];
      result.dimensions.push(_makeDim(cfg, cfg.key, _stripMd(para), i));
    });
  }

  result.insights.hasContent = !!result.insights.text;

  // Extract type name between 「」 from portrait text
  const nameMatch = result.portrait.text.match(/你是[「『""](.+?)[」』""]/);
  if (nameMatch) result.typeName = nameMatch[1];

  // Extract tagline: sentence after 。following type name bracket
  const tagMatch = result.portrait.text.match(/[」』"""]。\s*([^。\n]{6,40})/);
  if (tagMatch) result.typeTagline = tagMatch[1].trim();

  return result;
}

Page({
  data: {
    loading: true,
    personalityType: '',
    reportText: '',
    parsed: null,
    hasPortrait: false,
    hasDimensions: false,
    hasInsights: false,
    hasAdvice: false,
    hasEnding: false,
    sessionId: '',
    isHistory: false,
    showPoster: false,
    posterPath: '',
  },
  _pollTimer: null,

  onLoad(options) {
    const sessionId = options.session_id || app.globalData.sessionId;
    if (!sessionId) {
      tt.redirectTo({ url: '/pages/index/index' });
      return;
    }
    this.setData({ sessionId, isHistory: !!options.session_id });
    this._loadReport(sessionId);
  },

  onUnload() {
    if (this._pollTimer) {
      clearTimeout(this._pollTimer);
      this._pollTimer = null;
    }
  },

  async _loadReport(sessionId) {
    try {
      const res = await app.request({ url: '/result', data: { session_id: sessionId } });

      if (res.status === 'generating') {
        // Agent B still running — poll again in 4 seconds, keep loading state
        this._pollTimer = setTimeout(() => this._loadReport(sessionId), 4000);
        return;
      }

      const { personality_type: personalityType, report_text: reportText } = res;
      const parsed = _parseReport(reportText);
      this.setData({
        loading: false,
        personalityType,
        reportText,
        parsed,
        hasPortrait: !!parsed.portrait.text,
        hasDimensions: parsed.dimensions.length > 0,
        hasInsights: parsed.insights.hasContent,
        hasAdvice: parsed.advice.items.length > 0,
        hasEnding: !!parsed.ending.text,
      });
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
    const { personalityType, reportText, parsed } = this.data;
    const displayName = parsed.typeName || personalityType;
    const tagline = parsed.typeTagline || '';
    const portraitText = parsed.portrait.text || reportText;
    const summary = portraitText.includes('。')
      ? portraitText.split('。')[0] + '。'
      : portraitText.slice(0, 60);

    const ctx = tt.createCanvasContext('poster', this);
    const W = 375, H = 600;

    const bg = ctx.createLinearGradient(0, 0, 0, H);
    bg.addColorStop(0, '#2D0050');
    bg.addColorStop(0.5, '#6A0572');
    bg.addColorStop(1, '#C2185B');
    ctx.setFillStyle(bg);
    ctx.fillRect(0, 0, W, H);

    // Decorative circle top-right
    ctx.setFillStyle('rgba(255,255,255,0.06)');
    ctx.beginPath();
    ctx.arc(W - 20, 30, 110, 0, Math.PI * 2);
    ctx.fill();

    // Decorative circle bottom-left
    ctx.setFillStyle('rgba(255,255,255,0.04)');
    ctx.beginPath();
    ctx.arc(20, H - 30, 90, 0, Math.PI * 2);
    ctx.fill();

    // White card
    ctx.setFillStyle('rgba(255,255,255,0.95)');
    ctx.setShadow(0, 12, 30, 'rgba(0,0,0,0.25)');
    _roundRect(ctx, 24, 130, W - 48, 340, 20);
    ctx.fill();
    ctx.setShadow(0, 0, 0, 'transparent');

    // Emoji
    ctx.setTextAlign('center');
    ctx.setFontSize(56);
    ctx.setFillStyle('#fff');
    ctx.fillText('💗', W / 2, 72);

    // App name
    ctx.setFillStyle('rgba(255,255,255,0.88)');
    ctx.font = '500 18px sans-serif';
    ctx.fillText('恋爱侧写', W / 2, 110);

    // Card: label
    ctx.setFillStyle('#999');
    ctx.font = '400 12px sans-serif';
    ctx.fillText('你的恋爱人格是', W / 2, 178);

    // Type name
    ctx.setFillStyle('#C2185B');
    ctx.font = '700 34px sans-serif';
    ctx.fillText(displayName, W / 2, 230);

    // Tagline
    if (tagline) {
      ctx.setFillStyle('#7B1FA2');
      ctx.font = '400 14px sans-serif';
      ctx.fillText(tagline, W / 2, 262);
    }

    // Divider
    ctx.setStrokeStyle('#F8BBD0');
    ctx.setLineWidth(1);
    ctx.beginPath();
    ctx.moveTo(60, 284);
    ctx.lineTo(W - 60, 284);
    ctx.stroke();

    // Summary text
    ctx.setFillStyle('#555');
    ctx.font = '400 12px sans-serif';
    const lines = _wrapText(ctx, summary, W - 90);
    lines.slice(0, 7).forEach((line, i) => {
      ctx.fillText(line, W / 2, 308 + i * 21);
    });

    // Bottom bar
    const bottomBg = ctx.createLinearGradient(0, H - 70, 0, H);
    bottomBg.addColorStop(0, 'rgba(45,0,80,0)');
    bottomBg.addColorStop(1, 'rgba(45,0,80,0.8)');
    ctx.setFillStyle(bottomBg);
    ctx.fillRect(0, H - 70, W, 70);

    ctx.setFillStyle('rgba(255,255,255,0.85)');
    ctx.font = '400 13px sans-serif';
    ctx.fillText('💕 恋爱侧写小程序', W / 2, H - 36);
    ctx.setFillStyle('rgba(255,255,255,0.5)');
    ctx.font = '400 11px sans-serif';
    ctx.fillText('长按图片保存 · 分享给你在乎的人', W / 2, H - 16);

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
    const { personalityType, parsed } = this.data;
    const name = parsed.typeName || personalityType;
    return {
      title: '我的恋爱人格是「' + name + '」，来测测你的～',
      path: '/pages/index/index',
    };
  },
});
