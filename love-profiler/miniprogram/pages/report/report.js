const app = getApp();
const chartMixin = require('./report-chart');
const posterMixin = require('./report-poster');
const wsMixin = require('./report-ws');

// 类型主题色（按 D1 前缀映射，跟首页 GROUP_MAP 保持一致）
// primary 用于描边/重点；accent 用于浅彩底
const TYPE_THEME_MAP = {
  S:  { primary: '#3A8A8A', accent: '#E8F4F2' },
  MS: { primary: '#5B73C9', accent: '#ECEFFA' },
  MA: { primary: '#C9743A', accent: '#FBEFE0' },
  A:  { primary: '#C94F4F', accent: '#FBE4E2' },
};
const DEFAULT_TYPE_THEME = { primary: '#4FAFAF', accent: '#F2EDE6' };

function inferTypeTheme(typeCode) {
  if (!typeCode) return DEFAULT_TYPE_THEME;
  const prefix = String(typeCode).split('-')[0];
  return TYPE_THEME_MAP[prefix] || DEFAULT_TYPE_THEME;
}

// 雷达图五个维度轴颜色（与 DIM_CONFIGS 对应）
const RADAR_COLORS = ['#FF7B6E', '#4FC3F7', '#CE93D8', '#F48FB1', '#FFB74D'];

const DIM_CONFIGS = [
  { emoji: '🫂', color: '#FF7B6E', bg: 'rgba(255,123,110,0.12)', key: '依恋' },
  { emoji: '🌊', color: '#4FC3F7', bg: 'rgba(79,195,247,0.12)', key: '边界' },
  { emoji: '⚡', color: '#CE93D8', bg: 'rgba(206,147,216,0.12)', key: '冲突' },
  { emoji: '💝', color: '#F48FB1', bg: 'rgba(244,143,177,0.12)', key: '情感需求' },
  { emoji: '🎭', color: '#FFB74D', bg: 'rgba(255,183,77,0.12)', key: '风格表达' },
];

function _roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.arc(x + r,     y + r,     r, Math.PI,       Math.PI * 1.5);
  ctx.arc(x + w - r, y + r,     r, Math.PI * 1.5, 0);
  ctx.arc(x + w - r, y + h - r, r, 0,             Math.PI * 0.5);
  ctx.arc(x + r,     y + h - r, r, Math.PI * 0.5, Math.PI);
  ctx.closePath();
}

// 抖音 Canvas 1.0 不支持 8 位 hex alpha (#RRGGBBAA)，必须用 rgba()
function _hexAlpha(hex, alpha) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
}

// 抖音 Canvas 1.0 没有 createRadialGradient，用 6 层同心圆 + 平方衰减 alpha 模拟羽化
function _radialGlow(ctx, cx, cy, r, rgbTriplet, maxAlpha) {
  const layers = 6;
  for (let i = layers; i >= 1; i--) {
    const t = i / layers;
    const a = maxAlpha * (1 - t) * (1 - t);
    if (a < 0.005) continue;
    ctx.setFillStyle('rgba(' + rgbTriplet + ',' + a.toFixed(3) + ')');
    ctx.beginPath();
    ctx.arc(cx, cy, r * t, 0, Math.PI * 2);
    ctx.fill();
  }
}

// 抖音 Canvas 1.0 没有 setLineDash，虚线必须手画短线段
function _dashedLine(ctx, x1, y1, x2, y2, color, dashLen, gapLen) {
  dashLen = dashLen || 3;
  gapLen  = gapLen  || 3;
  const dx = x2 - x1, dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy);
  if (len < 1) return;
  const ux = dx / len, uy = dy / len;
  const segCount = Math.floor(len / (dashLen + gapLen));
  ctx.setStrokeStyle(color);
  ctx.setLineWidth(1);
  ctx.beginPath();
  for (let i = 0; i < segCount; i++) {
    const t = i * (dashLen + gapLen);
    const sx = x1 + t * ux, sy = y1 + t * uy;
    const ex = sx + dashLen * ux, ey = sy + dashLen * uy;
    ctx.moveTo(sx, sy);
    ctx.lineTo(ex, ey);
  }
  ctx.stroke();
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

const _DIM_KEY_MAP = {
  D1: '依恋', D2: '边界', D3: '冲突', D4: '情感需求', D5: '风格表达',
};

function _sectionsToDisplay(sections) {
  const result = _emptyParsed();
  result.typeName = sections.type_name || '';
  result.portrait = { title: '开篇画像', text: sections.portrait || '' };

  const dims = sections.dimensions || {};
  ['D1', 'D2', 'D3', 'D4', 'D5'].forEach((key, idx) => {
    const d = dims[key];
    if (!d || !d.text) return;
    const cfg = DIM_CONFIGS[idx] || DIM_CONFIGS[0];
    result.dimensions.push({
      name: d.title || _DIM_KEY_MAP[key],
      text: d.text,
      emoji: cfg.emoji,
      color: cfg.color,
      bg: cfg.bg,
      index: result.dimensions.length,
    });
  });

  const insightTexts = (sections.insights || []).map(i => i.text).filter(Boolean);
  result.insights = {
    title: '深层洞察',
    text: insightTexts.join('\n\n'),
    hasContent: insightTexts.length > 0,
  };

  result.ending = { title: '写在最后', text: sections.closing || '' };
  return result;
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
    typeTheme: DEFAULT_TYPE_THEME,  // 按 personalityType D1 前缀映射的主题色 {primary, accent}
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
    // Phase 5 心动级互动
    showCelebration: false,
    // 流式生成状态
    streaming: false,
    streamingDone: false,
    streamingTypeName: '',
    streamingTypeTagline: '',
    streamingTypeDetail: '',
    heroImageUrl: '',
    heroImageReady: false,
    dimChart: null,
    dimChartReady: false,
    chartImgD123: '',
    chartImgCombined: '',
    chartImgD4Bloom: '',
    chartImgD5Quadrant: '',
    chartImgFullRadar: '',
    // 分段内容（新格式）
    sec: { Title: '', Opening: '', Attachment: '', Boundary: '', Conflict: '', Language: '', Style: '', Suggestion: '' },
    highlights: [],       // [{idx, title, text, severity, isPositive}]
    highlightsMeta: [],   // 从 meta 消息预填充标题，不依赖 Agent B
    segmentDecode: [],    // [{dimension, code, label_cn, is_healthy}] D1/D2/D3 段落解码
    curSec: '',
    // 旧格式兜底
    streamingText: '',
  },
  _wsTask: null,
  _pollTimer: null,
  _streamTimer: null,

  onLoad(options) {
    const sessionId = options.session_id || app.globalData.sessionId;
    if (!sessionId) {
      tt.redirectTo({ url: '/pages/index/index' });
      return;
    }

    let heroImageUrl = '';
    if (options.img_path) {
      heroImageUrl = app.baseUrl + decodeURIComponent(options.img_path);
    }

    this.setData({
      sessionId,
      isHistory: !options.img_path,
      heroImageUrl,
    });
    // Mark image ready a tick later so the CSS transition fires.
    if (heroImageUrl) {
      setTimeout(() => this.setData({ heroImageReady: true }), 50);
    }
    this._loadReport(sessionId);
  },

  onUnload() {
    if (this._wsTask) {
      this._wsTask.close();
      this._wsTask = null;
    }
    if (this._pollTimer) {
      clearTimeout(this._pollTimer);
      this._pollTimer = null;
    }
    if (this._streamTimer) {
      clearInterval(this._streamTimer);
      this._streamTimer = null;
    }
  },

  // ── WS/渲染（委托到 report-ws.js）──
  _appendSectionChunk: function(s, t) { wsMixin._appendSectionChunk.call(this, s, t); },
  _parseHighlights: function(r) { return wsMixin._parseHighlights.call(this, r); },
  _loadReport: function(sid) { wsMixin._loadReport.call(this, sid); },
  _connectWs: function(sid, ticket, t0, elapsed) { wsMixin._connectWs.call(this, sid, ticket, t0, elapsed); },
  _onStreamDone: function(m) { wsMixin._onStreamDone.call(this, m); },
  _onStreamError: function(c) { wsMixin._onStreamError.call(this, c); },

  // ── 图表（委托到 report-chart.js）──
  _drawCombinedRadar: function(hr) { chartMixin._drawCombinedRadar.call(this, hr); },
  _drawFullRadar: function(a, b, c) { chartMixin._drawFullRadar.call(this, a, b, c); },
  _drawD123Gauges: function(d) { chartMixin._drawD123Gauges.call(this, d); },
  _drawD4Bloom: function(p) { chartMixin._drawD4Bloom.call(this, p); },
  _drawD5Quadrant: function(q) { chartMixin._drawD5Quadrant.call(this, q); },

  // ── 海报/分享（委托到 report-poster.js）──
  generatePoster: function() { posterMixin.generatePoster.call(this); },
  _renderPoster: function(p) { posterMixin._renderPoster.call(this, p); },
  savePoster: function() { posterMixin.savePoster.call(this); },
  closePoster: function() { posterMixin.closePoster.call(this); },
  onShareAppMessage: function() { return posterMixin.onShareAppMessage.call(this); },

  restart() {
    app.clearSession();
    tt.reLaunch({ url: '/pages/chat/chat' });
  },

  goHistory() {
    tt.navigateTo({ url: '/pages/history/history' });
  },

  goDeep() {
    tt.showToast({ title: '深度版即将上线，敬请期待 ✨', icon: 'none', duration: 2000 });
  },

  goCouple() {
    tt.showToast({ title: '双人版即将上线，敬请期待 💑', icon: 'none', duration: 2000 });
  },


});
