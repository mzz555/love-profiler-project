/**
 * 图表绘制模块 — Canvas 雷达图 / 五瓣花 / 象限图
 * 从 report.js 提取，通过 require() 引入后 .call(this, ...) 调用
 */
var _u = require('./report-utils');
var _hexAlpha = _u._hexAlpha;

module.exports = {
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

      // 5 色端点：与全维雷达同源色系，每根轴一个语义色
      // D1 依恋 / D2 边界 / D3 冲突 / AWARE 自我认知 / STYLE 表达成熟
      const COLORS = ['#FF7B6E', '#4FC3F7', '#CE93D8', '#FFB74D', '#5FD0B5'];
      const VALUE_GREY = 'rgba(130,120,112,0.85)';

      const angles = Array.from({length: N}, (_, i) => -Math.PI / 2 + i * 2 * Math.PI / N);
      const pt = (a, r) => ({ x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) });

      // 背景柔光圆
      ctx.setFillStyle('rgba(248,245,241,0.6)');
      ctx.beginPath(); ctx.arc(cx, cy, maxR + 12, 0, Math.PI * 2); ctx.fill();

      // 网格五边形（25/50/75/100）
      [0.25, 0.5, 0.75, 1.0].forEach(lvl => {
        const pts = angles.map(a => pt(a, maxR * lvl));
        ctx.beginPath(); ctx.moveTo(pts[0].x, pts[0].y);
        for (let i = 1; i < N; i++) ctx.lineTo(pts[i].x, pts[i].y);
        ctx.closePath();
        ctx.setStrokeStyle(lvl === 1 ? 'rgba(150,140,132,0.50)' : 'rgba(200,190,182,0.25)');
        ctx.setLineWidth(lvl === 1 ? 2 : 1); ctx.stroke();
      });

      // 轴线（每根用对应 COLORS 淡色）
      angles.forEach((a, i) => {
        const {x, y} = pt(a, maxR);
        ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(x, y);
        ctx.setStrokeStyle(_hexAlpha(COLORS[i], 0.33)); ctx.setLineWidth(1.5); ctx.stroke();
      });

      // 数据多边形（teal 浅填 + teal 描边，与全维雷达一致）
      const dpts = vals.map((v, i) => pt(angles[i], maxR * v));
      ctx.beginPath(); ctx.moveTo(dpts[0].x, dpts[0].y);
      for (let i = 1; i < N; i++) ctx.lineTo(dpts[i].x, dpts[i].y);
      ctx.closePath();
      ctx.setFillStyle('rgba(79,175,175,0.22)'); ctx.fill();
      ctx.setStrokeStyle('#4FAFAF'); ctx.setLineWidth(3); ctx.stroke();

      // 数据节点（5 色端点 + 白心，与全维雷达一致）
      dpts.forEach(({x, y}, i) => {
        ctx.beginPath(); ctx.arc(x, y, 9, 0, Math.PI * 2);
        ctx.setFillStyle(COLORS[i]); ctx.fill();
        ctx.beginPath(); ctx.arc(x, y, 4.5, 0, Math.PI * 2);
        ctx.setFillStyle('#FFFFFF'); ctx.fill();
      });

      // 标签 + 百分比（每个用对应 COLORS）
      labels.forEach((lbl, i) => {
        const a = angles[i], cosA = Math.cos(a), sinA = Math.sin(a);
        const {x, y} = pt(a, maxR + 38);
        const align = cosA > 0.2 ? 'left' : cosA < -0.2 ? 'right' : 'center';
        const dy = sinA < -0.4 ? -4 : sinA > 0.4 ? 12 : 6;
        ctx.setTextAlign(align);
        ctx.setFontSize(20); ctx.setFillStyle(COLORS[i]);
        ctx.fillText(lbl, x, y + dy);
        ctx.setFontSize(16); ctx.setFillStyle(VALUE_GREY);
        ctx.fillText(Math.round(vals[i] * 100) + '%', x, y + dy + 22);
      });

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

  // ── 图表5：10 轴全维全景雷达（D1-D3 + T1-T5 + S1-S2）─────────────────
  // 作为"全景参考图"，与 5 维健康度并列；语义上跨混"健康/偏好/风格"，
  // 不作为读图核心，但视觉饱满便于整体观感与海报展示
  _drawFullRadar(d123, d4, d5) {
    if (!d123 || d123.length < 3 || !d4 || !d5) return;
    const ctx = tt.createCanvasContext('full-radar', this);
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

      // 组扇形底色（D1-3 / T1-5 / S1-2 三组）
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
        ctx.setStrokeStyle(_hexAlpha(COLORS[i], 0.33)); ctx.setLineWidth(1.5); ctx.stroke();
      });

      // 数据多边形
      const dpts = vals.map((v, i) => pt(angles[i], maxR * Math.max(0, Math.min(1, v))));
      ctx.beginPath(); ctx.moveTo(dpts[0].x, dpts[0].y);
      for (let i = 1; i < N; i++) ctx.lineTo(dpts[i].x, dpts[i].y);
      ctx.closePath();
      ctx.setFillStyle('rgba(79,175,175,0.22)'); ctx.fill();
      ctx.setStrokeStyle('#4FAFAF'); ctx.setLineWidth(3); ctx.stroke();

      // 数据节点（10 色端点 + 白心）
      dpts.forEach(({x, y}, i) => {
        ctx.beginPath(); ctx.arc(x, y, 9, 0, Math.PI * 2);
        ctx.setFillStyle(COLORS[i]); ctx.fill();
        ctx.beginPath(); ctx.arc(x, y, 4.5, 0, Math.PI * 2);
        ctx.setFillStyle('#FFFFFF'); ctx.fill();
      });

      // 标签
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

      ctx.draw(false, () => {
        tt.canvasToTempFilePath({
          canvasId: 'full-radar',
          destWidth: W, destHeight: H,
          success: res => { console.log('[full-radar] img ok'); this.setData({ chartImgFullRadar: res.tempFilePath }); },
          fail: err => console.error('[full-radar] toImg fail', err),
        }, this);
      });
    } catch(e) { console.error('[full-radar] THROW', e.message, e); }
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

  // ── 图表1：D1/D2/D3 棒棒糖图 ──────────────────────────────────────
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
};
