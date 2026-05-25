/**
 * WebSocket 连接 + Section 渲染辅助
 * 从 report.js 提取，通过 .call(this, ...) 调用
 */
const app = getApp();

const TYPE_THEME_MAP = {
  S:  { primary: '#3A8A8A', accent: '#E8F4F2' },
  MS: { primary: '#5B73C9', accent: '#ECEFFA' },
  MA: { primary: '#C9743A', accent: '#FBEFE0' },
  A:  { primary: '#C94F4F', accent: '#FBE4E2' },
};
const DEFAULT_TYPE_THEME = { primary: '#4FAFAF', accent: '#F2EDE6' };

function inferTypeTheme(typeCode) {
  if (!typeCode) return DEFAULT_TYPE_THEME;
  var prefix = String(typeCode).split('-')[0];
  return TYPE_THEME_MAP[prefix] || DEFAULT_TYPE_THEME;
}

module.exports = {
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
      let text = m[2].trim();
      const hm = meta.find(h => h.idx === idx) || {};
      // LLM 输出格式 "High_N: <name_cn>：<body>"，正文里会复述一遍标题；
      // DB 注入的 hm.title 已经渲染在标题区，text 需要剥掉前缀避免视觉重复。
      // 兼容中文「：」和英文「:」，前缀长度限制 40 字防误伤超长正文。
      if (hm.title && text.startsWith(hm.title)) {
        const afterTitle = text.slice(hm.title.length).trimStart();
        if (afterTitle.startsWith('：') || afterTitle.startsWith(':')) {
          text = afterTitle.slice(1).trimStart();
        }
      }
      // 有标题或有正文都保留（标题来自 scoring engine，正文来自 report writer）
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
    var self = this;
    var t0 = Date.now();
    var elapsed = function() { return ((Date.now() - t0) / 1000).toFixed(2) + 's'; };

    console.log('[report] 请求 WS ticket session=', sessionId);
    app.request({ url: '/ws/ticket', method: 'POST', data: {} }).then(function(ticketRes) {
      var ticket = ticketRes.ticket;
      console.log('[report] ticket 获取成功，建立 WS 连接', elapsed());
      self._connectWs(sessionId, ticket, t0, elapsed);
    }).catch(function(err) {
      console.warn('[report] ticket 请求失败，降级用 token', err);
      self._connectWs(sessionId, null, t0, elapsed);
    });
  },

  _connectWs(sessionId, ticket, t0, elapsed) {
    var opts = { path: '/ws/result' };
    if (ticket) { opts.ticket = ticket; }
    var wsTask = app.connectSocket(opts);
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
          typeTheme: inferTypeTheme(msg.personality_type),
          streamingTypeName: msg.type_name,
          streamingTypeTagline: msg.type_tagline || '',
          streamingTypeDetail: msg.type_detail || '',
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
            this._drawFullRadar(dimChart.d123, dimChart.d4, dimChart.d5);
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
      typeTheme: inferTypeTheme(personalityType),
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
};
