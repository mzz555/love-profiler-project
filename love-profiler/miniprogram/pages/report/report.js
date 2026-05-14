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
      heroImageUrl = 'http://localhost:8000' + decodeURIComponent(options.img_path);
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
        this.setData({
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
        });
        if (dimChart) {
          // streaming 区块进入 DOM 后 canvas 已存在，200ms 足够 canvas 初始化
          setTimeout(() => {
            console.log('[charts] drawing d123=', !!dimChart.d123, 'd4=', !!dimChart.d4, 'd5=', !!dimChart.d5);
            this._drawD123Gauges(dimChart.d123);
            this._drawCombinedRadar(dimChart.d123, dimChart.d4, dimChart.d5);
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
    });
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

  // ── 图表2：10轴全维雷达（D1-D3 + T1-T5 + S1-S2）──────────────────────
  _drawCombinedRadar(d123, d4, d5) {
    if (!d123 || d123.length < 3 || !d4 || !d5) return;
    const ctx = tt.createCanvasContext('combined-radar', this);
    try {
      const W = 640, H = 640, cx = W / 2, cy = H / 2, maxR = 220, N = 10;

      const s1Raw = typeof d5.s1_raw === 'number' ? d5.s1_raw : 0;
      const s2Raw = typeof d5.s2_raw === 'number' ? d5.s2_raw : 0;

      const vals = [
        (d123[0].raw + 12) / 24,
        (d123[1].raw + 12) / 24,
        (d123[2].raw + 12) / 24,
        parseFloat(d4.T1 || 0),
        parseFloat(d4.T2 || 0),
        parseFloat(d4.T3 || 0),
        parseFloat(d4.T4 || 0),
        parseFloat(d4.T5 || 0),
        (s1Raw + 6) / 12,
        (s2Raw + 6) / 12,
      ];
      const labels = ['依恋', '边界', '冲突', '言语', '时刻', '惊喜', '服务', '接触', '直接', '分享'];
      const COLORS = ['#FF7B6E','#4FC3F7','#CE93D8','#FF8A65','#F48FB1','#E91E8C','#AB47BC','#EC407A','#FFB74D','#FFA726'];
      const G_FILL = ['rgba(255,120,100,0.07)','rgba(244,143,177,0.07)','rgba(255,183,77,0.07)'];
      const G_AXES = [[0,1,2],[3,4,5,6,7],[8,9]];

      const angles = Array.from({length: N}, (_, i) => -Math.PI / 2 + i * 2 * Math.PI / N);
      const pt = (a, r) => ({ x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) });

      // 背景圆
      ctx.setFillStyle('rgba(248,245,241,0.6)');
      ctx.beginPath(); ctx.arc(cx, cy, maxR + 8, 0, Math.PI * 2); ctx.fill();

      // 组扇形底色
      G_AXES.forEach((idxArr, gi) => {
        const aStart = angles[idxArr[0]] - Math.PI / N;
        const aEnd   = angles[idxArr[idxArr.length - 1]] + Math.PI / N;
        ctx.beginPath(); ctx.moveTo(cx, cy);
        ctx.arc(cx, cy, maxR + 4, aStart, aEnd);
        ctx.closePath();
        ctx.setFillStyle(G_FILL[gi]); ctx.fill();
      });

      // 网格多边形
      [0.25, 0.5, 0.75, 1.0].forEach(lvl => {
        const pts = angles.map(a => pt(a, maxR * lvl));
        ctx.beginPath(); ctx.moveTo(pts[0].x, pts[0].y);
        for (let i = 1; i < N; i++) ctx.lineTo(pts[i].x, pts[i].y);
        ctx.closePath();
        ctx.setStrokeStyle(lvl === 1 ? 'rgba(150,140,132,0.50)' : 'rgba(200,190,182,0.25)');
        ctx.setLineWidth(lvl === 1 ? 2 : 1); ctx.stroke();
      });

      // 轴线
      angles.forEach((a, i) => {
        const {x, y} = pt(a, maxR);
        ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(x, y);
        ctx.setStrokeStyle(COLORS[i] + '55'); ctx.setLineWidth(1.5); ctx.stroke();
      });

      // 数据多边形
      const dpts = vals.map((v, i) => pt(angles[i], maxR * Math.max(0, Math.min(1, v))));
      ctx.beginPath(); ctx.moveTo(dpts[0].x, dpts[0].y);
      for (let i = 1; i < N; i++) ctx.lineTo(dpts[i].x, dpts[i].y);
      ctx.closePath();
      ctx.setFillStyle('rgba(79,175,175,0.22)'); ctx.fill();
      ctx.setStrokeStyle('#4FAFAF'); ctx.setLineWidth(3); ctx.stroke();

      // 数据节点
      dpts.forEach(({x, y}, i) => {
        ctx.beginPath(); ctx.arc(x, y, 9, 0, Math.PI * 2);
        ctx.setFillStyle(COLORS[i]); ctx.fill();
        ctx.beginPath(); ctx.arc(x, y, 4.5, 0, Math.PI * 2);
        ctx.setFillStyle('#FFFFFF'); ctx.fill();
      });

      // 标签（字号更大，偏移更大）
      labels.forEach((lbl, i) => {
        const a = angles[i], cosA = Math.cos(a), sinA = Math.sin(a);
        const {x, y} = pt(a, maxR + 38);
        const align = cosA > 0.2 ? 'left' : cosA < -0.2 ? 'right' : 'center';
        const dy = sinA < -0.4 ? -4 : sinA > 0.4 ? 12 : 6;
        ctx.setTextAlign(align);
        ctx.setFontSize(20); ctx.setFillStyle(COLORS[i]);
        ctx.fillText(lbl, x, y + dy);
        ctx.setFontSize(16); ctx.setFillStyle('rgba(130,120,112,0.80)');
        ctx.fillText(Math.round(Math.max(0, Math.min(1, vals[i])) * 100) + '%', x, y + dy + 22);
      });

      // canvas 已是 640px，无需 ×2
      ctx.draw(false, () => {
        tt.canvasToTempFilePath({
          canvasId: 'combined-radar',
          destWidth: W, destHeight: H,
          success: res => { console.log('[combined] img ok'); this.setData({ chartImgCombined: res.tempFilePath }); },
          fail: err => console.error('[combined] toImg fail', err),
        }, this);
      });
    } catch(e) { console.error('[combined] THROW', e.message, e); }
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
