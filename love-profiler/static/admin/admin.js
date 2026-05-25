let _curView = 'overview';
let _curPage = 1;
let _curLimit = 50;
let _curQ = '';
let _editingRow = null;

function navigate(view, el) {
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  el.classList.add('active');
  _curView = view;
  _curPage = 1;
  _curQ = '';
  if (view === 'overview') loadOverview();
  else loadTable(view, 1, _curLimit, '');
}

function refreshCurrent() {
  if (_curView === 'overview') loadOverview();
  else loadTable(_curView, _curPage, _curLimit, _curQ);
}

function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
// JS 字符串字面量转义：用于嵌入 onclick="fn('${jsesc(x)}')" 这种场景，
// 防止 x 含单引号或反斜杠时断掉 JS。
function jsesc(s) {
  return String(s ?? '').replace(/\\/g,'\\\\').replace(/'/g,"\\'");
}
function fmtNum(n) {
  if (n == null) return '—';
  if (n >= 10000) return (n/1000).toFixed(1)+'k';
  return Number(n).toLocaleString();
}
function fmtDate(v) {
  if (!v) return '—';
  const d = new Date(v);
  const p = n => String(n).padStart(2,'0');
  return `${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
function badgeHtml(val) {
  if (val == null) return '<span class="dim">—</span>';
  const cls = String(val).toLowerCase().replace(/[^a-z]/g,'');
  return `<span class="badge badge-${cls}">${esc(val)}</span>`;
}
function boolHtml(val) {
  if (val == null) return '<span class="dim">—</span>';
  return val ? '<span class="bool-true">✓</span>' : '<span class="bool-false">✗</span>';
}
function cellHtml(val) {
  if (val == null) return '<span class="dim">—</span>';
  if (typeof val === 'boolean') return boolHtml(val);
  const s = String(val);
  if (['success','error','pending','paid','failed','complete','analyzed','generating',
       'high','moderate','info'].includes(s.toLowerCase())) return badgeHtml(s);
  return esc(s);
}
function showToast(msg, ok=true) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show ' + (ok ? 'ok' : 'err');
  setTimeout(() => t.className = 'toast', 2500);
}
function setMain(html) {
  document.getElementById('main').innerHTML = html;
}

// ===== 仪表盘状态 =====
let _dashRangeDays = 7;        // 默认 7 天窗口
let _dashLlmHours  = 24;       // LLM 监控固定 24h（最大不超过 168）
const _dashCharts = {};        // {key: echarts instance}

function _disposeDashCharts() {
  Object.values(_dashCharts).forEach(c => { try { c.dispose(); } catch(e){} });
  Object.keys(_dashCharts).forEach(k => delete _dashCharts[k]);
}

function _isDark() {
  return document.documentElement.getAttribute('data-theme') !== 'light';
}

// 主题色板（基于 CSS var 落到 JS 端，dark/light 自动切换）
function _palette() {
  const dark = _isDark();
  return {
    text:    dark ? '#e2e8f0' : '#2A2A3A',
    muted:   dark ? '#64748b' : '#8A857F',
    border:  dark ? '#1e2535' : '#E0DAD3',
    grid:    dark ? '#1c2330' : '#EDE7E0',
    bg:      dark ? '#161b27' : '#FFFFFF',
    accent:  dark ? '#3b82f6' : '#4FAFAF',
    teal:    '#4FAFAF',
    blue:    '#3b82f6',
    green:   dark ? '#4ade80' : '#15803D',
    yellow:  '#fbbf24',
    red:     dark ? '#f87171' : '#DC2626',
    purple:  '#a78bfa',
    pink:    '#f472b6',
    // D1 分组配色（16类柱状图按 D1 前缀分组）
    d1Group: { S:'#4ade80', MS:'#3b82f6', MA:'#fbbf24', A:'#f87171' },
  };
}

function _baseGrid() {
  return { left: 40, right: 16, top: 28, bottom: 28, containLabel: true };
}

function _initChart(id, option) {
  const dom = document.getElementById(id);
  if (!dom || !window.echarts) return null;
  const inst = echarts.init(dom, _isDark() ? 'dark' : null, { renderer: 'canvas' });
  inst.setOption(option);
  _dashCharts[id] = inst;
  return inst;
}

function _fmtDateShort(s) {
  if (!s) return '';
  // 'YYYY-MM-DD' → 'MM-DD'
  return s.length >= 10 ? s.slice(5, 10) : s;
}

function _fmtHourShort(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const p = n => String(n).padStart(2,'0');
  return `${p(d.getHours())}:00`;
}

async function loadOverview() {
  _disposeDashCharts();
  setMain('<div class="empty"><span class="spinner"></span>加载中…</div>');

  const days = _dashRangeDays;
  const [ov, biz, llm, qual] = await Promise.all([
    apiFetch('/admin/api/overview'),
    apiFetch(`/admin/api/metrics/business?days=${days}`),
    apiFetch(`/admin/api/metrics/llm?hours=${_dashLlmHours}&top_n=10`),
    apiFetch(`/admin/api/metrics/quality?days=${Math.max(days, 30)}`),
  ]);
  if (!ov) return;

  const t = ov.tables;
  const uStats = t.users || {};
  const aStats = t.assessments || {};
  const oStats = t.orders || {};
  const aiStats = t.ai_call_logs || {};
  const totalA = aStats.total || 0;
  const totalO = oStats.total || 0;
  const paidO  = (oStats.by_status||{}).paid || 0;
  const conversion = totalA > 0 ? (paidO / totalA * 100).toFixed(1) : '0.0';
  const dur = (llm && llm.duration) || {};

  const recentRows = (ov.recent_assessments || []).map(a => `
    <tr>
      <td class="mono dim">#${a.id}</td>
      <td class="mono dim">${esc((a.session_id||'').slice(0,8))}</td>
      <td>${esc(a.personality_type||'—')}</td>
      <td>${badgeHtml(a.status)}</td>
      <td class="dim">${fmtDate(a.created_at)}</td>
    </tr>`).join('') || '<tr><td colspan="5" class="empty">暂无数据</td></tr>';

  // 质量评分小卡
  const qb = (qual && qual.buckets) || {excellent:0,good:0,poor:0};
  const qTotal = qual && qual.total || 0;
  const qPct = (n) => qTotal > 0 ? (n/qTotal*100).toFixed(0) + '%' : '—';

  setMain(`
    <div class="section-title">仪表盘</div>
    <div class="range-toolbar">
      <span class="label">时间窗：</span>
      <button class="range-btn ${days===1?'active':''}" onclick="setDashRange(1)">24h</button>
      <button class="range-btn ${days===7?'active':''}" onclick="setDashRange(7)">7 天</button>
      <button class="range-btn ${days===30?'active':''}" onclick="setDashRange(30)">30 天</button>
      <span class="label" style="margin-left:16px">LLM 监控固定 24h</span>
    </div>

    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-label">用户总数</div>
        <div class="stat-val teal">${fmtNum(uStats.total)}</div>
        <div class="stat-sub">今日 +${uStats.today || 0}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">测评记录</div>
        <div class="stat-val">${fmtNum(totalA)}</div>
        <div class="stat-sub">今日 +${aStats.today || 0}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">付费转化率</div>
        <div class="stat-val green">${conversion}%</div>
        <div class="stat-sub">已付 ${fmtNum(paidO)} / 测评 ${fmtNum(totalA)}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">AI 调用（今日）</div>
        <div class="stat-val">${fmtNum(aiStats.today)}</div>
        <div class="stat-sub">总计 ${fmtNum(aiStats.total)}</div>
      </div>
    </div>

    <div class="chart-grid">
      <div class="chart-card">
        <div class="chart-hdr">
          <div class="chart-title">用户增长趋势</div>
          <div class="chart-sub">最近 ${days} 天</div>
        </div>
        <div class="chart-box" id="ch_users"></div>
      </div>
      <div class="chart-card">
        <div class="chart-hdr">
          <div class="chart-title">答题漏斗</div>
          <div class="chart-sub">${days} 天内 status 分布</div>
        </div>
        <div class="chart-box" id="ch_funnel"></div>
      </div>
      <div class="chart-card">
        <div class="chart-hdr">
          <div class="chart-title">16 类人格分布</div>
          <div class="chart-sub">按 D1 依恋分组配色</div>
        </div>
        <div class="chart-box" id="ch_persona"></div>
      </div>
      <div class="chart-card">
        <div class="chart-hdr">
          <div class="chart-title">订单趋势 + 收入</div>
          <div class="chart-sub">订单数（堆叠柱） + 收入（折线，元）</div>
        </div>
        <div class="chart-box" id="ch_orders"></div>
      </div>
      <div class="chart-card">
        <div class="chart-hdr">
          <div class="chart-title">AI 响应耗时分位（24h）</div>
          <div class="chart-sub">success 调用，共 ${dur.count || 0} 次</div>
        </div>
        <div class="dur-row">
          <div class="dur-cell"><div class="k">P50</div><div class="v">${fmtNum(dur.p50)}<span style="font-size:11px;color:var(--muted)">ms</span></div></div>
          <div class="dur-cell"><div class="k">P95</div><div class="v">${fmtNum(dur.p95)}<span style="font-size:11px;color:var(--muted)">ms</span></div></div>
          <div class="dur-cell"><div class="k">P99</div><div class="v">${fmtNum(dur.p99)}<span style="font-size:11px;color:var(--muted)">ms</span></div></div>
          <div class="dur-cell"><div class="k">MAX</div><div class="v">${fmtNum(dur.max)}<span style="font-size:11px;color:var(--muted)">ms</span></div></div>
        </div>
        <div class="chart-box" id="ch_llm_trend" style="height:180px;margin-top:8px"></div>
      </div>
      <div class="chart-card">
        <div class="chart-hdr">
          <div class="chart-title">报告质量评分</div>
          <div class="chart-sub">${Math.max(days, 30)} 天内 LLM-as-judge · 均分 ${(qual&&qual.avg_score) || 0}</div>
        </div>
        <div class="chart-box" id="ch_quality"></div>
        <div class="quality-mini">
          <div class="q-cell"><div class="qk">优秀 ≥8</div><div class="qv q-excellent">${qb.excellent} <span style="font-size:11px;color:var(--muted)">${qPct(qb.excellent)}</span></div></div>
          <div class="q-cell"><div class="qk">良好 6-7</div><div class="qv q-good">${qb.good} <span style="font-size:11px;color:var(--muted)">${qPct(qb.good)}</span></div></div>
          <div class="q-cell"><div class="qk">待改进 ≤5</div><div class="qv q-poor">${qb.poor} <span style="font-size:11px;color:var(--muted)">${qPct(qb.poor)}</span></div></div>
        </div>
      </div>
    </div>

    <div class="chart-grid full">
      <div class="chart-card">
        <div class="chart-hdr">
          <div class="chart-title">今日 Token 消耗 Top 10 用户</div>
          <div class="chart-sub">prompt + completion，按 total 倒序</div>
        </div>
        <div class="chart-box tall" id="ch_tokens"></div>
      </div>
    </div>

    <div class="section-title" style="margin-top:8px">最近 5 条测评</div>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>ID</th><th>Session</th><th>类型</th><th>状态</th><th>时间</th></tr></thead>
        <tbody>${recentRows}</tbody>
      </table>
    </div>
  `);

  _renderDashCharts(biz || {}, llm || {}, qual || {});
}

function setDashRange(d) {
  _dashRangeDays = d;
  loadOverview();
}

function _renderDashCharts(biz, llm, qual) {
  const p = _palette();

  // ① 用户增长 — 双线折线
  const du = biz.daily_users || [];
  _initChart('ch_users', {
    grid: _baseGrid(),
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: p.muted }, top: 0, right: 0 },
    xAxis: {
      type: 'category',
      data: du.map(r => _fmtDateShort(r.date)),
      axisLine: { lineStyle: { color: p.border } },
      axisLabel: { color: p.muted, fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: p.grid } },
      axisLabel: { color: p.muted, fontSize: 10 },
    },
    series: [
      { name: '新增用户', type: 'line', smooth: true, symbol: 'circle', symbolSize: 5,
        data: du.map(r => r.new_users), lineStyle: { color: p.teal, width: 2 },
        itemStyle: { color: p.teal },
        areaStyle: { color: p.teal, opacity: 0.08 } },
      { name: '完成测评', type: 'line', smooth: true, symbol: 'circle', symbolSize: 5,
        data: du.map(r => r.completed_assessments), lineStyle: { color: p.blue, width: 2 },
        itemStyle: { color: p.blue } },
    ],
  });

  // ② 答题漏斗
  const fn = (biz.funnel && biz.funnel.stages) || {};
  _initChart('ch_funnel', {
    tooltip: { trigger: 'item', formatter: '{b}: {c}' },
    legend: { textStyle: { color: p.muted }, top: 0, right: 0 },
    series: [{
      type: 'funnel',
      left: '5%', right: '5%', top: 30, bottom: 10,
      label: { color: p.text, fontSize: 12, formatter: '{b}: {c}' },
      labelLine: { lineStyle: { color: p.muted } },
      data: [
        { name: '待答题', value: fn.pending || 0, itemStyle: { color: '#94a3b8' } },
        { name: '生成中', value: fn.generating || 0, itemStyle: { color: p.yellow } },
        { name: '已分析', value: fn.analyzed || 0, itemStyle: { color: p.blue } },
        { name: '已完成', value: fn.complete || 0, itemStyle: { color: p.green } },
      ],
    }],
  });

  // ③ 16 类人格分布柱状
  const pd = biz.personality_distribution || [];
  _initChart('ch_persona', {
    grid: { ..._baseGrid(), bottom: 56 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: {
      type: 'category',
      data: pd.map(r => r.type_code),
      axisLine: { lineStyle: { color: p.border } },
      axisLabel: { color: p.muted, fontSize: 9, rotate: 35 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: p.grid } },
      axisLabel: { color: p.muted, fontSize: 10 },
    },
    series: [{
      type: 'bar',
      data: pd.map(r => ({
        value: r.count,
        itemStyle: { color: p.d1Group[r.d1_group] || p.accent, borderRadius: [3,3,0,0] },
      })),
      barMaxWidth: 22,
    }],
  });

  // ④ 订单趋势 — 堆叠柱 + 折线收入
  const dorders = biz.daily_orders || [];
  _initChart('ch_orders', {
    grid: _baseGrid(),
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { textStyle: { color: p.muted }, top: 0, right: 0 },
    xAxis: {
      type: 'category',
      data: dorders.map(r => _fmtDateShort(r.date)),
      axisLine: { lineStyle: { color: p.border } },
      axisLabel: { color: p.muted, fontSize: 10 },
    },
    yAxis: [
      { type: 'value', name: '订单', nameTextStyle: { color: p.muted, fontSize: 10 },
        splitLine: { lineStyle: { color: p.grid } },
        axisLabel: { color: p.muted, fontSize: 10 } },
      { type: 'value', name: '收入(¥)', nameTextStyle: { color: p.muted, fontSize: 10 },
        splitLine: { show: false },
        axisLabel: { color: p.muted, fontSize: 10 } },
    ],
    series: [
      { name: '已付', type: 'bar', stack: 'orders', barMaxWidth: 22,
        data: dorders.map(r => r.paid), itemStyle: { color: p.green } },
      { name: '失败', type: 'bar', stack: 'orders', barMaxWidth: 22,
        data: dorders.map(r => r.failed), itemStyle: { color: p.red } },
      { name: '待支付', type: 'bar', stack: 'orders', barMaxWidth: 22,
        data: dorders.map(r => r.pending), itemStyle: { color: p.muted } },
      { name: '收入(¥)', type: 'line', smooth: true, yAxisIndex: 1, symbol: 'circle', symbolSize: 5,
        data: dorders.map(r => r.revenue_yuan), lineStyle: { color: p.yellow, width: 2 },
        itemStyle: { color: p.yellow } },
    ],
  });

  // ⑤ LLM 调用量小时趋势（堆叠柱 success/error）
  const tr = llm.hourly_trend || [];
  _initChart('ch_llm_trend', {
    grid: { left: 36, right: 8, top: 18, bottom: 22, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { textStyle: { color: p.muted, fontSize: 10 }, top: 0, right: 0 },
    xAxis: {
      type: 'category',
      data: tr.map(r => _fmtHourShort(r.hour)),
      axisLine: { lineStyle: { color: p.border } },
      axisLabel: { color: p.muted, fontSize: 9, interval: 3 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: p.grid } },
      axisLabel: { color: p.muted, fontSize: 10 },
    },
    series: [
      { name: 'success', type: 'bar', stack: 'calls', barMaxWidth: 14,
        data: tr.map(r => r.success), itemStyle: { color: p.green } },
      { name: 'error', type: 'bar', stack: 'calls', barMaxWidth: 14,
        data: tr.map(r => r.error), itemStyle: { color: p.red } },
    ],
  });

  // ⑥ 报告质量评分 — 环形
  const qb = qual.buckets || { excellent:0, good:0, poor:0 };
  _initChart('ch_quality', {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { textStyle: { color: p.muted, fontSize: 10 }, top: 0, right: 0 },
    series: [{
      type: 'pie',
      radius: ['45%', '70%'],
      center: ['50%', '55%'],
      avoidLabelOverlap: true,
      label: { color: p.text, fontSize: 11, formatter: '{b}\n{d}%' },
      labelLine: { lineStyle: { color: p.muted } },
      data: [
        { name: '优秀 ≥8', value: qb.excellent, itemStyle: { color: p.green } },
        { name: '良好 6-7', value: qb.good,     itemStyle: { color: p.yellow } },
        { name: '待改进 ≤5', value: qb.poor,    itemStyle: { color: p.red } },
      ],
    }],
  });

  // ⑦ Token Top 10 横向条形
  const tu = llm.top_users || [];
  _initChart('ch_tokens', {
    grid: { left: 110, right: 24, top: 28, bottom: 28, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { textStyle: { color: p.muted }, top: 0, right: 0 },
    xAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: p.grid } },
      axisLabel: { color: p.muted, fontSize: 10 },
    },
    yAxis: {
      type: 'category',
      inverse: true,
      data: tu.map(u => u.openid_masked || ('#' + u.user_id)),
      axisLine: { lineStyle: { color: p.border } },
      axisLabel: { color: p.muted, fontSize: 11 },
    },
    series: [
      { name: 'prompt', type: 'bar', stack: 'tk', barMaxWidth: 16,
        data: tu.map(u => u.prompt_tokens), itemStyle: { color: p.blue } },
      { name: 'completion', type: 'bar', stack: 'tk', barMaxWidth: 16,
        data: tu.map(u => u.completion_tokens), itemStyle: { color: p.teal } },
    ],
  });
}

// 窗口大小变化时让所有图表自适应
window.addEventListener('resize', () => {
  Object.values(_dashCharts).forEach(c => { try { c.resize(); } catch(e){} });
});

// 表名中文映射
const TABLE_NAMES = {
  users:               '用户',
  assessments:         '测评记录',
  orders:              '订单',
  ai_call_logs:        'AI 调用日志',
  base_love_type:      '人格类型',
  highlights:          '深度洞察',
  base_dimension_meta: '维度元信息',
  base_segment_decode: '段落解码',
  base_D4_type:        '爱的语言',
  base_D5_quadrant:    '表达象限',
  questions:           '题库',
};

// 字段中文映射（按表分组，最后合并）
const FIELD_NAMES = {
  // 通用
  id: 'ID', user_id: '用户 ID', created_at: '创建时间', ts: '时间', version: '版本',

  // users
  openid: '抖音 OpenID',

  // assessments
  session_id: '会话 ID', signals: '答题信号', personality_type: '人格类型代码',
  report_text: '完整报告', summary: '报告摘要', status: '状态', mode: '测评模式',
  dimension_scores: '维度得分', answers_json: '答案数据', diagnosis_json: '诊断数据',
  report_json: '报告数据',

  // orders
  assessment_id: '测评 ID', out_trade_no: '商户订单号', amount: '金额（分）',

  // ai_call_logs
  agent: '智能体', model: '模型', temperature: '温度', retry_index: '重试序号',
  error_message: '错误信息', http_status_code: 'HTTP 状态', system_prompt_len: 'Prompt 字符数',
  messages_json: '请求消息', response_preview: '响应内容', response_len: '响应字符数',
  duration_ms: '耗时(ms)', prompt_tokens: '输入 Tokens', completion_tokens: '输出 Tokens',
  total_tokens: '总 Tokens',

  // base_love_type
  type_code: '类型代码', type_name: '人格类型名称', tagline: '副标题', img_path: '形象图路径',

  // highlights
  code: '编码', layer: '层级', involved_dims: '涉及维度', severity: '严重度',
  is_positive: '正向标志', name_cn: '中文名称', trigger_condition: '触发条件',
  interp_path: '解读路径', report_seed: '写作种子', sort_order: '排序',

  // base_dimension_meta
  description: '描述', score_model: '评分模型', radar_label: '雷达图标签',

  // base_segment_decode
  dimension: '维度', label_cn: '中文标签', score_range: '分数区间', is_healthy: '健康端',

  // base_D4_type
  love_languages_code: '爱语代码', love_languages_name: '爱语名称',
  love_languages_detail: '爱语详解',

  // base_D5_quadrant
  quadrant: '象限', style_name: '风格名称', guide: '解读指南',

  // questions
  question_id: '题目 ID', signal_code: '信号代码', signal_name: '信号名称',
  question_type: '题型', stem: '题干',
  option_a: '选项 A', option_b: '选项 B', option_c: '选项 C',
  option_d: '选项 D', option_e: '选项 E',
  score_a: 'A 计分', score_b: 'B 计分', score_c: 'C 计分',
  score_d: 'D 计分', score_e: 'E 计分',
  notes: '备注',
};

function tableLabel(t) { return TABLE_NAMES[t] || t; }
function fieldLabel(f) { return FIELD_NAMES[f] || f; }

const COL_CONFIG = {
  users:               ['id','openid','created_at'],
  assessments:         ['id','user_id','session_id','personality_type','status','mode','created_at'],
  orders:              ['id','user_id','assessment_id','out_trade_no','amount','status','created_at'],
  ai_call_logs:        ['id','ts','agent','session_id','model','status','duration_ms','total_tokens','retry_index'],
  base_love_type:      ['id','type_code','type_name','tagline'],
  highlights:          ['code','layer','involved_dims','severity','is_positive','name_cn','sort_order'],
  base_dimension_meta: ['code','name_cn','description','score_model','radar_label','sort_order'],
  base_segment_decode: ['id','dimension','code','label_cn','score_range','is_healthy'],
  base_D4_type:        ['id','love_languages_code','love_languages_name'],
  base_D5_quadrant:    ['quadrant','style_name','sort_order'],
  questions:           ['question_id','dimension','signal_code','signal_name','question_type','sort_order'],
};

const EDITABLE = {
  assessments:         ['status'],
  base_love_type:      ['type_name','tagline'],
  highlights:          ['name_cn','severity','is_positive'],
  base_dimension_meta: ['name_cn','description','radar_label'],
  base_segment_decode: ['label_cn','description','score_range'],
  base_D4_type:        ['love_languages_name','love_languages_detail'],
  base_D5_quadrant:    ['style_name','description','guide'],
};

const TEXTAREA_FIELDS = ['tagline','description','guide','interp_path','report_seed',
                         'trigger_condition','love_languages_detail','radar_label'];

function getPk(table) {
  const pks = { highlights:'code', base_dimension_meta:'code',
                base_D5_quadrant:'quadrant', questions:'question_id' };
  return pks[table] || 'id';
}

async function loadTable(table, page, limit, q) {
  _curView = table; _curPage = page; _curLimit = limit; _curQ = q;
  setMain(`<div class="empty"><span class="spinner"></span>加载中…</div>`);
  const params = new URLSearchParams({ page, limit });
  if (q) params.set('q', q);
  const data = await apiFetch(`/admin/api/${table}?${params}`);
  if (!data) return;
  if (data.error === 'table_not_available') {
    setMain(`<div class="section-title">${tableLabel(table)}</div>
             <div class="empty">此表在当前数据库不可用（可能需要 PostgreSQL 连接）</div>`);
    return;
  }
  const cols = COL_CONFIG[table] || Object.keys(data.rows[0] || {}).slice(0,8);
  const editable = EDITABLE[table] || [];
  const pk = getPk(table);
  const hasEdit = editable.length > 0;
  const theadCols = cols.map(c => `<th>${fieldLabel(c)}</th>`).join('');
  const tbodyRows = data.rows.length === 0
    ? `<tr><td colspan="${cols.length + (hasEdit?1:0)}" class="empty">暂无数据</td></tr>`
    : data.rows.map(row => renderRow(row, cols, editable, pk, table)).join('');

  setMain(`
    <div class="section-title">${tableLabel(table)}
      <span style="font-size:12px;font-weight:400;color:var(--muted);margin-left:8px">
        共 ${fmtNum(data.total)} 条
      </span>
    </div>
    <div class="tbl-toolbar">
      <input class="search-input" id="searchQ" placeholder="搜索…"
             value="${esc(q)}" onkeydown="if(event.key==='Enter')doSearch()">
      <button class="btn btn-sm" onclick="doSearch()">搜索</button>
      <select class="select-sm" onchange="loadTable('${table}',1,this.value,'${jsesc(q)}')">
        ${[20,50,100,200].map(n=>`<option value="${n}"${n==limit?' selected':''}>${n}条/页</option>`).join('')}
      </select>
      ${hasEdit ? '<span style="font-size:11px;color:var(--muted);margin-left:auto">✏️ 点击行末尾编辑</span>' : ''}
    </div>
    <div class="tbl-wrap">
      <table id="dataTable">
        <thead><tr>${theadCols}${hasEdit?'<th>操作</th>':''}</tr></thead>
        <tbody id="tbody">${tbodyRows}</tbody>
      </table>
    </div>
    <div class="pagination">
      <button onclick="loadTable('${table}',${page-1},${limit},'${jsesc(q)}')" ${page<=1?'disabled':''}>← 上一页</button>
      <span class="pg-info">第 ${page} / ${Math.ceil(data.total/limit)||1} 页</span>
      <button onclick="loadTable('${table}',${page+1},${limit},'${jsesc(q)}')"
        ${page >= Math.ceil(data.total/limit) ? 'disabled':''}>下一页 →</button>
    </div>`);
}

function renderRow(row, cols, editable, pk, table) {
  const pkVal = row[pk];
  const cells = cols.map(col => {
    const v = row[col];
    if (col === 'created_at' || col === 'ts') return `<td>${fmtDate(v)}</td>`;
    return `<td title="${esc(String(v??''))}">${cellHtml(v)}</td>`;
  }).join('');
  const editBtn = editable.length > 0
    ? `<td><div class="row-actions">
         <button class="btn-edit" onclick="event.stopPropagation();startEdit(this,'${table}','${pkVal}')">✏️ 编辑</button>
       </div></td>`
    : '';
  return `<tr class="clickable" data-pk="${pkVal}" onclick="openDetail('${table}','${pkVal}')">
    ${cells}${editBtn}
  </tr>`;
}

function doSearch() {
  const q = document.getElementById('searchQ')?.value || '';
  loadTable(_curView, 1, _curLimit, q);
}

async function startEdit(btn, table, pkVal) {
  const row = btn.closest('tr');
  _editingRow = row;
  row.classList.add('editing');
  const record = await apiFetch(`/admin/api/${table}/${pkVal}`);
  if (!record) return;
  const editable = EDITABLE[table] || [];
  const cols = COL_CONFIG[table] || [];
  let i = 0;
  for (const td of row.querySelectorAll('td:not(:last-child)')) {
    const col = cols[i++];
    if (!col) continue;
    if (editable.includes(col)) {
      const v = record[col] ?? '';
      const isLong = TEXTAREA_FIELDS.includes(col);
      if (typeof v === 'boolean') {
        td.innerHTML = `<select class="edit-input" data-field="${col}">
          <option value="true"${v?' selected':''}>true</option>
          <option value="false"${!v?' selected':''}>false</option>
        </select>`;
      } else if (isLong) {
        td.innerHTML = `<textarea class="edit-textarea" data-field="${col}">${esc(v)}</textarea>`;
      } else {
        td.innerHTML = `<input class="edit-input" data-field="${col}" value="${esc(v)}">`;
      }
    }
  }
  const actionTd = row.querySelector('td:last-child');
  if (actionTd) {
    actionTd.innerHTML = `<div class="row-actions">
      <button class="btn-save" onclick="saveEdit(this,'${table}','${pkVal}')">保存</button>
      <button class="btn-cancel" onclick="cancelEditByBtn(this,'${table}','${pkVal}')">取消</button>
    </div>`;
  }
}

async function saveEdit(btn, table, pkVal) {
  const row = btn.closest('tr');
  const inputs = row.querySelectorAll('[data-field]');
  const body = {};
  inputs.forEach(inp => {
    const f = inp.dataset.field;
    let v = inp.value;
    if (inp.tagName === 'SELECT' && (v === 'true' || v === 'false')) {
      v = v === 'true';
    }
    body[f] = v;
  });
  const result = await apiFetch(`/admin/api/${table}/${pkVal}`, 'PUT', body);
  if (!result) return;
  row.classList.remove('editing');
  _editingRow = null;
  showToast('保存成功');
  row.classList.add('flash-green');
  setTimeout(() => row.classList.remove('flash-green'), 700);
  setTimeout(() => loadTable(table, _curPage, _curLimit, _curQ), 500);
}

function cancelEditByBtn(btn, table, pkVal) {
  _editingRow = null;
  loadTable(table, _curPage, _curLimit, _curQ);
}

async function resetAssessmentStatus(pkVal, btn) {
  if (!confirm(`确认将 assessment #${pkVal} 的状态从 generating 重置为 analyzed？`)) return;
  btn.disabled = true;
  const result = await apiFetch(`/admin/api/assessments/${pkVal}`, 'PUT', { status: 'analyzed' });
  if (result?.ok) {
    showToast('重置成功');
    loadTable('assessments', _curPage, _curLimit, _curQ);
    closeDetail();
  }
}

async function openDetail(table, pkVal) {
  if (_editingRow) return;
  document.getElementById('dpTitle').textContent = `${tableLabel(table)} · ${pkVal}`;
  document.getElementById('dpBody').innerHTML = '<div class="empty"><span class="spinner"></span>加载中…</div>';
  document.getElementById('detailOverlay').classList.add('open');
  const data = await apiFetch(`/admin/api/${table}/${pkVal}`);
  if (!data) return;

  const BIG_FIELDS = ['diagnosis_json','report_text','answers_json','report_json',
                      'dimension_scores','summary','signals','messages_json',
                      'response_preview','trigger_condition','interp_path',
                      'report_seed','guide','description'];

  let basicKvs = '', bigKvs = '';
  for (const [k, v] of Object.entries(data)) {
    if (BIG_FIELDS.includes(k)) {
      let content;
      try { content = JSON.stringify(JSON.parse(v), null, 2); }
      catch { content = String(v ?? ''); }
      bigKvs += `<details style="margin-bottom:8px">
        <summary>${esc(fieldLabel(k))} (${String(v??'').length} 字符)</summary>
        <pre class="json">${esc(content)}</pre>
      </details>`;
    } else {
      const disp = typeof v === 'boolean' ? boolHtml(v)
                 : ['status','severity'].includes(k) ? badgeHtml(v)
                 : `<span class="v">${esc(String(v??'—'))}</span>`;
      basicKvs += `<span class="k">${esc(fieldLabel(k))}</span>${disp}`;
    }
  }

  const resetBtn = table === 'assessments' && data.status === 'generating'
    ? `<button class="btn-reset" onclick="resetAssessmentStatus('${pkVal}',this)">
         ⚠️ 重置 generating → analyzed
       </button>` : '';

  document.getElementById('dpBody').innerHTML = `
    <div class="dp-section">
      <h4>基本字段</h4>
      <div class="kv">${basicKvs}</div>
      ${resetBtn}
    </div>
    ${bigKvs ? `<div class="dp-section"><h4>大字段（展开查看）</h4>${bigKvs}</div>` : ''}`;
}

function closeDetail(e) {
  if (!e || e.target === document.getElementById('detailOverlay')) {
    document.getElementById('detailOverlay').classList.remove('open');
  }
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDetail(); });

async function apiFetch(url, method='GET', body=null) {
  const token = new URLSearchParams(location.search).get('token') || '';
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json',
               ...(token ? { 'X-Admin-Token': token } : {}) },
  };
  if (body) opts.body = JSON.stringify(body);
  try {
    const res = await fetch(url, opts);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      showToast(`错误 ${res.status}: ${err.detail || res.statusText}`, false);
      return null;
    }
    return await res.json();
  } catch (e) {
    showToast(`网络错误: ${e.message}`, false);
    return null;
  }
}

// ─── Theme switcher ──────────────────────────────────
function applyTheme(theme) {
  if (theme === 'light') {
    document.documentElement.setAttribute('data-theme', 'light');
    document.getElementById('themeBtn').textContent = '☀️';
  } else {
    document.documentElement.removeAttribute('data-theme');
    document.getElementById('themeBtn').textContent = '🌙';
  }
}
function toggleTheme() {
  const cur = localStorage.getItem('admin-theme') || 'dark';
  const next = cur === 'dark' ? 'light' : 'dark';
  localStorage.setItem('admin-theme', next);
  applyTheme(next);
  // 仪表盘视图下：切换主题需要重建图表（ECharts 主题在 init 时一次性应用）
  if (_curView === 'overview' && Object.keys(_dashCharts).length > 0) {
    loadOverview();
  }
}
applyTheme(localStorage.getItem('admin-theme') || 'dark');

loadOverview();
