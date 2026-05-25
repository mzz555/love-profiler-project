/**
 * 海报生成 + 分享模块
 * 从 report.js 提取，通过 require() 引入后 .call(this, ...) 调用
 */
var _u = require('./report-utils');
var _roundRect = _u._roundRect;
var _radialGlow = _u._radialGlow;
var _dashedLine = _u._dashedLine;
var _wrapText = _u._wrapText;

module.exports = {
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
    // 直接用 health_radar 5 维（依恋安全 / 边界清晰 / 冲突健康 / 自我认知 / 表达成熟）
    // 与报告页主雷达数据完全一致，避免海报与正文出现两套数字
    const _clamp = v => Math.max(0.05, Math.min(1, v));
    let radarVals = [0.85, 0.78, 0.72, 0.68, 0.80];
    let scorePcts = [90, 85, 80, 75];
    if (dimChart && Array.isArray(dimChart.health_radar) && dimChart.health_radar.length === 5) {
      const [d1v, d2v, d3v, aware, style] = dimChart.health_radar.map(x => parseFloat(x.value || 0));
      radarVals = [d1v, d2v, d3v, aware, style].map(_clamp);
      // 海报右侧 4 项相亲场景标签维持原映射：稳定性←D1、责任感←D2、沟通力←D5表达成熟、包容力←D3
      scorePcts = [
        Math.round(_clamp(d1v)   * 100),
        Math.round(_clamp(d2v)   * 100),
        Math.round(_clamp(style) * 100),
        Math.round(_clamp(d3v)   * 100),
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
};
