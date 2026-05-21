const app = getApp();

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
    heroImageUrl: '',
    heroImageReady: false,
    dimChart: null,
    dimChartReady: false,
    chartImgD123: '',
    chartImgCombined: '',
    chartImgD4Bloom: '',
    chartImgD5Quadrant: '',
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

  _appendSectionChunk(section, text) {
    if (section === 'Highlight') {
      this._hlBuf = (this._hlBuf || '') + text;
      this.setData({ highlights: this._parseHighlights(this._hlBuf) });
    } else {
      // 用本地 _secBuf 积累，避免 hasOwnProperty / setData 异步时读到旧值
      this._secBuf = this._secBuf || {};
      this._secBuf[section] = (this._secBuf[section] || '') + text;
      const key = 'sec.' + section;
      const update = {};
      update[key] = this._secBuf[section];
      this.setData(update);
    }
  },

  _parseHighlights(raw) {
    const items = [];
    const re = /High_(\d+):\s*([\s\S]*?)(?=High_\d+:|$)/g;
    const meta = this.data.highlightsMeta || [];
    let m;
    while ((m = re.exec(raw)) !== null) {
      const idx = parseInt(m[1], 10);
      const text = m[2].trim();
      const hm = meta.find(h => h.idx === idx) || {};
      // 有标题或有正文都保留（标题来自 Agent A，正文来自 Agent B）
      if (text || hm.title) {
        items.push({ idx, title: hm.title || '', text, severity: hm.severity || 'medium', isPositive: !!hm.isPositive });
      }
    }
    // Agent B 还未开始时，用 meta 预填充的空白条目
    if (items.length === 0 && meta.length > 0) {
      return meta.map(h => ({ ...h, text: '' }));
    }
    return items;
  },

  _loadReport(sessionId) {
    const t0 = Date.now();
    const elapsed = () => ((Date.now() - t0) / 1000).toFixed(2) + 's';

    console.log('[report] 建立 WS 连接 session=', sessionId);
    const wsTask = app.connectSocket({ path: '/ws/result' });
    this._wsTask = wsTask;

    wsTask.onOpen(() => {
      console.log('[report] WS 已连接，发送 session_id', elapsed());
      wsTask.send({ data: JSON.stringify({ session_id: sessionId }) });
    });

    wsTask.onMessage((res) => {
      const msg = JSON.parse(res.data);

      if (msg.type === 'meta') {
        console.log('[report] meta type_code=', msg.personality_type, elapsed());
        const dimChart = msg.dim_chart || null;
        this._hlBuf = '';
        this._secBuf = {};
        // 从 meta 预填充 highlights 标题（不等 Agent B）
        const highlightsMeta = (msg.highlights_meta || []).map(h => ({
          idx: h.idx, title: h.title || '', severity: h.severity || 'medium', isPositive: !!h.is_positive,
        }));
        const preHighlights = highlightsMeta.map(h => ({ ...h, text: '' }));
        // 流式模式下 onLoad 没拿到 img_path（路由没传），从 meta 补 → heroImageUrl
        const patch = {
          loading: false,
          streaming: true,
          streamingText: '',
          personalityType: msg.personality_type,
          streamingTypeName: msg.type_name,
          streamingTypeTagline: msg.type_tagline || '',
          sec: { Title: '', Opening: '', Attachment: '', Boundary: '', Conflict: '', Language: '', Style: '', Suggestion: '' },
          highlights: preHighlights,
          highlightsMeta,
          segmentDecode: msg.segment_decode || [],
          curSec: '',
          dimChart,
          dimChartReady: !!dimChart,
        };
        if (msg.img_path && !this.data.heroImageUrl) {
          patch.heroImageUrl = app.baseUrl + decodeURIComponent(msg.img_path);
          setTimeout(() => this.setData({ heroImageReady: true }), 50);
        }
        this.setData(patch);
        if (dimChart) {
          // streaming 区块进入 DOM 后 canvas 已存在，200ms 足够 canvas 初始化
          setTimeout(() => {
            console.log('[charts] drawing d123=', !!dimChart.d123,
                        'health=', !!dimChart.health_radar,
                        'd4=', !!dimChart.d4_preference,
                        'd5=', !!dimChart.d5_quadrant);
            this._drawD123Gauges(dimChart.d123);
            this._drawCombinedRadar(dimChart.health_radar);
            this._drawD4Bloom(dimChart.d4_preference);
            this._drawD5Quadrant(dimChart.d5_quadrant);
          }, 200);
        }
      } else if (msg.type === 'section_start') {
        this.setData({ curSec: msg.section });
      } else if (msg.type === 'section_chunk') {
        this._appendSectionChunk(msg.section, msg.text);
      } else if (msg.type === 'section_end') {
        // 留作未来扩展（e.g. 动画触发）
      } else if (msg.type === 'portrait_chunk') {
        // 旧格式兜底
        this.setData({ streamingText: this.data.streamingText + msg.text });
      } else if (msg.type === 'done') {
        const raw = (msg.report_json || {}).raw_llm_output || '';
        console.log('[report] done elapsed=', elapsed(), 'output_len=', raw.length);
        console.log('[report] raw_llm_output=', raw);
        wsTask.close();
        this._wsTask = null;
        this._onStreamDone(msg);
      } else if (msg.type === 'error') {
        console.error('[report] error code=', msg.code, msg.message, elapsed());
        wsTask.close();
        this._wsTask = null;
        this._onStreamError(msg.code);
      }
    });

    wsTask.onError((err) => {
      console.error('[report] WS 连接错误', elapsed(), err);
      this._wsTask = null;
      this._onStreamError(500);
    });

    wsTask.onClose((res) => {
      console.log('[report] WS 关闭 code=', res && res.code, elapsed());
      this._wsTask = null;
    });
  },

  _onStreamDone(msg) {
    const { personality_type: personalityType, report_json: sections } = msg;
    const rawOutput = (sections && sections.raw_llm_output) || this.data.streamingText;

    // 直接展示完整 AI 原始输出，不截取，不切换到结构化视图
    this.setData({
      personalityType,
      streamingText: rawOutput,
      streamingDone: true,
      showCelebration: true,
    });
    // Phase 5 心动级互动：完成时震动 + 2.4s 星花 micro-celebration
    if (tt.vibrateShort) {
      tt.vibrateShort({ type: 'medium' });
    }
    setTimeout(() => {
      this.setData({ showCelebration: false });
    }, 2400);
  },

  _onStreamError(code) {
    this.setData({ loading: false, streaming: false });
    if (code === 402) {
      tt.showModal({
        title: '报告未解锁',
        content: '请先完成解锁步骤（付费或观看广告）',
        showCancel: false,
        success: () => tt.navigateBack(),
      });
    } else if (code === 400 || code === 4001) {
      tt.showToast({ title: '测评尚未完成，请继续作答', icon: 'none', duration: 3000 });
      setTimeout(() => tt.navigateBack(), 1500);
    } else {
      tt.showToast({ title: 'AI服务暂时不可用，请稍后重试', icon: 'none', duration: 3000 });
    }
  },

  // ── 图表1：D1/D2/D3 棒棒糖图 ──────────────────────────────────────
  // 三条横轴，零点居中，彩色茎线 + 光晕圆点指向分数位
  _drawD123Gauges(d123) {
    if (!d123 || d123.length < 3) return;
    const ctx = tt.createCanvasContext('d123-gauge', this);
    try {
      const W = 630, H = 166;
      const padL = 82, padR = 92;    // 左：维度名；右：解读词
      const barL = padL, barR = W - padR;
      const barW = barR - barL;
      const midX = barL + barW / 2;  // 零点 X
      const rowH = 44, padTop = 17;

      const TEAL  = '#3ABFAF';
      const CORAL = '#E87070';
      const GREY  = '#C0BDB8';
      const clr   = s => s > 1 ? TEAL : s < -1 ? CORAL : GREY;

      const interpZh = {
        secure: '安全型',      moderate_secure: '中度安全',
        mixed: '混合型',       moderate_anxious: '中度焦虑', anxious: '焦虑型',
        clear: '清晰',         moderate_clear: '中度清晰',
        moderate_blurred: '中度模糊', blurred: '模糊型',
        healthy: '健康',       moderate_healthy: '中度健康',
        moderate_problematic: '中度问题', problematic: '问题型',
      };

      // 刻度参考线 ±6
      [-6, 6].forEach(v => {
        const tickX = midX + (v / 12) * (barW / 2);
        ctx.beginPath();
        ctx.moveTo(tickX, padTop - 4);
        ctx.lineTo(tickX, padTop + rowH * 3 + 2);
        ctx.setStrokeStyle('rgba(195,190,185,0.35)');
        ctx.setLineWidth(1);
        ctx.stroke();
      });

      d123.forEach((dim, i) => {
        const yc   = padTop + i * rowH + rowH / 2;
        const raw  = typeof dim.raw === 'number' ? dim.raw : 0;
        const dotX = midX + (raw / 12) * (barW / 2);
        const col  = clr(raw);
        const isPos = raw > 1, isNeg = raw < -1;

        // 横轴底线
        ctx.beginPath();
        ctx.moveTo(barL, yc);
        ctx.lineTo(barR, yc);
        ctx.setStrokeStyle('rgba(200,193,186,0.45)');
        ctx.setLineWidth(1.5);
        ctx.stroke();

        // 零刻（短竖线）
        ctx.beginPath();
        ctx.moveTo(midX, yc - 6);
        ctx.lineTo(midX, yc + 6);
        ctx.setStrokeStyle('rgba(155,150,145,0.60)');
        ctx.setLineWidth(1.5);
        ctx.stroke();

        // 茎线（零点 → 圆点，渐变色）
        if (Math.abs(raw) > 0.3) {
          const stemGrad = ctx.createLinearGradient(midX, yc, dotX, yc);
          stemGrad.addColorStop(0, 'rgba(180,175,170,0.4)');
          stemGrad.addColorStop(1, col);
          ctx.beginPath();
          ctx.moveTo(midX, yc);
          ctx.lineTo(dotX, yc);
          ctx.setStrokeStyle(stemGrad);
          ctx.setLineWidth(2.5);
          ctx.stroke();
        }

        // 圆点：外晕 → 中晕 → 白环 → 彩芯
        const base = isPos ? '58,191,175' : isNeg ? '232,112,112' : '190,185,180';
        [[13, 0.12], [9, 0.25], [6.5, 1]].forEach(([r, a]) => {
          ctx.beginPath();
          ctx.arc(dotX, yc, r, 0, Math.PI * 2);
          ctx.setFillStyle(a === 1 ? '#FFFFFF' : `rgba(${base},${a})`);
          ctx.fill();
        });
        ctx.beginPath();
        ctx.arc(dotX, yc, 4.5, 0, Math.PI * 2);
        ctx.setFillStyle(col);
        ctx.fill();

        // 分数数字（圆点正上方）
        ctx.setFontSize(12);
        ctx.setFillStyle(col);
        ctx.setTextAlign('center');
        ctx.fillText((raw > 0 ? '+' : '') + raw, dotX, yc - 14);

        // 左侧维度名
        ctx.setFontSize(13);
        ctx.setFillStyle('#4A4A58');
        ctx.setTextAlign('right');
        ctx.fillText(dim.name, barL - 10, yc + 5);

        // 右侧解读词
        ctx.setFontSize(11);
        ctx.setFillStyle(col);
        ctx.setTextAlign('left');
        ctx.fillText(interpZh[dim.interp] || '', barR + 8, yc + 5);
      });

      // 底部端点标注
      ctx.setFontSize(9);
      ctx.setFillStyle('rgba(155,150,145,0.65)');
      ctx.setTextAlign('left');
      ctx.fillText('← 问题端', barL, H - 4);
      ctx.setTextAlign('right');
      ctx.fillText('健康端 →', barR, H - 4);

      ctx.draw(false, () => {
        tt.canvasToTempFilePath({
          canvasId: 'd123-gauge',
          destWidth: W * 2, destHeight: H * 2,
          success: res => this.setData({ chartImgD123: res.tempFilePath }),
          fail: err => console.error('[d123] toImg fail', err),
        }, this);
      });
    } catch(e) { console.error('[d123] THROW', e.message, e); }
  },

  // ── 图表2：5 维健康度雷达（依恋/边界/冲突/自我认知/表达成熟）──────────
  // 语义统一"高=好"，让用户一眼看懂自己哪里强、哪里弱
  _drawCombinedRadar(healthRadar) {
    if (!Array.isArray(healthRadar) || healthRadar.length !== 5) {
      console.warn('[health-radar] expected 5 axes, got', healthRadar);
      return;
    }
    const ctx = tt.createCanvasContext('combined-radar', this);
    try {
      const W = 640, H = 640, cx = W / 2, cy = H / 2, maxR = 200, N = 5;
      const vals = healthRadar.map(r => Math.max(0, Math.min(1, parseFloat(r.value) || 0)));
      const labels = healthRadar.map(r => r.name || r.key);

      const PRIMARY = '#4FAFAF';     // teal 主色
      const PRIMARY_LIGHT = 'rgba(79,175,175,0.22)';
      const PRIMARY_DARK  = '#3A8C8C';
      const GRID = 'rgba(180,170,160,0.20)';
      const GRID_OUTER = 'rgba(150,140,132,0.45)';
      const LABEL = '#3A3A4A';
      const VALUE = 'rgba(110,100,90,0.85)';

      const angles = Array.from({length: N}, (_, i) => -Math.PI / 2 + i * 2 * Math.PI / N);
      const pt = (a, r) => ({ x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) });

      // 背景柔光圆
      ctx.setFillStyle('rgba(248,245,241,0.55)');
      ctx.beginPath(); ctx.arc(cx, cy, maxR + 12, 0, Math.PI * 2); ctx.fill();

      // 网格五边形（25/50/75/100）
      [0.25, 0.5, 0.75, 1.0].forEach(lvl => {
        const pts = angles.map(a => pt(a, maxR * lvl));
        ctx.beginPath(); ctx.moveTo(pts[0].x, pts[0].y);
        for (let i = 1; i < N; i++) ctx.lineTo(pts[i].x, pts[i].y);
        ctx.closePath();
        ctx.setStrokeStyle(lvl === 1 ? GRID_OUTER : GRID);
        ctx.setLineWidth(lvl === 1 ? 2 : 1); ctx.stroke();
      });

      // 轴线
      angles.forEach((a) => {
        const {x, y} = pt(a, maxR);
        ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(x, y);
        ctx.setStrokeStyle(GRID); ctx.setLineWidth(1); ctx.stroke();
      });

      // 数据多边形
      const dpts = vals.map((v, i) => pt(angles[i], maxR * v));
      ctx.beginPath(); ctx.moveTo(dpts[0].x, dpts[0].y);
      for (let i = 1; i < N; i++) ctx.lineTo(dpts[i].x, dpts[i].y);
      ctx.closePath();
      ctx.setFillStyle(PRIMARY_LIGHT); ctx.fill();
      ctx.setStrokeStyle(PRIMARY); ctx.setLineWidth(3); ctx.stroke();

      // 数据节点（深 teal 圆 + 白心）
      dpts.forEach(({x, y}) => {
        ctx.beginPath(); ctx.arc(x, y, 10, 0, Math.PI * 2);
        ctx.setFillStyle(PRIMARY_DARK); ctx.fill();
        ctx.beginPath(); ctx.arc(x, y, 4.5, 0, Math.PI * 2);
        ctx.setFillStyle('#FFFFFF'); ctx.fill();
      });

      // 标签 + 百分比
      labels.forEach((lbl, i) => {
        const a = angles[i], cosA = Math.cos(a), sinA = Math.sin(a);
        const {x, y} = pt(a, maxR + 44);
        const align = cosA > 0.2 ? 'left' : cosA < -0.2 ? 'right' : 'center';
        const dy = sinA < -0.4 ? -2 : sinA > 0.4 ? 14 : 6;
        ctx.setTextAlign(align);
        ctx.setFontSize(24); ctx.setFillStyle(LABEL);
        ctx.fillText(lbl, x, y + dy);
        ctx.setFontSize(18); ctx.setFillStyle(VALUE);
        ctx.fillText(Math.round(vals[i] * 100) + '%', x, y + dy + 26);
      });

      // 中心总分（5 维平均），辅助一眼读图
      const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
      ctx.setTextAlign('center');
      ctx.setFontSize(20); ctx.setFillStyle(VALUE);
      ctx.fillText('综合', cx, cy - 12);
      ctx.setFontSize(40); ctx.setFillStyle(PRIMARY_DARK);
      ctx.fillText(Math.round(avg * 100) + '%', cx, cy + 26);

      ctx.draw(false, () => {
        tt.canvasToTempFilePath({
          canvasId: 'combined-radar',
          destWidth: W, destHeight: H,
          success: res => { console.log('[health-radar] img ok'); this.setData({ chartImgCombined: res.tempFilePath }); },
          fail: err => console.error('[health-radar] toImg fail', err),
        }, this);
      });
    } catch(e) { console.error('[health-radar] THROW', e.message, e); }
  },

  // ── 图表3：D4 爱的语言"五瓣花"───────────────────────────────────────
  // 5 瓣按 normalized 精确缩放；三级配色：top1 暖橙 / top2 金色 / 3-5 淡灰
  _drawD4Bloom(pref) {
    if (!pref || !Array.isArray(pref.items) || pref.items.length !== 5) {
      console.warn('[d4-bloom] expected 5 items, got', pref);
      return;
    }
    const ctx = tt.createCanvasContext('d4-bloom', this);
    try {
      const W = 640, H = 640, cx = W / 2, cy = H / 2;
      const maxR = 210, minR = 30;       // 花瓣最小/最大半径（保证 0 偏好也可见底纹）
      const items = pref.items;

      // 按 value 降序找 top1 / top2 索引
      const ranked = items.map((it, i) => ({i, v: it.value || 0})).sort((a, b) => b.v - a.v);
      const top1Idx = ranked[0].i;
      const top2Idx = ranked[1] ? ranked[1].i : -1;

      // 三级配色（cream × teal 主题对应的暖色）
      const C_TOP1 = { fill: 'rgba(224,130,80,0.85)', stroke: '#C0622A', label: '#8B4513' };
      const C_TOP2 = { fill: 'rgba(212,165,108,0.70)', stroke: '#A8814A', label: '#6F5230' };
      const C_REST = { fill: 'rgba(180,170,160,0.30)', stroke: 'rgba(150,140,128,0.55)', label: 'rgba(110,100,90,0.85)' };

      const colorOf = (idx) => idx === top1Idx ? C_TOP1 : idx === top2Idx ? C_TOP2 : C_REST;

      // 5 瓣 × 72°，每瓣占 60°，瓣间 12° 留白
      const SECTOR_DEG = 60;
      const sectorRad = (SECTOR_DEG * Math.PI) / 180;
      const angles = Array.from({length: 5}, (_, i) => -Math.PI / 2 + i * (2 * Math.PI / 5));

      // 背景柔光圆
      ctx.setFillStyle('rgba(248,245,241,0.55)');
      ctx.beginPath(); ctx.arc(cx, cy, maxR + 24, 0, Math.PI * 2); ctx.fill();

      // 外圈虚线参考圆（100% 标记）
      ctx.setStrokeStyle('rgba(180,170,160,0.30)'); ctx.setLineWidth(1);
      ctx.beginPath(); ctx.arc(cx, cy, maxR, 0, Math.PI * 2); ctx.stroke();

      // 画 5 瓣
      items.forEach((it, i) => {
        const v = Math.max(0, Math.min(1, it.value || 0));
        const r = minR + (maxR - minR) * v;
        const ax = angles[i];
        const c = colorOf(i);

        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.arc(cx, cy, r, ax - sectorRad / 2, ax + sectorRad / 2);
        ctx.closePath();
        ctx.setFillStyle(c.fill); ctx.fill();
        ctx.setStrokeStyle(c.stroke); ctx.setLineWidth(2); ctx.stroke();
      });

      // 中心白圆 + top2 文字
      ctx.beginPath(); ctx.arc(cx, cy, 70, 0, Math.PI * 2);
      ctx.setFillStyle('#FFFFFF'); ctx.fill();
      ctx.setStrokeStyle('rgba(200,190,182,0.55)'); ctx.setLineWidth(1.5); ctx.stroke();

      ctx.setTextAlign('center');
      ctx.setFontSize(18); ctx.setFillStyle('rgba(110,100,90,0.85)');
      ctx.fillText('你最需要', cx, cy - 18);
      ctx.setFontSize(22); ctx.setFillStyle('#3A3A4A');
      const top2Names = (pref.top2_names || []).slice(0, 2);
      ctx.fillText(top2Names[0] || '—', cx, cy + 10);
      ctx.setFontSize(15); ctx.setFillStyle('rgba(130,120,112,0.85)');
      ctx.fillText('+ ' + (top2Names[1] || '—'), cx, cy + 34);

      // 外侧标签：中文名 + 百分比
      items.forEach((it, i) => {
        const ax = angles[i], cosA = Math.cos(ax), sinA = Math.sin(ax);
        const lx = cx + Math.cos(ax) * (maxR + 38);
        const ly = cy + Math.sin(ax) * (maxR + 38);
        const align = cosA > 0.2 ? 'left' : cosA < -0.2 ? 'right' : 'center';
        const c = colorOf(i);

        ctx.setTextAlign(align);
        ctx.setFontSize(22); ctx.setFillStyle(c.label);
        ctx.fillText(it.name || it.code, lx, ly);
        ctx.setFontSize(16); ctx.setFillStyle('rgba(130,120,112,0.85)');
        ctx.fillText(Math.round((it.value || 0) * 100) + '%', lx, ly + 22);
      });

      ctx.draw(false, () => {
        tt.canvasToTempFilePath({
          canvasId: 'd4-bloom',
          destWidth: W, destHeight: H,
          success: res => { console.log('[d4-bloom] img ok'); this.setData({ chartImgD4Bloom: res.tempFilePath }); },
          fail: err => console.error('[d4-bloom] toImg fail', err),
        }, this);
      });
    } catch(e) { console.error('[d4-bloom] THROW', e.message, e); }
  },

  // ── 图表4：D5 表达风格象限点图（9 宫格 + 用户定位点）─────────────────
  // X = 直接性 [-6, +6]，Y = 分享欲 [-6, +6]
  // 9 宫格按 base_D5_quadrant 9 类划分，用户点高亮，其它格淡色文字
  _drawD5Quadrant(q) {
    if (!q || typeof q.s1_raw !== 'number' || typeof q.s2_raw !== 'number') {
      console.warn('[d5-quadrant] missing s1/s2_raw', q);
      return;
    }
    const ctx = tt.createCanvasContext('d5-quadrant', this);
    try {
      const W = 640, H = 640;
      const padding = 60;
      const plotW = W - padding * 2, plotH = H - padding * 2;
      const cx = padding + plotW / 2, cy = padding + plotH / 2;
      // 9 宫格：每格 plotW/3 宽；坐标系范围 -6 到 +6
      const stepX = plotW / 3, stepY = plotH / 3;

      const PRIMARY = '#4FAFAF';
      const PRIMARY_DARK = '#3A8C8C';
      const PRIMARY_LIGHT = 'rgba(79,175,175,0.18)';
      const GRID = 'rgba(180,170,160,0.30)';
      const AXIS = 'rgba(140,130,120,0.55)';
      const CELL_LABEL = 'rgba(110,100,90,0.75)';
      const CELL_LABEL_ACTIVE = '#3A3A4A';
      const PALE_BG = 'rgba(248,245,241,0.55)';

      // 把分数（-6 ~ +6）映射到画布坐标
      const toX = (s) => padding + (s + 6) / 12 * plotW;
      const toY = (s) => padding + (1 - (s + 6) / 12) * plotH;   // s2 越大越向上（屏幕坐标 y 向下，所以翻转）

      // 9 类风格名（按 X×Y 排列：X 从低到高 = 含蓄→中→直接；Y 从低到高 = 低分享→中→高分享）
      const STYLE_GRID = [
        // 第一行（Y 高 = 高分享）
        ['含蓄分享型', '中直高分享型', '直爽热情型'],
        // 第二行（Y 中 = 中分享）
        ['含蓄中分享型', '平衡内敛型', '高直中分享型'],
        // 第三行（Y 低 = 低分享）
        ['含蓄收敛型', '中直低分享型', '清爽利落型'],
      ];

      // 用户所在格的 col/row
      const userCol = q.s1_raw > 3 ? 2 : q.s1_raw < -3 ? 0 : 1;
      const userRow = q.s2_raw > 3 ? 0 : q.s2_raw < -3 ? 2 : 1;

      // 背景柔光
      ctx.setFillStyle(PALE_BG);
      ctx.fillRect(padding - 8, padding - 8, plotW + 16, plotH + 16);

      // 用户所在格高亮底色
      ctx.setFillStyle(PRIMARY_LIGHT);
      ctx.fillRect(padding + userCol * stepX, padding + userRow * stepY, stepX, stepY);

      // 网格线
      ctx.setStrokeStyle(GRID); ctx.setLineWidth(1);
      for (let i = 1; i < 3; i++) {
        ctx.beginPath();
        ctx.moveTo(padding + i * stepX, padding);
        ctx.lineTo(padding + i * stepX, padding + plotH);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(padding, padding + i * stepY);
        ctx.lineTo(padding + plotW, padding + i * stepY);
        ctx.stroke();
      }

      // 外框
      ctx.setStrokeStyle(AXIS); ctx.setLineWidth(2);
      ctx.strokeRect(padding, padding, plotW, plotH);

      // 中轴十字（s=0）
      ctx.setStrokeStyle('rgba(140,130,120,0.40)');
      ctx.setLineWidth(1);
      ctx.beginPath(); ctx.moveTo(toX(0), padding); ctx.lineTo(toX(0), padding + plotH); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(padding, toY(0)); ctx.lineTo(padding + plotW, toY(0)); ctx.stroke();

      // 9 格风格名标签（用户所在格用深色，其他用淡色）
      ctx.setTextAlign('center');
      STYLE_GRID.forEach((row, r) => {
        row.forEach((name, c) => {
          const isUserCell = (r === userRow && c === userCol);
          const tx = padding + c * stepX + stepX / 2;
          const ty = padding + r * stepY + stepY / 2;
          ctx.setFontSize(isUserCell ? 18 : 15);
          ctx.setFillStyle(isUserCell ? CELL_LABEL_ACTIVE : CELL_LABEL);
          ctx.fillText(name, tx, ty);
        });
      });

      // 坐标轴标签
      ctx.setFontSize(16); ctx.setFillStyle(AXIS);
      // X 轴（左 = 含蓄，右 = 直接）
      ctx.setTextAlign('left');
      ctx.fillText('含蓄', padding, padding + plotH + 28);
      ctx.setTextAlign('right');
      ctx.fillText('直接', padding + plotW, padding + plotH + 28);
      ctx.setTextAlign('center');
      ctx.fillText('← 直接性 →', cx, padding + plotH + 50);
      // Y 轴（上 = 高分享，下 = 低分享）
      ctx.save();
      ctx.translate(padding - 30, cy);
      ctx.rotate(-Math.PI / 2);
      ctx.setTextAlign('center');
      ctx.fillText('← 分享欲 →', 0, 0);
      ctx.restore();
      ctx.setTextAlign('left');
      ctx.fillText('低分享', padding - 50, padding + plotH);
      ctx.fillText('高分享', padding - 50, padding + 12);

      // 用户定位点
      const px = toX(q.s1_raw), py = toY(q.s2_raw);
      // 外层光晕
      ctx.beginPath(); ctx.arc(px, py, 22, 0, Math.PI * 2);
      ctx.setFillStyle('rgba(79,175,175,0.20)'); ctx.fill();
      // 主点
      ctx.beginPath(); ctx.arc(px, py, 14, 0, Math.PI * 2);
      ctx.setFillStyle(PRIMARY_DARK); ctx.fill();
      // 白心
      ctx.beginPath(); ctx.arc(px, py, 6, 0, Math.PI * 2);
      ctx.setFillStyle('#FFFFFF'); ctx.fill();

      // 用户风格名（点旁边或顶部）
      if (q.style_name) {
        ctx.setTextAlign('center');
        ctx.setFontSize(22); ctx.setFillStyle(PRIMARY_DARK);
        ctx.fillText('你的风格：' + q.style_name, cx, padding - 16);
      }

      ctx.draw(false, () => {
        tt.canvasToTempFilePath({
          canvasId: 'd5-quadrant',
          destWidth: W, destHeight: H,
          success: res => { console.log('[d5-quadrant] img ok'); this.setData({ chartImgD5Quadrant: res.tempFilePath }); },
          fail: err => console.error('[d5-quadrant] toImg fail', err),
        }, this);
      });
    } catch(e) { console.error('[d5-quadrant] THROW', e.message, e); }
  },

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

  generatePoster() {
    console.log('[poster] start');
    tt.showLoading({ title: '生成中...' });
    // 抖音 Canvas drawImage 需要本地路径，先把 heroImageUrl 转 tempPath
    const heroImageUrl = this.data.heroImageUrl;
    if (heroImageUrl) {
      tt.getImageInfo({
        src: heroImageUrl,
        success: (res) => {
          console.log('[poster] hero img resolved', res.path);
          this._renderPoster(res.path || '');
        },
        fail: (err) => {
          console.warn('[poster] hero img resolve fail, fallback to text avatar', err);
          this._renderPoster('');
        },
      });
    } else {
      console.log('[poster] no heroImageUrl, use text avatar');
      this._renderPoster('');
    }
  },

  _renderPoster(localImgPath) {
    const t0 = Date.now();
    const ms = () => Date.now() - t0;
    const {
      personalityType, reportText, parsed,
      streamingTypeName, streamingTypeTagline, sec,
      segmentDecode, highlights, dimChart,
    } = this.data;

    const displayName = (parsed && parsed.typeName) || streamingTypeName || personalityType || '恋爱侧写';
    const tagline     = (parsed && parsed.typeTagline) || streamingTypeTagline || '';
    const portraitText = (parsed && parsed.portrait && parsed.portrait.text)
                       || (sec && sec.Opening) || reportText || '';
    const descLine = portraitText.includes('。')
      ? portraitText.split('。')[0] + '。'
      : portraitText.slice(0, 32);
    const subDesc = tagline || descLine || '稳定、清晰，你在关系里像一座让人安心靠近的灯塔。';
    const avatarText = (displayName || '').slice(0, 2);

    // tags 数据: segmentDecode 的 label_cn (D1/D2/D3) — 优先真实，兜底参考图原文
    const tagDefaults = ['安全感', '边界感', '引导型'];
    const tags = (segmentDecode && segmentDecode.length >= 3)
      ? segmentDecode.slice(0, 3).map((s, i) => (s.label_cn || s.code || tagDefaults[i]).slice(0, 5))
      : tagDefaults;

    // traits 直接用参考图三句精选文案（highlights 是诊断警示项，不是 trait 描述，不接入）
    const traits = [
      '情绪稳定，能给关系提供秩序',
      '表达直接，不轻易被情绪裹挟',
      '愿意认真经营长期关系',
    ];

    // 雷达 5 维 + score 4 条
    // 维度映射: 稳定性←D1依恋健康  责任感←D2边界清晰  沟通力←D5表达稳定  包容力←D3冲突韧性
    const _clamp = v => Math.max(0.05, Math.min(1, v));
    let radarVals = [0.85, 0.78, 0.72, 0.68, 0.80];
    let scorePcts = [90, 85, 80, 75];
    if (dimChart && dimChart.d123 && dimChart.d4 && dimChart.d5) {
      const d1n = ((dimChart.d123[0] && dimChart.d123[0].raw || 0) + 12) / 24;
      const d2n = ((dimChart.d123[1] && dimChart.d123[1].raw || 0) + 12) / 24;
      const d3n = ((dimChart.d123[2] && dimChart.d123[2].raw || 0) + 12) / 24;
      const t4Max = Math.max(
        parseFloat(dimChart.d4.T1 || 0), parseFloat(dimChart.d4.T2 || 0),
        parseFloat(dimChart.d4.T3 || 0), parseFloat(dimChart.d4.T4 || 0),
        parseFloat(dimChart.d4.T5 || 0),
      );
      const s1n = (parseFloat(dimChart.d5.s1_raw || 0) + 6) / 12;
      const s2n = (parseFloat(dimChart.d5.s2_raw || 0) + 6) / 12;
      const d5avg = (s1n + s2n) / 2;
      radarVals = [d1n, d2n, d3n, t4Max, d5avg].map(_clamp);
      scorePcts = [
        Math.round(_clamp(d1n)   * 100), // 稳定性 ← D1
        Math.round(_clamp(d2n)   * 100), // 责任感 ← D2
        Math.round(_clamp(d5avg) * 100), // 沟通力 ← D5
        Math.round(_clamp(d3n)   * 100), // 包容力 ← D3
      ];
    }

    const ctx = tt.createCanvasContext('poster', this);
    const W = 420, H = 660;

    // ═══ 背景: 多层渐变叠加 (粉红→橙黄→淡紫→淡绿) ═══
    const bg = ctx.createLinearGradient(0, 0, W, H);
    bg.addColorStop(0,    '#ffd4dd');
    bg.addColorStop(0.42, '#fff0d5');
    bg.addColorStop(0.76, '#e8dcff');
    bg.addColorStop(1,    '#d9fff2');
    ctx.setFillStyle(bg);
    ctx.fillRect(0, 0, W, H);

    // 左上暖白柔光 (径向用同心圆 6 层模拟)
    _radialGlow(ctx, W * 0.12, H * 0.08, W * 0.45, '255,255,255', 0.85);

    // 右上粉光
    _radialGlow(ctx, W * 0.86, H * 0.14, W * 0.50, '255,233,245', 0.78);

    // 左下绿光
    _radialGlow(ctx, W * 0.12, H * 0.86, W * 0.55, '204,255,238', 0.46);

    // 右中粉色半透明 (::after 模拟)
    _radialGlow(ctx, W - 78 + 105, 220, 105, '255,130,156', 0.18);

    // 外层 1px 描边 + 内层 10px inner border
    ctx.setStrokeStyle('rgba(255,255,255,0.78)');
    ctx.setLineWidth(1);
    _roundRect(ctx, 0.5, 0.5, W - 1, H - 1, 34);
    ctx.stroke();
    ctx.setStrokeStyle('rgba(255,255,255,0.72)');
    _roundRect(ctx, 10, 10, W - 20, H - 20, 28);
    ctx.stroke();

    // ═══ 装饰元素 (ribbon / heart×2 / star×2) ═══
    // Ribbon (右上倾斜 28°)
    ctx.save();
    ctx.translate(W - 56, 24);
    ctx.rotate(28 * Math.PI / 180);
    const ribbonGrad = ctx.createLinearGradient(0, 0, 118, 0);
    ribbonGrad.addColorStop(0, 'rgba(255,146,166,0.72)');
    ribbonGrad.addColorStop(1, 'rgba(255,218,171,0.78)');
    ctx.setFillStyle(ribbonGrad);
    _roundRect(ctx, 0, 0, 118, 22, 11);
    ctx.fill();
    ctx.restore();

    // Heart 1 (左上, -14°)
    ctx.save();
    ctx.translate(38, 44);
    ctx.rotate(-14 * Math.PI / 180);
    ctx.setFillStyle('rgba(255,109,138,0.7)');
    ctx.setFontSize(22);
    ctx.setTextAlign('center');
    ctx.fillText('💗', 0, 0);
    ctx.restore();

    // Heart 2 (右上, 12°)
    ctx.save();
    ctx.translate(W - 50, 56);
    ctx.rotate(12 * Math.PI / 180);
    ctx.setFillStyle('rgba(255,109,138,0.72)');
    ctx.setFontSize(18);
    ctx.fillText('💕', 0, 0);
    ctx.restore();

    // Star 1 (右上)
    ctx.setFillStyle('#ffb95e');
    ctx.setFontSize(18);
    ctx.setTextAlign('center');
    ctx.fillText('✦', W - 72, 108);

    // Star 2 (左下, 与 footer 同水平)
    ctx.setFillStyle('#ffca66');
    ctx.fillText('✦', 32, H - 24);

    // ═══ Header: eyebrow / H1 渐变 / subtitle ═══
    ctx.setTextAlign('center');

    // Eyebrow capsule
    ctx.setFillStyle('rgba(255,255,255,0.58)');
    _roundRect(ctx, W / 2 - 80, 66, 160, 26, 13);
    ctx.fill();
    ctx.setFillStyle('#d95b77');
    ctx.setFontSize(13);
    ctx.fillText('💘 LOVE PROFILE', W / 2, 83);

    // H1 渐变文字
    const h1Y = 122;
    const h1Grad = ctx.createLinearGradient(W * 0.2, h1Y, W * 0.8, h1Y);
    h1Grad.addColorStop(0,    '#ff5d7c');
    h1Grad.addColorStop(0.55, '#ff8c63');
    h1Grad.addColorStop(1,    '#ff5f9b');
    ctx.setFillStyle(h1Grad);
    ctx.setFontSize(28);
    ctx.fillText('恋爱侧写报告', W / 2, h1Y);

    // Subtitle
    ctx.setFillStyle('rgba(75,50,66,0.74)');
    ctx.setFontSize(13);
    ctx.fillText('看见你的关系模式，找到更适合的爱', W / 2, 148);

    // ═══ Profile 卡 (avatar + type-name + tags) ═══
    const profileY = 168;
    const profileH = 156;
    ctx.setFillStyle('#FFFFFF');
    ctx.setShadow(0, 16, 30, 'rgba(205,98,130,0.16)');
    _roundRect(ctx, 22, profileY, W - 44, profileH, 26);
    ctx.fill();
    ctx.setShadow(0, 0, 0, 'rgba(0,0,0,0)');
    // 卡片内部粉白渐变罩
    const profileTint = ctx.createLinearGradient(0, profileY, 0, profileY + profileH);
    profileTint.addColorStop(0, 'rgba(255,255,255,0)');
    profileTint.addColorStop(1, 'rgba(255,241,238,0.45)');
    ctx.setFillStyle(profileTint);
    _roundRect(ctx, 22, profileY, W - 44, profileH, 26);
    ctx.fill();
    // 卡片描边
    ctx.setStrokeStyle('rgba(255,255,255,0.68)');
    ctx.setLineWidth(1);
    _roundRect(ctx, 22.5, profileY + 0.5, W - 45, profileH - 1, 26);
    ctx.stroke();

    // Avatar 区 (78×92 圆角矩形 — 容纳人格小怪兽图)
    const avX = 30, avY = profileY + 12, avW = 78, avH = 92;
    const avGrad = ctx.createLinearGradient(avX, avY, avX + avW, avY + avH);
    avGrad.addColorStop(0,    '#ffd0dc');
    avGrad.addColorStop(0.54, '#ffe6c7');
    avGrad.addColorStop(1,    '#c9f7ea');
    ctx.setFillStyle(avGrad);
    ctx.setShadow(0, 12, 20, 'rgba(255,111,141,0.22)');
    _roundRect(ctx, avX, avY, avW, avH, 18);
    ctx.fill();
    ctx.setShadow(0, 0, 0, 'rgba(0,0,0,0)');
    ctx.setStrokeStyle('rgba(255,255,255,0.7)');
    ctx.setLineWidth(1);
    _roundRect(ctx, avX + 0.5, avY + 0.5, avW - 1, avH - 1, 18);
    ctx.stroke();
    // 人格图 OR 字符兜底
    if (localImgPath) {
      const padX = 4, padY = 4;
      ctx.drawImage(localImgPath, avX + padX, avY + padY, avW - padX * 2, avH - padY * 2);
    } else {
      ctx.setFillStyle('#d95775');
      ctx.setFontSize(22);
      ctx.setTextAlign('center');
      ctx.fillText(avatarText, avX + avW / 2, avY + avH / 2 + 8);
    }

    // Type name (渐变文字)
    const tnX = avX + avW + 14;
    const tnY = avY + 28;
    ctx.setTextAlign('left');
    const tnGrad = ctx.createLinearGradient(tnX, tnY, tnX + 200, tnY);
    tnGrad.addColorStop(0, '#ff617b');
    tnGrad.addColorStop(1, '#ff8f58');
    ctx.setFillStyle(tnGrad);
    ctx.setFontSize(22);
    ctx.fillText(displayName.slice(0, 9), tnX, tnY);

    // Type desc
    ctx.setFillStyle('rgba(75,50,66,0.72)');
    ctx.setFontSize(12);
    const descLines = _wrapText(ctx, subDesc, W - tnX - 30);
    descLines.slice(0, 2).forEach((line, i) => {
      ctx.fillText(line, tnX, tnY + 20 + i * 15);
    });

    // Tags (3 个胶囊)
    const tagY = profileY + 108;
    const tagH = 32;
    const tagGap = 8;
    const tagAreaX = 22 + 18;
    const tagAreaW = W - 44 - 36;
    const tagW = (tagAreaW - tagGap * 2) / 3;
    const TAG_COLORS = [
      { c1: '#fff2f5', c2: '#ffd6df', text: '#e95579', bd: 'rgba(255,134,158,0.45)', emoji: '🛡' },
      { c1: '#f6f1ff', c2: '#e7dcff', text: '#8560e8', bd: 'rgba(159,127,244,0.36)', emoji: '☁' },
      { c1: '#eefff9', c2: '#d1f7ec', text: '#2d9f8e', bd: 'rgba(91,202,176,0.36)', emoji: '🧭' },
    ];
    for (let i = 0; i < 3; i++) {
      const tx = tagAreaX + i * (tagW + tagGap);
      const tg = ctx.createLinearGradient(tx, tagY, tx, tagY + tagH);
      tg.addColorStop(0, TAG_COLORS[i].c1);
      tg.addColorStop(1, TAG_COLORS[i].c2);
      ctx.setFillStyle(tg);
      _roundRect(ctx, tx, tagY, tagW, tagH, 17);
      ctx.fill();
      ctx.setStrokeStyle(TAG_COLORS[i].bd);
      ctx.setLineWidth(1);
      _roundRect(ctx, tx + 0.5, tagY + 0.5, tagW - 1, tagH - 1, 17);
      ctx.stroke();

      ctx.setFillStyle(TAG_COLORS[i].text);
      ctx.setFontSize(12);
      ctx.setTextAlign('center');
      const lbl = (tags[i] || '').slice(0, 5);
      ctx.fillText(TAG_COLORS[i].emoji + ' ' + lbl, tx + tagW / 2, tagY + 21);
    }

    // ═══ Panel 1: 你的恋爱特质 ═══
    const p1Y = profileY + profileH + 12;
    const p1H = 116;
    ctx.setFillStyle('rgba(255,255,255,0.78)');
    ctx.setShadow(0, 14, 28, 'rgba(204,95,128,0.14)');
    _roundRect(ctx, 22, p1Y, W - 44, p1H, 24);
    ctx.fill();
    ctx.setShadow(0, 0, 0, 'rgba(0,0,0,0)');
    ctx.setStrokeStyle('rgba(255,255,255,0.72)');
    ctx.setLineWidth(1);
    _roundRect(ctx, 22.5, p1Y + 0.5, W - 45, p1H - 1, 24);
    ctx.stroke();

    // panel-title 倾斜胶囊
    ctx.save();
    ctx.translate(22 + 16, p1Y + 12);
    ctx.rotate(-1 * Math.PI / 180);
    const pt1Grad = ctx.createLinearGradient(0, 0, 122, 0);
    pt1Grad.addColorStop(0, '#ff748f');
    pt1Grad.addColorStop(1, '#ff9a76');
    ctx.setFillStyle(pt1Grad);
    ctx.setShadow(0, 8, 14, 'rgba(255,105,137,0.22)');
    _roundRect(ctx, 0, 0, 124, 28, 10);
    ctx.fill();
    ctx.setShadow(0, 0, 0, 'rgba(0,0,0,0)');
    ctx.setFillStyle('#FFFFFF');
    ctx.setFontSize(14);
    ctx.setTextAlign('center');
    ctx.fillText('你的恋爱特质', 62, 19);
    ctx.restore();

    // Traits 列表 (3 条 + 虚线)
    traits.forEach((t, i) => {
      const ty = p1Y + 58 + i * 20;
      ctx.setFillStyle('#ff6685');
      ctx.setFontSize(13);
      ctx.setTextAlign('left');
      ctx.fillText('❤', 22 + 16, ty);

      ctx.setFillStyle('rgba(75,50,66,0.8)');
      ctx.setFontSize(13);
      ctx.fillText(t, 22 + 36, ty);

      if (i < traits.length - 1) {
        _dashedLine(ctx, 22 + 16, ty + 8, W - 22 - 16, ty + 8, 'rgba(222,117,147,0.28)');
      }
    });

    // ═══ Panel 2: 关系能力图谱 + Radar + Score ═══
    const p2Y = p1Y + p1H + 12;
    const p2H = 148;
    ctx.setFillStyle('rgba(255,255,255,0.78)');
    ctx.setShadow(0, 14, 28, 'rgba(204,95,128,0.14)');
    _roundRect(ctx, 22, p2Y, W - 44, p2H, 24);
    ctx.fill();
    ctx.setShadow(0, 0, 0, 'rgba(0,0,0,0)');
    ctx.setStrokeStyle('rgba(255,255,255,0.72)');
    ctx.setLineWidth(1);
    _roundRect(ctx, 22.5, p2Y + 0.5, W - 45, p2H - 1, 24);
    ctx.stroke();

    // Radar (左侧 120×120 — 收紧)
    const radarCx = 22 + 16 + 56;
    const radarCy = p2Y + 14 + 56;
    const radarR = 48;
    ctx.setFillStyle('#fff7f8');
    ctx.beginPath();
    ctx.arc(radarCx, radarCy, radarR + 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.setStrokeStyle('rgba(255,117,149,0.25)');
    ctx.setLineWidth(1);
    ctx.beginPath();
    ctx.arc(radarCx, radarCy, radarR + 4, 0, Math.PI * 2);
    ctx.stroke();

    const N = 5;
    const angles = Array.from({ length: N }, (_, i) => -Math.PI / 2 + i * 2 * Math.PI / N);
    const pt = (a, r) => ({ x: radarCx + r * Math.cos(a), y: radarCy + r * Math.sin(a) });

    // 网格 3 层
    [0.45, 0.7, 1.0].forEach(lvl => {
      const pts = angles.map(a => pt(a, radarR * lvl));
      ctx.setStrokeStyle('rgba(205,111,145,0.22)');
      ctx.setLineWidth(1);
      ctx.beginPath();
      ctx.moveTo(pts[0].x, pts[0].y);
      for (let j = 1; j < N; j++) ctx.lineTo(pts[j].x, pts[j].y);
      ctx.closePath();
      ctx.stroke();
    });

    // 轴线
    angles.forEach(a => {
      const e = pt(a, radarR);
      ctx.setStrokeStyle('rgba(205,111,145,0.2)');
      ctx.setLineWidth(1);
      ctx.beginPath();
      ctx.moveTo(radarCx, radarCy);
      ctx.lineTo(e.x, e.y);
      ctx.stroke();
    });

    // 数据多边形
    const dpts = radarVals.map((v, i) => pt(angles[i], radarR * v));
    const radarGrad = ctx.createLinearGradient(radarCx - radarR, radarCy - radarR, radarCx + radarR, radarCy + radarR);
    radarGrad.addColorStop(0, 'rgba(255,115,144,0.72)');
    radarGrad.addColorStop(1, 'rgba(255,159,117,0.52)');
    ctx.setFillStyle(radarGrad);
    ctx.beginPath();
    ctx.moveTo(dpts[0].x, dpts[0].y);
    for (let i = 1; i < N; i++) ctx.lineTo(dpts[i].x, dpts[i].y);
    ctx.closePath();
    ctx.fill();
    ctx.setStrokeStyle('#ff6d8a');
    ctx.setLineWidth(2);
    ctx.beginPath();
    ctx.moveTo(dpts[0].x, dpts[0].y);
    for (let i = 1; i < N; i++) ctx.lineTo(dpts[i].x, dpts[i].y);
    ctx.closePath();
    ctx.stroke();

    // 端点 5 色圆点
    const RADAR_DOTS = ['#ff5f82', '#ff8d60', '#ffc064', '#9f7af0', '#5fd0b5'];
    dpts.forEach((d, i) => {
      ctx.setFillStyle(RADAR_DOTS[i]);
      ctx.beginPath();
      ctx.arc(d.x, d.y, 3.8, 0, Math.PI * 2);
      ctx.fill();
    });

    // chart-title + score-list (右侧)
    const slX = 22 + 16 + 120 + 14;
    const slY = p2Y + 18;
    ctx.setFillStyle('#6d435c');
    ctx.setFontSize(14);
    ctx.setTextAlign('left');
    ctx.fillText('关系能力图谱', slX, slY + 6);

    const SCORE_LABELS = ['稳定性', '责任感', '沟通力', '包容力'];
    for (let i = 0; i < 4; i++) {
      const sy = slY + 26 + i * 22;
      ctx.setFillStyle('rgba(75,50,66,0.72)');
      ctx.setFontSize(12);
      ctx.setTextAlign('left');
      ctx.fillText(SCORE_LABELS[i], slX, sy);

      ctx.setFillStyle('#ff6685');
      ctx.setFontSize(12);
      ctx.setTextAlign('right');
      ctx.fillText(scorePcts[i] + '%', W - 22 - 16, sy);

      if (i < 3) {
        _dashedLine(ctx, slX, sy + 7, W - 22 - 16, sy + 7, 'rgba(191,125,158,0.2)');
      }
    }

    // ═══ Footer (流光线 + 文字) — 接在 panel2 后 ═══
    const ftY = p2Y + p2H + 24;
    const lnA1 = ctx.createLinearGradient(W * 0.18, ftY, W * 0.36, ftY);
    lnA1.addColorStop(0, 'rgba(230,102,139,0)');
    lnA1.addColorStop(0.5, 'rgba(230,102,139,0.45)');
    lnA1.addColorStop(1, 'rgba(230,102,139,0)');
    ctx.setStrokeStyle(lnA1);
    ctx.setLineWidth(1);
    ctx.beginPath();
    ctx.moveTo(W * 0.18, ftY);
    ctx.lineTo(W * 0.36, ftY);
    ctx.stroke();

    const lnA2 = ctx.createLinearGradient(W * 0.64, ftY, W * 0.82, ftY);
    lnA2.addColorStop(0, 'rgba(230,102,139,0)');
    lnA2.addColorStop(0.5, 'rgba(230,102,139,0.45)');
    lnA2.addColorStop(1, 'rgba(230,102,139,0)');
    ctx.setStrokeStyle(lnA2);
    ctx.beginPath();
    ctx.moveTo(W * 0.64, ftY);
    ctx.lineTo(W * 0.82, ftY);
    ctx.stroke();

    ctx.setFillStyle('rgba(103,67,87,0.74)');
    ctx.setFontSize(13);
    ctx.setTextAlign('center');
    ctx.fillText('分享你的恋爱侧写', W / 2, ftY + 5);

    // 8 秒超时兜底：抖音 Canvas API 偶尔静默挂掉，避免用户永远看"生成中"
    const timeoutTimer = setTimeout(() => {
      console.error('[poster] TIMEOUT 8s — canvas/file API 未响应');
      tt.hideLoading();
      tt.showToast({ title: '海报生成超时，请重试', icon: 'none', duration: 3000 });
    }, 8000);

    console.log('[poster] before ctx.draw', ms(), 'ms');
    // 不依赖 ctx.draw 的 callback（抖音上某些场景永不触发），改用固定延迟兜底
    // 新画布 420x920 + ~200 drawCall (含多层 gradient + radar)，延迟从 400ms 提到 600ms
    ctx.draw(false);
    console.log('[poster] ctx.draw called (no cb), wait 600ms then export', ms(), 'ms');
    setTimeout(() => {
      console.log('[poster] calling canvasToTempFilePath', ms(), 'ms');
      tt.canvasToTempFilePath({
        canvasId: 'poster',
        destWidth: W * 2,
        destHeight: H * 2,
        success: (res) => {
          clearTimeout(timeoutTimer);
          console.log('[poster] OK', ms(), 'ms', res.tempFilePath);
          tt.hideLoading();
          // Phase 5：海报生成成功的轻量震动反馈
          if (tt.vibrateShort) {
            tt.vibrateShort({ type: 'light' });
          }
          this.setData({ posterPath: res.tempFilePath, showPoster: true });
        },
        fail: (err) => {
          clearTimeout(timeoutTimer);
          console.error('[poster] canvasToTempFilePath FAIL', ms(), 'ms', err);
          tt.hideLoading();
          tt.showToast({ title: '海报生成失败，请重试', icon: 'none' });
        },
      }, this);
    }, 600);
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
    const { personalityType, parsed, streamingTypeName, posterPath } = this.data;
    const name = (parsed && parsed.typeName) || streamingTypeName || personalityType || '恋爱侧写';
    return {
      channel: 'video',
      title: '我的恋爱人格是「' + name + '」，来测测你的～',
      desc: '看见你的关系模式，找到更适合的爱',
      imageUrl: posterPath || '',
      path: '/pages/index/index',
      extra: { image: posterPath || '' },
      success: () => {
        console.log('[share] success');
        tt.showToast({ title: '分享成功', icon: 'success', duration: 1500 });
      },
      fail: (err) => {
        console.warn('[share] fail', err);
        tt.showToast({ title: '分享取消', icon: 'none', duration: 1500 });
      },
    };
  },

});
