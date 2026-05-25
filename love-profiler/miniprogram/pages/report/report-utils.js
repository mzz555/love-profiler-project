/**
 * 报告页共享 Canvas 工具函数
 * chart / poster 模块通过 require('./report-utils') 引入
 */

function _roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.arc(x + r,     y + r,     r, Math.PI,       Math.PI * 1.5);
  ctx.arc(x + w - r, y + r,     r, Math.PI * 1.5, 0);
  ctx.arc(x + w - r, y + h - r, r, 0,             Math.PI * 0.5);
  ctx.arc(x + r,     y + h - r, r, Math.PI * 0.5, Math.PI);
  ctx.closePath();
}

function _hexAlpha(hex, alpha) {
  var r = parseInt(hex.slice(1, 3), 16);
  var g = parseInt(hex.slice(3, 5), 16);
  var b = parseInt(hex.slice(5, 7), 16);
  return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
}

function _radialGlow(ctx, cx, cy, r, rgbTriplet, maxAlpha) {
  var layers = 6;
  for (var i = layers; i >= 1; i--) {
    var t = i / layers;
    var a = maxAlpha * (1 - t) * (1 - t);
    if (a < 0.005) continue;
    ctx.setFillStyle('rgba(' + rgbTriplet + ',' + a.toFixed(3) + ')');
    ctx.beginPath();
    ctx.arc(cx, cy, r * t, 0, Math.PI * 2);
    ctx.fill();
  }
}

function _dashedLine(ctx, x1, y1, x2, y2, color, dashLen, gapLen) {
  dashLen = dashLen || 3;
  gapLen  = gapLen  || 3;
  var dx = x2 - x1, dy = y2 - y1;
  var len = Math.sqrt(dx * dx + dy * dy);
  if (len < 1) return;
  var ux = dx / len, uy = dy / len;
  var segCount = Math.floor(len / (dashLen + gapLen));
  ctx.setStrokeStyle(color);
  ctx.setLineWidth(1);
  ctx.beginPath();
  for (var i = 0; i < segCount; i++) {
    var s = i * (dashLen + gapLen);
    var sx = x1 + s * ux, sy = y1 + s * uy;
    var ex = sx + dashLen * ux, ey = sy + dashLen * uy;
    ctx.moveTo(sx, sy);
    ctx.lineTo(ex, ey);
  }
  ctx.stroke();
}

function _wrapText(ctx, text, maxWidth) {
  var lines = [];
  var line = '';
  for (var ci = 0; ci < text.length; ci++) {
    var test = line + text[ci];
    if (ctx.measureText(test).width > maxWidth && line) {
      lines.push(line);
      line = text[ci];
    } else {
      line = test;
    }
  }
  if (line) lines.push(line);
  return lines;
}

module.exports = {
  _roundRect: _roundRect,
  _hexAlpha: _hexAlpha,
  _radialGlow: _radialGlow,
  _dashedLine: _dashedLine,
  _wrapText: _wrapText,
};
